from odyssey.concierge.guardrail import before_tool_callback


class Ctx:
    def __init__(self, state):
        self.state = state


class Tool:
    def __init__(self, name):
        self.name = name


def test_blocked_without_cart():
    assert before_tool_callback(Tool("complete_trip"), {}, Ctx({})) is not None


def test_allowed_with_cart_in_budget():
    state = {"cart_mandates": [{"price": 100.0}], "total_budget": 2500.0}
    assert before_tool_callback(Tool("complete_trip"), {}, Ctx(state)) is None


def test_over_budget_blocked():
    state = {"cart_mandates": [{"price": 3000.0}], "total_budget": 2500.0}
    res = before_tool_callback(Tool("complete_trip"), {}, Ctx(state))
    assert res is not None and "budget" in str(res).lower()


def test_planning_always_allowed():
    assert before_tool_callback(Tool("plan_trip"), {}, Ctx({})) is None
