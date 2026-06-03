"""Cost/turn observability: usage threaded across A2A → real cost_usd.

Offline-only (no Gemini key): exercises the concierge-side extraction +
estimate + cost math. The merchant-side `after_model_callback` that emits the
`__odyssey_usage__` sentinel only fires under a live model call, so it's
verified by a live smoke test, not here.
"""
from __future__ import annotations

import json
import logging
from types import SimpleNamespace

from odyssey.common.types import Vertical
from odyssey.concierge.a2a_client import _estimate_usage, _extract_usage
from odyssey.concierge.negotiate import (
    GEMINI_2_5_FLASH_INPUT_USD_PER_TOKEN,
    GEMINI_2_5_FLASH_OUTPUT_USD_PER_TOKEN,
    _log_estimated_cost,
)


def _text_part(text: str) -> SimpleNamespace:
    return SimpleNamespace(root=SimpleNamespace(text=text, data=None))


def _data_part(data: dict) -> SimpleNamespace:
    return SimpleNamespace(root=SimpleNamespace(text=None, data=data))


def test_estimate_usage_is_positive_and_flagged() -> None:
    u = _estimate_usage("a" * 40, "b" * 80)
    assert u["prompt_token_count"] == 10  # ~4 chars/token
    assert u["candidates_token_count"] == 20
    assert u["estimated"] is True


def test_extract_usage_from_text_sentinel() -> None:
    sentinel = json.dumps(
        {"__odyssey_usage__": {"prompt_token_count": 321, "candidates_token_count": 42}}
    )
    usage = _extract_usage([_text_part("{...offer json...}"), _text_part(sentinel)])
    assert usage == {"prompt_token_count": 321, "candidates_token_count": 42}


def test_extract_usage_from_data_part() -> None:
    usage = _extract_usage(
        [_data_part({"usage_metadata": {"prompt_token_count": 7, "candidates_token_count": 3}})]
    )
    assert usage == {"prompt_token_count": 7, "candidates_token_count": 3}


def test_extract_usage_absent_returns_none() -> None:
    assert _extract_usage([_text_part('{"fits": true, "offers": []}')]) is None
    assert _extract_usage([]) is None


def test_cost_logged_real_from_threaded_usage(caplog) -> None:
    raw = {
        "fits": True,
        "offers": [],
        "_odyssey_usage": {"prompt_token_count": 1000, "candidates_token_count": 500},
    }
    expected = round(
        1000 * GEMINI_2_5_FLASH_INPUT_USD_PER_TOKEN
        + 500 * GEMINI_2_5_FLASH_OUTPUT_USD_PER_TOKEN,
        6,
    )
    with caplog.at_level(logging.INFO, logger="odyssey.negotiate"):
        _log_estimated_cost(Vertical.FLIGHT, raw)
    line = caplog.text
    assert f"cost_usd={expected}" in line
    assert "estimated=False" in line


def test_cost_logged_estimated_flag(caplog) -> None:
    raw = {
        "fits": True,
        "_odyssey_usage": {
            "prompt_token_count": 100,
            "candidates_token_count": 20,
            "estimated": True,
        },
    }
    with caplog.at_level(logging.INFO, logger="odyssey.negotiate"):
        _log_estimated_cost(Vertical.HOTEL, raw)
    assert "estimated=True" in caplog.text


def test_cost_zero_for_inprocess_no_llm(caplog) -> None:
    raw = {"fits": True, "offers": []}  # in-process fallback: no LLM call
    with caplog.at_level(logging.INFO, logger="odyssey.negotiate"):
        _log_estimated_cost(Vertical.ACTIVITY, raw)
    assert "cost_usd=0.0" in caplog.text
