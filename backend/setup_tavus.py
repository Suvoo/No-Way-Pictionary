"""Pip on Tavus, defined in code. The server runs ensure_pal() on every startup (app.py), so nobody has
to create or update the PAL by hand: set TAVUS_API_KEY and start the app.

    python -m backend.setup_tavus              # do the same by hand: find or create Pip, sync it to the code
    python -m backend.setup_tavus --update     # same thing (kept for old instructions)
    python -m backend.setup_tavus --dry-run    # print the JSON it would send, no API calls

What lives on the PAL: the system prompt, Raven-2 perception, speech-to-text hotwords, turn-taking
settings and the tools. What does NOT (sent per conversation by the backend): the greeting and every
round's context (prompts.py).
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

from backend.prompts import PAL_NAME, SYSTEM_PROMPT
from backend.tools import RETIRED_TOOLS, TOOL_SPECS
from backend.words import V1_WORDS

BASE = "https://tavusapi.com"
DEFAULT_FACE_ID = "r4b03c679d42"  # stock face from the Tavus docs examples

PERCEPTION: Dict[str, Any] = {
    "perception_model": "raven-2",
    "visual_awareness_queries": [
        "What object is drawn on the paper the user is holding up to the camera?",
        "Is the user holding up a paper with a drawing, and is it clear enough to read?",
        "Are there written letters or words on the paper instead of a drawing?",
    ],
    "callouts": "on",
}

# Live finding: "snowman" was transcribed as "slow man", "want" as "won't". Hotwords bias speech-to-text
# toward the words this game actually uses.
STT: Dict[str, Any] = {
    "stt_engine": "tavus-auto",
    "hotwords": (
        f"This is a Pictionary game with {PAL_NAME}. The player shouts short guesses such as "
        + ", ".join(V1_WORDS)
        + ", and says commands like let's start, ready, go, next round, skip, hint."
    ),
}

# Live findings: game 2 (patience "medium") the PAL replied while the player was mid-sentence; game 3
# (patience "high") every reply felt late. Back to "medium" for speed; high interruptibility stays, so the
# PAL stops the moment the player starts talking (they often shout guesses over it).
CONVERSATIONAL_FLOW: Dict[str, Any] = {
    "turn_detection_model": "sparrow-2",
    "turn_taking_patience": "medium",
    "pal_interruptibility": "high",
}


PAL_FULL_NAME = f"{PAL_NAME} - Doodle with Pip"  # how ensure_pal finds Pip on an account without TAVUS_PAL_ID


def pal_body(face_id: str) -> Dict[str, Any]:
    return {
        "pal_name": PAL_FULL_NAME,
        "system_prompt": SYSTEM_PROMPT,
        "default_face_id": face_id,
        "layers": {"perception": PERCEPTION, "stt": STT, "conversational_flow": CONVERSATIONAL_FLOW},
    }


def pal_patch() -> List[Dict[str, Any]]:
    """JSON Patch for --update. 'add' on an existing object member replaces it (RFC 6902)."""
    return [
        {"op": "replace", "path": "/system_prompt", "value": SYSTEM_PROMPT},
        {"op": "add", "path": "/layers/perception", "value": PERCEPTION},
        {"op": "add", "path": "/layers/stt", "value": STT},
        {"op": "add", "path": "/layers/conversational_flow", "value": CONVERSATIONAL_FLOW},
    ]


def _tool_bodies() -> List[Dict[str, Any]]:
    """LLM tools default to origin "llm"; perception tools (origin "vision") must omit on_call/on_resolve."""
    bodies = []
    for t in TOOL_SPECS:
        body = {"trigger_type": "in_call", "delivery": {"app_message": True}, "origin": "llm", **t}
        if body["origin"] != "llm":
            body.pop("on_call", None)
            body.pop("on_resolve", None)
        bodies.append(body)
    return bodies


class SetupError(Exception):
    pass


def _client(api_key: str) -> httpx.Client:
    return httpx.Client(base_url=BASE, headers={"x-api-key": api_key}, timeout=30)


def _ensure_tools(c: httpx.Client, log=print) -> List[str]:
    """Create each tool, or reuse the one with that name (tool names are unique per account)."""
    ids: List[str] = []
    for body in _tool_bodies():
        r = c.post("/v2/tools", json=body)
        if r.status_code == 409:  # already exists: reuse it
            found = c.get("/v2/tools", params={"name_or_uuid": body["name"]}).json()
            match = [t for t in found.get("data", []) if t.get("name") == body["name"]]
            if not match:
                raise SetupError(f"tool {body['name']} exists but could not be found")
            ids.append(match[0]["tool_id"])
            continue
        if r.status_code != 200:
            raise SetupError(f"create tool {body['name']} failed: {r.status_code} {r.text[:200]}")
        ids.append(r.json()["tool_id"])
        log(f"created tool {body['name']}: {ids[-1]}")
    return ids


def _find_pal_by_name(c: httpx.Client, name: str) -> Optional[str]:
    for page in range(1, 21):
        r = c.get("/v2/pals", params={"pal_type": "user", "limit": 100, "page": page})
        if r.status_code != 200:
            return None
        data = r.json().get("data", [])
        for p in data:
            if p.get("pal_name") == name:
                return p.get("pal_id")
        if len(data) < 100:
            return None
    return None


def _in_sync(pal: Dict[str, Any]) -> bool:
    """Does the PAL on Tavus already match the code? Then nothing needs patching."""
    layers = pal.get("layers") or {}
    stt, flow, perc = layers.get("stt") or {}, layers.get("conversational_flow") or {}, layers.get("perception") or {}
    return (
        pal.get("system_prompt") == SYSTEM_PROMPT
        and stt.get("hotwords") == STT["hotwords"]
        and all(flow.get(k) == v for k, v in CONVERSATIONAL_FLOW.items())
        and perc.get("perception_model") == PERCEPTION["perception_model"]
        and perc.get("visual_awareness_queries") == PERCEPTION["visual_awareness_queries"]
    )


def _sync_tools(c: httpx.Client, pal_id: str, log=print) -> None:
    attached = c.get(f"/v2/pals/{pal_id}/tools").json().get("data", [])
    names = {t.get("name") for t in attached}
    for t in attached:
        if t.get("name") in RETIRED_TOOLS:
            c.delete(f"/v2/pals/{pal_id}/tools/{t['tool_id']}")
            log(f"detached retired tool {t['name']}")
    if all(t["name"] in names for t in TOOL_SPECS):
        return
    r = c.post(f"/v2/pals/{pal_id}/tools", json={"tool_ids": _ensure_tools(c, log)})
    if r.status_code != 200:
        raise SetupError(f"attach tools failed: {r.status_code} {r.text[:200]}")
    log("attached tools")


def ensure_pal(c: httpx.Client, pal_id: Optional[str], face_id: str, log=print) -> str:
    """Make Pip exist on Tavus and match this code; return its id. Idempotent, safe on every boot.

    1. Use TAVUS_PAL_ID if it exists on the account; else find the PAL named PAL_FULL_NAME; else create it.
    2. If its prompt or settings differ from the code, patch it in place (same id).
    3. Make sure its tools are attached (and retired tools detached).
    """
    pal: Optional[Dict[str, Any]] = None
    if pal_id:
        r = c.get(f"/v2/pals/{pal_id}")
        if r.status_code == 200:
            pal = r.json()
        else:
            log(f"TAVUS_PAL_ID {pal_id} not found on this account ({r.status_code}); looking for Pip by name")
            pal_id = None
    if not pal_id:
        pal_id = _find_pal_by_name(c, PAL_FULL_NAME)
        if pal_id:
            log(f"found existing Pip: {pal_id}")
            pal = c.get(f"/v2/pals/{pal_id}").json()
    if not pal_id:
        tool_ids = _ensure_tools(c, log)
        r = c.post("/v2/pals", json=pal_body(face_id))
        if r.status_code != 200:
            raise SetupError(f"create PAL failed: {r.status_code} {r.text[:200]}")
        pal_id = r.json()["pal_id"]
        log(f"created Pip: {pal_id}")
        r = c.post(f"/v2/pals/{pal_id}/tools", json={"tool_ids": tool_ids})
        if r.status_code != 200:
            raise SetupError(f"attach tools failed: {r.status_code} {r.text[:200]}")
        return pal_id
    if pal is not None and not _in_sync(pal):
        r = c.patch(f"/v2/pals/{pal_id}", json=pal_patch())
        if r.status_code not in (200, 204, 304):
            raise SetupError(f"update PAL failed: {r.status_code} {r.text[:200]}")
        log(f"updated Pip {pal_id} to match the code (prompt, perception, hotwords, turn-taking)")
    _sync_tools(c, pal_id, log)
    return pal_id


def main(argv: List[str]) -> int:
    """Manual use; the server already does this on startup (app.py). Kept for scripts and debugging."""
    load_dotenv()
    face_id = os.getenv("TAVUS_FACE_ID") or DEFAULT_FACE_ID
    if "--dry-run" in argv:
        print(json.dumps({"tools": _tool_bodies(), "pal": pal_body(face_id), "update_patch": pal_patch()}, indent=2))
        return 0
    key = os.getenv("TAVUS_API_KEY")
    if not key:
        print("Set TAVUS_API_KEY in .env first.", file=sys.stderr)
        return 1
    try:
        pal_id = ensure_pal(_client(key), os.getenv("TAVUS_PAL_ID"), face_id)
    except SetupError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"Pip is ready: {pal_id}  (optional: TAVUS_PAL_ID={pal_id} in .env)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
