from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


def test_evaluation_results_are_filtered_by_workspace(monkeypatch):
    from app.services import conversation_evaluation_service as service
    query = MagicMock()
    for name in ('select','eq','order','limit'):
        getattr(query,name).return_value = query
    query.execute.return_value = SimpleNamespace(data=[])
    client = SimpleNamespace(table=MagicMock(return_value=query))
    monkeypatch.setattr(service,'supabase',client)
    assert service.list_conversation_evaluations('workspace-a') == {'items':[]}
    query.eq.assert_called_once_with('workspace_id','workspace-a')


def test_question_rules_reject_invalid_regex_and_missing_groups():
    import json
    from app.services.configuration_validation import validate_values
    rules = {name:['test'] for name in ('questionPatterns','commitPatterns','conditionalPatterns')}
    field = {'key':'productQuestionRules','type':'textarea','label':'Regras','default':json.dumps(rules)}
    assert validate_values({},[field])['productQuestionRules'] == field['default']
    for invalid in ({},[],{**rules,'questionPatterns':['(']}):
        with pytest.raises(HTTPException):
            validate_values({'productQuestionRules':json.dumps(invalid)},[field])
