"""Remove clientes, produtos e pedidos do Supabase (dados Mercos antigos)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.supabase_service import supabase

TABLES = ("pedidos", "clientes", "produtos")
SENTINEL_ID = "00000000-0000-0000-0000-000000000000"


def count_table(name: str) -> int:
    res = supabase.table(name).select("*", count="exact").limit(1).execute()
    if hasattr(res, "count") and res.count is not None:
        return res.count
    return len(res.data or [])


def clear_table(name: str) -> int:
    before = count_table(name)
    if before == 0:
        return 0
    supabase.table(name).delete().neq("id", SENTINEL_ID).execute()
    after = count_table(name)
    if after > 0:
        raise RuntimeError(f"Tabela {name}: restaram {after} registros após limpeza.")
    return before


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="PERIGO: apaga pedidos/clientes/produtos no Supabase. NÃO é sync."
    )
    parser.add_argument(
        "--confirm-delete-all",
        required=True,
        help='Digite exatamente: EU_QUERO_APAGAR_TODOS_OS_PRODUTOS',
    )
    args = parser.parse_args()
    if args.confirm_delete_all != "EU_QUERO_APAGAR_TODOS_OS_PRODUTOS":
        raise SystemExit(
            "Abortado. Confirmação inválida — produtos NÃO foram apagados."
        )

    print("=== Limpeza dados Mercos (Supabase) ===\n")
    print("Antes:")
    for table in TABLES:
        print(f"  {table}: {count_table(table)}")

    print("\nLimpando...")
    removed: dict[str, int] = {}
    for table in TABLES:
        removed[table] = clear_table(table)
        print(f"  {table}: {removed[table]} removidos")

    print("\nDepois:")
    for table in TABLES:
        print(f"  {table}: {count_table(table)}")

    print("\nOK — pronto para sincronizar a conta Mercos nova.")


if __name__ == "__main__":
    main()
