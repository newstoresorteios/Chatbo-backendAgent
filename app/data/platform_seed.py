from datetime import datetime, timedelta

_now = datetime.utcnow

SEED_CHANNELS = [
    {"id": "ch1", "type": "whatsapp", "name": "WhatsApp Comercial", "connected": True, "messagesToday": 342, "phone": "+55 11 99999-0001", "lastActivity": _now().isoformat()},
    {"id": "ch2", "type": "instagram", "name": "Instagram @tironitech", "connected": True, "messagesToday": 89, "lastActivity": _now().isoformat()},
    {"id": "ch3", "type": "facebook", "name": "Facebook Messenger", "connected": True, "messagesToday": 56},
    {"id": "ch4", "type": "telegram", "name": "Telegram Suporte", "connected": True, "messagesToday": 23},
    {"id": "ch5", "type": "webchat", "name": "WebChat Site", "connected": True, "messagesToday": 112},
    {"id": "ch6", "type": "sms", "name": "SMS Campanhas", "connected": False, "messagesToday": 0},
    {"id": "ch7", "type": "email", "name": "E-mail Suporte", "connected": True, "messagesToday": 45},
]

SEED_FUNNEL = [
    {"id": "s1", "name": "Lead", "deals": []},
    {"id": "s2", "name": "Qualificação", "deals": []},
    {"id": "s3", "name": "Proposta", "deals": []},
    {"id": "s4", "name": "Negociação", "deals": []},
    {"id": "s5", "name": "Fechado", "deals": []},
]

SEED_CAMPAIGNS = [
    {"id": "cp1", "name": "Black Friday 2024", "channel": "whatsapp", "status": "completed", "recipients": 2500, "sent": 2480, "opened": 1890},
    {"id": "cp2", "name": "Boas-vindas novos leads", "channel": "whatsapp", "status": "running", "recipients": 450, "sent": 320, "opened": 280},
    {"id": "cp3", "name": "Pesquisa NPS", "channel": "sms", "status": "scheduled", "recipients": 800, "sent": 0, "opened": 0, "scheduledAt": "2024-07-01T10:00:00"},
    {"id": "cp4", "name": "Newsletter Junho", "channel": "email", "status": "draft", "recipients": 1200, "sent": 0, "opened": 0},
]

SEED_CHATBOTS = [
    {"id": "bot1", "name": "Triagem Inicial", "active": True, "triggers": 1240, "resolved": 856, "channel": "whatsapp"},
    {"id": "bot2", "name": "FAQ Produtos", "active": True, "triggers": 890, "resolved": 720, "channel": "webchat"},
    {"id": "bot3", "name": "Agendamento", "active": False, "triggers": 340, "resolved": 210, "channel": "instagram"},
    {"id": "bot4", "name": "Pós-venda", "active": True, "triggers": 560, "resolved": 445, "channel": "whatsapp"},
]

SEED_INTEGRATIONS = [
    {"id": "i1", "name": "HubSpot", "category": "crm", "connected": True},
    {"id": "i2", "name": "RD Station", "category": "marketing", "connected": True},
    {"id": "i3", "name": "Pipedrive", "category": "crm", "connected": False},
    {"id": "i4", "name": "Salesforce", "category": "crm", "connected": False},
    {"id": "i5", "name": "Omie", "category": "erp", "connected": True},
    {"id": "i6", "name": "Shopify", "category": "ecommerce", "connected": False},
    {"id": "i7", "name": "Bling ERP", "category": "erp", "connected": True},
    {"id": "i8", "name": "Nuvemshop", "category": "ecommerce", "connected": False},
    {"id": "mercos", "name": "Mercos", "category": "erp", "connected": True},
]

SEED_CONVERSATIONS = [
    {"id": "c1", "customerId": "9255263", "customerName": "Carlos Mendes", "lastMessage": "Preciso de um orçamento para 50 unidades", "lastMessageAt": (_now() - timedelta(minutes=2)).isoformat(), "status": "active", "unreadCount": 2, "channel": "whatsapp", "department": "Comercial", "protocol": "PD-2024-8841", "assignedTo": "Ana Silva"},
    {"id": "c2", "customerId": "9255310", "customerName": "Mariana Costa", "lastMessage": "Obrigada pelo atendimento!", "lastMessageAt": (_now() - timedelta(hours=1)).isoformat(), "status": "closed", "unreadCount": 0, "channel": "instagram", "department": "Suporte", "protocol": "PD-2024-8839"},
    {"id": "c3", "customerId": "9255314", "customerName": "Roberto Alves", "lastMessage": "Quando chega meu pedido #4521?", "lastMessageAt": (_now() - timedelta(hours=2)).isoformat(), "status": "waiting", "unreadCount": 1, "channel": "whatsapp", "department": "Logística", "protocol": "PD-2024-8835"},
]

SEED_MESSAGES = {
    "c1": [
        {"id": "m1", "conversationId": "c1", "content": "Olá, bom dia! Preciso de um orçamento.", "sender": "customer", "timestamp": (_now() - timedelta(minutes=10)).isoformat(), "status": "read"},
        {"id": "m2", "conversationId": "c1", "content": "Olá Carlos! Claro, posso ajudar. Qual produto você precisa?", "sender": "ai", "timestamp": (_now() - timedelta(minutes=9)).isoformat(), "status": "read"},
        {"id": "m3", "conversationId": "c1", "content": "Preciso do modelo Pro-X500, cerca de 50 unidades.", "sender": "customer", "timestamp": (_now() - timedelta(minutes=8)).isoformat(), "status": "read"},
    ],
    "c2": [
        {"id": "m4", "conversationId": "c2", "content": "Obrigada pelo atendimento!", "sender": "customer", "timestamp": (_now() - timedelta(hours=1)).isoformat(), "status": "read"},
    ],
    "c3": [
        {"id": "m5", "conversationId": "c3", "content": "Quando chega meu pedido #4521?", "sender": "customer", "timestamp": (_now() - timedelta(hours=2)).isoformat(), "status": "read"},
    ],
}
