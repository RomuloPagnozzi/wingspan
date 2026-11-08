import json
from datetime import datetime, timedelta, timezone

import lab.cloud_agent as agent
from lab.data import GamesWriter
from lab.simulation import simulate_game
from wingspan.ai import RandomStrategy


def test_saved_games_count_closed_parts_only(tmp_path):
    runs = tmp_path / "runs"
    with GamesWriter(runs, "run", rotate=2) as games:
        for seed in (40, 41, 42):
            result, _ = simulate_game([RandomStrategy(seed=1), RandomStrategy(seed=2)], seed, ["a", "b"])
            games.add_game(result)
        assert agent.games_saved(runs) == (2, 41)  # the third game is still in the open .tmp part
    assert agent.games_saved(runs) == (3, 42)  # closed at the end of the run
    assert agent.games_saved(tmp_path / "empty") == (0, None)


def test_the_guard_waits_an_hour_past_the_deadline(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "CONTROL", tmp_path)
    marker = tmp_path / "destroyed"
    (tmp_path / "agent.json").write_text(json.dumps({"destroy": {"dry_run_file": str(marker)}}))
    for minutes_past, destroyed in ((-5, False), (30, False), (61, True)):
        deadline = datetime.now(timezone.utc) - timedelta(minutes=minutes_past)
        (tmp_path / "deadline").write_text(deadline.isoformat())
        agent.guard()
        assert marker.exists() == destroyed, minutes_past
