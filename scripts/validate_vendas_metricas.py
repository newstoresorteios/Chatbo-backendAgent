"""Valida métricas de venda contra dados reais do Supabase (etapa 1 — dev)."""
from app.services.vendas_service import vendas_service
from app.services.supabase_service import supabase


def count_table(name: str) -> int:
    res = supabase.table(name).select("*", count="exact").limit(1).execute()
    if hasattr(res, "count") and res.count is not None:
        return res.count
    return len(res.data or [])


def main() -> None:
    print("=== ETAPA 1: Validação métricas de venda ===\n")

    tables = ["pedidos", "funil_negocios", "funil_estagios", "conversas"]
    print("Registros no Supabase:")
    for t in tables:
        print(f"  {t}: {count_table(t)}")

    m = vendas_service.metricas()
    print("\nMétricas calculadas:")
    print(f"  Quantidade vendas (confirmados): {m['quantidadeVendas']}")
    print(f"  Concluídos (enviado+entregue): {m['quantidadeConcluidas']}")
    print(f"  Entregues: {m['quantidadeEntregues']}")
    print(f"  Valor total vendido: R$ {m['valorTotalVendido']:,.2f}")
    print(f"  Valor concluído: R$ {m['valorConcluido']:,.2f}")
    print(f"  Volume bruto: R$ {m['volumeBruto']:,.2f}")
    print(f"  Valor retido: R$ {m['valorRetido']:,.2f}")
    print(f"  Taxa conversao (contato->entrega): {m['taxaConversao']}%")
    print(f"  Taxa retenção: {m['taxaRetencao']}%")

    print(f"\nFunil ({len(m['funil'])} etapas):")
    for e in m["funil"]:
        pct_topo = e["conversaoPct"]
        if pct_topo > 100:
            print(f"  AVISO: {e['label']} com {pct_topo}% > 100")
        print(
            f"  {e['label']}: {e['quantidade']} un | "
            f"R$ {e['valor']:,.2f} | {pct_topo}% do topo"
        )

    print("\nPor status:")
    for s in m["porStatus"]:
        print(f"  {s['label']}: {s['quantidade']} (R$ {s['valor']:,.2f})")

    dias_com_venda = sum(1 for d in m["vendasPorDia"] if d["vendas"] > 0)
    print(f"\nDias com venda (últimos 30): {dias_com_venda}")

    ok = m["quantidadeVendas"] > 0 or m["volumeBruto"] > 0
    pct_ok = all(e["conversaoPct"] <= 100 for e in m["funil"])
    valor_ok = m["valorTotalVendido"] == m["volumeBruto"]
    print("\n" + ("OK — há dados para exibir em /relatorios" if ok else "AVISO — funil pode aparecer vazio/zerado"))
    print("OK — percentuais do funil <= 100%" if pct_ok else "AVISO — funil com % acima de 100%")
    print("OK — valor vendido = volume bruto (pedidos confirmados)" if valor_ok else "AVISO — valor vendido inconsistente")


if __name__ == "__main__":
    main()
