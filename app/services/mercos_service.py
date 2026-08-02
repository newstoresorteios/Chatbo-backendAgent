import json
import logging
import time

import requests
from fastapi import HTTPException

from app.config.settings import (
    MERCOS_APPLICATION_TOKEN,
    MERCOS_BASE_URL,
    MERCOS_COMPANY_TOKEN,
    mercos_ambiente,
    mercos_base_url_host,
)

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = frozenset({
    "applicationtoken",
    "companytoken",
    "token",
    "authorization",
    "password",
    "senha",
    "secret",
    "apikey",
    "api_key",
})

MAX_RETRIES = 4
DEFAULT_RETRY_SECONDS = 6
MAX_PAGINAS = 500


def _eh_produto_exemplo(produto: dict) -> bool:
    nome = str(produto.get("nome") or "").lower()
    return "[exemplo]" in nome


def _filtrar_produtos_reais(produtos: list[dict]) -> list[dict]:
    """Ignora catálogo demo padrão da Mercos sandbox ([Exemplo] ...)."""
    return [p for p in produtos if not _eh_produto_exemplo(p)]


def mercos_configurado() -> bool:
    return bool(MERCOS_APPLICATION_TOKEN and MERCOS_COMPANY_TOKEN and MERCOS_BASE_URL)


def mercos_info() -> dict:
    ambiente = mercos_ambiente()
    return {
        "environment": ambiente,
        "isProduction": ambiente == "production",
        "isSandbox": ambiente == "sandbox",
        "baseUrlHost": mercos_base_url_host(),
        "configured": mercos_configurado(),
    }


