"""SQLite persistence: games survive restarts, and their history feeds the menu and leaderboard.

Each game is one self-contained JSON document: `config` (seats, scoring side, seed) + `actions`
(the lab's format: str() of each applied action) rebuild it by replay. A small `summary` sits
next to it so listings never parse the full documents. Moving to another database later is a
copy of these rows.
"""

import json
import secrets
import sqlite3
import threading
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (id TEXT PRIMARY KEY, updated TEXT NOT NULL, summary TEXT NOT NULL, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users (uid TEXT PRIMARY KEY, name TEXT NOT NULL, created TEXT NOT NULL, avatar TEXT);
CREATE TABLE IF NOT EXISTS avatars (id TEXT PRIMARY KEY, image BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY, created TEXT NOT NULL, uid TEXT NOT NULL, report TEXT NOT NULL);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str, readonly: bool = False):
        self.readonly = (
            readonly  # debugging a copy of the live database must never write to it
        )
        uri = f"file:{path}?mode=ro" if readonly else f"file:{path}"
        self.db = sqlite3.connect(uri, uri=True, check_same_thread=False)
        self.lock = threading.Lock()
        if not readonly:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript(SCHEMA)
            if "avatar" not in [
                c[1] for c in self.db.execute("PRAGMA table_info(users)")
            ]:  # added later
                self.db.execute("ALTER TABLE users ADD COLUMN avatar TEXT")

    def _query(self, sql: str, *args) -> list[tuple]:
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    def _write(self, sql: str, *args):
        if self.readonly:
            return
        with self.lock, self.db:
            self.db.execute(sql, args)

    def load(self, gid: str) -> dict | None:
        rows = self._query("SELECT doc FROM games WHERE id = ?", gid)
        return json.loads(rows[0][0]) if rows else None

    def save(self, gid: str, doc: dict, summary: dict):
        self._write(
            "INSERT OR REPLACE INTO games (id, updated, summary, doc) VALUES (?, ?, ?, ?)",
            gid,
            summary["updated"],
            json.dumps(summary),
            json.dumps(doc),
        )

    def summaries(self) -> list[dict]:
        """Every game's summary, most recently played first."""
        return [
            json.loads(s)
            for (s,) in self._query("SELECT summary FROM games ORDER BY updated DESC")
        ]

    def profiles(self) -> dict[str, dict]:
        """uid -> {name, avatar}: what players chose to be shown as."""
        return {
            uid: {"name": name, "avatar": avatar}
            for uid, name, avatar in self._query("SELECT uid, name, avatar FROM users")
        }

    def set_name(self, uid: str, name: str):
        self._write(
            "INSERT INTO users (uid, name, created) VALUES (?, ?, ?) ON CONFLICT(uid) DO UPDATE SET name = excluded.name",
            uid,
            name,
            now(),
        )

    def set_avatar(self, uid: str, image: bytes | None):
        """Replace a player's picture. Each upload gets a new random id: it never reveals the email,
        and the new URL busts browser caches."""
        if self.readonly:
            return
        new = secrets.token_urlsafe(9) if image else None
        with self.lock, self.db:
            old = self.db.execute(
                "SELECT avatar FROM users WHERE uid = ?", (uid,)
            ).fetchone()
            if image:
                self.db.execute(
                    "INSERT INTO avatars (id, image) VALUES (?, ?)", (new, image)
                )
            self.db.execute("UPDATE users SET avatar = ? WHERE uid = ?", (new, uid))
            if old and old[0]:
                self.db.execute("DELETE FROM avatars WHERE id = ?", (old[0],))

    def add_report(self, uid: str, report: dict):
        """A player's bug report: their words plus where they were (game id and move number)."""
        self._write(
            "INSERT INTO reports (created, uid, report) VALUES (?, ?, ?)",
            now(),
            uid,
            json.dumps(report),
        )

    def reports(self) -> list[dict]:
        rows = self._query(
            "SELECT id, created, uid, report FROM reports ORDER BY id DESC"
        )
        return [
            {"id": i, "created": c, "uid": u, **json.loads(r)} for i, c, u, r in rows
        ]

    def avatar(self, avatar_id: str) -> bytes | None:
        rows = self._query("SELECT image FROM avatars WHERE id = ?", avatar_id)
        return rows[0][0] if rows else None


def backup(src: str, dest: str):
    """A consistent copy of a live database (a plain file copy can miss writes still in the WAL)."""
    with sqlite3.connect(src) as live, sqlite3.connect(dest) as copy:
        live.backup(copy)


if __name__ == "__main__":  # python -m wingspan.web.store reports <db>   (make reports)
    import sys

    _, command, path = sys.argv
    assert command == "reports", "usage: python -m wingspan.web.store reports <db>"
    reports = Store(path, readonly=True).reports()
    if not reports:
        print("No bug reports.")
    for r in reports:
        where = (
            f"make debug ID={r['game']} AT={r['version']}"
            if r.get("game")
            else "(not in a game)"
        )
        print(
            f"#{r['id']}  {r['created']}  {r['uid']}  (app {r.get('app_version')})\n  {r['text']}\n  {where}  {r.get('context') or ''}\n"
        )
