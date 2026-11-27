"""Print what happened in a game, from the database. The first thing to run after a live game.

    python -m backend.inspect_game            # latest game
    python -m backend.inspect_game <game_id>  # a specific game
    make last-game

Shows each round (word, who drew, outcome, guesses used, strokes, flags), every guess with its raw
text and why it did or did not count, and the measured turn latency (player stops talking -> Pip
starts). Pair it with the backend log, which shows every message sent to Pip ("-> PAL ...") and
everything Tavus relayed ("<- pal said ...", "<- user said ...").
"""
from __future__ import annotations

import datetime
import json
import os
import sqlite3
import sys
from statistics import median

from dotenv import load_dotenv


def _t(x):
    return datetime.datetime.fromtimestamp(x).strftime("%H:%M:%S") if x else "-"


def main(argv):
    load_dotenv(".env")
    db = sqlite3.connect(os.getenv("DB_PATH", "data/pictionary.db"))
    if argv:
        row = db.execute("SELECT data FROM games WHERE id=?", (argv[0],)).fetchone()
    else:
        row = db.execute("SELECT data FROM games ORDER BY updated_at DESC LIMIT 1").fetchone()
    if not row:
        print("No game found. Play one first (make dev, then press Play).")
        return 1
    g = json.loads(row[0])
    mode = "demo" if g["mock"] else f"live, conversation {g['conversation_id']}"
    print(f"Game {g['id']}  ({mode})  state={g['state']}  score: you {g['score']['user']} - Pip {g['score']['pal']}")
    print(f"created {_t(g['created_at'])}\n")
    print("Rounds")
    for r in g["rounds"]:
        if r["status"] == "pending":
            continue
        who = {"user": "you", "pal": "Pip", None: "nobody"}[r["winner"]]
        extra = f"  retired={r['retired_words']}" if r.get("retired_words") else ""
        print(f"  R{r['index']} {'you draw' if r['drawer'] == 'user' else 'Pip draws':9} {r['word']:12} "
              f"{r['end_reason'] or r['status']:15} point to {who:6} guesses {r['guesses_used']}  "
              f"strokes {r['strokes_drawn']}  {_t(r['started_at'])}-{_t(r['ended_at'])}  "
              f"started by {r.get('started_by', 'button')}{extra}")
        for f in r["flags"]:
            print(f"       flag: {f}")
    print("\nGuesses (counted: X wrong, OK right, . not counted)")
    for x in g["guesses"]:
        mark = "OK" if x["correct"] else ("X " if x["counted"] else ". ")
        print(f"  R{x['round']} {_t(x['at'])} {'Pip' if x['guesser'] == 'pal' else 'you':3} {mark} "
              f"{str(x['guess']):18} {x['note'][:34]:34} \"{x['text'][:70]}\"")
    lat = g.get("latencies") or []
    if lat:
        print(f"\nLatency (you stop talking -> Pip starts): median {median(lat):.2f}s, "
              f"max {max(lat):.2f}s over {len(lat)} turns")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