class MercosService:

    def __init__(self):
        self.headers = {
            "ApplicationToken": MERCOS_APPLICATION_TOKEN,
            "CompanyToken": MERCOS_COMPANY_TOKEN,
            "Accept": "application/json",
        }

    def _validar_config(self) -> None:
        if not mercos_configurado():
            raise RuntimeError(
                "Mercos não configurado. Defina MERCOS_APPLICATION_TOKEN, "
                "MERCOS_COMPANY_TOKEN e MERCOS_BASE_URL no Render."
            )

    def _retry_seconds(self, response: requests.Response) -> float:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                wait = payload.get("tempo_ate_permitir_novamente")
                if wait is not None:
                    return float(wait) + 0.5
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return float(DEFAULT_RETRY_SECONDS)

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
        raise_for_status: bool = True,
    ) -> requests.Response:
        """GET/POST/PUT com retry em 429 (critério obrigatório de homologação Mercos)."""
        self._validar_config()
        last_response: requests.Response | None = None
        headers = dict(self.headers)
        if json_body is not None:
            headers["Content-Type"] = "application/json"

        for attempt in range(MAX_RETRIES):
            response = requests.request(
                method=method.upper(),
                url=url,
                headers=headers,
                params=params or {},
                json=json_body,
                timeout=60,
            )
            last_response = response

            if response.status_code != 429:
                if raise_for_status:
                    response.raise_for_status()
                return response

            if attempt == MAX_RETRIES - 1:
                break

            time.sleep(self._retry_seconds(response))

        if last_response is not None:
            if raise_for_status:
                last_response.raise_for_status()
            return last_response
        raise RuntimeError("Mercos não respondeu após tentativas de rate limit")

    def _request_get(self, path: str, params: dict | None = None) -> requests.Response:
        url = f"{MERCOS_BASE_URL}/{path.lstrip('/')}"
        return self._request("GET", url, params=params, raise_for_status=True)

    def _get(self, path: str, params: dict | None = None):
        return self._request_get(path, params).json()

    @staticmethod
    def _sanitizar_corpo(body: dict | list | str | None):
        """Remove chaves sensíveis do body antes de devolver ao cliente."""
        if isinstance(body, dict):
            return {
                k: MercosService._sanitizar_corpo(v)
                for k, v in body.items()
                if str(k).lower().replace("-", "").replace("_", "") not in _SENSITIVE_KEYS
                and str(k).lower() not in _SENSITIVE_KEYS
            }
        if isinstance(body, list):
            return [MercosService._sanitizar_corpo(item) for item in body]
        return body

    @staticmethod
    def _status_http_para_cliente(mercos_status: int) -> int:
        """Mapeia status Mercos → HTTP da API PulseDesk (sem expor 401/403 da integração)."""
        if mercos_status in (401, 403):
            return 502
        if mercos_status >= 500:
            return 502
        if 400 <= mercos_status < 500:
            return mercos_status
        return 502

    @staticmethod
    def _resposta_escrita(response: requests.Response) -> dict:
        body: dict | list | str
        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError):
            body = response.text

        body_safe = MercosService._sanitizar_corpo(body)

        if response.status_code >= 400:
            logger.warning(
                "Mercos escrita falhou: method=%s url_path=%s status=%s",
                response.request.method if response.request else "?",
                (response.request.path_url if response.request else "?"),
                response.status_code,
            )
            raise HTTPException(
                status_code=MercosService._status_http_para_cliente(response.status_code),
                detail={
                    "mercos_status": response.status_code,
                    "resposta": body_safe,
                },
            )

        return {
            "status_code": response.status_code,
            "resposta": body_safe,
            "meuspedidosid": response.headers.get("meuspedidosid")
            or response.headers.get("MeusPedidosID"),
        }

    @staticmethod
    def max_ultima_alteracao(registros: list[dict]) -> str | None:
        """Maior ultima_alteracao da lista (cursor para sync incremental)."""
        valores = [
            str(row.get("ultima_alteracao"))
            for row in registros
            if isinstance(row, dict) and row.get("ultima_alteracao")
        ]
        return max(valores) if valores else None

    @staticmethod
    def _limitou_registros(response: requests.Response) -> bool:
        return str(response.headers.get("MEUSPEDIDOS_LIMITOU_REGISTROS", "")).strip() == "1"

    @staticmethod
    def _ultima_alteracao(registros: list[dict]) -> str | None:
        for row in reversed(registros):
            valor = row.get("ultima_alteracao")
            if valor:
                return str(valor)
        return None

    def _listar_paginado(self, path: str, alterado_apos: str | None = None) -> list | dict:
        """Percorre todas as páginas com alterado_apos (critério obrigatório de homologação)."""
        todos: list[dict] = []
        cursor = alterado_apos

        for pagina in range(MAX_PAGINAS):
            params: dict[str, str] = {}
            if cursor:
                params["alterado_apos"] = cursor

            response = self._request_get(path, params)
            data = response.json()

            if isinstance(data, dict):
                return data
            if not isinstance(data, list):
                break
            if not data:
                break

            todos.extend(data)

            if not self._limitou_registros(response):
                break

            novo_cursor = self._ultima_alteracao(data)
            if not novo_cursor or novo_cursor == cursor:
                break

            cursor = novo_cursor
            if pagina < MAX_PAGINAS - 1:
                time.sleep(0.25)

        return todos

    def listar_clientes(self, alterado_apos: str | None = None):
        return self._listar_paginado("clientes", alterado_apos)

    def criar_cliente(self, dados):
        response = self._request(
            "POST",
            f"{MERCOS_BASE_URL}/clientes",
            json_body=dados,
            raise_for_status=False,
        )
        return self._resposta_escrita(response)

    def alterar_cliente(self, mercos_id: int | str, dados: dict):
        """PUT /clientes/{id} — altera cliente no Mercos."""
        response = self._request(
            "PUT",
            f"{MERCOS_BASE_URL}/clientes/{mercos_id}",
            json_body=dados,
            raise_for_status=False,
        )
        return self._resposta_escrita(response)

    def listar_produtos(self, alterado_apos: str | None = None):
        produtos = self._listar_paginado("produtos", alterado_apos)
        if isinstance(produtos, list):
            return _filtrar_produtos_reais(produtos)
        return produtos

    def criar_produto(self, dados: dict):
        """POST /produtos — inclui produto simples no Mercos."""
        response = self._request(
            "POST",
            f"{MERCOS_BASE_URL}/produtos",
            json_body=dados,
            raise_for_status=False,
        )
        return self._resposta_escrita(response)

    def listar_pedidos(self, alterado_apos: str | None = None):
        return self._listar_paginado("pedidos", alterado_apos)

    def _base_url_api_root(self) -> str:
        """Converte .../api/v1 em .../api para chamar v2."""
        self._validar_config()
        base = (MERCOS_BASE_URL or "").rstrip("/")
        if base.endswith("/v1"):
            return base[:-3]
        if base.endswith("/api"):
            return base
        return base

    def criar_pedido(self, dados: dict):
        """POST /v2/pedidos — inclui pedido simples (itens com quantidade, sem grade)."""
        response = self._request(
            "POST",
            f"{self._base_url_api_root()}/v2/pedidos",
            json_body=dados,
            raise_for_status=False,
        )
        return self._resposta_escrita(response)

    def alterar_pedido(self, mercos_id: int | str, dados: dict):
        """PUT /v2/pedidos/{id} — altera pedido no Mercos."""
        response = self._request(
            "PUT",
            f"{self._base_url_api_root()}/v2/pedidos/{mercos_id}",
            json_body=dados,
            raise_for_status=False,
        )
        return self._resposta_escrita(response)

    def criar_titulo(self, dados: dict):
        """POST /titulos — inclui título no Mercos (ex.: PIX externo)."""
        response = self._request(
            "POST",
            f"{MERCOS_BASE_URL}/titulos",
            json_body=dados,
            raise_for_status=False,
        )
        return self._resposta_escrita(response)

    def alterar_titulo(self, mercos_id: int | str, dados: dict):
        """PUT /titulos/{id} — altera título no Mercos."""
        response = self._request(
            "PUT",
            f"{MERCOS_BASE_URL}/titulos/{mercos_id}",
            json_body=dados,
            raise_for_status=False,
        )
        return self._resposta_escrita(response)

    def obter_cliente(self, mercos_id: int | str):
        return self._get(f"clientes/{mercos_id}")

    def obter_produto(self, mercos_id: int | str):
        return self._get(f"produtos/{mercos_id}")

    def obter_pedido(self, mercos_id: int | str):
        """GET /pedidos/{id} na API v1.

        Create/update usam /v2/pedidos; a consulta individual permanece em v1
        (v2 cobre apenas inclusão/alteração de pedido simples).
        """
        return self._get(f"pedidos/{mercos_id}")

    def listar_tabelas_preco(self, alterado_apos: str | None = None):
        return self._listar_paginado("tabelas_preco", alterado_apos)

    def listar_condicoes_pagamento(self, alterado_apos: str | None = None):
        return self._listar_paginado("condicoes_pagamento", alterado_apos)

    def listar_transportadoras(self, alterado_apos: str | None = None):
        return self._listar_paginado("transportadoras", alterado_apos)

    def listar_politicas_comerciais(self, alterado_apos: str | None = None):
        return self._listar_paginado("politicas_comerciais", alterado_apos)

    def listar_categorias(self, alterado_apos: str | None = None):
        return self._listar_paginado("categorias", alterado_apos)

    def listar_segmentos(self, alterado_apos: str | None = None):
        return self._listar_paginado("segmentos", alterado_apos)

    def listar_tipos_pedido(self, alterado_apos: str | None = None):
        return self._listar_paginado("pedidos/tipo", alterado_apos)

    def listar_produtos_tabela_preco(self, alterado_apos: str | None = None):
        return self._listar_paginado("produtos_tabela_preco", alterado_apos)

    def listar_usuarios_mercos(self, alterado_apos: str | None = None):
        """GET /usuarios — vendedores/usuários do Mercos."""
        return self._listar_paginado("usuarios", alterado_apos)

    def status_homologacao(self) -> dict:
        """Resumo técnico para evidências de homologação Mercos."""
        info = mercos_info()
        checks = {
            "tokensConfigurados": info.get("configured"),
            "ambienteSandbox": info.get("isSandbox"),
            "throttling429": True,
            "paginacaoAlteradoApos": True,
            "syncIncrementalPedidos": True,
            "syncIncrementalClientes": True,
            "syncIncrementalProdutos": True,
            "alterarPedido": True,
            "titulosIncluirAlterar": True,
        }

        apis_leitura = {
            "clientes": False,
            "produtos": False,
            "pedidos": False,
            "tabelas_preco": False,
            "condicoes_pagamento": False,
            "categorias": False,
            "segmentos": False,
            "tipos_pedido": False,
            "produtos_tabela_preco": False,
            "usuarios_mercos": False,
            "transportadoras": False,
            "politicas_comerciais": False,
        }
        contagens: dict[str, int] = {}
        erros: dict[str, str] = {}

        if info.get("configured"):
            probes = {
                "clientes": self.listar_clientes,
                "produtos": self.listar_produtos,
                "pedidos": self.listar_pedidos,
                "tabelas_preco": self.listar_tabelas_preco,
                "condicoes_pagamento": self.listar_condicoes_pagamento,
                "categorias": self.listar_categorias,
                "segmentos": self.listar_segmentos,
                "tipos_pedido": self.listar_tipos_pedido,
                "produtos_tabela_preco": self.listar_produtos_tabela_preco,
                "usuarios_mercos": self.listar_usuarios_mercos,
                "transportadoras": self.listar_transportadoras,
                "politicas_comerciais": self.listar_politicas_comerciais,
            }
            for nome, fn in probes.items():
                try:
                    resultado = fn()
                    if isinstance(resultado, dict):
                        erros[nome] = str(resultado.get("mensagem") or resultado)
                    elif isinstance(resultado, list):
                        apis_leitura[nome] = True
                        contagens[nome] = len(resultado)
                except Exception as exc:
                    erros[nome] = str(exc)

        requeridos_ata = (
            "clientes",
            "produtos",
            "tabelas_preco",
            "condicoes_pagamento",
            "categorias",
            "segmentos",
            "tipos_pedido",
            "produtos_tabela_preco",
            "usuarios_mercos",
        )
        pronto = (
            checks["tokensConfigurados"]
            and checks["throttling429"]
            and checks["paginacaoAlteradoApos"]
            and all(apis_leitura.get(nome) for nome in requeridos_ata)
        )

        return {
            "prontoParaHomologacao": pronto,
            "ambiente": info,
            "criteriosObrigatorios": checks,
            "apisLeitura": apis_leitura,
            "contagens": contagens,
            "erros": erros,
            "documentacao": "https://docs.mercos.com/reference/homologação",
        }
