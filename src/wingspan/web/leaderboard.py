"""Humans vs AI: standings computed from game summaries.

A game is won by the seat placing 1st alone (score, then leftover food); a shared 1st is a draw.
Games left unfinished for ABANDONED_DAYS count as abandoned and are shown, not scored.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone

ABANDONED_DAYS = 7


def is_abandoned(summary: dict) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(days=ABANDONED_DAYS)
    return (
        summary["status"] != "finished"
        and datetime.fromisoformat(summary["updated"]) < cutoff
    )


def winner(summary: dict) -> int | None:
    """The seat that won, or None for a draw."""
    firsts = [i for i, r in enumerate(summary["result"]) if r["place"] == 1]
    return firsts[0] if len(firsts) == 1 else None


def leaderboard(
    summaries: list[dict],
    names: dict[str, str],
    bot_names: dict[str, str],
    champion: str,
) -> dict:
    humans_vs_ai = {
        "all": {"humans": 0, "ai": 0, "draws": 0},
        "champion": {"humans": 0, "ai": 0, "draws": 0},
    }
    players = defaultdict(
        lambda: {"games": 0, "wins": 0, "draws": 0, "scores": [], "abandoned": 0}
    )
    bots = defaultdict(lambda: {"games": 0, "wins": 0, "draws": 0, "scores": []})
    records = {"high_score": None, "biggest_win": None}

    for g in summaries:
        humans = [i for i, s in enumerate(g["seats"]) if s["kind"] == "human"]
        if is_abandoned(g):
            for i in humans:
                players[g["seats"][i]["uid"]]["abandoned"] += 1
        if g["status"] != "finished":
            continue
        w = winner(g)
        side = "draws" if w is None else "humans" if w in humans else "ai"
        bot_ids = {s["bot"] for s in g["seats"] if s["kind"] == "ai"}
        humans_vs_ai["all"][side] += 1
        if champion in bot_ids:
            humans_vs_ai["champion"][side] += 1

        # A bot fielding several seats in one game still played (and won or lost) one game
        for bot in bot_ids:
            mine = [i for i, s in enumerate(g["seats"]) if s.get("bot") == bot]
            stats = bots[bot]
            stats["games"] += 1
            stats["wins"] += w in mine
            stats["draws"] += w is None and any(
                g["result"][i]["place"] == 1 for i in mine
            )
            stats["scores"] += [g["result"][i]["score"] for i in mine]

        for i, (seat, r) in enumerate(zip(g["seats"], g["result"])):
            if seat["kind"] == "human":
                stats = players[seat["uid"]]
                stats["games"] += 1
                stats["wins"] += w == i
                stats["draws"] += w is None and r["place"] == 1
                stats["scores"].append(r["score"])
                name = names.get(seat["uid"], seat["name"])
                if (
                    not records["high_score"]
                    or r["score"] > records["high_score"]["score"]
                ):
                    records["high_score"] = {
                        "name": name,
                        "score": r["score"],
                        "game": g["id"],
                        "date": g["updated"],
                    }
                if w == i:
                    margin = r["score"] - max(
                        o["score"] for j, o in enumerate(g["result"]) if j != i
                    )
                    if (
                        not records["biggest_win"]
                        or margin > records["biggest_win"]["margin"]
                    ):
                        records["biggest_win"] = {
                            "name": name,
                            "margin": margin,
                            "game": g["id"],
                            "date": g["updated"],
                        }

    def table(rows: dict, label) -> list[dict]:
        out = []
        for key, s in rows.items():
            scores = s.pop("scores")
            out.append(
                {
                    "id": key,
                    "name": label(key),
                    **s,
                    "win_rate": s["wins"] / s["games"] if s["games"] else None,
                    "avg_score": sum(scores) / len(scores) if scores else None,
                    "best_score": max(scores, default=None),
                }
            )
        return sorted(
            out, key=lambda r: (r["wins"], r["win_rate"] or 0, r["games"]), reverse=True
        )

    return {
        "humans_vs_ai": humans_vs_ai,
        "players": table(players, lambda uid: names.get(uid, uid.split("@")[0])),
        "bots": table(bots, lambda bot: bot_names.get(bot, bot)),
        "records": records,
    }
