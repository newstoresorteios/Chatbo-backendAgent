from app.services.nsagent_persona_bridge import compile_instructions


def test_invalid_fixture_identity_is_rejected_before_any_database_access():
    import pytest
    from app.services.nsagent_persona_bridge import NsAgentPersonaBridge
    with pytest.raises(ValueError, match="invalid_persona_workspace_link"):
        NsAgentPersonaBridge().publish_active({"id": "persona-1", "workspace_id": "workspace-a"})


def test_supabase_proxy_introspection_does_not_open_a_connection():
    from app.services.supabase_service import supabase
    assert not hasattr(supabase, "__func__")


def test_compile_instructions_includes_core_fields():
    text = compile_instructions(
        {
            "name": "Felipe Bot",
            "role": "consultor comercial",
            "tone": "objetivo e cordial",
            "greeting": "Olá! Sou da New Store.",
            "sales_goals": ["Qualificar lead", "Agendar atendimento"],
            "restrictions": ["Não inventar preço"],
            "examples": [
                {
                    "customerMessage": "Tem relógio?",
                    "expectedResponse": "Temos várias linhas. Qual estilo você busca?",
                }
            ],
        }
    )
    assert "Felipe Bot" in text
    assert "consultor comercial" in text
    assert "Qualificar lead" in text
    assert "Não inventar preço" in text
    assert "Tem relógio?" in text


def test_compile_instructions_groups_prefixed_restrictions():
    text = compile_instructions(
        {
            "name": "Felipe Bot",
            "role": "consultor",
            "restrictions": [
                "ASSUNTO PROIBIDO — política",
                "NÃO PROMETER — garantia de lucro",
                "NÃO INVENTAR — preço",
                "SÓ COM HUMANO — desconto especial",
            ],
        }
    )
    assert "Assuntos proibidos:" in text
    assert "política" in text
    assert "Promessas que não pode fazer:" in text
    assert "Condições comerciais que exigem humano:" in text


def test_compile_instructions_includes_knowledge_docs():
    text = compile_instructions(
        {
            "name": "Felipe Bot",
            "role": "consultor",
            "greeting": "Olá",
            "tone": "objetivo",
        },
        knowledge_docs=[
            {
                "filename": "faq-frete.txt",
                "extracted_text": "Frete grátis acima de R$ 500 para SP capital.",
            }
        ],
    )
    assert "Base de conhecimento aprovada" in text
    assert "faq-frete.txt" in text
    assert "Frete grátis" in text
    # preço volátil deve ser scrubado
    assert "R$" not in text or "[dado dinâmico" in text
