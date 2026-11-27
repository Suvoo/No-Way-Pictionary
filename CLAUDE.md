# CLAUDE.md: guide for AI agents working on this repo

Doodle with Pip is a turn-based drawing game against a live Tavus video human ("Pip"). The player draws on
paper and Pip guesses through the camera; then Pip draws on a canvas and the player guesses. **README.md
is the source of truth** (what, why, architecture, API, deploy, eval results). This file is the map.

## Read in this order
1. `README.md`: Quick start, Architecture, API.
2. `backend/game.py`: the whole game (state machine, rules, timers, scoring). Pure: takes `now`, returns
   *effects* (messages for Pip) instead of calling Tavus.
3. `backend/prompts.py`: everything Pip is told. `backend/scorer.py`: how speech becomes a scored guess.
4. `backend/app.py` (routes) and `backend/tavus.py` (the only Tavus API client).

## Commands
```bash
make setup         # once: venv + pip + npm, copies .env.example -> .env
make dev           # backend :8000 + frontend :5173. Demo mode (typed guesses) until .env has Tavus keys
make check         # eval (46 cases) + API/unit tests + frontend build. Run after EVERY change
make last-game     # what happened in the latest game: rounds, every guess and why, latency
make tavus-setup   # once: create Pip (PAL) + its tools on Tavus, prints TAVUS_PAL_ID for .env
make tavus-update  # after changing SYSTEM_PROMPT or PAL settings (setup_tavus.py): update Pip in place
make docker        # production image on http://localhost:8080 (what Render runs)
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
- **Giving the word away** (saying it, or writing it on the paper, seen by Raven's `written_word_on_paper`
  vision tool) swaps the word once; a second time gives Pip the point. Only the secret word counts.
- **Every live bug becomes an eval case** in `backend/evals/golden_set.json` ("Live replay (date): ...").

## Where to change things
- Rules, timings, scoring: constants and functions at the top of `backend/game.py`.
- What Pip says or knows: `backend/prompts.py`. Per-round context is sent each game (no update needed).
  `SYSTEM_PROMPT`, hotwords and turn-taking live on the PAL: run `make tavus-update` after changing them.
- Add a word: an entry in `backend/words.py` + a stroke template in `backend/strokes.json`, then `make eval`.
- UI: `frontend/src/` (`Game.tsx` round screen, `CviEmbed.tsx` video + event relay, `Landing.tsx`).

## Deploy
One Docker service: FastAPI serves the API and the built React app. Env vars (see `.env.example`):
`TAVUS_API_KEY`, `TAVUS_PAL_ID` (required for live video), `PUBLIC_URL` (the deployed URL, enables
webhooks), `TAVUS_CALLBACK_SECRET` (any random string). Render: New > Blueprint (`render.yaml`).
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
