"""API tests in demo mode (no Tavus key). Run: pytest backend/tests -q"""
from __future__ import annotations

import hashlib
import hmac
import json
import os

os.environ["DB_PATH"] = ":memory:"
os.environ["TAVUS_API_KEY"] = ""
os.environ["TAVUS_PAL_ID"] = ""
os.environ["TAVUS_CALLBACK_SECRET"] = "test-secret"

from fastapi.testclient import TestClient  # noqa: E402

from backend import app as app_module  # noqa: E402
from backend.app import app, store  # noqa: E402

client = TestClient(app)


def _new():
    r = client.post("/api/games", json={})
    assert r.status_code == 200
    body = r.json()
    return body["game_id"], {"X-Player-Token": body["player_token"]}


def _word(gid, index):
    return store.get(gid).rounds[index - 1].word


def test_health():
    assert client.get("/health").json() == {"ok": True, "mode": "demo"}


def test_token_required():
    gid, _ = _new()
    assert client.get(f"/api/games/{gid}").status_code == 403
    assert client.get(f"/api/games/{gid}", headers={"X-Player-Token": "nope"}).status_code == 403
    assert client.get("/api/games/missing", headers={"X-Player-Token": "x"}).status_code == 404


def test_secret_handling_round_by_round():
    gid, h = _new()
    # Round 1: player draws, the browser gets the word.
    v = client.post(f"/api/games/{gid}/start-round", headers=h).json()
    assert v["state"] == "USER_DRAW" and v["round"]["your_word"] == _word(gid, 1)
    # Demo-mode PAL guesses it correctly -> PAL wins the round.
    v = client.post(f"/api/games/{gid}/guesses", headers=h, json={"guesser": "pal", "text": _word(gid, 1)}).json()
    assert v["state"] == "REVEAL" and v["score"] == {"user": 0, "pal": 1}
    # Round 2: PAL draws. Its word must not appear anywhere in what the browser receives.
    v = client.post(f"/api/games/{gid}/start-round", headers=h).json()
    secret = _word(gid, 2)
    assert v["state"] == "PAL_DRAW" and v["round"]["your_word"] is None
    assert len(v["round"]["strokes"]) == 1  # canvas never starts blank
    raw = client.get(f"/api/games/{gid}", headers=h).text.lower()
    assert f'"{secret}"' not in raw and "label" not in raw
    # Player guesses it -> revealed.
    v = client.post(f"/api/games/{gid}/guesses", headers=h, json={"text": secret}).json()
    assert v["round"]["revealed_word"] == secret and v["score"]["user"] == 1


def test_tool_call_relay_is_idempotent():
    gid, h = _new()
    client.post(f"/api/games/{gid}/start-round", headers=h)
    ev = {"message_type": "conversation", "event_type": "conversation.tool_call", "seq": 7,
          "properties": {"name": "submit_guess", "arguments": json.dumps({"guess": "zebra"}), "tool_call_id": "call_1"}}
    first = client.post(f"/api/games/{gid}/events", headers=h, json=ev).json()
    again = client.post(f"/api/games/{gid}/events", headers=h, json=ev).json()
    assert first["handled"] and "Wrong" in first["output"]
    assert again == {"handled": False, "reason": "duplicate"}
    assert client.get(f"/api/games/{gid}", headers=h).json()["round"]["guesses_left"] == 2


def test_utterance_relay_scores_user_speech():
    gid, h = _new()
    client.post(f"/api/games/{gid}/start-round", headers=h)
    client.post(f"/api/games/{gid}/guesses", headers=h, json={"guesser": "pal", "text": "zebra"})
    client.post(f"/api/games/{gid}/guesses", headers=h, json={"guesser": "pal", "text": "rocket"})
    client.post(f"/api/games/{gid}/guesses", headers=h, json={"guesser": "pal", "text": "banana"})
    v = client.get(f"/api/games/{gid}", headers=h).json()
    assert v["state"] == "REVEAL" and v["score"] == {"user": 0, "pal": 0}  # PAL stumped -> nobody scores (guessers only)
    client.post(f"/api/games/{gid}/start-round", headers=h)
    ev = {"event_type": "conversation.utterance", "inference_id": "i1",
          "properties": {"role": "user", "speech": f"Is it a {_word(gid, 2)}?"}}
    assert client.post(f"/api/games/{gid}/events", headers=h, json=ev).json()["handled"]
    assert client.get(f"/api/games/{gid}", headers=h).json()["score"]["user"] == 1


