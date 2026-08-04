"""Aplica todas as migrations supabase/*.sql em ordem.

Requer SUPABASE_DB_URL (connection string Postgres do Supabase).

  python scripts/apply_all_schema.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "supabase"

# Skip scripts destrutivos / só de limpeza demo.
SKIP = {
    "010_clear_demo.sql",
}

# Ordem estável: prefixo numérico + nome.
def migration_files() -> list[Path]:
    files = sorted(SQL_DIR.glob("*.sql"), key=lambda p: p.name)
    return [p for p in files if p.name not in SKIP]


def load_db_url() -> str:
    # Carrega .env simples se existir
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

    url = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    if not url:
        print("SUPABASE_DB_URL (ou DATABASE_URL) não configurada.")
        print("Crie um .env na raiz com:")
        print("  SUPABASE_DB_URL=postgresql://postgres.[ref]:[SENHA]@...supabase.com:5432/postgres")
        sys.exit(1)
    return url


def main() -> None:
    db_url = load_db_url()
    try:
        import psycopg2
    except ImportError:
        print("Instale: pip install psycopg2-binary")
        sys.exit(1)

    files = migration_files()
    if not files:
        print("Nenhum arquivo SQL em supabase/")
        sys.exit(1)

    print(f"Aplicando {len(files)} migrations em {SQL_DIR} ...")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS public.schema_migrations (
                  filename TEXT PRIMARY KEY,
                  applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            for path in files:
                cur.execute(
                    "SELECT 1 FROM public.schema_migrations WHERE filename = %s",
                    (path.name,),
                )
                if cur.fetchone():
                    print(f"  skip  {path.name}")
                    continue
                sql = path.read_text(encoding="utf-8")
                print(f"  apply {path.name} ...", end="", flush=True)
                try:
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO public.schema_migrations(filename) VALUES (%s)",
                        (path.name,),
                    )
                    print(" ok")
                except Exception as exc:
                    print(" FAIL")
                    print(f"Erro em {path.name}: {exc}")
                    sys.exit(1)
    finally:
        conn.close()

    print("Schema aplicado com sucesso.")


if __name__ == "__main__":
    main()
