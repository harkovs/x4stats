import contextlib
import sqlite3
import threading
import time
from pathlib import Path

# Columns stored per event, in table order
EVENT_FIELDS = ["time", "kind", "name", "code", "location", "commander", "attacker", "title", "text"]


class EventStore:
    """Local SQLite history of destroyed/attacked events, per game (savegame guid).

    The game trims its logbook, so events are kept here once seen. An event is identified by game, game time and
    message title, so reloading the same or an older save never duplicates it.
    """

    def __init__(self, db_path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        with self.__connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    game_guid  TEXT NOT NULL,
                    time       REAL NOT NULL,
                    kind       TEXT NOT NULL,
                    name       TEXT,
                    code       TEXT,
                    location   TEXT,
                    commander  TEXT,
                    attacker   TEXT,
                    title      TEXT NOT NULL,
                    text       TEXT,
                    first_seen REAL NOT NULL,
                    PRIMARY KEY (game_guid, time, title)
                )""")

    # Connection that commits on success and is always closed
    @contextlib.contextmanager
    def __connect(self):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    # Store events of a game. Returns the events that were not known yet. On the first import of a game the whole
    # backlog is new, so is_first_import lets callers skip notifying about old history.
    def record(self, game_guid, events):
        if not game_guid:
            return [], False
        now = time.time()
        new = []
        with self._lock, self.__connect() as con:
            is_first_import = con.execute(
                "SELECT COUNT(*) FROM events WHERE game_guid = ?", (game_guid,)).fetchone()[0] == 0
            for e in events:
                cur = con.execute(
                    f"INSERT OR IGNORE INTO events (game_guid, {', '.join(EVENT_FIELDS)}, first_seen) "
                    f"VALUES (?, {', '.join('?' for _ in EVENT_FIELDS)}, ?)",
                    [game_guid] + [e.get(f) for f in EVENT_FIELDS] + [now])
                if cur.rowcount:
                    new.append(e)
        return new, is_first_import

    # All events of a game, newest first
    def get_events(self, game_guid):
        if not game_guid:
            return []
        with self.__connect() as con:
            rows = con.execute(
                "SELECT * FROM events WHERE game_guid = ? ORDER BY time DESC", (game_guid,)).fetchall()
        return [dict(r) for r in rows]
