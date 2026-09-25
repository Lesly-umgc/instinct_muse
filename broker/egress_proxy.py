"""Egress gate: allowlist check plus just-in-time credential injection.

MVP version of Muse's "Sentinel". Run it as the sandbox's only route out
(set HTTP(S)_PROXY in the sandbox and block other egress with Docker networks).
"""
from urllib.parse import urlparse

from broker.token_broker import TokenBroker


class EgressGate:
    def __init__(self, allowlist: set[str], broker: TokenBroker) -> None:
        self.allowlist = allowlist
        self.broker = broker

    def check(self, url: str, headers: dict[str, str]) -> tuple[bool, dict[str, str], str]:
        host = urlparse(url).hostname or ""
        if host not in self.allowlist:
            return False, headers, f"blocked: {host} is not on the egress allowlist"
        out = dict(headers)
        auth = out.get("Authorization", "")
        if auth.startswith("Bearer srg_"):
            real = self.broker.resolve(auth.removeprefix("Bearer "), host)
            if real is None:
                return False, headers, "blocked: surrogate token not valid for this host"
            out["Authorization"] = f"Bearer {real}"
        return True, out, "allowed"
