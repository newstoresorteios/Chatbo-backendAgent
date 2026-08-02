"""Cria usuários iniciais na tabela usuarios do Supabase."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.password import hash_senha
from app.repositories.usuario_repository import UsuarioRepository

USUARIOS_INICIAIS = [
    {
        "email": "admin@pulsedesk.com",
        "senha": "admin123",
        "nome": "Administrador",
        "perfil": "admin",
    },
    {
        "email": "vendedor@pulsedesk.com",
        "senha": "vendedor123",
        "nome": "Vendedor Teste",
        "perfil": "vendedor",
    },
    {
        "email": "supervisor@pulsedesk.com",
        "senha": "super123",
        "nome": "Supervisor Teste",
        "perfil": "supervisor",
    },
]


def main():
    repo = UsuarioRepository()
    existentes = set(repo.listar_emails())

    for item in USUARIOS_INICIAIS:
        email = item["email"]
        if email in existentes:
            print(f"Já existe: {email}")
            continue

        repo.criar({
            "email": email,
            "senha_hash": hash_senha(item["senha"]),
            "nome": item["nome"],
            "perfil": item["perfil"],
            "ativo": True,
        })
        print(f"Criado: {email} / senha: {item['senha']}")

    print("\nPronto. Use essas contas no login do PulseDesk.")


if __name__ == "__main__":
    main()
