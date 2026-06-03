from __future__ import annotations

import base64
import hashlib
import json
import os
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
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from odyssey.common.types import Money

STUB_PREFIX = "STUB-SIG:"  # marks a SIMULATED, non-cryptographic signature


def _now_plus(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _stub_sign(payload: dict) -> str:
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return f"{STUB_PREFIX}{digest}"


ECDSA_PREFIX = "ECDSA-P256:"  # a real cryptographic signature
# Demo keypair derived DETERMINISTICALLY so the separate concierge & merchant
# processes share one key (a production deployment uses per-party keys / a PKI —
# see the honesty note). The secret is reduced into the P-256 group order.
_P256_ORDER = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_DEMO_SECRET = (
    int.from_bytes(hashlib.sha256(b"odyssey-demo-ap2-key").digest(), "big") % (_P256_ORDER - 1)
) + 1
_DEMO_KEY = ec.derive_private_key(_DEMO_SECRET, ec.SECP256R1())
_DEMO_PUB = _DEMO_KEY.public_key()
# Real ECDSA by default; set ODYSSEY_AP2_SIGNING=stub for the legacy SHA-256 placeholder.
_SIGNING = os.getenv("ODYSSEY_AP2_SIGNING", "ecdsa").lower()


def _payload_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True).encode()


def _ecdsa_sign(payload: dict) -> str:
    sig = _DEMO_KEY.sign(_payload_bytes(payload), ec.ECDSA(hashes.SHA256()))
    return ECDSA_PREFIX + base64.b64encode(sig).decode()


def _ecdsa_verify(payload: dict, token: str) -> bool:
    try:
        _DEMO_PUB.verify(base64.b64decode(token[len(ECDSA_PREFIX):]),
                         _payload_bytes(payload), ec.ECDSA(hashes.SHA256()))
        return True
    except Exception:
        return False


def _sign(payload: dict) -> str:
    """Sign a mandate payload — real ECDSA P-256 by default, SHA-256 stub fallback."""
    return _stub_sign(payload) if _SIGNING == "stub" else _ecdsa_sign(payload)


def _verify(payload: dict, token: str | None) -> bool:
    """Verify a mandate signature, dispatching on its scheme prefix."""
    if token and token.startswith(ECDSA_PREFIX):
        return _ecdsa_verify(payload, token)
    if token and token.startswith(STUB_PREFIX):
        return token == _stub_sign(payload)
    return False


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
    cm.merchant_authorization = _sign(_cart_payload(cm))
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
    pm.user_authorization = _sign(
        {"cart": _cart_payload(cart), "merchant_agent": merchant_agent}
    )
    return pm


def verify_cart_mandate(cart: CartMandate) -> bool:
    return _verify(_cart_payload(cart), cart.merchant_authorization)


def verify_payment_mandate(payment: PaymentMandate, cart: CartMandate) -> bool:
    payload = {
        "cart": _cart_payload(cart),
        "merchant_agent": payment.payment_mandate_contents.merchant_agent,
    }
    return _verify(payload, payment.user_authorization) and verify_cart_mandate(cart)
