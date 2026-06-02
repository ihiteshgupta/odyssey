"""ADK agent-discovery shim for Cloud Run.

`get_fast_api_app(agents_dir="deploy_agents")` scans this directory; each subpackage
that exposes `root_agent` is served as an agent. We re-export the real concierge so the
whole `odyssey` package (installed editable) stays importable without ADK trying to load
odyssey's non-agent subpackages (common/data/protocols/merchants) as agents.
"""

from odyssey.concierge.agent import root_agent

__all__ = ["root_agent"]
