from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from ap2.models.mandate import (
    CartContents,
    CartMandate,
    IntentMandate,
    PaymentMandate,
    PaymentMandateContents,
)
from ap2.models.payment_request import (
    PaymentCurrencyAmount,
    PaymentDetailsInit,
    PaymentItem,
    PaymentMethodData,
    PaymentRequest,
    PaymentResponse,
)

from odyssey.common.types import Money

STUB_PREFIX = "STUB-SIG:"  # marks a SIMULATED, non-cryptographic signature


def _now_plus(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _stub_sign(payload: dict) -> str:
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return f"{STUB_PREFIX}{digest}"


def _cart_payload(cart: CartMandate) -> dict:
    c = cart.contents
    amt = c.payment_request.details.total.amount
    return {
        "id": c.id,
        "merchant_name": c.merchant_name,
        "total": f"{float(amt.value):.2f}",
        "currency": amt.currency,
    }  # stable string for hashing


def build_intent_mandate(description: str, expiry_minutes: int = 30) -> IntentMandate:
    return IntentMandate(
        natural_language_description=description,
        intent_expiry=_now_plus(expiry_minutes),
    )


def build_cart_mandate(
    cart_id: str,
    merchant_name: str,
    total: Money,
    label: str,
    expiry_minutes: int = 15,
) -> CartMandate:
    item = PaymentItem(
        label=label,
        amount=PaymentCurrencyAmount(currency=total.currency, value=round(total.amount, 2)),
    )
    pr = PaymentRequest(
        method_data=[PaymentMethodData(supported_methods="basic-card")],
        details=PaymentDetailsInit(id=cart_id, display_items=[item], total=item),
    )
    contents = CartContents(
        id=cart_id,
        user_cart_confirmation_required=True,
        payment_request=pr,
        cart_expiry=_now_plus(expiry_minutes),
        merchant_name=merchant_name,
    )
    cm = CartMandate(contents=contents)
    cm.merchant_authorization = _stub_sign(_cart_payload(cm))
    return cm


def build_payment_mandate(cart: CartMandate, merchant_agent: str) -> PaymentMandate:
    total = cart.contents.payment_request.details.total
    contents = PaymentMandateContents(
        payment_mandate_id=f"pm-{cart.contents.id}",
        payment_details_id=cart.contents.id,
        payment_details_total=total,
        payment_response=PaymentResponse(
            request_id=cart.contents.id,
            method_name="basic-card",
            details={},
        ),
        merchant_agent=merchant_agent,
    )
    pm = PaymentMandate(payment_mandate_contents=contents)
    pm.user_authorization = _stub_sign(
        {"cart": _cart_payload(cart), "merchant_agent": merchant_agent}
    )
    return pm


def verify_cart_mandate(cart: CartMandate) -> bool:
    return cart.merchant_authorization == _stub_sign(_cart_payload(cart))


def verify_payment_mandate(payment: PaymentMandate, cart: CartMandate) -> bool:
    expected = _stub_sign(
        {
            "cart": _cart_payload(cart),
            "merchant_agent": payment.payment_mandate_contents.merchant_agent,
        }
    )
    return payment.user_authorization == expected and verify_cart_mandate(cart)
