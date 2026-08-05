from app.services.nsagent_persona_bridge import compile_instructions


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
