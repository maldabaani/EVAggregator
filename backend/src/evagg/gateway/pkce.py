"""PKCE (RFC 7636) helpers for the mobile app's Authorization Code + PKCE flow.

Only the S256 challenge method is supported — `plain` is intentionally not
implemented since it defeats the purpose of PKCE on a public client.
"""

from __future__ import annotations

import base64
import hashlib
import hmac


def compute_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def verify_code_verifier(code_verifier: str, code_challenge: str) -> bool:
    expected = compute_code_challenge(code_verifier)
    return hmac.compare_digest(expected, code_challenge)
