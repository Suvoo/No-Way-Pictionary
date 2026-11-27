"""The only module that talks to the Tavus API. Field names verified against
https://docs.tavus.io/openapi.yaml on Nov 26 2026.

If TAVUS_API_KEY or TAVUS_PAL_ID is missing, the client runs in DEMO MODE: no video call,
effects are logged instead of sent, and the game is played with typed guesses. That keeps
the repo runnable (and testable) with zero credentials.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Dict, List, Optional

import httpx

from backend.game import Effect

log = logging.getLogger("tavus")
BASE_URL = "https://tavusapi.com"


class TavusError(Exception):
    pass


class TavusClient:
    def __init__(self, api_key: str = "", pal_id: str = "", face_id: str = "", base_url: str = BASE_URL):
        self.api_key, self.pal_id, self.face_id, self.base_url = api_key, pal_id, face_id, base_url
        self.enabled = bool(api_key and pal_id)
        self.sent: List[Dict[str, Any]] = []  # demo mode: what would have been sent (debug only)
        # One pooled keep-alive client. Live finding: a new connection per call cost ~0.8s per message
        # (TLS handshake each time), and a round start sends two messages back to back.
        self.http = httpx.Client(base_url=base_url, headers={"x-api-key": api_key}, timeout=15)

    def _post(self, path: str, body: Optional[Dict[str, Any]] = None, retries: int = 3) -> httpx.Response:
        last: Optional[httpx.Response] = None
        for attempt in range(retries):
            try:
                started = time.monotonic()
                resp = self.http.post(path, json=body or {})
                log.debug("tavus %s %s in %.2fs", path, resp.status_code, time.monotonic() - started)
            except httpx.HTTPError as e:
                log.warning("tavus %s network error (attempt %d): %s", path, attempt + 1, e)
                time.sleep(0.5 * 2 ** attempt)
                continue
            if resp.status_code in (429, 502, 503) and attempt < retries - 1:
                time.sleep(float(resp.headers.get("Retry-After", 0.5 * 2 ** attempt)))
                last = resp
                continue
            return resp
        if last is not None:
            return last
        raise TavusError(f"Tavus unreachable: {path}")

    def create_conversation(self, context: str, greeting: str, callback_url: str = "",
                            callback_secret: str = "", name: str = "Doodle with Pip") -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "pal_id": self.pal_id,
            "conversation_name": name,
            "conversational_context": context,
            "custom_greeting": greeting,
            "properties": {
                "max_call_duration": 1200,  # 20 min hard cap; a full game is ~7 min
                "participant_left_timeout": 30,
                "participant_absent_timeout": 180,
            },
        }
        if self.face_id:
            body["face_id"] = self.face_id
        if callback_url:
            body["callback_url"] = callback_url
            if callback_secret:
                body["callback_secret"] = callback_secret
        resp = self._post("/v2/conversations", body, retries=1)
        if resp.status_code != 200:
            raise TavusError(f"create conversation failed ({resp.status_code}): {resp.text[:300]}")
        return resp.json()

    def send_app_message(self, conversation_id: str, event_type: str, properties: Dict[str, Any]) -> None:
        body = {"message_type": "conversation", "event_type": event_type, "properties": properties}
        if not self.enabled:
            self.sent.append({"conversation_id": conversation_id, **body})
            log.info("[demo] would send %s: %s", event_type, str(properties)[:160])
            return
        resp = self._post(f"/v2/conversations/{conversation_id}/send-app-message", body)
        if resp.status_code != 200:
            log.error("send-app-message %s failed (%s): %s", event_type, resp.status_code, resp.text[:200])
        else:  # server-side log only; may contain the PAL's secret word for its own round
            log.info("-> PAL %s %s: %s", conversation_id, event_type, str(properties)[:200])

    def end_conversation(self, conversation_id: str) -> None:
        if not self.enabled:
            self.sent.append({"conversation_id": conversation_id, "event_type": "end"})
            return
        resp = self._post(f"/v2/conversations/{conversation_id}/end", retries=2)
        if resp.status_code != 200:
            log.error("end conversation failed (%s): %s", resp.status_code, resp.text[:200])


class EffectDispatcher:
    """Sends game effects to Tavus in order, off the request thread.
    One worker thread = messages reach the PAL in the order the game produced them."""

    def __init__(self, client: TavusClient):
        self.client = client
        self.q: "queue.Queue[tuple]" = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()

    def dispatch(self, conversation_id: Optional[str], effects: List[Effect]) -> None:
        if not effects:
            return
        for e in effects:
            if e["kind"] == "end_conversation" and e.get("delay"):
                threading.Timer(e["delay"], self.q.put, args=((conversation_id, e),)).start()
            else:
                self.q.put((conversation_id, e))

    def _worker(self) -> None:
        while True:
            conversation_id, e = self.q.get()
            try:
                self._send(conversation_id, e)
            except Exception:  # never let one bad message kill the worker
                log.exception("effect failed: %s", e.get("kind"))

    def _send(self, cid: Optional[str], e: Effect) -> None:
        if not cid and self.client.enabled:
            return
        cid = cid or "demo"
        kind = e["kind"]
        if kind == "context":
            self.client.send_app_message(cid, "conversation.overwrite_llm_context", {"context": e["text"]})
        elif kind == "append_context":
            self.client.send_app_message(cid, "conversation.append_llm_context", {"context": e["text"]})
        elif kind == "say":  # the PAL answers this in its own words (an LLM turn)
            self.client.send_app_message(cid, "conversation.respond", {"text": e["text"]})
        elif kind == "speak":  # the PAL says exactly this text, word for word
            self.client.send_app_message(cid, "conversation.echo", {"modality": "text", "text": e["text"], "done": True})
        elif kind == "tool_result":
            self.client.send_app_message(cid, "conversation.tool_result",
                                         {"tool_call_id": e["tool_call_id"], "output": e["output"], "status": "success"})
        elif kind == "end_conversation":
            self.client.end_conversation(cid)
