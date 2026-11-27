"""Pip's auto-setup (setup_tavus.ensure_pal) against a fake Tavus API. Run: pytest backend/tests -q"""
from __future__ import annotations

import json

import httpx

from backend import setup_tavus as st
from backend.tools import TOOL_SPECS


class FakeTavus:
    """Just enough of /v2/pals and /v2/tools to exercise ensure_pal, recording every write."""

    def __init__(self, pals=None, tools=None, attached=None):
        self.pals = pals or {}            # pal_id -> pal JSON
        self.tools = tools or {}          # name -> tool_id
        self.attached = attached or {}    # pal_id -> [tool names]
        self.writes = []

    def handler(self, req: httpx.Request) -> httpx.Response:
        path, method = req.url.path, req.method
        body = json.loads(req.content) if req.content else None
        if method != "GET":
            self.writes.append((method, path))
        if path == "/v2/pals" and method == "GET":
            return httpx.Response(200, json={"data": list(self.pals.values())})
        if path == "/v2/pals" and method == "POST":
            pid = f"p{len(self.pals) + 1}"
            self.pals[pid] = {"pal_id": pid, **body}
            return httpx.Response(200, json={"pal_id": pid})
        if path == "/v2/tools" and method == "POST":
            if body["name"] in self.tools:
                return httpx.Response(409, json={"error": "exists"})
            self.tools[body["name"]] = f"t{len(self.tools) + 1}"
            return httpx.Response(200, json={"tool_id": self.tools[body["name"]]})
        if path == "/v2/tools" and method == "GET":
            name = req.url.params["name_or_uuid"]
            return httpx.Response(200, json={"data": [{"name": name, "tool_id": self.tools[name]}]})
        parts = path.split("/")  # /v2/pals/{id}[/tools]
        pid = parts[3]
        if len(parts) == 4 and method == "GET":
            return httpx.Response(200, json=self.pals[pid]) if pid in self.pals else httpx.Response(404, json={})
        if len(parts) == 4 and method == "PATCH":
            for op in body:
                if op["path"] == "/system_prompt":
                    self.pals[pid]["system_prompt"] = op["value"]
            return httpx.Response(200, json={})
        if parts[-1] == "tools" and method == "GET":
            names = self.attached.get(pid, [])
            return httpx.Response(200, json={"data": [{"name": n, "tool_id": self.tools.get(n, "x")} for n in names]})
        if parts[-1] == "tools" and method == "POST":
            ids = set(body["tool_ids"])
            self.attached[pid] = [n for n, t in self.tools.items() if t in ids]
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404, json={})

    def client(self) -> httpx.Client:
        return httpx.Client(base_url=st.BASE, transport=httpx.MockTransport(self.handler))


def _in_sync_pal(pid: str) -> dict:
    return {"pal_id": pid, "pal_name": st.PAL_FULL_NAME, "system_prompt": st.SYSTEM_PROMPT,
            "layers": {"perception": st.PERCEPTION, "stt": st.STT, "conversational_flow": st.CONVERSATIONAL_FLOW}}


def test_fresh_account_creates_pip_with_its_tools():
    fake = FakeTavus()
    pid = st.ensure_pal(fake.client(), None, "face1", log=lambda m: None)
    assert pid in fake.pals and fake.pals[pid]["pal_name"] == st.PAL_FULL_NAME
    assert sorted(fake.attached[pid]) == sorted(t["name"] for t in TOOL_SPECS)


def test_up_to_date_pip_is_left_alone():
    names = [t["name"] for t in TOOL_SPECS]
    fake = FakeTavus(pals={"p9": _in_sync_pal("p9")}, tools={n: f"t{i}" for i, n in enumerate(names)}, attached={"p9": names})
    assert st.ensure_pal(fake.client(), "p9", "face1", log=lambda m: None) == "p9"
    assert fake.writes == []  # no PATCH, no POST: nothing changed on Tavus


def test_changed_prompt_is_patched_in_place_and_found_by_name():
    names = [t["name"] for t in TOOL_SPECS]
    old = _in_sync_pal("p9") | {"system_prompt": "an older prompt"}
    fake = FakeTavus(pals={"p9": old}, tools={n: f"t{i}" for i, n in enumerate(names)}, attached={"p9": names})
    assert st.ensure_pal(fake.client(), None, "face1", log=lambda m: None) == "p9"  # no TAVUS_PAL_ID: found by name
    assert ("PATCH", "/v2/pals/p9") in fake.writes and fake.pals["p9"]["system_prompt"] == st.SYSTEM_PROMPT
