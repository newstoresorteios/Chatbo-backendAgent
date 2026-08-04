"""Provisionamento de empresas (workspaces) e admins — exclusivo system_admin."""

from __future__ import annotations

import logging
import re

from fastapi import HTTPException

from app.core.password import hash_senha
from app.repositories.usuario_repository import UsuarioRepository
from app.repositories.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ADMIN_ROLES = {"owner", "admin"}


class SystemCompaniesService:
    def __init__(self) -> None:
        self.workspaces = WorkspaceRepository()
        self.usuarios = UsuarioRepository()

    def _map_company(self, row: dict, members: list[dict] | None = None) -> dict:
        workspace_id = str(row.get("id"))
        company_id = str(row.get("company_id") or workspace_id)
        member_rows = members if members is not None else self.workspaces.listar_memberships_detalhados(workspace_id)
        admin_count = sum(1 for m in member_rows if m.get("role") in ADMIN_ROLES and m.get("status") == "active")
        return {
            "id": workspace_id,
            "companyId": company_id,
            "workspaceId": workspace_id,
            "name": row.get("name") or "Empresa",
            "brandName": row.get("brand_name"),
            "status": row.get("status") or "active",
            "membersCount": len(member_rows),
            "adminsCount": admin_count,
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
        }

    def _map_member(self, membership: dict, user: dict | None) -> dict:
        return {
            "membershipId": str(membership.get("id")),
            "userId": str(membership.get("user_id")),
            "role": membership.get("role") or "member",
            "status": membership.get("status") or "active",
            "name": (user or {}).get("nome") or "",
            "email": (user or {}).get("email") or "",
            "active": (user or {}).get("ativo") is not False,
            "accountType": (user or {}).get("account_type") or "workspace_user",
            "company": (user or {}).get("empresa"),
            "createdAt": membership.get("created_at") or (user or {}).get("created_at"),
        }

    def listar_empresas(self) -> list[dict]:
        rows = self.workspaces.listar_workspaces()
        return [self._map_company(row) for row in rows]

    def obter_empresa(self, company_id: str) -> dict:
        workspace = self.workspaces.buscar_workspace(company_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")
        return self._map_company(workspace)

    def criar_empresa(self, *, name: str, brand_name: str | None = None) -> dict:
        clean_name = (name or "").strip()
        if len(clean_name) < 2:
            raise HTTPException(status_code=400, detail="Informe o nome da empresa")
        brand = (brand_name or clean_name).strip() or clean_name

        workspace = self.workspaces.criar_workspace(name=clean_name, brand_name=brand)
        workspace_id = str(workspace.get("id"))
        if not workspace_id:
            raise HTTPException(status_code=500, detail="Falha ao criar workspace da empresa")

        try:
            self.workspaces.criar_settings(
                workspace_id,
                {"currency": "BRL", "country": "BR"},
            )
            self.workspaces.criar_onboarding(
                workspace_id,
                status="complete",
                current_step="ativacao",
            )
            try:
                from app.services.agent_registry_service import agent_registry_service

                agent_registry_service.repo.upsert(
                    workspace_id,
                    {
                        "agent_type": "nsagent",
                        "status": "active",
                        "display_name": brand,
                    },
                )
            except Exception:
                logger.exception("Não foi possível provisionar agente para empresa %s", workspace_id)
        except Exception as exc:
            try:
                self.workspaces.excluir_workspace(workspace_id)
            except Exception:
                pass
            raise HTTPException(status_code=500, detail="Falha ao provisionar a empresa") from exc

        return self._map_company(self.workspaces.buscar_workspace(workspace_id) or workspace)

    def atualizar_empresa(
        self,
        company_id: str,
        *,
        name: str | None = None,
        brand_name: str | None = None,
        status: str | None = None,
    ) -> dict:
        workspace = self.workspaces.buscar_workspace(company_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")

        payload: dict = {}
        if name is not None:
            clean = name.strip()
            if len(clean) < 2:
                raise HTTPException(status_code=400, detail="Nome inválido")
            payload["name"] = clean
        if brand_name is not None:
            payload["brand_name"] = brand_name.strip() or None
        if status is not None:
            if status not in {"active", "inactive"}:
                raise HTTPException(status_code=400, detail="Status inválido")
            payload["status"] = status
        # Mantém company_id alinhado ao id
        payload["company_id"] = str(workspace.get("id"))

        if payload:
            workspace = self.workspaces.atualizar_workspace(str(workspace["id"]), payload)
        return self._map_company(workspace)

    def listar_membros(self, company_id: str) -> list[dict]:
        workspace = self.workspaces.buscar_workspace(company_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")
        memberships = self.workspaces.listar_memberships_detalhados(str(workspace["id"]))
        user_ids = [str(m.get("user_id")) for m in memberships if m.get("user_id")]
        users = {str(u.get("id")): u for u in self.usuarios.listar_por_ids(user_ids)}
        return [self._map_member(m, users.get(str(m.get("user_id")))) for m in memberships]

    def criar_admin_empresa(
        self,
        company_id: str,
        *,
        name: str,
        email: str,
        password: str,
        role: str = "admin",
    ) -> dict:
        workspace = self.workspaces.buscar_workspace(company_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")

        clean_name = (name or "").strip()
        clean_email = (email or "").strip().lower()
        if len(clean_name) < 2:
            raise HTTPException(status_code=400, detail="Informe o nome do administrador")
        if not EMAIL_RE.match(clean_email):
            raise HTTPException(status_code=400, detail="E-mail inválido")
        if len(password or "") < 6:
            raise HTTPException(status_code=400, detail="Senha deve ter pelo menos 6 caracteres")

        member_role = role if role in ADMIN_ROLES else "admin"
        # Nunca cria system_admin por esta rota
        if self.usuarios.buscar_por_email(clean_email):
            raise HTTPException(status_code=409, detail="Já existe um usuário com este e-mail")

        usuario = self.usuarios.criar(
            {
                "email": clean_email,
                "senha_hash": hash_senha(password),
                "nome": clean_name,
                "perfil": "admin",
                "ativo": True,
                "empresa": workspace.get("name") or clean_name,
                "account_type": "workspace_user",
            }
        )
        user_id = str(usuario.get("id"))
        membership = self.workspaces.criar_membership(
            workspace_id=str(workspace["id"]),
            user_id=user_id,
            role=member_role,
        )

        try:
            from app.services.billing_service import billing_service

            billing_service.criar_trial(str(workspace["id"]), user_id)
        except Exception:
            logger.exception("Trial não criado para empresa %s (usuário ok)", company_id)

        return self._map_member(membership, usuario)


system_companies_service = SystemCompaniesService()
