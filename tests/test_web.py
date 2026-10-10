"""Web server: players, seats, persistence by replay, spectators, debug mode, leaderboard."""

import random
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from wingspan.web.leaderboard import leaderboard
from wingspan.web.server import create_app, parse_args
from wingspan.web.store import Store, backup


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "games.db")


def client(db, user="ana@example.com", *extra):
    args = parse_args(
        [
            "--db",
            db,
            "--user",
            user,
            "--sims",
            "5",
            "--workers",
            "1",
            "--no-browser",
            *extra,
        ]
    )
    return TestClient(create_app(args))


def play(c, state, moves=10**6):
    """Random legal moves for us, AI steps otherwise, until `moves` requests or the game ends."""
    gid = state["id"]
    for _ in range(moves):
        if state["game_over"]:
            break
        if state["actions"]:
            body = {
                "index": random.randrange(len(state["actions"])),
                "version": state["version"],
            }
            state = c.post(f"/api/games/{gid}/act", json=body).json()
        else:
            state = c.post(f"/api/games/{gid}/step").json()
    return state


def new_game(c, **body):
    c.post("/api/me", json={"name": "Ana"})
    return c.post("/api/games", json=body).json()


def strip(state):
    return {
        k: v for k, v in state.items() if k not in ("actions", "prompt", "bonus_offer")
    }


def test_name_required_before_playing(db):
    with client(db) as c:
        assert c.get("/api/me").json()["name"] is None
        assert c.post("/api/games", json={}).status_code == 409
        assert c.post("/api/me", json={"name": "Ana"}).json()["name"] == "Ana"
        assert (
            c.post("/api/games", json={"opponents": 3, "scoring": "blue"}).status_code
            == 200
        )


def test_game_resumes_after_restart(db):
    with client(db) as c:
        state = play(c, new_game(c, opponents=2), 40)
    with client(db) as c:  # a fresh server: empty memory, same database
        resumed = c.get(f"/api/games/{state['id']}").json()
    assert strip(resumed) == strip(state)
    assert [p["name"] for p in resumed["players"]] == [
        "You",
        "Dodo.exe 2",
        "Dodo.exe 3",
    ]


def test_stale_action_is_rejected(db):
    with client(db) as c:
        state = new_game(c)
        while not state["actions"]:
            state = c.post(f"/api/games/{state['id']}/step").json()
        stale = {"index": 0, "version": state["version"] - 1}
        assert c.post(f"/api/games/{state['id']}/act", json=stale).status_code == 409


def test_opponent_bonus_points_stay_hidden_until_game_over(db):
    with client(db) as c:
        state = play(c, new_game(c), 60)
        me, opp = state["players"][state["human"]], state["players"][1 - state["human"]]
        assert isinstance(me["score"]["bonus"], int)
        assert opp["score"]["bonus"] is None
        # the total must not reveal the bonus either
        assert opp["score"]["total"] == sum(
            v for k, v in opp["score"].items() if k not in ("total", "bonus")
        )
        state = play(c, state)
        assert all(isinstance(p["score"]["bonus"], int) for p in state["players"])


def test_spectator_sees_public_info_only(db):
    with client(db) as c:
        state = play(c, new_game(c), 20)
        c.post("/api/me", json={"name": "Ana B"})  # renamed after the game started
    with client(db, "bo@example.com") as c:
        seen = c.get(f"/api/games/{state['id']}").json()
        assert seen["spectating"] and not seen["actions"]
        assert isinstance(seen["players"][0]["hand"], int)  # Ana's hand stays hidden
        assert seen["players"][0]["name"] == "Ana B"
        assert (
            c.post(
                f"/api/games/{state['id']}/act",
                json={"index": 0, "version": seen["version"]},
            ).status_code
            == 409
        )
        assert c.post(f"/api/games/{state['id']}/step").status_code == 403
        assert c.get("/api/games").json() == []  # not Bo's game...
        assert (
            len(c.get("/api/games?scope=all").json()) == 1
        )  # ...but listed for everyone


def test_debug_mode_plays_owner_seat_without_writing(db, tmp_path):
    with client(db) as c:
        state = play(c, new_game(c), 20)
    copy = str(tmp_path / "copy.db")
    backup(db, copy)
    before = open(copy, "rb").read()
    with client(copy, "me@localhost", "--debug") as c:
        seen = c.get(f"/api/games/{state['id']}").json()
        assert not seen["spectating"] and isinstance(seen["players"][0]["hand"], list)
        play(c, seen, 20)
    assert open(copy, "rb").read() == before


