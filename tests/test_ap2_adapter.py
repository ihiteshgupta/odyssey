from odyssey.common.types import Money
from odyssey.protocols.ap2_adapter import (
    ECDSA_PREFIX,
    build_cart_mandate,
    build_intent_mandate,
    build_payment_mandate,
    verify_cart_mandate,
    verify_payment_mandate,
)


def test_intent_mandate_has_description_and_expiry():
    im = build_intent_mandate("5 days in Bali for 2 under $2500", expiry_minutes=30)
    assert im.natural_language_description.startswith("5 days") and im.intent_expiry


def test_cart_mandate_merchant_signed_and_verifiable():
    cm = build_cart_mandate("c1", "Bali Beach Resort", Money("USD", 640.0), "Hotel", expiry_minutes=15)
    assert cm.merchant_authorization.startswith(ECDSA_PREFIX) and verify_cart_mandate(cm) is True


def test_payment_mandate_user_signed_and_verifiable():
    cm = build_cart_mandate("c1", "X", Money("USD", 10.0), "Y", 15)
    pm = build_payment_mandate(cart=cm, merchant_agent="hotel_merchant")
    assert pm.user_authorization.startswith(ECDSA_PREFIX) and verify_payment_mandate(pm, cart=cm) is True


def test_tampered_cart_fails_verification():
    cm = build_cart_mandate("c1", "X", Money("USD", 10.0), "Y", 15)
    cm.contents.payment_request.details.total.amount.value = 999.0
    assert verify_cart_mandate(cm) is False


def test_cart_roundtrips_through_model_validate():
    from ap2.models.mandate import CartMandate
    cm = build_cart_mandate("c2", "Z", Money("USD", 500.0), "Flight", 15)
    rebuilt = CartMandate.model_validate(cm.model_dump())
    assert verify_cart_mandate(rebuilt) is True
