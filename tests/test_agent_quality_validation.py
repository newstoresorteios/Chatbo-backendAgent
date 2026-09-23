import json
import re
import pytest
from app.services.agent_quality_validation import validate_quality_controls

@pytest.mark.parametrize('field,value', [('modelRolePolicies','[]'),('modelRolePolicies','{"wrong":{}}'),('institutionalRoutingRules','{"question":"[","action":"x"}'),('evaluationCampaignPolicy','{"enabled":true}')])
def test_invalid_controls_rejected(field,value):
    with pytest.raises((ValueError,TypeError,re.error)):
        validate_quality_controls({field:value})

def test_role_capabilities_checked_before_publication():
    data={'modelRolePolicies':json.dumps({'review':{'model':'example','reasoning_effort':'low'}}),
        'modelCapabilityRegistry':json.dumps({'example':{'reasoning_efforts':['low'],'responses':True}})}
    validate_quality_controls(data)
    data['modelRolePolicies']=json.dumps({'review':{'model':'example','reasoning_effort':'none'}})
    with pytest.raises(ValueError):validate_quality_controls(data)

def test_disabled_campaign_needs_no_credentials_or_pricing():
    validate_quality_controls({'evaluationCampaignPolicy':'{"enabled":false,"max_calls":0}'})
