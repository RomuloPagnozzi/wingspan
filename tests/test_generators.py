from lab.generators import count_games, get_generator

CONFIG = {
    "mode": "continuous",
    "seeds": {"start": 500, "count": 6},
    "matchups": [[{"strategy": "random", "label": "a"}, {"strategy": "random", "label": "b"}]],
}


def test_continuous_with_seeds_plays_one_game_per_seed_and_stops():
    games = list(get_generator(CONFIG))
    assert count_games(CONFIG) == len(games) == 6
    assert [seed for _, seed, _ in games] == list(range(500, 506))  # a new deal every game
    for strategies, seed, labels in games:
        assert labels == ["a", "b"]
        assert [s.seed for s in strategies] == [2 * seed, 2 * seed + 1]  # reproducible, distinct


def test_continuous_without_seeds_is_open_ended():
    config = {k: v for k, v in CONFIG.items() if k != "seeds"}
    assert count_games(config) is None
    games = get_generator(config)
    assert len([next(games) for _ in range(20)]) == 20


def test_seeds_without_a_count_run_endlessly():
    config = CONFIG | {"seeds": {"start": 7}}
    assert count_games(config) is None
    games = get_generator(config)
    assert [next(games)[1] for _ in range(50)] == list(range(7, 57))


def test_a_games_scoring_side_is_fixed_by_its_seed():
    from lab.__main__ import scoring_for

    sides = [scoring_for(seed, 0.2) for seed in range(10_000)]
    assert sides == [scoring_for(seed, 0.2) for seed in range(10_000)]  # reproducible
    assert 0.18 < sides.count("blue") / len(sides) < 0.22
    assert {scoring_for(seed, 0.0) for seed in range(1000)} == {"green"}


def test_clock_seeds_start_from_the_current_time():
    import time

    before = int(time.time())
    first_seed = next(get_generator(CONFIG | {"seeds": {"start": "clock"}}))[1]
    assert before <= first_seed <= int(time.time())


# --- paired / vs_reference ---------------------------------------------------------------------

VS_REF = {
    "mode": "vs_reference",
    "base": {"strategy": "random"},
    "compare": {
        "reference_label": "ref",
        "reference": {"strategy": "random"},
        "values": [{"label": "a", "overrides": {"strategy": "random"}}, {"label": "b", "overrides": {"strategy": "random"}}],
    },
    "seeds": {"start": 100, "count": 3},
}


def test_vs_reference_plays_every_arm_on_a_seed_from_both_seats_before_the_next_seed():
    games = list(get_generator(VS_REF))
    assert count_games(VS_REF) == len(games) == 3 * 2 * 2
    assert [(seed, labels) for _, seed, labels in games[:4]] == [
        (100, ["a", "ref"]), (100, ["ref", "a"]), (100, ["b", "ref"]), (100, ["ref", "b"])
    ]
    assert [seed for _, seed, _ in games] == [s for s in (100, 101, 102) for _ in range(4)]  # seed-major
    for strategies, seed, _ in games:
        assert [s.seed for s in strategies] == [seed, seed]


def test_vs_reference_without_a_count_is_open_ended_and_balanced():
    config = VS_REF | {"seeds": {"start": 7}}
    assert count_games(config) is None
    games = get_generator(config)
    labels = [next(games)[2][0] for _ in range(40)]
    assert labels.count("a") == labels.count("b")  # interleaved: balanced at any stopping point


def test_paired_plays_every_pair_on_a_seed_before_the_next_seed():
    config = {
        "mode": "paired",
        "base": {"strategy": "random"},
        "compare": {"values": [{"label": x, "overrides": {"strategy": "random"}} for x in "xyz"]},
        "seeds": {"start": 1, "count": 2},
    }
    games = list(get_generator(config))
    assert count_games(config) == len(games) == 3 * 2 * 2  # 3 pairs, 2 seeds, 2 seats
    assert [seed for _, seed, _ in games] == [1] * 6 + [2] * 6
    assert [labels for _, _, labels in games[:2]] == [["x", "y"], ["y", "x"]]


def test_config_validation_rejects_bad_seeds_and_reference():
    import pytest

    from lab.generators import ConfigError, validate_config

    validate_config(VS_REF)
    for bad in (
        VS_REF | {"seeds": {"count": 0}},
        VS_REF | {"seeds": {"start": "soon"}},
        VS_REF | {"compare": VS_REF["compare"] | {"reference": {"simulations": 5}}},  # no strategy name
        VS_REF | {"compare": {k: v for k, v in VS_REF["compare"].items() if k != "reference"}},  # no reference
    ):
        with pytest.raises(ConfigError):
            validate_config(bad)


# --- results -------------------------------------------------------------------------------------


def test_winner_label_and_summary_use_labels_not_seats():
    import pandas as pd

    from lab.summary import summarize

    # Two seeds; arm "a" vs "ref" from both seats each: a wins 3, one tie (equal score and food)
    rows = []
    for gid, seed, a_pos, a_score, ref_score, a_wins, tie in [
        ("g1", 1, 1, 80, 70, True, False), ("g2", 1, 2, 75, 70, True, False),
        ("g3", 2, 1, 70, 70, False, True), ("g4", 2, 2, 90, 60, True, False),
    ]:
        rows.append({"game_id": gid, "game_seed": seed, "arm_label": "a", "player_position": a_pos,
                     "total_score": a_score, "is_winner": a_wins, "duration_s": 2.0})
        rows.append({"game_id": gid, "game_seed": seed, "arm_label": "ref", "player_position": 3 - a_pos,
                     "total_score": ref_score, "is_winner": not a_wins and not tie, "duration_s": 2.0})
    table = summarize(pd.DataFrame(rows))
    assert len(table) == 1
    r = table.iloc[0]
    assert (r.arm, r.opponent, r.games, r.seeds) == ("a", "ref", 4, 2)
    assert r.win_rate == (3 + 0.5) / 4
    assert r.score_diff == (10 + 5 + 0 + 30) / 4
    assert r.per_seed_diff == ((10 + 5) / 2 + (0 + 30) / 2) / 2


def test_tuning_rejects_unknown_params():
    import pytest

    from lab.tune.objective import arm_spec

    assert arm_spec({"simulations": 50}, {"exploration_constant": 1.0})["strategy"] == "mcts"
    with pytest.raises(ValueError, match="simulatons"):
        arm_spec({"simulatons": 50}, {})
