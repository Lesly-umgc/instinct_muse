from broker.egress_proxy import EgressGate
from broker.token_broker import TokenBroker


def test_surrogate_swapped_only_for_its_host():
    broker = TokenBroker()
    srg = broker.register("github", "ghp_real", "api.github.com")
    gate = EgressGate({"api.github.com", "evil.example"}, broker)

    ok, headers, _ = gate.check("https://api.github.com/user", {"Authorization": f"Bearer {srg}"})
    assert ok and headers["Authorization"] == "Bearer ghp_real"

    ok, headers, reason = gate.check("https://evil.example/x", {"Authorization": f"Bearer {srg}"})
    assert not ok and "surrogate" in reason


def test_unlisted_host_blocked():
    gate = EgressGate({"api.github.com"}, TokenBroker())
    ok, _, reason = gate.check("https://example.com", {})
    assert not ok and "allowlist" in reason
