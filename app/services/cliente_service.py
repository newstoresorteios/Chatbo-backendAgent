from app.services.mercos_service import MercosService
from app.repositories.cliente_repository import ClienteRepository
from app.repositories.mercos_sync_repository import MercosSyncRepository


class ClienteService:

    def __init__(self):
        self.mercos = MercosService()
        self.repository = ClienteRepository()
        self.sync_logs = MercosSyncRepository()

    def sincronizar(self, *, incremental: bool = True):
        alterado_apos = None
        if incremental:
            alterado_apos = self.sync_logs.ultima_sincronizacao("customers")

        clientes = self.mercos.listar_clientes(alterado_apos=alterado_apos)

        if isinstance(clientes, dict):
            raise RuntimeError(
                f"Resposta inesperada do Mercos: {clientes.get('mensagem') or clientes}"
            )

        if not isinstance(clientes, list):
            raise RuntimeError("Mercos não retornou lista de clientes.")

        quantidade = 0

        for cliente in clientes:

            nome = cliente.get("nome") or cliente.get("razao_social")

            emails = cliente.get("emails", [])
            email = None

            if emails:
                if isinstance(emails[0], dict):
                    email = emails[0].get("email")
                else:
                    email = emails[0]

            dados = {
                "mercos_id": cliente.get("id"),
                "nome": nome,
                "razao_social": cliente.get("razao_social"),
                "cnpj": cliente.get("cnpj"),
                "inscricao_estadual": cliente.get("inscricao_estadual"),
                "email": email,
                "telefone": cliente.get("telefone"),
                "celular": cliente.get("celular"),
                "endereco": cliente.get("endereco"),
                "numero": cliente.get("numero"),
                "complemento": cliente.get("complemento"),
                "bairro": cliente.get("bairro"),
                "cidade": cliente.get("cidade"),
                "estado": cliente.get("estado"),
                "cep": cliente.get("cep")
            }

            self.repository.salvar(dados)
            quantidade += 1

        cursor = MercosService.max_ultima_alteracao(clientes)
        mensagem = f"Clientes sincronizados: {quantidade}."
        self.sync_logs.registrar(
            tipo="customers",
            mensagem=mensagem,
            quantidade=quantidade,
            cursor_ultima_alteracao=cursor,
        )

        return {
            "mensagem": "Sincronização concluída.",
            "clientes_sincronizados": quantidade,
            "cursor_ultima_alteracao": cursor,
            "incremental": bool(alterado_apos),
        }