def test_finished_game_reaches_the_leaderboard(db):
    with client(db) as c:
        state = play(c, new_game(c))
        assert state["game_over"]
        board = c.get("/api/leaderboard").json()
        mine = c.get("/api/games").json()[0]
    assert mine["status"] == "finished" and len(mine["result"]) == 2
    totals = board["humans_vs_ai"]["all"]
    assert totals["humans"] + totals["ai"] + totals["draws"] == 1
    assert board["players"][0]["name"] == "Ana" and board["players"][0]["games"] == 1
    assert board["bots"][0]["games"] == 1


def summary(gid, seats, scores, food=None, status="finished", days_ago=0):
    keys = list(zip(scores, food or [0] * len(scores))) if scores else []
    updated = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return {
        "id": gid,
        "status": status,
        "updated": updated,
        "seats": seats,
        "result": (
            [
                {"score": s, "food": f, "place": 1 + sum(o > (s, f) for o in keys)}
                for s, f in keys
            ]
            if status == "finished"
            else None
        ),
    }


def test_leaderboard_rules():
    ana = {"kind": "human", "uid": "ana", "name": "Ana"}
    v1 = {"kind": "ai", "bot": "v1", "name": "V1"}
    games = [
        summary("a", [ana, v1], [80, 70]),  # Ana wins
        summary(
            "b", [ana, v1, v1, v1], [60, 75, 50, 40]
        ),  # V1 wins once, though it held 3 seats
        summary("c", [ana, v1], [70, 70], food=[2, 2]),  # full tie: a draw
        summary(
            "d", [ana, v1], [70, 70], food=[3, 1]
        ),  # leftover food breaks the tie: Ana
        summary("e", [ana, v1], None, status="in_progress", days_ago=10),  # abandoned
    ]
    board = leaderboard(games, {"ana": "Ana B."}, {"v1": "MCTS v1"}, champion="v1")
    assert board["humans_vs_ai"]["all"] == {"humans": 2, "ai": 1, "draws": 1}
    [ana_row] = board["players"]
    assert (
        ana_row["name"],
        ana_row["games"],
        ana_row["wins"],
        ana_row["draws"],
        ana_row["abandoned"],
    ) == ("Ana B.", 4, 2, 1, 1)
    [bot_row] = board["bots"]
    assert (bot_row["name"], bot_row["games"], bot_row["wins"], bot_row["draws"]) == (
        "MCTS v1",
        4,
        1,
        1,
    )
    assert board["records"]["biggest_win"]["margin"] == 10


def test_uploaded_avatar_is_reencoded_and_shown(db):
    import io

    from PIL import Image

    photo = io.BytesIO()
    Image.new("RGB", (300, 200), "teal").save(photo, "PNG")  # not square
    with client(db) as c:
        assert (
            c.post("/api/me/avatar", content=photo.getvalue()).status_code == 409
        )  # name first
        c.post("/api/me", json={"name": "Ana"})
        assert c.post("/api/me/avatar", content=b"not an image").status_code == 422
        url = c.post("/api/me/avatar", content=photo.getvalue()).json()["avatar"]
        assert (
            url.startswith("/api/avatar/") and "ana" not in url
        )  # never exposes the email
        served = c.get(url)
        assert served.headers["content-type"] == "image/webp"
        assert Image.open(io.BytesIO(served.content)).size == (256, 256)

        state = c.post("/api/games", json={}).json()
        assert state["players"][0]["avatar"] == url
        assert c.get("/api/games").json()[0]["seats"][0]["avatar"] == url

        assert c.delete("/api/me/avatar").json()["avatar"] is None
        assert (
            c.get(url).status_code == 404
        )  # the old picture is gone, not just unlinked


def test_bug_report_reopens_the_reported_moment(db, tmp_path):
    from wingspan.engine.core import IdAction
    from wingspan.web.session import describe

    assert describe(IdAction("choose_player", 1), ["You", "Dodo.exe 2"]) == "Dodo.exe 2"
    with client(db) as c:
        state = play(c, new_game(c), 30)
        moment = c.get(f"/api/games/{state['id']}").json()
        report = {
            "text": "the fish vanished",
            "game": state["id"],
            "version": moment["version"],
            "context": {"phase": moment["phase"]},
        }
        assert c.post("/api/reports", json=report).json() == {"ok": True}
        play(c, moment, 20)  # the game moves on after the report
    copy = str(tmp_path / "copy.db")
    backup(db, copy)
    with client(copy, "me@localhost", "--debug") as c:
        reopened = c.get(f"/api/games/{state['id']}@{moment['version']}").json()
        assert c.get(f"/api/games/{state['id']}@nope").status_code == 404
    assert reopened["id"] == f"{state['id']}@{moment['version']}"
    assert {**strip(reopened), "id": None} == {**strip(moment), "id": None}
    [saved] = Store(copy, readonly=True).reports()
    assert (saved["uid"], saved["text"], saved["version"]) == (
        "ana@example.com",
        "the fish vanished",
        moment["version"],
    )
