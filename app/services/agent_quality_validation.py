"""Validate quality controls before publishing the operator configuration."""
import json
import math
import re


def validate_quality_controls(values):
    def object_value(key):
        value = json.loads(values.get(key, '{}'))
        if not isinstance(value, dict):
            raise ValueError(key + ': informe um objeto JSON')
        return value

    roles = object_value('modelRolePolicies')
    registry = object_value('modelCapabilityRegistry')
    if set(roles) - {'interpretation','composition','vision','review','evaluation'}:
        raise ValueError('Função de modelo desconhecida')
    for model, caps in registry.items():
        if not isinstance(caps, dict) or not model.strip():
            raise ValueError('Cadastro de capacidades inválido')
        for key in ('responses','structured_outputs','tools','chat_completions','chat_tools','verbosity','parallel_tools','temperature'):
            if key in caps and not isinstance(caps[key], bool):
                raise ValueError('Capacidade deve ser booleana: ' + key)
        efforts = caps.get('reasoning_efforts', [])
        if not isinstance(efforts, list) or any(v not in {'none','minimal','low','medium','high','xhigh','max','ultra'} for v in efforts):
            raise ValueError('Esforços de raciocínio inválidos')
    main_model, effort = values.get('openai_model'), values.get('openai_reasoning_effort')
    if main_model in registry and effort and effort not in registry[main_model].get('reasoning_efforts', []):
        raise ValueError('O modelo principal não suporta esse esforço de raciocínio')
    for role, config in roles.items():
        if not isinstance(config, dict) or set(config) - {'model','reasoning_effort','max_output_tokens','timeout_seconds','allow_transport_fallback'}:
            raise ValueError('Configuração inválida para a função ' + role)
        model = config.get('model') or values.get('openai_model')
        if model not in registry:
            raise ValueError('Cadastre as capacidades do modelo ' + str(model))
        if config.get('reasoning_effort') is not None and config['reasoning_effort'] not in registry[model].get('reasoning_efforts', []):
            raise ValueError('O modelo não suporta esse esforço de raciocínio')
        for key,maximum in (('max_output_tokens',128000),('timeout_seconds',180)):
            if config.get(key) is not None:
                value=config[key]
                if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=maximum or (key=='max_output_tokens' and type(value) is not int):
                    raise ValueError('Limite inválido: ' + key)
        if 'allow_transport_fallback' in config and not isinstance(config['allow_transport_fallback'],bool):
            raise ValueError('Fallback deve ser booleano')
    routing = object_value('institutionalRoutingRules')
    if routing:
        if set(routing)!={'question','action'}:
            raise ValueError('Preserve question e action nas regras institucionais')
        for value in routing.values():
            if not isinstance(value,str) or not value or len(value)>2000:
                raise ValueError('Expressão institucional inválida')
            re.compile(value)
    campaign = object_value('evaluationCampaignPolicy')
    if campaign.get('enabled'):
        if not campaign.get('campaign_id') or not campaign.get('price_version'):
            raise ValueError('Defina campanha e versão dos preços')
        for key in ('max_calls','max_tokens','max_cost_usd','max_input_tokens_per_call'):
            value=campaign.get(key)
            if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
                raise ValueError('Orçamento positivo obrigatório: ' + key)
        if not isinstance(campaign.get('prices'),dict) or not campaign['prices']:
            raise ValueError('Cadastre os preços por modelo')
        for rates in campaign['prices'].values():
            if not isinstance(rates,dict) or not all(type(rates.get(k)) in (int,float) and math.isfinite(rates[k]) and rates[k]>=0 for k in ('input','output')):
                raise ValueError('Preços de entrada e saída inválidos')
