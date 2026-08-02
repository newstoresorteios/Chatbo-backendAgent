"""ConversaRepository preenche cliente_id uuid sem remover cliente_mercos_id."""

from unittest.mock import MagicMock, patch

from app.repositories.conversa_repository import ConversaRepository
from app.services.conversa_cliente_link import (
    enriquecer_dados_conversa_com_cliente_id,
    resolver_cliente_id_conversa,
)


def test_resolver_prioriza_mercos_id():
    with patch("app.services.conversa_cliente_link.supabase") as mock_sb:
        table = MagicMock()
        mock_sb.table.return_value = table
        table.select.return_value = table
        table.eq.return_value = table
        table.limit.return_value = table
        table.execute.return_value = MagicMock(data=[{"id": "uuid-abc"}])

        cid = resolver_cliente_id_conversa(
            cliente_mercos_id="9255263",
            telefone="5543999999999",
        )
        assert cid == "uuid-abc"
        table.eq.assert_called_with("mercos_id", 9255263)


def test_enriquecer_nao_remove_cliente_mercos_id():
    with patch(
        "app.services.conversa_cliente_link.resolver_cliente_id_conversa",
        return_value="uuid-xyz",
    ):
        out = enriquecer_dados_conversa_com_cliente_id(
            {
                "customer_name": "Ana",
                "cliente_mercos_id": "9255263",
                "contact_phone": "5543999000111",
            }
        )
    assert out["cliente_id"] == "uuid-xyz"
    assert out["cliente_mercos_id"] == "9255263"


def test_criar_conversa_nova_preenche_cliente_id_quando_cliente_existe():
    repo = ConversaRepository()
    captured = {}

    def fake_insert(payload):
        captured["payload"] = dict(payload)
        chain = MagicMock()
        chain.execute.return_value = MagicMock(
            data=[{**payload, "id": "conv-1"}]
        )
        return chain

    with patch(
        "app.repositories.conversa_repository.enriquecer_dados_conversa_com_cliente_id",
        side_effect=lambda dados, existente=None: {
            **dados,
            "cliente_id": "cli-uuid-1",
        },
    ), patch("app.repositories.conversa_repository.supabase") as mock_sb:
        table = MagicMock()
        mock_sb.table.return_value = table
        table.insert.side_effect = fake_insert

        row = repo.criar(
            {
                "customer_name": "Carlos",
                "cliente_mercos_id": "9255263",
                "channel": "whatsapp",
                "status": "active",
            }
        )

    assert captured["payload"]["cliente_id"] == "cli-uuid-1"
    assert captured["payload"]["cliente_mercos_id"] == "9255263"
    assert row["id"] == "conv-1"


def test_criar_sem_match_nao_forca_cliente_id():
    repo = ConversaRepository()
    captured = {}

    def fake_insert(payload):
        captured["payload"] = dict(payload)
        chain = MagicMock()
        chain.execute.return_value = MagicMock(data=[payload])
        return chain

    with patch(
        "app.repositories.conversa_repository.enriquecer_dados_conversa_com_cliente_id",
        side_effect=lambda dados, existente=None: dict(dados),
    ), patch("app.repositories.conversa_repository.supabase") as mock_sb:
        table = MagicMock()
        mock_sb.table.return_value = table
        table.insert.side_effect = fake_insert
        repo.criar({"customer_name": "Sem Cliente", "channel": "whatsapp"})

    assert "cliente_id" not in captured["payload"]
