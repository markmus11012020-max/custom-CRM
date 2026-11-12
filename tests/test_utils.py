from __future__ import annotations

import hashlib

from app.services.payments import robokassa_payment_signature, robokassa_result_signature
from app.services.search import normalize


def test_search_normalize_cyrillic():
    assert normalize("Иван", "ПЕТРОВ", None, "") == "иван петров"


def test_robokassa_signatures():
    payment = robokassa_payment_signature("merchant", "1000.00", "42", "password1")
    assert payment == hashlib.md5(b"merchant:1000.00:42:password1").hexdigest()
    result = robokassa_result_signature("1000.00", "42", "password2")
    assert result == hashlib.md5(b"1000.00:42:password2").hexdigest()
