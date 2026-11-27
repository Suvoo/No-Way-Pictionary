# Doodle with Pip

**Pip guesses your doodles out loud. Then you guess Pip's.** A turn-based Pictionary-style drawing game against a live Tavus video human. In your rounds you draw on real paper and hold it up, and the AI (Pip) watches through your camera with Raven-2 and guesses out loud. In its rounds it sketches on a canvas, one line at a time, and you shout your guess.

> **A PAL is a prompt. This is a system.** The PAL is one component: face, voice and guesser. The game state machine, the secret handling, the turn-taking, the referee that scores every guess, the stroke templates and the eval are the application, and none of that lives in the Tavus dashboard.

- **Play it:** `TODO: live link after deploy` (no login, no setup; grab paper and a thick pen)
- **Watch it:** `TODO: 2-minute Loom`
- **How it works:** [Architecture](#architecture) · **Why this project:** [Why this project](#why-this-project) · **Does it work:** [Eval results and live testing](#eval-results)
- **Repo:** https://github.com/Suvoo/No-Way-Pictionary
- **Run it locally in 3 steps:** see [Quick start](#quick-start). It works with **no Tavus key** (demo mode).
- **Check it works:** `make check` runs the golden-set eval (43 cases), API and unit tests, and the frontend build.
- **AI agents:** start with [`CLAUDE.md`](CLAUDE.md): read order, commands, the rules that must not break, where to change things.

---

## Why this project

- **Anyone can test it in 45 seconds.** Draw a terrible bicycle, laugh when it says "is that a car?". A game gets played. A mock interview gets closed.
- **It only works with video.** The camera has to see your paper, and you have to see its canvas. Take the video away and there is no game.
- **It is original on Tavus.** No Pictionary or sketch-guessing build in the Tavus Community Showcase or official examples (checked Nov 26 2026). Non-Tavus analogues (Mattel Pictionary Vs. AI, Quick, Draw!) are one-sided: you draw, a classifier guesses, nobody draws back.
- **It exercises the FDE loop:** take a vague brief, build one narrow path, show it works with an eval, and explain the trade-offs.

**Who it is for:** anyone with a laptop or phone, paper and a pen. **Success measure:** a full game finishes in about 6 to 7 minutes with a final score, all 6 words and who scored each round, plus a guess log (API and database) showing every guess, how many tries it took, and whether it was right.

## How to play (the 30 second version)

1. Open the link, grab paper and a **thick black pen**, press **Play**, allow camera and mic. Pip says hi and asks if you want the rules; ask anything, then say **"let's start"** (or press Start).
2. **Round 1 (you draw):** you see a secret word the AI cannot see. Draw it, hold it up, press **Look now**. It guesses out loud: right within 3 guesses and it scores a point.
3. **Round 2 (it draws):** a canvas appears. It draws its secret word stroke by stroke. Shout your guess (or type it). Get it within 3 guesses and you score a point.
4. Alternate for 6 rounds, 45 seconds each. Final scoreboard with every word and who scored each round.

Scoring: **guessers only.** Guess right within 3 tries and you get the point; a missed round scores for nobody. So the score is who guessed more, and drawing badly on purpose never pays. (An earlier rule gave the drawer the point on a miss, which rewarded bad drawings.)

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
make tavus-setup  # creates Pip (the PAL, Raven-2) + its draw tool on Tavus, prints TAVUS_PAL_ID
# 2. put TAVUS_PAL_ID=... in .env, then
make dev
```

Requirements: Python 3.9+, Node 20+. No database setup (SQLite file, created on first run).

| Command | What it does |
|---|---|
| `make dev` | backend + frontend with hot reload |
| `make eval` | golden-set eval, prints pass/fail per case |
| `make test` | API and unit tests (secret handling, idempotency, webhooks, garbage input, not talking over Pip) |
| `make last-game` | what happened in the latest game: rounds, every guess and why it counted, turn latency |
| `make stop` | free ports 8000 / 5173 if a dev server was left running |
| `make check` | eval + tests + frontend build. Run this after any change |
| `make tavus-setup` | one-time PAL + tool creation, prints `TAVUS_PAL_ID` (`--dry-run` to see the JSON) |
| `make tavus-update` | after changing Pip's system prompt or settings: update the same PAL in place |
| `make docker` | build and run the production image on http://localhost:8080 (same image Render runs) |

## Deploy (one service)

The production image builds the React app and serves it from FastAPI, so there is **one URL, one service, no CORS**. It needs an always-on container (the backend runs round timers), HTTPS (browsers only allow camera and mic on HTTPS) and these env vars:

| Var | Required | What |
|---|---|---|
| `TAVUS_API_KEY` | for live video | Tavus API key (server-side only) |
| `TAVUS_PAL_ID` | for live video | printed by `make tavus-setup` |
| `PUBLIC_URL` | recommended | the deployed URL, e.g. `https://doodle-with-pip.onrender.com`; enables webhooks |
| `TAVUS_CALLBACK_SECRET` | with `PUBLIC_URL` | any random string, signs webhooks |

Without the two Tavus vars the deploy still works, in demo mode.

- **Render** (configured, free tier): New > Blueprint > this repo (`render.yaml`), fill the vars. The free tier sleeps after 15 idle minutes (about 50s to wake), so open the link once before sharing it.
- **Railway** (no config needed, small monthly cost, no sleep): New Project > Deploy from GitHub repo; it builds the `Dockerfile`. Add the vars, then Settings > Networking > Generate Domain, and put that domain in `PUBLIC_URL`.
- **Fly.io, Cloud Run, any Docker host:** `docker build -t doodle-with-pip .` and run it with the vars and `PORT`. On Cloud Run set min and max instances to 1 (one process owns the timers and the SQLite file).

Check it is up: `curl https://<your-app>/health` returns `{"ok": true, "mode": "live"}`. Then open the link in an incognito window and on a phone. Game history (SQLite in the container) resets on redeploy; games themselves are unaffected.

---

## Architecture

```
BROWSER  React + Vite + Tailwind (built and served by the backend in production)
│  Landing -> Game -> Scoreboard. Renders whatever the backend returns; owns no rules.
│  CviEmbed.tsx: joins the Daily room, shows Pip's video + your camera preview, and relays
│                Tavus app-messages (speech, tool calls, started/stopped speaking)
│
│  POST /api/games ...................... create a game + its Tavus conversation -> room URL
│  POST /api/games/{id}/events .......... relayed app-messages (the only way speech reaches the backend)
│  POST /api/games/{id}/start-round|look|guesses|hint|next-stroke|complete ... buttons and typed guesses
│  GET  /api/games/{id} ................. polled every 1s -> public view (never Pip's secret word)
▼
BACKEND  FastAPI, one process, owns ALL game state
│  game.py ......... state machine, timers, scoring. Pure: returns effects (what Pip should hear or say)
│  scorer.py ....... speech -> scored guess (matching, near misses, voice commands)
│  route_effects ... (in game.py) holds Pip's spoken lines until Pip stops talking; drops stale prompts
│  tavus.py ........ sends effects to Tavus one at a time, in order (demo mode: logs them instead)
│  prompts.py ...... everything Pip is told     store.py ... SQLite, one row per game
│  webhooks.py ..... HMAC-verified callbacks    inspect_game.py ... `make last-game`
│
│  POST /v2/conversations ........................ create the call: pal_id, per-game context, greeting
│  POST /v2/conversations/{id}/send-app-message
│       overwrite_llm_context / append_llm_context ... round context and secrets (silent)
│       respond ...................................... Pip answers in its own words (nudges, round starts)
│       echo ......................................... Pip says this exact line (reveals)
│       tool_result .................................. answer to Pip's draw_next_stroke
│  POST /v2/conversations/{id}/end ............... at game over, Home, Play again or Quit
▼
TAVUS CVI
   PAL "Pip", created once by setup_tavus.py (`make tavus-update` to change it): system prompt,
     Raven-2 with paper-focused awareness questions, speech hotwords, turn-taking settings, draw tool
   Conversation = a Daily WebRTC room: Raven-2 sees -> Sparrow-2 turn-taking -> LLM -> TTS -> Phoenix video
   Live app-messages go to the BROWSER only (hence the relay); post-call callbacks -> POST /webhooks/tavus
```

**Browser.** One page: landing, then game, then scoreboard. It renders whatever state the backend returns and owns no rules. The canvas is shown **only** in PAL-draw rounds, and the word box only in yours, so paper stays the input and canvas the output. Layout: the live video is the stage (two thirds of the width on desktop) and the round's controls sit in a slim rail; on phones they stack. `CviEmbed.tsx` joins the Daily room with a Daily *call object* and draws the tracks itself: Pip's video fills the stage, the player's camera is a small corner preview for aiming the paper, Pip's lines appear as captions, and there is no stock pre-join screen. It also **relays** Tavus app-messages (`conversation.utterance`, `conversation.tool_call`, `started/stopped_speaking`) to the backend, because Tavus delivers those only to the browser (see [Tavus API notes](#tavus-api-notes-verified-nov-26-2026)).

**Backend state machine (`game.py`).** `ROUND_START -> USER_DRAW | PAL_DRAW -> REVEAL -> ... -> GAME_OVER`. Rules enforced in code, not in the prompt: 45s timer (server clock, 3s grace for speech lag), 3 guesses, no duplicate words per game, a repeated guess does not burn a try, auto-stroke every 7s if the PAL stalls (narrated out loud only when nobody is talking), a single nudge after 15s of player silence in Pip's rounds, and in the player's rounds a "look at the camera now" prompt whenever the PAL has been quiet for about 9s (up to 3 a round). If the player says their own word out loud, they get a new word and a fresh round; a second time, Pip gets the point. A user utterance that Tavus re-sends as it grows ("No, I think-" then "No, I think- drummers") is scored once, on its new words only. It is pure: it takes `now` and returns *effects* (messages for the PAL) instead of calling Tavus, which is why the eval can replay rounds without a video call.

**Secret handling.** The backend knows every word but tells one side at a time:
- *Your round:* the word goes to the browser only. The PAL gets "the player is drawing, you do not know the word".
- *Its round:* the word goes to the PAL only, via `conversation.overwrite_llm_context` at the moment the round starts (server-side, not broadcast to the room). The browser gets stroke geometry, never the word or the stroke labels. `test_api.py` and eval case 15 check this.
- Each round **overwrites** the PAL's context, so it never holds a future word or the player's word.

**Referee (`scorer.py` + `game.record_guess`).** The PAL never scores itself. Each rule below came from a live game and has an eval case.
- **Matching:** a guess is right if the word or a variant appears as a whole word ("bike" for bicycle, "kitty" for cat, "smile" for smiley face), ignoring case, punctuation and plurals.
- **Pip's guesses** are read from what it says out loud, so the score matches what the player heard: questions ("is it a cup?") count; exclamations count only if they name a game word ("it's a bicycle!", not "that's cheating!"); descriptions do not ("it looks like a scoop on a triangle"); if one guess in a sentence is right, only that one counts.
- **Player guesses** come from speech or the typed box: short utterances are guesses; questions ("What is it?") and filler ("Of it.") are not; in a longer sentence, a game word is the guess ("I just said a ladder"). A guess one or two letters off ("slow man" for snowman) is a likely mishearing: it does not use up a try, and Pip asks again. A growing utterance that Tavus re-sends is scored once.
- **Voice commands:** between rounds, "let's start", "ready", "go" or "next round" do what the button does; "not ready" and "wait" win.

**Not talking over the PAL (`game.route_effects`).** Every line the backend makes the PAL say is a new turn that interrupts whatever it is saying, so the backend tracks `started/stopped_speaking` (and estimates the length of the PAL's own sentence, about 0.36s a word) and holds those lines until the PAL finishes, max 8s. Stale timer prompts are dropped. Reveals are fixed lines spoken word for word with `conversation.echo`, and always name the word: "Boom, it was glasses.", "Yes! It was heart. Point to you.", "Time's up! It was pizza. No point this round."

**PAL tool (`tools.py`).** `draw_next_stroke()` for its drawing. (A `submit_guess` tool was retired after two live games: the PAL never called it, so the referee scores what the PAL says out loud, which is also what the player hears.) The PAL decides *when* to draw, and the template decides *what* is drawn, so it cannot draw nonsense or the wrong word. `reveal_answer` (`game.end_round`) is backend-only on purpose, so the PAL cannot end a round early. The hint is a player button, enabled only in PAL-draw rounds, because a hint in your round would leak your word to the PAL.

**Canvas and stroke templates (`strokes.json`).** 28 words, 2 to 6 strokes each, as plain shapes (line, circle, ellipse, arc) in a 100×100 box. They are rendered as rough black marker lines with a little deterministic wobble, and each new stroke animates in like a pen. Add a word: one entry in `words.py`, one template in `strokes.json`, then `make eval`.

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
| `POST /api/games/{id}/events` | browser relays a raw Tavus app-message (utterance, tool_call, started/stopped_speaking). Idempotent |
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

# a relayed utterance, exactly as Tavus sends it to the browser: Pip guesses out loud, the referee scores it
curl -s -X POST localhost:8000/api/games/Xk2../events -H 'X-Player-Token: 9fQ..' -H 'content-type: application/json' \
  -d '{"event_type":"conversation.utterance","inference_id":"i1","properties":{"role":"pal","speech":"Two circles... is it a car?"}}'
# {"handled":true}   (GET /api/games/Xk2.. now shows guesses_left 2 and "car" in guess_log)
```

---

## How do I know it is not making things up?

**You don't have to trust the PAL.** The backend picks the words, keeps each secret on the right side, checks every spoken guess against the secret, and logs every guess with a timestamp, its source (tool, transcript, speech, typed) and why it did or did not count. The PAL talks; the backend referees.

1. **Measured spike (before building, Nov 26 2026):** a Raven-2 PAL, 5 easy words (star, house, fish, bicycle, cat), thick black marker, held steady for 3s, good room light, real phone browser: **5/5 correct within 3 guesses.** That is the only perception result claimed. It is 5 easy words, not all 345 categories.
2. **Golden-set eval (`make eval`):** 43 scripted cases (including replays of real live-game transcripts) replayed against the real engine with a fake clock. They prove the game logic: scoring, timers, synonyms, repeats, secret handling, cheat flags, the honesty fallback, and that the PAL cannot guess in its own round.
3. **Live audit trail:** every guess is stored with its raw text, source and why it did or did not count, in the database and in `GET /api/games/{id}/scoreboard` (`guess_log`). Players see only the words and who scored; anyone checking the game can re-score it by hand from the log.

### Eval results

```
PASS  # 1  Easy word, clear drawing: PAL guesses star first try
PASS  # 2  Medium word: PAL commits to car, changes its mind to bicycle
PASS  # 3  Hard word is excluded from the v1 word bank
PASS  # 4  Wrong guess then correct: scored after 2 guesses, not 1
PASS  # 5  Timer expiry: no correct guess in 45s, nobody scores, game advances
PASS  # 6  No duplicate words in a game (200 seeds), Play Again avoids last game's words
PASS  # 7  PAL-draw round: player says house after stroke 3
PASS  # 8  PAL-draw round: player wrong 3 times, reveal shows key, nobody scores
PASS  # 9  Silent player: PAL nudges once after 15s, backend keeps drawing
PASS  #10  Cannot see paper: honesty fallback is logged, not counted as a guess
PASS  #11  Synonym counts: 'kitty' is accepted for cat
PASS  #12  Repeated wrong guess does not burn a second guess
PASS  #13  Guess 2.5s after the buzzer still counts (speech lag grace)
PASS  #14  Late guess after grace window is rejected
PASS  #15  Anti-cheat: PAL-draw word never appears in what the browser sees
PASS  #16  Player says their own word: it is replaced with a new word and Pip's guesses reset
PASS  #17  PAL tries to guess in its own drawing round: refused
PASS  #18  Every v1 word has 2-7 template strokes and a hint
PASS  #19  Live replay (Nov 26): a growing utterance is one guess, not three
PASS  #20  Live replay (Nov 26): PAL that has not guessed is prompted to look, then again if still quiet
PASS  #21  A PAL that keeps talking and guessing is not prompted
PASS  #22  Auto-stroke is narrated out loud only when nobody is talking
PASS  #23  Live replay (Nov 26): prompted to look at ~9s, then again when it goes quiet after a wrong guess
PASS  #24  Live replay (Nov 26): saying "No, let's start." starts round 1 by voice
PASS  #25  "I'm not ready yet" does not start the round
PASS  #26  Saying "Next round!" after a reveal starts the next round
PASS  #27  Live replay (Nov 26): "slow man" for snowman is a near miss, not a wasted guess
PASS  #28  Short words are never near misses: "car" for cat is a real wrong guess
PASS  #29  Live replay (Nov 26): "What is it?" is a question, not a wasted guess
PASS  #30  Live replay (Nov 26): "Uh, bro, I just said a ladder?" counts as the guess ladder
PASS  #31  Live replay (Nov 26): voice start of a player round sends no second scripted line
PASS  #32  Long chatter without a game word is still not a guess
PASS  #33  Live replay (Nov 26): "it looks like a scoop on a triangle" is a description, not a wasted guess
PASS  #34  Live replay (Nov 26): when Pip guesses right, it says exactly "Boom, it was ice cream."
PASS  #35  When the player guesses Pip's drawing, Pip says "Yes! It was heart. Point to you."
PASS  #36  Live replay (Nov 26): "A heart and a cone... is it an ice cream?" guesses ice cream, not heart
PASS  #37  Guessers-only scoring: a missed round scores for nobody, a right guess scores for the guesser
PASS  #38  Live replay (Nov 26): "The word is fish, bro." swaps the word; "that is cheating!" is not a guess
PASS  #39  Saying the word a second time in the same round gives Pip the point
PASS  #40  Live replay (Nov 26): "Of it." is speech debris, not a wasted guess
PASS  #41  Live replay (Nov 26): "a smile" counts for smiley face
PASS  #42  Pip's exclamation counts only when it names a game word ("Wait, it's a bicycle!")
PASS  #43  After a word swap, Pip may guess an old guess again on the new word (not "already tried")

43/43 passed
```

**Live testing (Nov 26 2026):** nine games (29 rounds) against the live PAL. Secrets held in every game. Measured turn latency, from the player stopping talking to the PAL starting, had a median of 0.88s over 49 turns (2 readings were excluded: the PAL was answering a backend line, not the player, a measurement bug since fixed). Every problem the games surfaced is fixed and replayed as an eval case labelled "Live replay": a growing utterance scored three times, the PAL waiting to be spoken to before looking, mishearings, the PAL misreading who won, the backend cutting the PAL off mid-sentence, the player saying their own word, and more.

**What the eval does not prove:** that Raven reads every drawing, or that the PAL always follows its prompt (calls the tool, waits its turn, says "hold it closer" instead of guessing). Cases 9 and 10 check the *backend* side of those behaviours (the nudge fires, an "I can't see" line is not counted, the prompt contains the rule). Whether the PAL follows the rule live is checked by playing, and the guess log records what it did.

---

## Will build / will NOT build (v1)

**Built:** landing + game + scoreboard on one site · backend state machine, 6 alternating rounds · 28-word bank from Quick Draw · paper + camera + Raven-2 rounds · canvas + stroke template rounds · referee scoring + guess log · a PAL draw tool · voice start · webhooks with HMAC · golden-set eval + API tests · demo mode with no key · one-service deploy.

**Not built, on purpose:** a second game mode, multiplayer, accounts, leaderboards · all 345 categories · image generation (sketch-like only) · a trained sketch classifier · auth, billing, payments · any accuracy claim beyond the spike.

## Trade-offs

1. **6 rounds × 45s × 28 easy words vs all 345 categories.** Chose depth and playability. Breadth would break guessing: Raven is a general perception model, not a sketch classifier.
2. **Backend referee vs letting the PAL score.** Chose the backend: reproducible, testable, cheat-proof. Cost: the backend has to parse speech (rules above, each with an eval case), with a typed box as a fallback.
3. **Stroke templates vs the LLM inventing coordinates.** Chose templates. Reliable, auditable, and the PAL still decides when to draw. Cost: 28 hand-made sketches, one per word.
4. **Browser relays live events vs tools delivered to the backend over HTTPS.** Tavus sends utterances only to the browser, and HTTPS tool delivery needs a public URL (no localhost), so v1 uses one relay path that works everywhere. Cost: see limitations.
5. **One service vs Vercel + Railway.** Chose one Docker service: one URL, no CORS, one thing to deploy. Split deploy still works.
6. **Live link + repo vs a recorded Loom only.** Chose both, with the live link primary (the team asked for a hosted link they can test), and a short Loom as backup.

## Known limitations

- **Relayed events are trusted.** A determined player could POST fake utterances to `/events` from devtools and win. Fine for a party game. Fix: deliver tools to the backend over HTTPS (`delivery.api` with HMAC auth) and score PAL guesses only from those.
- **PAL turn-taking is prompt-level.** The PAL may talk over you or ask an unprompted question; that is a known CVI conversational limit. The prompt asks it to wait, and the referee ignores anything that is not a guess.
- **Speech-to-text can mishear** ("house" as "mouse"). The raw text is logged next to the scored guess so it can be audited, and the typed box is the escape hatch.
- **SQLite on a free host is ephemeral.** It survives a process restart, not a redeploy.
- **Free hosting sleeps.** On Render's free tier the first visit after 15 idle minutes takes about 50s.
- **One game per browser tab.** Two tabs means two separate games and two calls.
- **PAL guesses are read from its speech.** The prompt has it phrase guesses as "is it a ___?", and the referee extracts them with speech patterns. A guess phrased outside those patterns is missed, and the round ends on the timer instead.

## Edge cases

Handled in v1: synonyms and plurals · repeated guesses · the same guess heard twice · late guesses (3s grace, then rejected) · speech-to-text near misses ("slow man" for snowman: not counted, the PAL asks again; never for 3-letter words) · starting by voice ("let's start", "ready", "next round"; "not ready" and "wait" win) · a growing or cut-off utterance (scored once, fragments ignored) · a PAL that waits instead of looking (prompted after ~9s of quiet) · timer expiry (nobody scores) · duplicate words in a game · Play Again avoiding the last game's words · the player saying their own word out loud (first time: a new word, a fresh 45s and Pip's guesses reset, with a warning on screen; second time in the round: Pip gets the point) · the PAL saying its own word (flagged) · the PAL guessing in its own round (refused) · "can't see, hold it closer" (logged, not a guess) · a silent player (one nudge + auto strokes) · a PAL that stops drawing (auto stroke every 7s) · duplicate webhooks and relayed events (idempotent) · garbage or malformed events (ignored, never crash) · a dropped call (Reconnect, same game) · a backend restart (state persisted after every change) · the conversation left open (closed at game end, on Home or Play again, plus a 20 min `max_call_duration` cap).

Noted, not built in v1: writing the word on paper (the prompt tells the PAL to call it out, with no automatic detection) · holding up a phone image or print · a second person shouting guesses (no speaker ID) · lined or grid paper, a mirrored front camera, glare, shaky hands · rude drawings (prompt-level only) · rotating the phone mid-round · running out of Tavus minutes mid-game (the create call fails cleanly with a message, but there is no warning mid-game) · a slow connection delaying Raven's view.

## What I would do with two more days

Score PAL guesses from HTTPS tool delivery only (closing the relay trust gap) · a small sketch classifier trained on Quick Draw as a second opinion next to Raven · a bigger word bank with difficulty tiers · calibration runs with real players (does 45s feel right? do people hold the paper steady?) · re-run the golden set plus a recorded live session after every prompt change, to catch drift · a post-call perception report on what Raven saw each round.

---

## Tavus API notes (verified Nov 26 2026)

Checked against `https://docs.tavus.io/openapi.yaml` and the docs pages. If anything here disagrees with the live spec, the live spec wins.

- **Live utterances and tool calls go to the browser only**, over the Daily data channel (`conversation.utterance` with `role` `user` / `pal`, plus a legacy duplicate with `replica`; `conversation.tool_call`). Webhooks are lifecycle and post-call only. Hence the browser relay.
- **The server can push into a live call:** `POST /v2/conversations/{id}/send-app-message` accepts `overwrite_llm_context`, `append_llm_context`, `respond`, `echo` (say this text word for word), `tool_result` and more (120 req/min, 64 KB). This is how per-round secrets reach the PAL without ever sitting in its context early.
- **Current field names are `pal_id` + `face_id`.** The Santa Demo's `persona_id` / `replica_id` are the legacy names. PAL fields used: `pal_name`, `system_prompt`, `default_face_id`, `layers.perception.perception_model: "raven-2"`, `visual_awareness_queries`, `callouts`.
- **Speech and turn-taking settings on the PAL** (live findings): `layers.stt.hotwords` lists the 28 game words and the voice commands ("snowman" was transcribed as "slow man"), and `layers.conversational_flow` uses `turn_taking_patience: medium` and `pal_interruptibility: high`. We tried `high` patience after the PAL talked over a player, but every reply then felt late; medium patience plus high interruptibility (the PAL stops the moment the player speaks) is the balance. The browser also relays `conversation.started_speaking` / `stopped_speaking`, and the backend logs the gap from "player stopped talking" to "PAL started talking" for every turn (stored per game as `latencies`). The greeting is a short `custom_greeting` question; the PAL explains the rules in its own words from the per-conversation context.
- **Tools** are created with `POST /v2/tools` and attached with `POST /v2/pals/{id}/tools` (inline `layers.llm.tools` is legacy). Delivery `app_message` (default) goes to the browser; `delivery.api` makes Tavus call an HTTPS URL directly.
- **The conversation response** has `conversation_url` (for the Daily SDK; used here) and `room_url` (the Tavus-hosted page). End with `POST /v2/conversations/{id}/end`.

## Files

```
CLAUDE.md           guide for AI agents: read order, commands, invariants, where to change things
README.md           this file (source of truth)
Makefile            every command: setup, dev, check, last-game, tavus-setup/update, docker, stop
Dockerfile          one image: builds the React app, serves it from FastAPI
render.yaml         Render blueprint (one web service, health check /health)
.env.example        every env var, with comments
backend/
  app.py            FastAPI routes (+ serves frontend/dist in production)
  game.py           state machine, timers, rules, scoring, not-talking-over-Pip (start here)
  scorer.py         speech -> scored guess: matching, synonyms, near misses, voice commands
  prompts.py        system prompt + per-round context: everything the PAL is told
  tools.py          the PAL's draw tool + handler
  words.py          28-word v1 bank (+ all 345 Quick Draw categories for reference)
  strokes.json      stroke templates, one per word
  store.py          SQLite persistence
  tavus.py          Tavus API client + ordered effect dispatcher, demo mode
  webhooks.py       HMAC verification + callback handling
  setup_tavus.py    create the PAL once; --update applies prompt and settings changes in place
  inspect_game.py   `make last-game`: one game's rounds, guesses and latency from the DB
  evals/            golden_set.json + run_evals.py (43 cases, many replaying live games)
  tests/            test_api.py (HTTP, secrets, webhooks), test_game.py (timing, holds, swaps)
frontend/src/
  App.tsx  Landing.tsx  Game.tsx  CviEmbed.tsx  Canvas.tsx  Scoreboard.tsx  api.ts
```

Word bank from the [Google Quick, Draw! dataset](https://github.com/googlecreativelab/quickdraw-dataset) (CC BY 4.0). heart is a hand-added word; boat and balloon map to Quick Draw's "sailboat" and "hot air balloon".

Built by Suvodeep Sinha as a Tavus Forward Deployed Engineer take-home.
