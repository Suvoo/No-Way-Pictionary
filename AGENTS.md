# AGENTS.md: guide for AI coding agents (Claude Code, Cursor, Codex, Copilot...) working on this repo

Doodle with Pip is a turn-based drawing game against a live Tavus video human ("Pip"). The player draws on
paper and Pip guesses through the camera; then Pip draws on a canvas and the player guesses. **README.md
is the source of truth** (what, why, architecture, API, deploy, eval results). This file is the map.

## Read in this order
1. `README.md`: Quick start, Architecture, API.
2. `backend/game.py`: the whole game (state machine, rules, timers, scoring). Pure: takes `now`, returns
   *effects* (messages for Pip) instead of calling Tavus.
3. `backend/prompts.py`: everything Pip is told. `backend/scorer.py`: how speech becomes a scored guess.
4. `backend/app.py` (routes) and `backend/tavus.py` (the only Tavus API client).

## Run it (one command)
```bash
make up            # Docker only: builds + runs everything on http://localhost:8080 (creates .env if missing)
curl localhost:8080/health   # -> {"ok": true, "mode": "demo" | "live"}
make down          # stop
```
Demo mode (typed guesses) until `.env` has `TAVUS_API_KEY`. With a key, the server finds or **creates Pip**
on that Tavus account at startup (`backend/setup_tavus.py: ensure_pal`) and logs `pip ready: <pal_id>`.
No PAL id, no setup script. If the code changes Pip's prompt/settings/tools, the next start syncs them.

## Commands for working on the code (Python 3.9+, Node 20+)
```bash
make setup         # once: venv + pip + npm, copies .env.example -> .env
make dev           # backend :8000 + frontend :5173 with hot reload
make check         # eval (50 cases) + API/unit tests + frontend build. Run after EVERY change
make last-game     # what happened in the latest game: rounds, every guess and why, latency
make tavus-setup   # optional: the same Pip sync the server does at startup, by hand (--dry-run for JSON)
make docker        # production image without compose on http://localhost:8080
make stop          # free ports 8000/5173 if a dev server was left running
```

## Rules that must not break (tests enforce them)
- **Secrets:** in the player's rounds the word goes to the browser only, never to Pip. In Pip's rounds
  the word goes to Pip only (`overwrite_llm_context`), never to the browser, not even stroke labels.
  `public_view()` is the only thing the browser sees. Eval #15 and `test_api.py` check this.
- **The backend referees.** Pip never scores itself. Pip's guesses are read from what it says out loud
  (questions; exclamations only if they name a game word). Scoring is **guessers only**: a right guess
  within 3 tries scores 1 for the guesser, a miss scores nobody.
- **Never talk over Pip.** Anything Pip must say goes out as a `say` (Pip answers in its own words) or
  `speak` (word for word, used for reveals) effect, and `game.route_effects` holds it until Pip
  finishes. Do not send `conversation.respond` / `echo` around that path.
  The screen follows the same timing: `reveal_ready` stays false ("Checking Pip's guess...") and the next
  round can't start until the held reveal line has gone out.
- **Giving the word away** (saying it, or writing it on the paper, seen by Raven's `written_word_on_paper`
  vision tool) swaps the word once; a second time gives Pip the point. Only the secret word counts.
- **Pip is a game host, not a chatbot.** Off-topic talk gets one friendly sentence, then back to the game.
  If no round starts for 3 minutes (`IDLE_GOODBYE_SECONDS`, before round 1 or between rounds), Pip says a
  fixed goodbye and the backend ends the call. Chatting does not reset that clock; starting a round does.
- **Every live bug becomes an eval case** in `backend/evals/golden_set.json` ("Live replay (date): ...").

## Where to change things
- Rules, timings, scoring: constants and functions at the top of `backend/game.py`.
- What Pip says or knows: `backend/prompts.py`. Per-round context is sent each game (no update needed).
  `SYSTEM_PROMPT`, hotwords, turn-taking and tools live on the PAL: synced automatically on the next server start.
- Add a word: an entry in `backend/words.py` + a stroke template in `backend/strokes.json`, then `make eval`.
- UI: `frontend/src/` (`Game.tsx` round screen, `CviEmbed.tsx` video + event relay, `Landing.tsx`).

## Deploy
One Docker service: FastAPI serves the API and the built React app. Env vars (see `.env.example`):
only `TAVUS_API_KEY` is needed for live video. Optional: `TAVUS_PAL_ID` (pin a PAL; empty = find or create
Pip), `PUBLIC_URL` + `TAVUS_CALLBACK_SECRET` (signed webhooks; on Render the URL defaults to
`RENDER_EXTERNAL_URL` and the blueprint generates the secret). Render: New > Blueprint (`render.yaml`).
Railway / Fly / any Docker host: build the `Dockerfile`, set the env vars, health check `GET /health`.
Verify: `curl https://<url>/health` -> `{"ok": true, "mode": "live"}`.

## Debugging a live game
`make last-game`, then the backend log: `-> PAL ...` is every message sent to Pip, `<- pal said` /
`<- user said` is what Tavus heard, `latency: ...` is each turn. Tavus sends live speech only to the
browser; `CviEmbed.tsx` relays it to `POST /api/games/{id}/events`.

## Gotchas
- Python 3.9 compatible (`from __future__ import annotations`, `Optional[...]`), Node 20+.
- Never commit `.env`. The Tavus key stays server-side; the browser only gets the Daily room URL.
- Every Play starts a real Tavus call that uses credits; the backend ends it at game over / Home / Quit.
