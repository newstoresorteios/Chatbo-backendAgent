from app.services.persona_restrictions import decode_restrictions, encode_restriction_groups


def test_round_trip_keeps_section_9_lists_apart():
    encoded = encode_restriction_groups(
        {
            "forbiddenSubjects": ["política"],
            "forbiddenPromises": ["garantir lucro"],
            "nonInventableInformation": ["preço"],
            "humanOnlyCommercialTerms": ["desconto especial"],
        }
    )
    decoded = decode_restrictions(encoded)

    assert decoded["forbiddenSubjects"] == ["política"]
    assert decoded["forbiddenPromises"] == ["garantir lucro"]
    assert decoded["nonInventableInformation"] == ["preço"]
    assert decoded["humanOnlyCommercialTerms"] == ["desconto especial"]
    assert encoded[0].startswith("ASSUNTO PROIBIDO — ")


def test_decode_accepts_existing_manual_prefixes():
    decoded = decode_restrictions(
        [
            "ASSUNTO PROIBIDO — política",
            "NÃO PROMETER — garantia",
            "NÃO INVENTAR — estoque",
            "SÓ COM HUMANO — parcelamento",
            "item legado sem prefixo",
        ]
    )

    assert decoded["forbiddenSubjects"] == ["política"]
    assert decoded["forbiddenPromises"] == ["garantia"]
    assert decoded["nonInventableInformation"] == ["estoque", "item legado sem prefixo"]
    assert decoded["humanOnlyCommercialTerms"] == ["parcelamento"]
