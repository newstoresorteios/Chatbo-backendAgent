import pytest
from fastapi import HTTPException
from app.services.configuration_validation import validate_values
from app.services.configuration_validation import configuration_diagnostics, validate_structured
import json

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


def test_technical_vocabulary_and_phrases_are_operator_editable():
    feature = {"field":"crystal", "value":"sapphire", "label":"Safira", "query":"safira",
               "aliases":["safira", "sapphire"], "evidenceFields":["glass"]}
    validate_structured(json.dumps([feature]), "technicalFeatures")
    validate_structured(json.dumps(["sem exigência de {feature}"]), "featurePhrases")
    for invalid in ([feature, feature], [{**feature, "aliases":[]}], [{**feature, "field":"price"}]):
        with pytest.raises(ValueError):
            validate_structured(json.dumps(invalid), "technicalFeatures")


@pytest.mark.parametrize("phrase", ["sem variável", "{feature.__class__}", "{feature!r}", "{feature} {feature}"])
def test_feature_phrases_reject_unsafe_or_missing_variables(phrase):
    with pytest.raises(ValueError):
        validate_structured(json.dumps([phrase]), "featurePhrases")


def test_review_diagnostics_explain_promotion_and_reject_incompatible_limits():
    values = {"agent_critique_mode":"shadow", "agent_critique_enforce_on_commerce":True,
              "agent_llm_budget_enabled":True, "agent_max_llm_calls_per_turn":2,
              "agent_max_llm_calls_per_turn_complex":1, "agent_critique_max_retries":4}
    diagnoses = {item["code"]:item["level"] for item in configuration_diagnostics(values)}
    assert diagnoses["commerce_review_promoted"] == "info"
    assert diagnoses["review_budget_incompatible"] == "error"
    assert diagnoses["complex_budget_below_base"] == "error"
    values.update(agent_max_llm_calls_per_turn=3, agent_max_llm_calls_per_turn_complex=4)
    assert not any(d["level"] == "error" for d in configuration_diagnostics(values))
