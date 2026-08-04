"""Cria/atualiza admin@chatbo.com.br com senha 123456 + workspace + agente.

Requer:
  SUPABASE_URL
  SUPABASE_KEY (service_role)
  (opcional) SUPABASE_DB_URL — se workspaces já existirem via API

  python scripts/seed_admin_chatbo.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> None:
    load_env()
    # Reimport settings after env load
    from app.config import settings as settings_mod

    settings_mod.SUPABASE_URL = os.getenv("SUPABASE_URL")
    settings_mod.SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not settings_mod.SUPABASE_URL or not settings_mod.SUPABASE_KEY:
        print("Configure SUPABASE_URL e SUPABASE_KEY (service_role) no .env")
        sys.exit(1)

    from app.core.password import hash_senha
    from app.repositories.usuario_repository import UsuarioRepository
    from app.services.agent_registry_service import agent_registry_service
    from app.services.workspace_service import workspace_service

    email = "admin@chatbo.com.br"
    password = "123456"
    nome = "Administrador Chatbo"
    company = "Chatbo Admin"

    repo = UsuarioRepository()
    existente = repo.buscar_por_email(email)
    if existente:
        user_id = str(existente["id"])
        repo.atualizar(
            user_id,
            {
                "senha_hash": hash_senha(password),
                "nome": nome,
                "perfil": "admin",
                "ativo": True,
                "empresa": company,
                "account_type": "system_admin",
            },
        )
        usuario = repo.buscar_por_id(user_id)
        print(f"Atualizado: {email}")
    else:
        usuario = repo.criar(
            {
                "email": email,
                "senha_hash": hash_senha(password),
                "nome": nome,
                "perfil": "admin",
                "ativo": True,
                "empresa": company,
                "account_type": "system_admin",
            }
        )
        print(f"Criado: {email}")

    user_id = str(usuario["id"])
    try:
        context = workspace_service.get_current_workspace_context(usuario)
        workspace_id = context["workspaceId"]
        print(f"Workspace existente: {workspace_id}")
    except Exception:
        workspace = workspace_service.criar_workspace_inicial(
            user_id=user_id,
            name=company,
        )
        workspace_id = str(workspace["id"])
        print(f"Workspace criado: {workspace_id}")

    try:
        agent_registry_service.repo.upsert(
            workspace_id,
            {
                "agent_type": "nsagent",
                "status": "active",
                "display_name": company,
            },
        )
        print("Agente nsagent vinculado ao workspace.")
    except Exception as exc:
        print(f"Aviso: não foi possível vincular agente ({exc})")

    print("")
    print("Login:")
    print(f"  email: {email}")
    print(f"  senha: {password}")


if __name__ == "__main__":
    main()
