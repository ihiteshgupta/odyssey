from __future__ import annotations

import itertools

WELL_KNOWN = "/.well-known/ucp"   # dual-path probing of agent cards is a Phase-2 stretch


class UCPClient:
    """Hand-written UCP client over the MCP/JSON-RPC binding (tools/call).
    `transport` has .get(path) and .post(path, json=...) returning a response with .json()
    — a FastAPI TestClient in tests, an httpx.Client(base_url=...) in production.
    """

    def __init__(self, transport):
        self._t = transport
        self._ids = itertools.count(1)

    def discover(self) -> dict:
        return self._t.get(WELL_KNOWN).json()["ucp"]["capabilities"]

    def call(self, name: str, arguments: dict) -> dict:
        resp = self._t.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": next(self._ids),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
        ).json()
        # JSON-RPC envelope-level error (rare for this server).
        if isinstance(resp, dict) and resp.get("error"):
            raise RuntimeError(f"UCP transport error: {resp['error']}")
        result = resp.get("result")
        if result is None:
            raise RuntimeError(f"UCP malformed response (no result): {resp}")
        # Dispatch-level errors are returned nested under `result` as a sole
        # {"error": ...} entry — surface them so callers get a clean RuntimeError
        # instead of a KeyError on result["checkout"] / result["products"].
        if isinstance(result, dict) and set(result) == {"error"}:
            raise RuntimeError(f"UCP error: {result['error']}")
        return result
