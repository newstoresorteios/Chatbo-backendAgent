import pytest

from app.services.customer_phone import whatsapp_phone


@pytest.mark.parametrize('value, expected', [
    ('(11) 99999-1234', '5511999991234'),
    ('11 3333-1234', '551133331234'),
    ('+55 (11) 99999-1234', '5511999991234'),
    ('5511999991234', '5511999991234'),
    ('+1 (212) 555-1234', '12125551234'),
    ('005511999991234', '5511999991234'),
    ('', ''), (None, ''), ('1234', ''), ('00000000000', ''),
    ('+1234567890123456', ''),
])
def test_whatsapp_phone(value, expected):
    assert whatsapp_phone(value) == expected
