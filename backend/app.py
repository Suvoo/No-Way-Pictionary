"""FastAPI entry point: routes only. Game rules live in game.py, Tavus calls in tavus.py.

Run locally:  uvicorn backend.app:app --reload --port 8000
Every /api/games/{id}/... route needs the X-Player-Token header returned by POST /api/games.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import game, prompts, tools, webhooks
from backend.store import Store
from backend.tavus import EffectDispatcher, TavusClient, TavusError

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

CALLBACK_SECRET = os.getenv("TAVUS_CALLBACK_SECRET", "")
# The deployed https URL, for webhooks. Render sets RENDER_EXTERNAL_URL itself, so there it needs no config.
PUBLIC_URL = (os.getenv("PUBLIC_URL") or os.getenv("RENDER_EXTERNAL_URL", "")).rstrip("/")
store = Store(os.getenv("DB_PATH", "data/pictionary.db"))
tavus = TavusClient(os.getenv("TAVUS_API_KEY", ""), os.getenv("TAVUS_PAL_ID", ""), os.getenv("TAVUS_FACE_ID", ""))
dispatcher = EffectDispatcher(tavus)


async def _ticker() -> None:
    """Round timers and auto-strokes. Runs every second for games with an active round."""
    while True:
        await asyncio.sleep(1)
        for gid in store.active_ids():
            try:
                with store.transaction(gid) as g:
                    now = time.time()
                    effects = game.route_effects(g, game.tick(g, now), now) if g else []
                if g:
                    dispatcher.dispatch(g.conversation_id, effects)
            except Exception:
                log.exception("tick failed for %s", gid)


def setup_pip() -> None:
    """With a Tavus key, make sure Pip exists on the account and matches the code, then go live.
    Creates Pip on a fresh account, finds it by name if TAVUS_PAL_ID is unset, and patches it only when
    the prompt or settings changed. TAVUS_AUTO_SETUP=0 skips this and uses TAVUS_PAL_ID as-is."""
    if not tavus.api_key:
        return
    if os.getenv("TAVUS_AUTO_SETUP", "1") == "0":
        return
    from backend import setup_tavus  # imported here: only needed with a key
    try:
        pal_id = setup_tavus.ensure_pal(
            setup_tavus._client(tavus.api_key), tavus.pal_id or None,
            os.getenv("TAVUS_FACE_ID") or setup_tavus.DEFAULT_FACE_ID, log=lambda m: log.info("pip setup: %s", m))
    except Exception as e:  # never block the app: fall back to TAVUS_PAL_ID or demo mode
        log.error("pip setup failed (%s); using TAVUS_PAL_ID as-is", e)
        return
    tavus.pal_id, tavus.enabled = pal_id, True
    log.info("pip ready: %s", pal_id)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await asyncio.to_thread(setup_pip)
    task = asyncio.create_task(_ticker())
    log.info("mode: %s", "LIVE (Tavus)" if tavus.enabled else "DEMO (no TAVUS_API_KEY)")
    yield
    task.cancel()


app = FastAPI(title="Doodle with Pip", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------- helpers

def _mutate(game_id: str, token: Optional[str], fn) -> Any:
    """Load the game, check the player token, run fn(g, now) -> (result, effects), save, send effects."""
    now = time.time()
    with store.transaction(game_id) as g:
        if g is None:
            raise HTTPException(404, "game not found")
        if token != g.player_token:
            raise HTTPException(403, "bad or missing X-Player-Token")
        effects = game.tick(g, now)
        try:
            result, more = fn(g, now)
        except game.GameError as e:
            raise HTTPException(409, str(e))
        effects = game.route_effects(g, effects + more, now)
    dispatcher.dispatch(g.conversation_id, effects)
    return result


def _view(g: game.Game, now: float) -> Dict[str, Any]:
    return game.public_view(g, now)


# ---------------------------------------------------------------- routes

@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "mode": "live" if tavus.enabled else "demo"}


@app.get("/api/config")
def config() -> Dict[str, Any]:
    return {"mode": "live" if tavus.enabled else "demo", "rounds": game.ROUNDS,
            "round_seconds": game.ROUND_SECONDS, "max_guesses": game.MAX_GUESSES, "pal_name": prompts.PAL_NAME}


class NewGame(BaseModel):
    previous_game_id: Optional[str] = None  # Play Again: avoid repeating last game's words


@app.post("/api/games")
def create_game(body: NewGame = NewGame()) -> Dict[str, Any]:
    exclude: List[str] = []
    if body.previous_game_id:
        prev = store.get(body.previous_game_id)
        exclude = [r.word for r in prev.rounds] if prev else []
    now = time.time()
    g = game.new_game(now, rng=random.Random(), exclude=exclude, mock=not tavus.enabled)
    if tavus.enabled:
        try:
            conv = tavus.create_conversation(
                context=prompts.LOBBY_CONTEXT, greeting=prompts.GREETING,
                callback_url=f"{PUBLIC_URL}/webhooks/tavus" if PUBLIC_URL and CALLBACK_SECRET else "",
                callback_secret=CALLBACK_SECRET, name=f"Doodle with Pip {g.id}")
        except TavusError as e:
            log.error("%s", e)
            raise HTTPException(502, "Could not start the video call. The Tavus account may be out of minutes or at its concurrent call limit.")
        g.conversation_id, g.conversation_url = conv.get("conversation_id"), conv.get("conversation_url")
    store.save(g)
    log.info("game %s created (conversation %s)", g.id, g.conversation_id)
    return {"game_id": g.id, "player_token": g.player_token, "conversation_id": g.conversation_id,
            "conversation_url": g.conversation_url, "mode": "demo" if g.mock else "live",
            "rounds": game.ROUNDS, "round_duration_sec": game.ROUND_SECONDS, "pal_name": prompts.PAL_NAME}


@app.get("/api/games/{game_id}")
def get_game(game_id: str, x_player_token: Optional[str] = Header(None)) -> Dict[str, Any]:
    return _mutate(game_id, x_player_token, lambda g, now: (_view(g, now), []))


@app.post("/api/games/{game_id}/start-round")
def start_round(game_id: str, x_player_token: Optional[str] = Header(None)) -> Dict[str, Any]:
    return _mutate(game_id, x_player_token, lambda g, now: (lambda fx: (_view(g, now), fx))(game.start_round(g, now)))


@app.post("/api/games/{game_id}/look")
def look(game_id: str, x_player_token: Optional[str] = Header(None)) -> Dict[str, Any]:
    return _mutate(game_id, x_player_token, lambda g, now: ({"ok": g.state == "USER_DRAW"}, game.look_now(g, now)))


@app.post("/api/games/{game_id}/hint")
def hint(game_id: str, x_player_token: Optional[str] = Header(None)) -> Dict[str, Any]:
    def fn(g: game.Game, now: float):
        text, fx = game.request_hint(g, now)
        if text is None:
            raise HTTPException(409, "no hint available yet")
        return {"hint": text}, fx
    return _mutate(game_id, x_player_token, fn)


@app.post("/api/games/{game_id}/next-stroke")
def next_stroke(game_id: str, x_player_token: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Player's "Skip, draw more" button (same as saying "skip")."""
    def fn(g: game.Game, now: float):
        label, fx = game.draw_next_stroke(g, now, by="player_skip")
        if label:
            fx = fx + [{"kind": "append_context", "text": f"[game] The player asked for another line. Stroke {g.round().strokes_drawn} appeared: {label}."}]
        return _view(g, now), fx
    return _mutate(game_id, x_player_token, fn)


