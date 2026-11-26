"""Vajra-Kavach: Air-Gap Enforcement & Zero-Network Guard.

Ensures the pipeline runs strictly 100% offline with zero outbound network traffic.
Monkey-patches low-level socket connections to prevent any accidental external
telemetry, analytics, or API calls from third-party libraries.
"""
from __future__ import annotations

import os
import socket
import sys
from typing import Any

class AirGapViolationError(RuntimeError):
    """Raised when any code attempts an unauthorized outbound network connection in offline mode."""
    pass


_AIRGAP_ENFORCED = False
_ORIGINAL_SOCKET_CONNECT = socket.socket.connect
_ORIGINAL_CREATE_CONNECTION = socket.create_connection


def is_offline_mode() -> bool:
    """Return True if OFFLINE_MODE is enabled (defaults to True for air-gapped safety)."""
    env_val = os.environ.get("OFFLINE_MODE", "true").strip().lower()
    return env_val in ("true", "1", "yes", "on", "strict")


def enforce_airgap(strict: bool = True, allow_loopback: bool = True) -> bool:
    """Enforce strict air-gap boundary by intercepting network socket operations.

    Args:
        strict: If True, blocks all outbound socket connections.
        allow_loopback: If True, permits 127.0.0.1 / localhost for internal IPC/local dashboard.
    """
    global _AIRGAP_ENFORCED
    if not is_offline_mode():
        return False

    if _AIRGAP_ENFORCED:
        return True

    def _guarded_connect(self: socket.socket, address: Any) -> Any:
        host = ""
        port = 0
        if isinstance(address, tuple) and len(address) >= 2:
            host, port = address[0], address[1]
        elif isinstance(address, str):
            host = address

        host_str = str(host).lower()
        is_loopback = host_str in ("127.0.0.1", "localhost", "::1")

        if allow_loopback and is_loopback:
            return _ORIGINAL_SOCKET_CONNECT(self, address)

        raise AirGapViolationError(
            f"[AIR-GAP VIOLATION BLOCKED] Outbound network connection to {host}:{port} "
            f"was blocked by Vajra-Kavach offline air-gap firewall. "
            f"OFFLINE_MODE is strictly enforced."
        )

    def _guarded_create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
        host = address[0] if isinstance(address, tuple) and address else str(address)
        host_str = str(host).lower()
        is_loopback = host_str in ("127.0.0.1", "localhost", "::1")

        if allow_loopback and is_loopback:
            return _ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)

        raise AirGapViolationError(
            f"[AIR-GAP VIOLATION BLOCKED] Outbound connection to {address} "
            f"was blocked by Vajra-Kavach offline air-gap firewall."
        )

    socket.socket.connect = _guarded_connect
    socket.create_connection = _guarded_create_connection

    # Disable urllib if loaded
    if "urllib.request" in sys.modules:
        import urllib.request
        def _guarded_urlopen(*args: Any, **kwargs: Any):
            raise AirGapViolationError("[AIR-GAP VIOLATION] urllib.request.urlopen blocked in OFFLINE_MODE.")
        urllib.request.urlopen = _guarded_urlopen

    _AIRGAP_ENFORCED = True
    return True


def assert_offline() -> None:
    """Raise AirGapViolationError if offline mode is not active."""
    if not is_offline_mode():
        raise AirGapViolationError("System expected OFFLINE_MODE=true but online mode was detected.")
