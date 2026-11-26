"""One-time Tavus setup: creates the two tools and the PAL, prints TAVUS_PAL_ID.

    python -m backend.setup_tavus              # create tools + PAL
    python -m backend.setup_tavus --dry-run    # print the JSON it would send, no API calls

Needs TAVUS_API_KEY in .env. Optional TAVUS_FACE_ID (a stock face from the Face Library;
defaults to the stock face used in the Tavus docs). Re-running reuses existing tools by
name and creates a new PAL; put the printed id in .env as TAVUS_PAL_ID.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

import httpx
from dotenv import load_dotenv

from backend.prompts import PAL_NAME, SYSTEM_PROMPT
from backend.tools import TOOL_SPECS

BASE = "https://tavusapi.com"
DEFAULT_FACE_ID = "r4b03c679d42"  # stock face from the Tavus docs examples


def pal_body(face_id: str) -> Dict[str, Any]:
    return {
        "pal_name": f"{PAL_NAME} - Reverse Pictionary",
        "system_prompt": SYSTEM_PROMPT,
        "default_face_id": face_id,
        "layers": {
            "perception": {
                "perception_model": "raven-2",
                "visual_awareness_queries": [
                    "What object is drawn on the paper the user is holding up to the camera?",
                    "Is the user holding up a paper with a drawing, and is it clear enough to read?",
                    "Are there written letters or words on the paper instead of a drawing?",
                ],
                "callouts": "on",
            }
        },
    }


def main(argv: List[str]) -> int:
    load_dotenv()
    face_id = os.getenv("TAVUS_FACE_ID") or DEFAULT_FACE_ID
    tool_bodies = [{**t, "trigger_type": "in_call", "origin": "llm", "delivery": {"app_message": True}} for t in TOOL_SPECS]
    if "--dry-run" in argv:
        print(json.dumps({"tools": tool_bodies, "pal": pal_body(face_id)}, indent=2))
        return 0
    key = os.getenv("TAVUS_API_KEY")
    if not key:
        print("Set TAVUS_API_KEY in .env first.", file=sys.stderr)
        return 1
    h = {"x-api-key": key}

    tool_ids: List[str] = []
    for body in tool_bodies:
        r = httpx.post(f"{BASE}/v2/tools", json=body, headers=h, timeout=30)
        if r.status_code == 409:  # already exists: reuse it
            found = httpx.get(f"{BASE}/v2/tools", params={"name_or_uuid": body["name"]}, headers=h, timeout=30).json()
            match = [t for t in found.get("data", []) if t.get("name") == body["name"]]
            if not match:
                print(f"tool {body['name']} exists but could not be found: {found}", file=sys.stderr)
                return 1
            tool_ids.append(match[0]["tool_id"])
            print(f"reusing tool {body['name']}: {match[0]['tool_id']}")
            continue
        if r.status_code != 200:
            print(f"create tool {body['name']} failed: {r.status_code} {r.text}", file=sys.stderr)
            return 1
        tool_ids.append(r.json()["tool_id"])
        print(f"created tool {body['name']}: {tool_ids[-1]}")

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


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
