from app.schemas.persona import AgentPersonaUpdate, PersonaExample


def test_update_accepts_long_customer_address_style():
    body = AgentPersonaUpdate(
        customerAddressStyle="Olá, {nome}! Vou te tratar pelo primeiro nome, de forma calorosa e próxima, como consultor da New Store."
        * 3
    )
    assert body.customerAddressStyle
    assert len(body.customerAddressStyle) > 120


def test_update_accepts_duplicate_restrictions_without_422():
    items = [f"Não inventar preço {i}" for i in range(20)]
    body = AgentPersonaUpdate(restrictions=[*items, *items])
    assert len(body.restrictions or []) == 40


def test_example_accepts_snake_case_and_empty_placeholder():
    example = PersonaExample.model_validate(
        {"customer_message": "Tem estoque?", "expected_response": "Sim, confirmo agora."}
    )
    assert example.customerMessage == "Tem estoque?"
    placeholder = PersonaExample.model_validate({"id": "ex-1", "customerMessage": "", "expectedResponse": ""})
    assert placeholder.customerMessage == ""
