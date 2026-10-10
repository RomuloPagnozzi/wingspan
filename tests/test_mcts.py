"""MCTS must model the opponent as playing for itself, not for the searching player.

Toy game with a known minimax answer, run through the real search code:
  P0 "safe"  -> ends 5:5
  P0 "risky" -> P1 "gift" -> ends 10:0, or P1 "punish" -> ends 0:10
A rational P1 punishes, so "safe" is correct.
"""

import copy
from types import SimpleNamespace as NS

import pytest

import wingspan.ai.mcts as mcts
from wingspan.ai import MCTSStrategy, ValueFunction

FINAL = {("safe",): (5, 5), ("risky", "gift"): (10, 0), ("risky", "punish"): (0, 10)}
MOVES = {(): ["safe", "risky"], ("risky",): ["gift", "punish"]}


def _state(path: tuple) -> NS:
    totals = FINAL.get(path, (0, 0))
    return NS(
        path=path,
        current_player_index=0 if not path else 1,
        players=[NS(score=NS(total=t), food={}) for t in totals],
    )


@pytest.fixture
def toy_game(monkeypatch):
    def step(s, a):
        return _state(s.path + (a,))

    monkeypatch.setattr(mcts, "get_actions", lambda s: list(MOVES.get(s.path, [])))
    monkeypatch.setattr(mcts, "transition_state", step)
    monkeypatch.setattr(mcts, "transition_state_inplace", step)
    monkeypatch.setattr(mcts, "copy_state", copy.deepcopy)
    monkeypatch.setattr(mcts, "redeterminize", lambda s, p, rng: copy.deepcopy(s))


@pytest.mark.parametrize("determinize", [False, True])
@pytest.mark.parametrize("value_function", list(ValueFunction))
def test_opponent_plays_for_itself(toy_game, determinize, value_function):
    strategy = MCTSStrategy(
        simulations=500, value_function=value_function, determinize=determinize, seed=0
    )
    assert strategy.select_action(_state(()), ["safe", "risky"]) == "safe"
