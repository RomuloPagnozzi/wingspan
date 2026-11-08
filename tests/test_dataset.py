import math

import numpy as np
import pytest

from lab.data import DecisionsWriter, GamesWriter
from lab.dataset import build, load
from lab.simulation import simulate_game
from wingspan.ai import RandomStrategy
from wingspan.ai.encoding import PHASES, action_bird_ids, encode_action, encode_obs
from wingspan.engine.actions import get_actions
from wingspan.engine.core import initiate_state
from wingspan.engine.engine import transition_state


def players(seed):
    return [RandomStrategy(seed=seed), RandomStrategy(seed=seed + 100)]


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    """Two random games recorded by the lab's own writers, then built into a dataset."""
    root = tmp_path_factory.mktemp("run")
    with GamesWriter(root, "run") as games, DecisionsWriter(root, "run") as decisions:
        for seed in (3, 4):  # seed 4 is a 37-37 tie broken by leftover food
            result, recorded = simulate_game(players(seed), seed, ["a", "b"], record_decisions=True)
            games.add_game(result)
            decisions.add_game_decisions(recorded)
    build([root / "run"], root / "dataset", workers=2)
    return load(root / "dataset")


def test_every_stored_decision_matches_a_fresh_encoding(dataset):
    arrays, meta = dataset
    i = 0
    for seed in meta["seeds"]:  # games in dataset order; replay each with the same players
        bots, state = players(seed), initiate_state(2, seed=seed)
        while actions := get_actions(state):
            action = bots[state.current_player_index].select_action(state, actions)
            if len(actions) > 1:
                obs = encode_obs(state, state.current_player_index)
                assert np.array_equal(arrays["obs"][i], np.array(obs.flat(), np.float16))
                assert list(arrays["hand"][slice(*arrays["hand_off"][i : i + 2])]) == obs.hand
                assert list(arrays["tray"][slice(*arrays["tray_off"][i : i + 2])]) == obs.tray
                a0, a1 = arrays["act_off"][i : i + 2]
                assert a1 - a0 == len(actions)
                for j, move in zip(range(a0, a1), actions):
                    assert np.array_equal(arrays["act"][j], np.array(encode_action(state, move), np.float16))
                    assert list(arrays["act_birds"][slice(*arrays["act_birds_off"][j : j + 2])]) == action_bird_ids(move)
                    assert arrays["visits"][j] == 0 and math.isnan(arrays["q"][j])  # random players: no search
                assert actions[arrays["taken"][i]] == action
                assert PHASES[arrays["phase"][i]] == state.game_phase.value
                assert arrays["player"][i] == state.current_player_index
                i += 1
            state = transition_state(state, action)
    assert i == meta["n_decisions"] == len(arrays["obs"])


def test_results_are_from_the_deciders_seat(dataset):
    arrays, _ = dataset
    won, lost = arrays["outcome"] == 1, arrays["outcome"] == -1
    assert won.any() and lost.any()
    assert (arrays["score"][won] >= arrays["opp_score"][won]).all()  # ties go to leftover food
    assert (arrays["score"][lost] <= arrays["opp_score"][lost]).all()


def test_a_rotating_run_writes_complete_parts_that_build_into_one_dataset(tmp_path):
    with GamesWriter(tmp_path, "run", rotate=2) as games, DecisionsWriter(tmp_path, "run", rotate=2) as decisions:
        for seed in (5, 6, 7):
            result, recorded = simulate_game(players(seed), seed, ["a", "b"], record_decisions=True)
            games.add_game(result)
            decisions.add_game_decisions(recorded)
            if seed == 6:  # mid-run: the first two games are in a closed, complete part
                assert sorted(p.name for p in (tmp_path / "run").glob("games_*")) == ["games_0000.parquet"]
    run = tmp_path / "run"
    assert sorted(p.name for p in run.iterdir()) == [
        "decisions_0000.parquet", "decisions_0001.parquet", "games_0000.parquet", "games_0001.parquet",
    ]  # fmt: skip
    build([run], tmp_path / "dataset", workers=1)
    assert sorted(load(tmp_path / "dataset")[1]["seeds"]) == [5, 6, 7]


def test_blue_games_are_replayed_and_encoded_as_blue(tmp_path):
    from wingspan.ai.encoding import shared_feature_names

    with GamesWriter(tmp_path, "run") as games, DecisionsWriter(tmp_path, "run") as decisions:
        for seed, scoring in ((8, "blue"), (9, "green")):
            result, recorded = simulate_game(players(seed), seed, ["a", "b"], record_decisions=True, scoring=scoring)
            games.add_game(result)
            decisions.add_game_decisions(recorded)
    build([tmp_path / "run"], tmp_path / "dataset", workers=1)  # a wrong side would fail the replay check or encode wrongly
    arrays, meta = load(tmp_path / "dataset")
    n_player = len(meta["player_features"])
    green = arrays["obs"][:, 2 * n_player + list(shared_feature_names()).index("scoring_green")]
    by_seed = {meta["seeds"][g]: set(green[arrays["game"] == g].tolist()) for g in range(len(meta["games"]))}
    assert by_seed == {8: {0.0}, 9: {1.0}}
