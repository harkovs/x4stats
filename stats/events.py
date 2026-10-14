import contextlib
import sqlite3
import threading
import time
from pathlib import Path

# Columns stored per event, in table order. asset_id is the logbook entry's component, the id of the own asset.
EVENT_FIELDS = ["time", "kind", "name", "code", "location", "commander", "attacker", "title", "text", "asset_id"]
# Last known state of the asset of an event, copied from the asset history when the event is first seen
SNAPSHOT_FIELDS = ["ship_type", "default_order", "orders"]
# Columns stored per own ship/station
ASSET_FIELDS = ["code", "name", "ship_type", "commander", "default_order", "orders"]
# events columns added after the first version, older databases get them on startup
ADDED_EVENT_FIELDS = ["asset_id"] + SNAPSHOT_FIELDS

INSERT_EVENT = (
    f"INSERT INTO events (game_guid, {', '.join(EVENT_FIELDS + SNAPSHOT_FIELDS)}, first_seen) "
    f"VALUES (?, {', '.join('?' for _ in EVENT_FIELDS + SNAPSHOT_FIELDS)}, ?)")
# Events stored before asset ids were kept get them (and the asset state) once they are seen in a save again
BACKFILL_EVENT = (
    f"UPDATE events SET asset_id = ?, {', '.join(f'{f} = ?' for f in SNAPSHOT_FIELDS)}, "
    f"commander = COALESCE(commander, ?), code = COALESCE(code, ?) "
    f"WHERE game_guid = ? AND time = ? AND title = ?")
# The newest save is the current timeline, also when it is older in game time (an earlier save was loaded)
UPSERT_ASSET = (
    f"INSERT INTO assets (game_guid, id, {', '.join(ASSET_FIELDS)}, last_seen) "
    f"VALUES (?, ?, {', '.join('?' for _ in ASSET_FIELDS)}, ?) "
    f"ON CONFLICT (game_guid, id) DO UPDATE SET "
    f"{', '.join(f'{f} = excluded.{f}' for f in ASSET_FIELDS)}, last_seen = excluded.last_seen")

class EventStore:
    """Local SQLite history of destroyed/attacked events, per game (savegame guid).

    The game trims its logbook, so events are kept here once seen. An event is identified by game, game time and
    message title, so reloading the same or an older save never duplicates it.

    It also keeps the last known commander and orders of every own ship and station, so a lost asset (which is gone
    from the save that reports its loss) can still be shown with what it was doing.
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
            existing = {r["name"] for r in con.execute("PRAGMA table_info(events)")}
            for field in ADDED_EVENT_FIELDS:
                if field not in existing:
                    con.execute(f"ALTER TABLE events ADD COLUMN {field} TEXT")
            # last_seen is the game time of the last save the asset was in
            con.execute(f"""
                CREATE TABLE IF NOT EXISTS assets (
                    game_guid  TEXT NOT NULL,
                    id         TEXT NOT NULL,
                    {', '.join(f'{f} TEXT' for f in ASSET_FIELDS)},
                    last_seen  REAL NOT NULL,
                    PRIMARY KEY (game_guid, id)
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

    # Store events of a game and the own assets (X4stats.get_fleet()) of the save at game_time. Returns the events
    # that were not known yet, with the last known state of their asset. On the first import of a game the whole
    # backlog is new, so is_first_import lets callers skip notifying about old history.
    def record(self, game_guid, events, assets=(), game_time=None):
        if not game_guid:
            return [], False
        now = time.time()
        new = []
        with self._lock, self.__connect() as con:
            # stored asset id per known event
            known = {(r["time"], r["title"]): r["asset_id"] for r in con.execute(
                "SELECT time, title, asset_id FROM events WHERE game_guid = ?", (game_guid,))}
            is_first_import = not known and con.execute(
                "SELECT 1 FROM assets WHERE game_guid = ? LIMIT 1", (game_guid,)).fetchone() is None
            # the logbook keeps old entries, only look at new ones and old ones that can get their asset now
            pending = [e for e in events if (e["time"], e["title"]) not in known
                       or (known[(e["time"], e["title"])] is None and e.get("asset_id"))]
            if pending:
                # state from the previous load, from before the events of this save
                stored = [dict(r) for r in con.execute("SELECT * FROM assets WHERE game_guid = ?", (game_guid,))]
                current_ids = {a["id"] for a in assets}
                # a destroyed asset is gone from the save reporting it, any match in that save is another asset
                lookups = {"destroyed": self.__asset_lookup([a for a in stored if a["id"] not in current_ids]),
                           "attacked": self.__asset_lookup(list(assets) + stored)}
            for e in pending:
                e = {**e, **self.__snapshot(lookups.get(e["kind"], lookups["attacked"]), e)}
                key = (e["time"], e["title"])
                if key in known:
                    con.execute(BACKFILL_EVENT, [e["asset_id"]] + [e.get(f) for f in SNAPSHOT_FIELDS]
                                + [e.get("commander"), e.get("code"), game_guid, e["time"], e["title"]])
                else:
                    con.execute(INSERT_EVENT, [game_guid] + [e.get(f) for f in EVENT_FIELDS + SNAPSHOT_FIELDS]
                                + [now])
                    # same time and title twice in one logbook
                    known[key] = e.get("asset_id")
                    new.append(e)
            if game_time is not None:
                con.executemany(UPSERT_ASSET, [[game_guid, a["id"]] + [a.get(f) for f in ASSET_FIELDS] + [game_time]
                                               for a in assets])
        return new, is_first_import

    # id, code and name -> asset; later entries win, so stored state goes after the current save
    @staticmethod
    def __asset_lookup(assets):
        lookup = {"id": {}, "code": {}, "name": {}}
        for a in assets:
            for key, by_key in lookup.items():
                if a.get(key):
                    by_key[a[key]] = a
        return lookup

    # Last known state of the asset of an event. Matched on the asset id from the logbook, else on the code (only in
    # some messages), else on the name. Name is only tried without id and code, those identify one asset. The
    # logbook commander is kept when the message has one.
    @staticmethod
    def __snapshot(lookup, event):
        if event.get("asset_id"):
            a = lookup["id"].get(event["asset_id"])
        elif event.get("code"):
            a = lookup["code"].get(event["code"])
        else:
            a = lookup["name"].get(event.get("name"))
        if not a:
            return {}
        return {**{f: a[f] for f in SNAPSHOT_FIELDS}, "asset_id": a["id"],
                "commander": event.get("commander") or a["commander"], "code": event.get("code") or a["code"]}

    # All events of a game, newest first
    def get_events(self, game_guid):
        if not game_guid:
            return []
        with self.__connect() as con:
            rows = con.execute(
                "SELECT * FROM events WHERE game_guid = ? ORDER BY time DESC", (game_guid,)).fetchall()
        return [dict(r) for r in rows]
