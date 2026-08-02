from fastapi import HTTPException, status

from app.core.password import hash_senha
from app.repositories.usuario_repository import UsuarioRepository
from app.repositories.workspace_repository import WorkspaceRepository
from app.services.workspace_service import WORKSPACE_ADMIN_ROLES, workspace_service

PERFIS_VALIDOS = {"admin", "supervisor", "vendedor", "user"}
PERFIL_TO_WORKSPACE_ROLE = {
    "admin": "admin",
    "supervisor": "supervisor",
    "vendedor": "seller",
    "user": "member",
}


class UsuarioService:

    def __init__(self):
        self.repository = UsuarioRepository()
        self.workspace_repository = WorkspaceRepository()

    def _mapear(self, usuario: dict) -> dict:
        return {
            "id": str(usuario.get("id")),
            "name": usuario.get("nome") or usuario.get("email", "").split("@")[0],
            "email": usuario.get("email", ""),
            "role": usuario.get("perfil") or "user",
            "company": usuario.get("empresa") or "PulseDesk",
            "active": usuario.get("ativo") is not False,
            "createdAt": usuario.get("created_at"),
        }

    def listar(self, actor: dict | None = None) -> list[dict]:
        if not actor:
            return [self._mapear(u) for u in self.repository.listar()]
        context = workspace_service.get_current_workspace_context(actor)
        members = self.workspace_repository.listar_members_workspace(context["workspaceId"])
        usuarios = self.repository.listar_por_ids([str(member.get("user_id")) for member in members])
        return [self._mapear(u) for u in usuarios]

    def criar(
        self,
        *,
        name: str,
        email: str,
        password: str,
        role: str = "user",
        company: str | None = None,
        actor: dict | None = None,
    ) -> dict:
        context = workspace_service.get_current_workspace_context(actor) if actor else None
        if context and context.get("workspaceRole") not in WORKSPACE_ADMIN_ROLES:
            raise HTTPException(status_code=403, detail="Você não possui permissão para alterar a empresa")

        email_normalizado = email.strip().lower()
        perfil = (role or "user").strip().lower()

        if perfil not in PERFIS_VALIDOS:
            raise HTTPException(status_code=400, detail="Perfil inválido")

        if len(password) < 6:
            raise HTTPException(status_code=400, detail="Senha deve ter no mínimo 6 caracteres")

        if self.repository.buscar_por_email(email_normalizado):
            raise HTTPException(status_code=409, detail="Este e-mail já está cadastrado")

        dados = {
            "email": email_normalizado,
            "senha_hash": hash_senha(password),
            "nome": name.strip(),
            "perfil": perfil,
            "ativo": True,
        }
        if company and company.strip():
            dados["empresa"] = company.strip()
        elif context:
            dados["empresa"] = context["workspaceName"]

        usuario = self.repository.criar(dados)
        if context:
            self.workspace_repository.criar_membership(
                workspace_id=context["workspaceId"],
                user_id=str(usuario.get("id")),
                role=PERFIL_TO_WORKSPACE_ROLE.get(perfil, "member"),
            )
        return self._mapear(usuario)

    def atualizar(
        self,
        usuario_id: str,
        *,
        actor_id: str,
        actor_role: str,
        actor: dict | None = None,
        name: str | None = None,
        role: str | None = None,
        active: bool | None = None,
        company: str | None = None,
    ) -> dict:
        usuario = self.repository.buscar_por_id(usuario_id)
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        context = workspace_service.get_current_workspace_context(actor) if actor else None
        is_admin = bool(context and context.get("workspaceRole") in WORKSPACE_ADMIN_ROLES) or actor_role == "admin"
        if not is_admin and actor_id != usuario_id:
            raise HTTPException(status_code=403, detail="Sem permissão para alterar este usuário")

        membership = self.workspace_repository.buscar_membership_ativo(usuario_id) if context else None
        if context and (not membership or str(membership.get("workspace_id")) != context["workspaceId"]):
            raise HTTPException(status_code=404, detail="Usuário não pertence a este workspace")
        current_workspace_role = membership.get("role") if membership else None
        if context and context.get("workspaceRole") == "admin" and current_workspace_role == "owner":
            raise HTTPException(status_code=403, detail="Admin não pode alterar o owner do workspace")

        dados: dict = {}

        if name is not None and name.strip():
            dados["nome"] = name.strip()

        if company is not None:
            dados["empresa"] = company.strip() or None

        if is_admin:
            if role is not None:
                perfil = role.strip().lower()
                if perfil not in PERFIS_VALIDOS:
                    raise HTTPException(status_code=400, detail="Perfil inválido")
                if context and context.get("workspaceRole") == "admin" and perfil == "admin":
                    raise HTTPException(status_code=403, detail="Admin não pode elevar outro membro a admin")
                dados["perfil"] = perfil

            if active is not None:
                if actor_id == usuario_id and active is False:
                    raise HTTPException(
                        status_code=400,
                        detail="Você não pode desativar sua própria conta",
                    )
                dados["ativo"] = active

            if context and current_workspace_role == "owner" and (active is False or role in {"user", "vendedor", "supervisor"}):
                owners = [row for row in self.workspace_repository.listar_members_workspace(context["workspaceId"]) if row.get("role") == "owner"]
                if len(owners) <= 1:
                    raise HTTPException(status_code=409, detail="O último owner precisa transferir a propriedade antes de sair")

        if not dados:
            return self._mapear(usuario)

        atualizado = self.repository.atualizar(usuario_id, dados)
        return self._mapear(atualizado or usuario)


usuario_service = UsuarioService()
