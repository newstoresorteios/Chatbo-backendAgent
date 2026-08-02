import logging
import time

from app.repositories.mercos_sync_repository import MercosSyncRepository
from app.services.cliente_service import ClienteService
from app.services.mercos_service import mercos_configurado, mercos_info
from app.services.pedido_service import PedidoService
from app.services.produto_service import ProdutoService

logger = logging.getLogger(__name__)

PAUSA_ENTRE_ETAPAS_SEG = 6


class EtlService:
    """ETL agendado: extrai do Mercos, carrega no Supabase. Evita sync manual em massa."""

    def __init__(self):
        self.clientes = ClienteService()
        self.produtos = ProdutoService()
        self.pedidos = PedidoService()
        self.logs = MercosSyncRepository()

    def _exigir_mercos(self) -> None:
        if not mercos_configurado():
            raise RuntimeError("Mercos não configurado — ETL ignorado.")

    def _prefixo(self) -> str:
        ambiente = mercos_info().get("environment") or "unknown"
        return f"[ETL/{ambiente}] "

    def sincronizar_pedidos(self) -> dict:
        self._exigir_mercos()
        resultado = self.pedidos.sincronizar(incremental=True)
        qtd = resultado.get("pedidos_sincronizados", 0)
        mensagem = resultado.get("mensagem") or f"{self._prefixo()}Pedidos ETL: {qtd}."
        self.logs.registrar(tipo="etl_orders", mensagem=mensagem, quantidade=qtd, resumo=resultado.get("resumo"))
        return {"job": "orders", "success": True, "message": mensagem, "pedidos_sincronizados": qtd, "resumo": resultado.get("resumo")}

    def sincronizar_catalogo(self) -> dict:
        """Clientes + produtos — rodar 1x/dia."""
        self._exigir_mercos()
        prefix = self._prefixo()

        clientes = self.clientes.sincronizar()
        time.sleep(PAUSA_ENTRE_ETAPAS_SEG)
        produtos = self.produtos.sincronizar(incremental=False)

        qtd_c = clientes.get("clientes_sincronizados", 0)
        qtd_p = produtos.get("produtos_sincronizados", 0)
        mensagem = f"{prefix}Catálogo ETL — clientes: {qtd_c}, produtos: {qtd_p}."
        self.logs.registrar(
            tipo="etl_catalog",
            mensagem=mensagem,
            quantidade=qtd_c + qtd_p,
        )
        return {
            "job": "catalog",
            "success": True,
            "message": mensagem,
            "clientes_sincronizados": qtd_c,
            "produtos_sincronizados": qtd_p,
        }

    def sincronizar_completo(self) -> dict:
        """Pedidos + catálogo com pausas — uso em manutenção."""
        self._exigir_mercos()
        prefix = self._prefixo()

        clientes = self.clientes.sincronizar()
        time.sleep(PAUSA_ENTRE_ETAPAS_SEG)
        produtos = self.produtos.sincronizar(incremental=False)
        time.sleep(PAUSA_ENTRE_ETAPAS_SEG)
        pedidos = self.pedidos.sincronizar(incremental=True)

        qtd_c = clientes.get("clientes_sincronizados", 0)
        qtd_p = produtos.get("produtos_sincronizados", 0)
        qtd_o = pedidos.get("pedidos_sincronizados", 0)
        mensagem = f"{prefix}ETL completo — clientes: {qtd_c}, produtos: {qtd_p}, pedidos: {qtd_o}."
        self.logs.registrar(
            tipo="etl_full",
            mensagem=mensagem,
            quantidade=qtd_c + qtd_p + qtd_o,
            resumo=pedidos.get("resumo"),
        )
        return {
            "job": "full",
            "success": True,
            "message": mensagem,
            "clientes_sincronizados": qtd_c,
            "produtos_sincronizados": qtd_p,
            "pedidos_sincronizados": qtd_o,
            "resumo": pedidos.get("resumo"),
        }

    def executar(self, job: str) -> dict:
        job = (job or "").strip().lower()
        if job == "orders":
            return self.sincronizar_pedidos()
        if job == "catalog":
            return self.sincronizar_catalogo()
        if job == "full":
            return self.sincronizar_completo()
        raise ValueError(f"Job ETL desconhecido: {job}. Use orders, catalog ou full.")


etl_service = EtlService()
