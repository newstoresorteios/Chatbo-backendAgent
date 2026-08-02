import logging
from datetime import datetime

from fastapi import HTTPException, status

from app.config.settings import AUTH_RESET_DEBUG, FRONTEND_URL, JWT_ACCESS_MINUTES
from app.core.auth import revogar_access_token
from app.core.password import hash_senha, verificar_senha
from app.core.rate_limit import limpar_tentativas, registrar_falha_login, verificar_limite_login
from app.core.security import criar_access_token, criar_refresh_token_opaco
from app.repositories.token_repository import TokenRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.services.email_service import EmailService
from app.services.workspace_service import workspace_service

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self):
        self.repository = UsuarioRepository()
        self.token_repository = TokenRepository()
        self.email_service = EmailService()

    def login(self, email: str, password: str) -> dict:
        chave = email.strip().lower()
        verificar_limite_login(chave)

        usuario = self.repository.buscar_por_email(chave)
        if not usuario:
            registrar_falha_login(chave)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha inválidos")

        if usuario.get("ativo") is False:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuário inativo")

        senha_hash = usuario.get("senha_hash") or ""
        if not verificar_senha(password, senha_hash):
            registrar_falha_login(chave)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha inválidos")

        limpar_tentativas(chave)
        return self._emitir_sessao(usuario)

    def register(self, name: str, email: str, password: str, company: str | None = None) -> dict:
        usuario: dict | None = None
        workspace: dict | None = None
        try:
            email_normalizado = email.strip().lower()

            if self.repository.buscar_por_email(email_normalizado):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Este e-mail já está cadastrado")

            dados = {
                "email": email_normalizado,
                "senha_hash": hash_senha(password),
                "nome": name.strip(),
                "perfil": "user",
                "ativo": True,
            }
            if company and company.strip():
                dados["empresa"] = company.strip()

            usuario = self.repository.criar(dados)
            workspace = workspace_service.criar_workspace_inicial(
                user_id=str(usuario.get("id")),
                name=(company.strip() if company and company.strip() else name.strip()),
            )
            return self._emitir_sessao(usuario)
        except HTTPException:
            raise
        except Exception:
            if workspace and workspace.get("id"):
                workspace_service.excluir_workspace(str(workspace.get("id")))
            if usuario and usuario.get("id"):
                self.repository.excluir(str(usuario.get("id")))
            raise

    def refresh(self, refresh_token: str) -> dict:
        registro = self.token_repository.buscar_refresh(refresh_token)
        if not registro:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão expirada — faça login novamente")

        expira = registro.get("expira_em")
        if expira:
            try:
                expira_dt = datetime.fromisoformat(str(expira).replace("Z", "+00:00")).replace(tzinfo=None)
                if datetime.utcnow() > expira_dt:
                    self.token_repository.revogar_refresh(refresh_token)
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Sessão expirada — faça login novamente",
                    )
            except HTTPException:
                raise
            except ValueError:
                pass

        usuario_id = str(registro.get("usuario_id") or "")
        usuario = self.repository.buscar_por_id(usuario_id)
        if not usuario or usuario.get("ativo") is False:
            self.token_repository.revogar_refresh(refresh_token)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário inválido ou inativo")

        self.token_repository.revogar_refresh(refresh_token)
        return self._emitir_sessao(usuario)

    def logout(self, access_token: str, usuario_id: str, refresh_token: str | None = None) -> dict:
        revogar_access_token(access_token)
        if refresh_token:
            self.token_repository.revogar_refresh(refresh_token)
        else:
            self.token_repository.revogar_todos_refresh_usuario(usuario_id)
        return {"success": True}

    def solicitar_reset_senha(self, email: str) -> dict:
        mensagem = "Se o e-mail estiver cadastrado, enviamos instruções para redefinir a senha."
        usuario = self.repository.buscar_por_email(email)

        if not usuario:
            return {"success": True, "message": mensagem}

        import secrets
        from datetime import timedelta

        token = secrets.token_urlsafe(32)
        expira = datetime.utcnow() + timedelta(hours=1)

        self.repository.atualizar(str(usuario["id"]), {
            "reset_token": token,
            "reset_token_expires": expira.isoformat(),
        })

        reset_url = f"{FRONTEND_URL}/redefinir-senha?token={token}"
        resposta = {"success": True, "message": mensagem}
        nome = usuario.get("nome") or usuario.get("email", "").split("@")[0]

        if self.email_service.configurado:
            try:
                self.email_service.enviar_reset_senha(usuario["email"], nome, reset_url)
            except RuntimeError:
                logger.exception("Falha ao enviar e-mail de reset para %s", email)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Não foi possível enviar o e-mail. Tente novamente em instantes.",
                )
        elif AUTH_RESET_DEBUG:
            resposta["resetUrl"] = reset_url
            logger.warning("SMTP não configurado — link de reset exposto em modo debug para %s", email)

        return resposta

    def redefinir_senha(self, token: str, password: str) -> dict:
        usuario = self.repository.buscar_por_reset_token(token)
        if not usuario:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Link de recuperação inválido ou expirado")

        expira = usuario.get("reset_token_expires")
        if expira:
            try:
                expira_dt = datetime.fromisoformat(str(expira).replace("Z", "+00:00")).replace(tzinfo=None)
                if datetime.utcnow() > expira_dt:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Link de recuperação expirado. Solicite um novo.",
                    )
            except HTTPException:
                raise
            except ValueError:
                pass

        self.repository.atualizar(str(usuario["id"]), {
            "senha_hash": hash_senha(password),
            "reset_token": None,
            "reset_token_expires": None,
        })
        self.token_repository.revogar_todos_refresh_usuario(str(usuario["id"]))
        return {"success": True, "message": "Senha redefinida com sucesso. Faça login com a nova senha."}

    def atualizar_perfil(self, usuario_id: str, name: str | None = None, company: str | None = None) -> dict:
        usuario = self.repository.buscar_por_id(usuario_id)
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        dados: dict = {}
        if name is not None and name.strip():
            dados["nome"] = name.strip()
        if company is not None:
            dados["empresa"] = company.strip() or None

        if not dados:
            return self._mapear_usuario(usuario)

        atualizado = self.repository.atualizar(usuario_id, dados)
        return self._mapear_usuario(atualizado or usuario)

    def _emitir_sessao(self, usuario: dict) -> dict:
        user = self._mapear_usuario(usuario)
        access, _, _ = criar_access_token({
            "sub": str(usuario.get("id")),
            "email": user["email"],
            "role": user["role"],
        })
        refresh_plain, expira_refresh = criar_refresh_token_opaco()
        self.token_repository.salvar_refresh(str(usuario.get("id")), refresh_plain, expira_refresh)

        return {
            "token": access,
            "refreshToken": refresh_plain,
            "expiresIn": JWT_ACCESS_MINUTES * 60,
            "user": user,
        }

    def _mapear_usuario(self, usuario: dict) -> dict:
        mapped = {
            "id": str(usuario.get("id")),
            "name": usuario.get("nome") or usuario.get("email", "").split("@")[0],
            "email": usuario.get("email", ""),
            "role": usuario.get("perfil") or "user",
            "company": usuario.get("empresa") or "NITRUS",
            "avatar": usuario.get("avatar"),
        }
        context = workspace_service.get_current_workspace_context(usuario)
        mapped.update({
            "accountType": context["accountType"],
            "workspaceId": context["workspaceId"],
            "workspaceName": context["workspaceName"],
            "workspaceRole": context["workspaceRole"],
            "onboardingStatus": context["onboardingStatus"],
            "company": context["workspaceName"] or mapped["company"],
        })
        return mapped
