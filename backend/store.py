"""SQLite persistence. One table, one row per game, the game stored as JSON.

Every request does load -> mutate -> save inside one lock, so state survives a backend
restart (it is persisted after every change) and two requests never interleave.
Reset everything: delete the file at DB_PATH (default data/pictionary.db).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional

from backend.game import ACTIVE_STATES, Game


class Store:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.RLock()
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS games ("
            " id TEXT PRIMARY KEY, conversation_id TEXT, state TEXT, data TEXT, updated_at REAL)"
        )
        self.db.execute("CREATE INDEX IF NOT EXISTS games_conv ON games(conversation_id)")
        self.db.commit()

    def save(self, g: Game) -> None:
        with self.lock:
            self.db.execute(
                "INSERT OR REPLACE INTO games (id, conversation_id, state, data, updated_at) VALUES (?,?,?,?,?)",
                (g.id, g.conversation_id, g.state, json.dumps(g.to_dict()), time.time()),
            )
            self.db.commit()

    def get(self, game_id: str) -> Optional[Game]:
        with self.lock:
            row = self.db.execute("SELECT data FROM games WHERE id=?", (game_id,)).fetchone()
        return Game.from_dict(json.loads(row[0])) if row else None

    def get_by_conversation(self, conversation_id: str) -> Optional[Game]:
        with self.lock:
            row = self.db.execute("SELECT data FROM games WHERE conversation_id=?", (conversation_id,)).fetchone()
        return Game.from_dict(json.loads(row[0])) if row else None

    def active_ids(self) -> List[str]:
        with self.lock:
            rows = self.db.execute(
                f"SELECT id FROM games WHERE state IN ({','.join('?' * len(ACTIVE_STATES))})", ACTIVE_STATES
            ).fetchall()
        return [r[0] for r in rows]

    @contextmanager
    def transaction(self, game_id: str) -> Iterator[Optional[Game]]:
        """with store.transaction(id) as g: ... mutate g ...  (saved on exit)"""
        with self.lock:
            g = self.get(game_id)
            yield g
            if g is not None:
                self.save(g)