class TypedGuess(BaseModel):
    text: str
    guesser: str = "user"  # "pal" only allowed in demo mode, to simulate the PAL


@app.post("/api/games/{game_id}/guesses")
def typed_guess(game_id: str, body: TypedGuess, x_player_token: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Typed fallback for noisy rooms / accessibility, and the demo-mode PAL simulator."""
    def fn(g: game.Game, now: float):
        if body.guesser == "pal":
            if not g.mock:
                raise HTTPException(403, "the PAL guesses by itself in live mode")
            if game.scorer.extract_pal_guesses(body.text) or game.scorer.is_unsure(body.text):
                fx = game.handle_pal_speech(g, body.text, now)  # full sentence, parsed like live speech
            else:  # a bare word typed into the simulator
                _, fx = game.record_guess(g, "pal", body.text, game.scorer.strip_fillers(body.text) or None, now, "mock")
            return _view(g, now), fx
        if g.state != "PAL_DRAW":
            raise HTTPException(409, "you can only guess while the PAL is drawing")
        _, fx = game.record_guess(g, "user", body.text, game.scorer.strip_fillers(body.text) or None, now, "typed")
        return _view(g, now), fx
    return _mutate(game_id, x_player_token, fn)


@app.post("/api/games/{game_id}/events")
async def cvi_event(game_id: str, request: Request, x_player_token: Optional[str] = Header(None)) -> Dict[str, Any]:
    """The browser relays Tavus app-messages here: conversation.utterance and conversation.tool_call.
    Idempotent: the same event relayed twice is handled once."""
    try:
        ev = await request.json()
    except ValueError:
        raise HTTPException(400, "body must be JSON")
    if not isinstance(ev, dict):
        raise HTTPException(400, "body must be a JSON object")
    event_type = ev.get("event_type")
    props = ev.get("properties") or {}
    if event_type == "conversation.utterance":
        speech = str(props.get("speech", ""))
        if speech.startswith("[game]"):
            log.info("<- (echo of our own [game] message, ignored)")
        else:
            log.info("<- %s said: %s", props.get("role"), speech[:200])
    elif event_type == "conversation.tool_call":
        log.info("<- PAL tool %s(%s)", props.get("name"), str(props.get("arguments", ""))[:120])

    def fn(g: game.Game, now: float):
        if ev.get("conversation_id") and g.conversation_id and ev["conversation_id"] != g.conversation_id:
            raise HTTPException(409, "event is for a different conversation")
        if event_type == "conversation.utterance":
            role, speech = props.get("role"), (props.get("speech") or "").strip()
            if role not in ("user", "pal") or not speech:  # "replica" is a legacy duplicate of "pal"
                return {"handled": False, "reason": "ignored role or empty speech"}, []
            key = f"utt:{ev.get('inference_id') or ev.get('seq')}:{role}:{hashlib.sha1(speech.encode()).hexdigest()[:12]}"
            if g.seen(key):
                return {"handled": False, "reason": "duplicate"}, []
            fx = game.handle_user_speech(g, speech, now) if role == "user" else game.handle_pal_speech(g, speech, now)
            return {"handled": True}, fx
        if event_type == "conversation.tool_call":
            call_id = props.get("tool_call_id") or f"seq{ev.get('seq')}"
            if g.seen(f"tool:{call_id}"):
                return {"handled": False, "reason": "duplicate"}, []
            output, fx = tools.handle_tool_call(g, props.get("name", ""), props.get("arguments"), call_id, now)
            fx = [{"kind": "tool_result", "tool_call_id": call_id, "output": output}] + fx
            return {"handled": True, "output": output}, fx
        if event_type == "conversation.perception_tool_call":
            # Raven's vision tool (see tools.py). The browser strips the frame images before relaying.
            name = props.get("name")
            key = f"perc:{name}:{ev.get('seq') or ev.get('timestamp')}"
            if g.seen(key):
                return {"handled": False, "reason": "duplicate"}, []
            if name != "written_word_on_paper":
                return {"handled": False, "reason": f"ignored perception tool {name}"}, []
            args = tools._parse_args(props.get("arguments"))
            text = str(args.get("text", ""))
            log.info("<- Raven saw writing on the paper: %r", text[:60])
            return {"handled": True}, game.handle_written_text(g, text, now)
        if event_type in ("conversation.started_speaking", "conversation.stopped_speaking"):
            # Latency measurement: player stops talking -> PAL starts talking (Tavus timestamps).
            role, ts = props.get("role"), ev.get("timestamp")
            if role not in ("user", "pal") or not isinstance(ts, (int, float)):
                return {"handled": False, "reason": "ignored role or timestamp"}, []
            if g.seen(f"spk:{event_type}:{role}:{ts}"):
                return {"handled": False, "reason": "duplicate"}, []
            if role == "pal":  # track whether the PAL is mid-sentence (see game.route_effects)
                if event_type == "conversation.started_speaking":
                    game.pal_started_speaking(g, now)
                else:
                    game.pal_stopped_speaking(g, now)
            if event_type == "conversation.stopped_speaking" and role == "user":
                g.last_user_stop_ts = float(ts)
            elif event_type == "conversation.started_speaking" and role == "pal" and g.last_user_stop_ts:
                gap = float(ts) - g.last_user_stop_ts
                g.last_user_stop_ts = None
                if 0 <= gap < 20:
                    g.latencies = (g.latencies + [round(gap, 2)])[-200:]
                    log.info("latency: you stopped talking -> Pip started %.2fs (%s)", gap, g.state)
            return {"handled": True}, []
        return {"handled": False, "reason": f"ignored {event_type}"}, []

    return _mutate(game_id, x_player_token, fn)


@app.post("/api/games/{game_id}/complete")
def complete(game_id: str, x_player_token: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Quit or finish: closes the Tavus conversation (saves minutes) and returns the scoreboard."""
    return _mutate(game_id, x_player_token, lambda g, now: (lambda fx: (game.scoreboard(g), fx))(game.quit_game(g, now)))


@app.get("/api/games/{game_id}/scoreboard")
def get_scoreboard(game_id: str, x_player_token: Optional[str] = Header(None)) -> Dict[str, Any]:
    return _mutate(game_id, x_player_token, lambda g, now: (game.scoreboard(g), []))


@app.post("/webhooks/tavus")
async def tavus_webhook(request: Request) -> JSONResponse:
    raw = await request.body()
    if not webhooks.verify_signature(raw, request.headers.get("X-Tavus-Signature"), CALLBACK_SECRET):
        log.warning("webhook rejected: bad or missing signature")
        return JSONResponse({"error": "invalid signature"}, status_code=401)
    try:
        payload = json.loads(raw)
        cid = payload.get("conversation_id")
        found = store.get_by_conversation(cid) if cid else None
        if found is None:
            return JSONResponse({"ok": True, "note": "unknown conversation"})
        with store.transaction(found.id) as g:
            if g.seen(webhooks.dedupe_key(payload)):
                return JSONResponse({"ok": True, "note": "duplicate"})
            what = webhooks.apply(g, payload)
        log.info("webhook %s: %s", payload.get("event_type"), what)
        return JSONResponse({"ok": True, "note": what})
    except Exception:
        log.exception("webhook processing failed")
        return JSONResponse({"error": "processing failed"}, status_code=500)  # 500 -> Tavus retries


# ---------------------------------------------------------------- frontend (production build)

_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        f = _DIST / path
        return FileResponse(f if path and f.is_file() else _DIST / "index.html")
