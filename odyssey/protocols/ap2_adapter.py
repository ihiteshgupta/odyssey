from __future__ import annotations

import base64
import hashlib
import json
import logging
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
if _SIGNING == "stub":
    # Make the downgrade loud: the stub is keyless, so anyone can mint a valid
    # signature from the public cart fields. Never silent (was a hidden footgun).
    logging.getLogger("odyssey.ap2").warning(
        "AP2 signing DOWNGRADED to keyless SHA-256 stub (ODYSSEY_AP2_SIGNING=stub) — "
        "mandates are NOT cryptographically authentic; use only for local demos."
    )


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
    """Verify a mandate signature against the CONFIGURED scheme ONLY.

    Pinned to one scheme to prevent signature-downgrade / algorithm-confusion: in
    ECDSA mode a keyless ``STUB-SIG:`` token — which any client can recompute from
    the public cart fields returned by create_checkout — is rejected outright, even
    though ``_stub_sign`` would "match". The scheme is decided by trusted local
    config, never inferred from the attacker-supplied token's prefix.
    """
    if not token:
        return False
    if _SIGNING == "stub":
        return token.startswith(STUB_PREFIX) and token == _stub_sign(payload)
    return token.startswith(ECDSA_PREFIX) and _ecdsa_verify(payload, token)


def _cart_payload(cart: CartMandate) -> dict:
    c = cart.contents
    total = c.payment_request.details.total
    amt = total.amount
    return {
        "id": c.id,
        "merchant_name": c.merchant_name,
        "total": f"{float(amt.value):.2f}",
        "currency": amt.currency,
        # Bind the fields a user/merchant actually commits to, so they can't be
        # swapped while keeping a valid signature: the item label, the cart expiry,
        # and whether explicit user confirmation is required.
        "label": total.label,
        "cart_expiry": c.cart_expiry,
        "confirmation_required": c.user_cart_confirmation_required,
    }  # stable mapping for hashing


def cart_total(cart: "CartMandate | dict") -> tuple[float, str]:
    """Return ``(amount, currency)`` of a cart's signed total — the authoritative
    charged amount. Accepts a ``CartMandate`` or its ``model_dump()`` dict. Raises
    KeyError/TypeError/ValueError on a malformed cart so callers can fail closed."""
    if isinstance(cart, dict):
        amt = cart["contents"]["payment_request"]["details"]["total"]["amount"]
        return float(amt["value"]), amt["currency"]
    amt = cart.contents.payment_request.details.total.amount
    return float(amt.value), amt.currency


def _payment_payload(cart: CartMandate, contents: PaymentMandateContents) -> dict:
    """The bytes the user signs: the cart commitment PLUS the PaymentMandate's own
    value and ids, so the authorized amount/instrument can't be altered after signing
    (the cart payload alone left payment_details_total etc. unbound)."""
    amt = contents.payment_details_total.amount
    return {
        "cart": _cart_payload(cart),
        "merchant_agent": contents.merchant_agent,
        "payment_mandate_id": contents.payment_mandate_id,
        "payment_details_id": contents.payment_details_id,
        "payment_total": f"{float(amt.value):.2f}",
        "payment_currency": amt.currency,
    }


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
    pm.user_authorization = _sign(_payment_payload(cart, contents))
    return pm


def verify_cart_mandate(cart: CartMandate) -> bool:
    return _verify(_cart_payload(cart), cart.merchant_authorization)


def verify_payment_mandate(payment: PaymentMandate, cart: CartMandate) -> bool:
    contents = payment.payment_mandate_contents
    # 1. the user signature must cover the PaymentMandate's own fields + the cart.
    if not _verify(_payment_payload(cart, contents), payment.user_authorization):
        return False
    # 2. the authorized payment total must equal the signed cart total (no value swap).
    pay = contents.payment_details_total.amount
    cart_amt = cart.contents.payment_request.details.total.amount
    if (f"{float(pay.value):.2f}", pay.currency) != (
        f"{float(cart_amt.value):.2f}",
        cart_amt.currency,
    ):
        return False
    # 3. the cart itself must carry an intact merchant signature.
    return verify_cart_mandate(cart)
