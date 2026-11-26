# Reverse Pictionary: You vs the AI

**You draw, it guesses. It draws, you guess.** A turn-based Pictionary game against a live Tavus video human. In your rounds you draw on real paper and hold it up, and the AI (Pip) watches through your camera with Raven-2 and guesses out loud. In its rounds it sketches on a canvas, one line at a time, and you shout your guess.

> **A PAL is a prompt. This is a system.** The PAL is one component: face, voice and guesser. The game state machine, the secret handling, the turn-taking, the referee that scores every guess, the stroke templates and the eval are the application, and none of that lives in the Tavus dashboard.

- **Live link:** `TODO: add after deploy`
- **Repo:** https://github.com/Suvoo/No-Way-Pictionary
- **Run it locally in 3 steps:** see [Quick start](#quick-start). It works with **no Tavus key** (demo mode).
- **Check it works:** `make check` runs the golden-set eval (18 cases), API tests and the frontend build.

---

## Why this project

- **Anyone can test it in 45 seconds.** Draw a terrible bicycle, laugh when it says "is that a car?". A game gets played. A mock interview gets closed.
- **It only works with video.** The camera has to see your paper, and you have to see its canvas. Take the video away and there is no game.
- **It is original on Tavus.** No Pictionary or sketch-guessing build in the Tavus Community Showcase or official examples (checked Nov 26 2026). Non-Tavus analogues (Mattel Pictionary Vs. AI, Quick, Draw!) are one-sided: you draw, a classifier guesses, nobody draws back.
- **It exercises the FDE loop:** take a vague brief, build one narrow path, show it works with an eval, and explain the trade-offs.

**Who it is for:** anyone with a laptop or phone, paper and a pen. **Success measure:** a full game finishes in about 6 to 7 minutes with a final score, all 6 words, and a guess log showing every guess, how many tries it took, and whether it was right.

## How to play (the 30 second version)

1. Open the link, grab paper and a **thick black pen**, press **Play**, allow camera and mic.
2. **Round 1 (you draw):** you see a secret word the AI cannot see. Draw it, hold it up, press **Look now**. It guesses out loud: right within 3 guesses and it wins the round, otherwise you do.
3. **Round 2 (it draws):** a canvas appears. It draws its secret word stroke by stroke. Shout your guess (or type it). Get it within 3 guesses and you win the round.
4. Alternate for 6 rounds, 45 seconds each. Final scoreboard with every word and the full guess log.

Scoring: **every round has a winner.** Guess right within 3 tries and the guesser gets the point. Otherwise the drawer wins it for stumping them.

---

## Quick start

```bash
git clone https://github.com/Suvoo/No-Way-Pictionary.git && cd No-Way-Pictionary
make setup        # venv + pip install + npm install + copies .env.example to .env
make dev          # backend :8000 + frontend :5173 -> open http://localhost:5173
```

That runs in **demo mode** (no video): the whole game, referee and scoring run for real, and you type what the AI "says". To play live with the video human:

```bash
# 1. put TAVUS_API_KEY=... in .env
make tavus-setup  # creates the 2 tools + the PAL (Raven-2) on Tavus, prints TAVUS_PAL_ID
# 2. put TAVUS_PAL_ID=... in .env, then
make dev
```

Requirements: Python 3.9+, Node 20+. No database setup (SQLite file, created on first run).

| Command | What it does |
|---|---|
| `make dev` | backend + frontend with hot reload |
| `make eval` | golden-set eval, prints pass/fail per case |
| `make test` | API tests (secret handling, idempotency, webhooks, garbage input) |
| `make check` | eval + tests + frontend build. Run this after any change |
| `make tavus-setup` | one-time PAL + tools creation (`--dry-run` to see the JSON) |
| `make docker` | run the production image locally on :8000 |

## Deploy (one service)

The production image builds the React app and serves it from FastAPI, so there is **one URL, one service, no CORS**.

**Render (recommended):** New > Blueprint > select this repo (`render.yaml`). Set `TAVUS_API_KEY`, `TAVUS_PAL_ID` and `PUBLIC_URL` (the Render URL, for webhooks). Health check: `GET /health`.
**Any Docker host** (Railway, Fly, Cloud Run): `docker build -t reverse-pictionary .` then run with the env vars above and `PORT`.

Check it is up: `curl https://<your-app>/health` returns `{"ok": true, "mode": "live"}`. Then open the link in an incognito window and on a phone.

Split deploy is also supported (frontend on Vercel with `VITE_API_URL=https://<backend>`, backend anywhere, `CORS_ORIGINS=https://<frontend>`), but one service is simpler.

---

## Architecture

```
 Browser (React + Vite + Tailwind)                     FastAPI backend (owns ALL game state)
 ┌────────────────────────────────────┐               ┌─────────────────────────────────────────┐
 │ Landing -> Game -> Scoreboard      │  POST /games  │ app.py      routes                      │
 │                                    │──────────────>│ game.py     state machine, timer, rules │
 │ CviEmbed (Daily iframe)            │<── room url ──│ scorer.py   guess matching + synonyms   │
 │   PAL video + your camera          │               │ tools.py    submit_guess, draw_next_... │
 │   app-messages from Tavus:         │  POST /events │ prompts.py  everything the PAL is told  │
 │   utterances + tool calls ─────────┼──────────────>│ store.py    SQLite, one row per game    │
 │                                    │               │ webhooks.py HMAC-verified callbacks     │
 │ Canvas (SVG, PAL rounds only)      │<─ GET /games ─│ tavus.py    the only Tavus API client   │
 │ Word box (your rounds only)        │   (1s poll)   └───────────────┬─────────────────────────┘
 └──────────────┬─────────────────────┘                               │ send-app-message:
                │ WebRTC (Daily)                                       │ overwrite/append context,
                v                                                      │ respond, tool_result, end
 ┌──────────────────────────────────────────────────────────────────────v──────────────────────┐
 │ Tavus CVI: PAL "Pip" (system prompt + 2 tools) + Face + Conversation (Daily room)           │
 │ Raven-2 perception (sees your paper) -> Sparrow turn-taking -> LLM -> TTS -> Phoenix video  │
 │ Callbacks (post-call transcript, shutdown) ─────────────> POST /webhooks/tavus              │
 └─────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Browser.** One page: landing, then game, then scoreboard. It renders whatever state the backend returns and owns no rules. The canvas is shown **only** in PAL-draw rounds, and the word box only in yours, so paper stays the input and canvas the output. `CviEmbed.tsx` joins the Daily room and **relays** Tavus app-messages (`conversation.utterance`, `conversation.tool_call`) to the backend, because Tavus delivers those only to the browser (see [Tavus API notes](#tavus-api-notes-verified-nov-26-2026)).

**Backend state machine (`game.py`).** `ROUND_START -> USER_DRAW | PAL_DRAW -> REVEAL -> ... -> GAME_OVER`. Rules enforced in code, not in the prompt: 45s timer (server clock, 1.5s network grace), 3 guesses, no duplicate words per game, a repeated guess does not burn a try, auto-stroke every 7s if the PAL stalls, a single nudge after 10s of silence. It is pure: it takes `now` and returns *effects* (messages for the PAL) instead of calling Tavus, which is why the eval can replay rounds without a video call.

**Secret handling.** The backend knows every word but tells one side at a time:
- *Your round:* the word goes to the browser only. The PAL gets "the player is drawing, you do not know the word".
- *Its round:* the word goes to the PAL only, via `conversation.overwrite_llm_context` at the moment the round starts (server-side, not broadcast to the room). The browser gets stroke geometry, never the word or the stroke labels. `test_api.py` and eval case 15 check this.
- Each round **overwrites** the PAL's context, so it never holds a future word or the player's word.

**Referee (`scorer.py` + `game.record_guess`).** The PAL never scores itself. A guess is correct if the secret or a variant appears as a whole word ("bike" counts for bicycle, "kitty" for cat), case- and punctuation-insensitive, with plurals. PAL guesses arrive two ways: the `submit_guess` tool, and as a fallback, "is it a X?" patterns in its speech. The same guess arriving by both paths within 8s counts once. Player guesses come from their speech (short utterances only, so chatter is not a guess) or the typed box.

**PAL tools (`tools.py`).** `submit_guess(guess)` for the PAL's guesses and `draw_next_stroke()` for its drawing. The PAL decides *when* to draw, and the template decides *what* is drawn, so it cannot draw nonsense or the wrong word. `reveal_answer` (`game.end_round`) is backend-only on purpose, so the PAL cannot end a round early. The hint is a player button, enabled only in PAL-draw rounds, because a hint in your round would leak your word to the PAL.

**Canvas and stroke templates (`strokes.json`).** 28 words, 3 to 6 strokes each, as plain shapes (line, circle, ellipse, arc) in a 100×100 box. They are rendered as rough black marker lines with a little deterministic wobble, and each new stroke animates in like a pen. Add a word: one entry in `words.py`, one template in `strokes.json`, then `make eval`.

**Webhooks (`webhooks.py`).** `X-Tavus-Signature` (HMAC-SHA256 of the raw body) is verified before parsing, and unsigned requests get 401. Events are deduplicated, and processing failures return 500 so Tavus retries. Webhooks store the post-call transcript for the audit trail. Live gameplay does not depend on them.

**Storage (`store.py`).** SQLite, one row per game as JSON, saved after every change inside one lock, so a backend restart resumes the game.

## API

All `/api/games/{id}/...` routes need the `X-Player-Token` header returned by `POST /api/games`. Every mutating route returns the same game view as `GET`.

| Method & path | Purpose |
|---|---|
| `GET /health` | `{"ok": true, "mode": "live" \| "demo"}` |
| `GET /api/config` | rounds, seconds, guesses, PAL name, mode |
| `POST /api/games` | `{"previous_game_id"?}` -> creates a game + Tavus conversation |
| `GET /api/games/{id}` | game view (state, round, score, strokes, guess log) |
| `POST /api/games/{id}/start-round` | start round 1, or the next round from REVEAL |
| `POST /api/games/{id}/look` | your round: tell the PAL the paper is up, guess now |
| `POST /api/games/{id}/events` | browser relays a raw Tavus app-message (utterance / tool_call). Idempotent |
| `POST /api/games/{id}/guesses` | typed guess `{"text": "bike"}`. Demo mode: `{"text": "Is it a car?", "guesser": "pal"}` simulates the PAL |
| `POST /api/games/{id}/next-stroke` | PAL round: "draw more" button |
| `POST /api/games/{id}/hint` | PAL round: hint, after 2 wrong guesses or 20s |
| `POST /api/games/{id}/complete` | quit / finish: closes the Tavus conversation, returns scoreboard |
| `GET /api/games/{id}/scoreboard` | final score, all words, full guess log |
| `POST /webhooks/tavus` | Tavus callbacks, HMAC verified |

Example:

```bash
curl -s -X POST localhost:8000/api/games -H 'content-type: application/json' -d '{}'
# {"game_id":"Xk2..","player_token":"9fQ..","conversation_url":"https://tavus.daily.co/c123","mode":"live","rounds":6,"round_duration_sec":45,"pal_name":"Pip", ...}

curl -s -X POST localhost:8000/api/games/Xk2../start-round -H 'X-Player-Token: 9fQ..'
# {"state":"USER_DRAW","round":{"index":1,"drawer":"user","your_word":"bicycle","seconds_left":45,"guesses_left":3,"strokes":[],...},"score":{"user":0,"pal":0},...}

# a relayed tool call, exactly as Tavus sends it to the browser
curl -s -X POST localhost:8000/api/games/Xk2../events -H 'X-Player-Token: 9fQ..' -H 'content-type: application/json' \
  -d '{"event_type":"conversation.tool_call","properties":{"name":"submit_guess","arguments":"{\"guess\":\"car\"}","tool_call_id":"call_1"}}'
# {"handled":true,"output":"Wrong. 2 guesses left. Look again and change your mind out loud."}
```

---

## How do I know it is not making things up?

**You don't have to trust the PAL.** The backend picks the words, keeps each secret on the right side, checks every spoken guess against the secret, and logs every guess with a timestamp, its source (tool, transcript, speech, typed) and why it did or did not count. The PAL talks; the backend referees.

1. **Measured spike (before building, Nov 26 2026):** a Raven-2 PAL, 5 easy words (star, house, fish, bicycle, cat), thick black marker, held steady for 3s, good room light, real phone browser: **5/5 correct within 3 guesses.** That is the only perception result claimed. It is 5 easy words, not all 345 categories.
2. **Golden-set eval (`make eval`):** 18 scripted cases replayed against the real engine with a fake clock. They prove the game logic: scoring, timers, synonyms, repeats, secret handling, cheat flags, the honesty fallback, and that the PAL cannot guess in its own round.
3. **Live audit trail:** the scoreboard shows all 6 words and every guess. Anyone can re-score a game by hand from the log.

### Eval results

```
PASS  # 1  Easy word, clear drawing: PAL guesses star first try
PASS  # 2  Medium word: PAL commits to car, changes its mind to bicycle
PASS  # 3  Hard word is excluded from the v1 word bank
PASS  # 4  Wrong guess then correct: scored after 2 guesses, not 1
PASS  # 5  Timer expiry: no correct guess in 45s, drawer wins, game advances
PASS  # 6  No duplicate words in a game (200 seeds), Play Again avoids last game's words
PASS  # 7  PAL-draw round: player says house after stroke 3
PASS  # 8  PAL-draw round: player wrong 3 times, reveal shows key, PAL wins
PASS  # 9  Silent player: PAL nudges once after 10s, backend keeps drawing
PASS  #10  Cannot see paper: honesty fallback is logged, not counted as a guess
PASS  #11  Synonym counts: 'kitty' is accepted for cat
PASS  #12  Repeated wrong guess does not burn a second guess
PASS  #13  Guess 1s after the buzzer still counts (network grace)
PASS  #14  Late guess after grace window is rejected
PASS  #15  Anti-cheat: PAL-draw word never appears in what the browser sees
PASS  #16  Player says their own word out loud while drawing: flagged in the audit log
PASS  #17  PAL tries to guess in its own drawing round: refused
PASS  #18  Every v1 word has 3-7 stroke template strokes and a hint

18/18 passed
```

**What the eval does not prove:** that Raven reads every drawing, or that the PAL always follows its prompt (calls the tool, waits its turn, says "hold it closer" instead of guessing). Cases 9 and 10 check the *backend* side of those behaviours (the nudge fires, an "I can't see" line is not counted, the prompt contains the rule). Whether the PAL follows the rule live is checked by playing, and the guess log records what it did.

---

## Will build / will NOT build (v1)

**Built:** landing + game + scoreboard on one site · backend state machine, 6 alternating rounds · 28-word bank from Quick Draw · paper + camera + Raven-2 rounds · canvas + stroke template rounds · referee scoring + guess log · 2 PAL tools · webhooks with HMAC · golden-set eval + API tests · demo mode with no key · one-service deploy.

**Not built, on purpose:** a second game mode, multiplayer, accounts, leaderboards · all 345 categories · image generation (sketch-like only) · a trained sketch classifier · auth, billing, payments · any accuracy claim beyond the spike.

## Trade-offs

1. **6 rounds × 45s × 28 easy words vs all 345 categories.** Chose depth and playability. Breadth would break guessing: Raven is a general perception model, not a sketch classifier.
2. **Backend referee vs letting the PAL score.** Chose the backend: reproducible, testable, cheat-proof. Cost: the backend has to parse speech, so it also accepts a tool call and a typed guess.
3. **Stroke templates vs the LLM inventing coordinates.** Chose templates. Reliable, auditable, and the PAL still decides when to draw. Cost: 28 hand-made sketches, one per word.
4. **Browser relays live events vs tools delivered to the backend over HTTPS.** Tavus sends utterances only to the browser, and HTTPS tool delivery needs a public URL (no localhost), so v1 uses one relay path that works everywhere. Cost: see limitations.
5. **One service vs Vercel + Railway.** Chose one Docker service: one URL, no CORS, one thing to deploy. Split deploy still works.
6. **Live link + repo vs a recorded Loom only.** Chose both, with the live link primary (the team asked for a hosted link they can test), and a short Loom as backup.

## Known limitations

- **Relayed events are trusted.** A determined player could POST fake utterances to `/events` from devtools and win. Fine for a party game. Fix: deliver tools to the backend over HTTPS (`delivery.api` with HMAC auth) and score PAL guesses only from those.
- **PAL turn-taking is prompt-level.** The PAL may talk over you or ask an unprompted question; that is a known CVI conversational limit. The prompt asks it to wait, and the referee ignores anything that is not a guess.
- **Speech-to-text can mishear** ("house" as "mouse"). The raw text is logged next to the scored guess so it can be audited, and the typed box is the escape hatch.
- **SQLite on a free host is ephemeral.** It survives a process restart, not a redeploy.
- **One game per browser tab.** Two tabs means two separate games and two calls.
- **The 3-guess cap depends on the PAL calling `submit_guess`.** If it only talks, wrong guesses are still caught by the "is it a X?" speech patterns, but phrasings outside those patterns are missed, and the round ends on the timer instead.

## Edge cases

Handled in v1: synonyms and plurals · repeated guesses · the same guess heard twice (tool + speech) · late guesses (1.5s grace, then rejected) · timer expiry (drawer wins) · duplicate words in a game · Play Again avoiding the last game's words · the player saying their own word out loud (flagged) · the PAL saying its own word (flagged) · the PAL guessing in its own round (refused) · "can't see, hold it closer" (logged, not a guess) · a silent player (one nudge + auto strokes) · a PAL that stops drawing (auto stroke every 7s) · duplicate webhooks and relayed events (idempotent) · garbage or malformed events (ignored, never crash) · a dropped call (Reconnect, same game) · a backend restart (state persisted after every change) · the conversation left open (closed at game end, plus a 20 min `max_call_duration` cap).

Noted, not built in v1: writing the word on paper (the prompt tells the PAL to call it out, with no automatic detection) · holding up a phone image or print · a second person shouting guesses (no speaker ID) · lined or grid paper, a mirrored front camera, glare, shaky hands · rude drawings (prompt-level only) · rotating the phone mid-round · running out of Tavus minutes mid-game (the create call fails cleanly with a message, but there is no warning mid-game) · a slow connection delaying Raven's view.

## What I would do with two more days

Score PAL guesses from HTTPS tool delivery only (closing the relay trust gap) · a small sketch classifier trained on Quick Draw as a second opinion next to Raven · a bigger word bank with difficulty tiers · calibration runs with real players (does 45s feel right? do people hold the paper steady?) · re-run the golden set plus a recorded live session after every prompt change, to catch drift · a post-call perception report on what Raven saw each round.

---

## Tavus API notes (verified Nov 26 2026)

Checked against `https://docs.tavus.io/openapi.yaml` and the docs pages. If anything here disagrees with the live spec, the live spec wins.

- **Live utterances and tool calls go to the browser only**, over the Daily data channel (`conversation.utterance` with `role` `user` / `pal`, plus a legacy duplicate with `replica`; `conversation.tool_call`). Webhooks are lifecycle and post-call only. Hence the browser relay.
- **The server can push into a live call:** `POST /v2/conversations/{id}/send-app-message` accepts `overwrite_llm_context`, `append_llm_context`, `respond`, `tool_result` and more (120 req/min, 64 KB). This is how per-round secrets reach the PAL without ever sitting in its context early.
- **Current field names are `pal_id` + `face_id`.** The Santa Demo's `persona_id` / `replica_id` are the legacy names. PAL fields used: `pal_name`, `system_prompt`, `default_face_id`, `layers.perception.perception_model: "raven-2"`, `visual_awareness_queries`, `callouts`.
- **Tools** are created with `POST /v2/tools` and attached with `POST /v2/pals/{id}/tools` (inline `layers.llm.tools` is legacy). Delivery `app_message` (default) goes to the browser; `delivery.api` makes Tavus call an HTTPS URL directly.
- **The conversation response** has `conversation_url` (for the Daily SDK; used here) and `room_url` (the Tavus-hosted page). End with `POST /v2/conversations/{id}/end`.

## Files

```
backend/
  app.py            FastAPI routes (+ serves frontend/dist in production)
  game.py           state machine, timers, rules, public view (start here)
  scorer.py         guess matching, synonyms, speech parsing
  tools.py          PAL tool specs + handlers
  prompts.py        system prompt + per-round context: everything the PAL is told
  words.py          28-word v1 bank (+ all 345 Quick Draw categories for reference)
  strokes.json      stroke templates, one per word
  store.py          SQLite persistence
  tavus.py          Tavus API client + ordered effect dispatcher, demo mode
  webhooks.py       HMAC verification + callback handling
  setup_tavus.py    one-time PAL + tools creation
  evals/            golden_set.json + run_evals.py
  tests/test_api.py
frontend/src/
  App.tsx  Landing.tsx  Game.tsx  CviEmbed.tsx  Canvas.tsx  Scoreboard.tsx  api.ts
```

Word bank from the [Google Quick, Draw! dataset](https://github.com/googlecreativelab/quickdraw-dataset) (CC BY 4.0). heart is a hand-added word; boat and balloon map to Quick Draw's "sailboat" and "hot air balloon".

Built by Suvodeep Sinha as a Tavus Forward Deployed Engineer take-home.
