from odyssey.common.types import Money, Offer, Intent, NegotiationRequest, NegotiationResponse, Vertical

def test_money_add_same_currency():
    assert (Money("USD", 100.0) + Money("USD", 50.5)) == Money("USD", 150.5)

def test_money_add_rejects_mismatch():
    import pytest
    with pytest.raises(ValueError):
        Money("USD", 1.0) + Money("EUR", 1.0)

def test_offer_and_negotiation_shapes():
    off = Offer(id="F1", vertical=Vertical.FLIGHT, title="JFK→DPS", price=Money("USD", 800.0), raw={})
    req = NegotiationRequest(
        intent=Intent(origin="JFK", destination="DPS", start_date="2026-09-01",
                      end_date="2026-09-06", party_size=2, total_budget=Money("USD", 2500.0), prefs=["beachy"]),
        budget_slice=Money("USD", 1100.0), round=0)
    resp = NegotiationResponse(offers=[off], fits=True, cheapest=Money("USD", 800.0),
                               nearest_above=None, note="ok")
    assert resp.offers[0].price.amount == 800.0 and req.budget_slice.amount == 1100.0
