"""Tavus conversation callbacks -> POST /webhooks/tavus.

Tavus webhooks are lifecycle and post-call only (system.pal_joined, system.shutdown,
application.transcription_ready, application.perception_analysis). Live speech and tool
calls do NOT come here; they arrive in the browser over Daily (see tools.py).

Security: X-Tavus-Signature = hex HMAC-SHA256 of the raw body with TAVUS_CALLBACK_SECRET.
Verified before parsing. Unsigned or mismatched requests get 401. Signing has no replay
protection, so each event is deduplicated on (conversation_id, event_type, timestamp).
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any, Dict, Optional

from backend.game import Game


def verify_signature(raw_body: bytes, supplied: Optional[str], secret: str) -> bool:
    if not secret or not supplied:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied.strip().lower())


def dedupe_key(payload: Dict[str, Any]) -> str:
    return f"wh:{payload.get('conversation_id')}:{payload.get('event_type')}:{payload.get('timestamp')}"


def apply(g: Game, payload: Dict[str, Any]) -> str:
    """Apply one callback to the game. Returns what happened (for logs)."""
    event = payload.get("event_type", "")
    props = payload.get("properties") or {}
    if event in ("system.shutdown",):
        g.conversation_ended = True
        return "conversation ended"
    if event == "application.transcription_ready":
        g.transcript = props.get("transcript") or []
        return f"transcript stored ({len(g.transcript)} turns)"
    if event in ("system.pal_joined", "system.replica_joined"):
        return "pal joined"
    return f"ignored {event}"
