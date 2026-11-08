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