def test_full_game_and_scoreboard():
    gid, h = _new()
    for i in range(1, 7):
        client.post(f"/api/games/{gid}/start-round", headers=h)
        who = "pal" if i % 2 == 1 else "user"
        client.post(f"/api/games/{gid}/guesses", headers=h, json={"guesser": who, "text": _word(gid, i)})
    sb = client.get(f"/api/games/{gid}/scoreboard", headers=h).json()
    assert sb["state"] == "GAME_OVER" and sb["score"] == {"user": 3, "pal": 3} and sb["result"] == "tie"
    assert len(sb["rounds"]) == 6 and len({r["word"] for r in sb["rounds"]}) == 6
    assert any(m.get("event_type") == "conversation.respond" for m in app_module.tavus.sent)


def test_play_again_avoids_last_words():
    gid, _ = _new()
    old = {r.word for r in store.get(gid).rounds}
    body = client.post("/api/games", json={"previous_game_id": gid}).json()
    assert not old & {r.word for r in store.get(body["game_id"]).rounds}


def _sign(raw: bytes) -> str:
    return hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()


def test_webhook_signature_and_dedupe():
    gid, _ = _new()
    g = store.get(gid)
    g.conversation_id = "c_test"
    store.save(g)
    raw = json.dumps({"conversation_id": "c_test", "event_type": "application.transcription_ready",
                      "timestamp": "2026-11-26T10:00:00Z",
                      "properties": {"transcript": [{"role": "user", "content": "bike!"}]}}).encode()
    assert client.post("/webhooks/tavus", content=raw).status_code == 401
    assert client.post("/webhooks/tavus", content=raw, headers={"X-Tavus-Signature": "bad"}).status_code == 401
    ok = client.post("/webhooks/tavus", content=raw, headers={"X-Tavus-Signature": _sign(raw)})
    assert ok.status_code == 200 and "transcript stored" in ok.json()["note"]
    dup = client.post("/webhooks/tavus", content=raw, headers={"X-Tavus-Signature": _sign(raw)})
    assert dup.json()["note"] == "duplicate"
    assert store.get(gid).transcript == [{"role": "user", "content": "bike!"}]


def test_garbage_events_do_not_crash():
    gid, h = _new()
    client.post(f"/api/games/{gid}/start-round", headers=h)
    assert client.post(f"/api/games/{gid}/events", headers=h, content=b"not json").status_code == 400
    for ev in [{}, {"event_type": "conversation.utterance"}, {"event_type": "conversation.utterance", "properties": {"role": "user", "speech": ""}},
               {"event_type": "conversation.tool_call", "properties": {"name": "draw_next_stroke", "arguments": "{bad json"}},
               {"event_type": "something.else"}]:
        assert client.post(f"/api/games/{gid}/events", headers=h, json=ev).status_code == 200


def test_speaking_events_measure_latency():
    gid, h = _new()
    ev = lambda kind, role, ts: {"event_type": f"conversation.{kind}_speaking", "timestamp": ts, "properties": {"role": role}}
    for e in [ev("stopped", "user", 100.0), ev("started", "pal", 101.25), ev("started", "pal", 101.25),  # duplicate ignored
              ev("stopped", "user", 110.0), ev("started", "replica", 110.5), ev("started", "pal", 110.8)]:
        assert client.post(f"/api/games/{gid}/events", headers=h, json=e).status_code == 200
    assert store.get(gid).latencies == [1.25, 0.8]
