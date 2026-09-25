"""Credential broker (host side, outside the sandbox).

The agent only ever sees surrogate tokens like `srg_github_ab12`. The egress
proxy swaps a surrogate for the real OAuth token just before a request leaves,
and only for allowlisted hosts. Real secrets never enter the sandbox.
"""
import secrets


class TokenBroker:
    def __init__(self) -> None:
        self._real: dict[str, str] = {}
        self._host_for: dict[str, str] = {}

    def register(self, service: str, real_token: str, host: str) -> str:
        surrogate = f"srg_{service}_{secrets.token_hex(4)}"
        self._real[surrogate] = real_token
        self._host_for[surrogate] = host
        return surrogate

    def resolve(self, surrogate: str, host: str) -> str | None:
        """Return the real token only if the request is going to the host it was issued for."""
        if self._host_for.get(surrogate) != host:
            return None
        return self._real.get(surrogate)
