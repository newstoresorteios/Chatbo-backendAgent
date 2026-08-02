"""Aplica campos de pedidos Mercos no Supabase (requer SUPABASE_DB_URL no .env)."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SQL_PATH = Path(__file__).resolve().parent.parent / "supabase" / "004_pedidos_mercos.sql"


def main() -> None:
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("SUPABASE_DB_URL nao configurada.")
        print("")
        print("Cole no Supabase SQL Editor:")
        print(f"  Arquivo: {SQL_PATH}")
        print("")
        print("Ou adicione SUPABASE_DB_URL no .env e rode este script de novo.")
        sys.exit(1)

    try:
        import psycopg2
    except ImportError:
        print("Instale: pip install psycopg2-binary")
        sys.exit(1)

    sql = SQL_PATH.read_text(encoding="utf-8")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        print("Schema pedidos Mercos aplicado com sucesso.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
