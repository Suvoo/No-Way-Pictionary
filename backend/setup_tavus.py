"""Tavus setup for Pip: create it once, then update it in place after prompt, settings or tool changes.

    python -m backend.setup_tavus              # create the tool + PAL, prints TAVUS_PAL_ID
    python -m backend.setup_tavus --update     # update the PAL in TAVUS_PAL_ID in place (same id)
    python -m backend.setup_tavus --dry-run    # print the JSON it would send, no API calls

Needs TAVUS_API_KEY in .env. Optional TAVUS_FACE_ID (a stock face from the Face Library;
defaults to the stock face used in the Tavus docs).

What lives on the PAL (changes here need --update): the system prompt, Raven-2 perception,
speech-to-text hotwords, turn-taking settings and the attached tool. What does NOT (changes take
effect on the next game, no update needed): the greeting and every round's context, which the
backend sends per conversation (see prompts.py).
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

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


def pal_body(face_id: str) -> Dict[str, Any]:
    return {
        "pal_name": f"{PAL_NAME} - Doodle with Pip",
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


def _ensure_tools(h: Dict[str, str]) -> List[str]:
    ids: List[str] = []
    for body in _tool_bodies():
        r = httpx.post(f"{BASE}/v2/tools", json=body, headers=h, timeout=30)
        if r.status_code == 409:  # already exists: reuse it
            found = httpx.get(f"{BASE}/v2/tools", params={"name_or_uuid": body["name"]}, headers=h, timeout=30).json()
            match = [t for t in found.get("data", []) if t.get("name") == body["name"]]
            if not match:
                raise SystemExit(f"tool {body['name']} exists but could not be found: {found}")
            ids.append(match[0]["tool_id"])
            print(f"reusing tool {body['name']}: {ids[-1]}")
            continue
        if r.status_code != 200:
            raise SystemExit(f"create tool {body['name']} failed: {r.status_code} {r.text}")
        ids.append(r.json()["tool_id"])
        print(f"created tool {body['name']}: {ids[-1]}")
    return ids


def create(h: Dict[str, str], face_id: str) -> int:
    tool_ids = _ensure_tools(h)
    r = httpx.post(f"{BASE}/v2/pals", json=pal_body(face_id), headers=h, timeout=30)
    if r.status_code != 200:
        print(f"create PAL failed: {r.status_code} {r.text}", file=sys.stderr)
        return 1
    pal_id = r.json().get("pal_id")
    print(f"created PAL: {pal_id}")
    r = httpx.post(f"{BASE}/v2/pals/{pal_id}/tools", json={"tool_ids": tool_ids}, headers=h, timeout=30)
    if r.status_code != 200:
        print(f"attach tools failed: {r.status_code} {r.text}", file=sys.stderr)
        return 1
    print("attached tools")
    print(f"\nAdd this to .env:\nTAVUS_PAL_ID={pal_id}")
    return 0


def update(h: Dict[str, str], pal_id: str) -> int:
    r = httpx.patch(f"{BASE}/v2/pals/{pal_id}", json=pal_patch(), headers=h, timeout=30)
    if r.status_code not in (200, 204, 304):
        print(f"patch PAL failed: {r.status_code} {r.text}", file=sys.stderr)
        return 1
    print(f"updated PAL {pal_id}: system prompt, perception, speech-to-text hotwords, turn-taking")

    attached = httpx.get(f"{BASE}/v2/pals/{pal_id}/tools", headers=h, timeout=30).json().get("data", [])
    for t in attached:
        if t.get("name") in RETIRED_TOOLS:
            d = httpx.delete(f"{BASE}/v2/pals/{pal_id}/tools/{t['tool_id']}", headers=h, timeout=30)
            print(f"detached retired tool {t['name']}: {d.status_code}")
    wanted = _ensure_tools(h)
    r = httpx.post(f"{BASE}/v2/pals/{pal_id}/tools", json={"tool_ids": wanted}, headers=h, timeout=30)
    print(f"tools attached: {[t.get('name') for t in r.json().get('data', [])] if r.status_code == 200 else r.text}")
    return 0


def main(argv: List[str]) -> int:
    load_dotenv()
    face_id = os.getenv("TAVUS_FACE_ID") or DEFAULT_FACE_ID
    if "--dry-run" in argv:
        print(json.dumps({"tools": _tool_bodies(), "pal": pal_body(face_id), "update_patch": pal_patch()}, indent=2))
        return 0
    key = os.getenv("TAVUS_API_KEY")
    if not key:
        print("Set TAVUS_API_KEY in .env first.", file=sys.stderr)
        return 1
    h = {"x-api-key": key}
    if "--update" in argv:
        pal_id = os.getenv("TAVUS_PAL_ID")
        if not pal_id:
            print("Set TAVUS_PAL_ID in .env first (or run without --update to create a PAL).", file=sys.stderr)
            return 1
        return update(h, pal_id)
    return create(h, face_id)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
