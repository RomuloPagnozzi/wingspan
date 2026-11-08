"""Running games in a worker pool gives exactly the games a single process plays."""

import pytest

pytest.importorskip("wingspan_rs")

from lab.__main__ import _work_iter  # noqa: E402
from lab.generators import get_generator  # noqa: E402
from lab.simulation import play_games  # noqa: E402

CONFIG = {
    "mode": "paired",
    "base": {"strategy": "mcts_rs", "determinize": True, "simulations": 30},
    "compare": {"values": [
        {"label": "delta", "overrides": {"value_function": "score_delta"}},
        {"label": "absolute", "overrides": {"value_function": "absolute_score"}},
    ]},
    "seeds": {"start": 1, "count": 2},
}


def _games(num_workers: int) -> dict:
    work = _work_iter(get_generator(CONFIG), total_games=None, record_decisions=False)
    return {
        idx: ([p.total_score for p in r.players], r.winner_label(), r.total_decisions)
        for r, _, idx in play_games(work, num_workers)
    }


def test_worker_count_does_not_change_the_games():
    sequential = _games(1)
    assert len(sequential) == 4  # 1 pair x 2 seeds x 2 seats
    assert _games(2) == sequential
