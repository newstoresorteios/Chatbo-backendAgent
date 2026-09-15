import pytest
from fastapi import HTTPException
from app.services.configuration_validation import validate_values

FIELDS = [
    {"key": "calls", "label": "Chamadas", "type": "integer", "default": 2, "min": 0, "max": 8},
    {"key": "message.checkout", "label": "Checkout", "target": "message", "type": "textarea",
     "default": "Finalize em {url}", "maxLength": 100},
]

@pytest.mark.parametrize("value", [-1, 9, True, 1.5, "3"])
def test_invalid_budget_rejected(value):
    with pytest.raises(HTTPException):
        validate_values({"calls": value}, FIELDS)

def test_zero_budget_and_message_are_editable():
    result = validate_values({"calls": 0, "message.checkout": "Seu link: {url}"}, FIELDS)
    assert result["calls"] == 0
    assert result["message.checkout"] == "Seu link: {url}"

@pytest.mark.parametrize("value", ["Sem link", "{url.__class__}", "{url!r}", "{url:>20}", "{secret}", ""])
def test_template_contract_preserved(value):
    with pytest.raises(HTTPException):
        validate_values({"message.checkout": value}, FIELDS)
