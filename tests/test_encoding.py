import random

from conftest import place_bird_on_board

from wingspan.ai.encoding import (
    ACTION_KINDS,
    GOALS,
    HABITATS,
    POWER_TEMPLATES,
    ROUNDS,
    action_bird_ids,
    action_feature_names,
    action_features,
    action_kind,
    bird_feature_names,
    bird_features,
    bird_table,
    bonus_feature_names,
    bonus_features,
    bonus_table,
    encode_action,
    encode_obs,
    encode_pending,
    encode_player,
    encode_public,
    pending_feature_names,
    pending_features,
    player_feature_names,
    player_features,
    public_feature_names,
    public_features,
    shared_feature_names,
)
from wingspan.engine.actions import get_actions
from wingspan.engine.core import (
    BIRD_REGISTRY,
    BONUS_REGISTRY,
    CostPayment,
    DrawCardsAction,
    EggMapAction,
    FoodMapAction,
    GamePhase,
    IdAction,
    PlayBirdAction,
    PowerExecution,
    SelectInitialAction,
    SimpleAction,
    TradeAction,
    init_registries,
    initiate_state,
    redeterminize,
)
from wingspan.engine.engine import transition_state

init_registries()


def group(features: dict[str, float], prefix: str) -> list[float]:
    return [v for k, v in features.items() if k.startswith(prefix)]


def test_every_card_has_a_full_row():
    assert len(bird_table()) == len(BIRD_REGISTRY) == 170
    assert all(len(row) == len(bird_feature_names()) for row in bird_table().values())
    assert len(bonus_table()) == len(BONUS_REGISTRY) == 26
    assert all(len(row) == len(bonus_feature_names()) for row in bonus_table().values())


def test_feature_names_are_unique():
    assert len(set(bird_feature_names())) == len(bird_feature_names())
    assert len(set(bonus_feature_names())) == len(bonus_feature_names())


def test_values_are_scaled():
    for row in [*bird_table().values(), *bonus_table().values()]:
        assert all(0.0 <= v <= 1.0 for v in row)


def test_bird_one_hot_groups():
    for card in BIRD_REGISTRY.values():
        f = bird_features(card)
        assert sum(group(f, "nest_")) == (1 if isinstance(card.nest, str) else 0)
        assert sum(group(f, "habitat_")) == len(card.habitats)
        assert sum(group(f, "power_color_")) == 1
        assert sum(group(f, "power_template_")) == 1


def test_birds_without_a_power():
    no_power = [
        c for c in BIRD_REGISTRY.values() if bird_features(c)["power_template_0"] == 1
    ]
    assert len(no_power) == 6
    assert all(bird_features(c)["power_color_none"] == 1 for c in no_power)
    assert len(group(bird_features(no_power[0]), "power_template_")) == len(
        POWER_TEMPLATES
    )


def test_or_cost_is_averaged_and_flagged():
    robin = next(c for c in BIRD_REGISTRY.values() if c.name == "American Robin")
    f = bird_features(robin)  # 1 invertebrate OR 1 fruit
    assert f["cost_is_or"] == 1
    assert f["cost_invertebrate"] == f["cost_fruit"] == 1 / 2 / 3
    assert f["cost_min_total"] == 1 / 3

    bittern = next(c for c in BIRD_REGISTRY.values() if c.name == "American Bittern")
    f = bird_features(bittern)  # 1 fish + 1 invertebrate + 1 rodent, all required
    assert f["cost_is_or"] == 0
    assert f["cost_fish"] == f["cost_invertebrate"] == f["cost_rodent"] == 1 / 3
    assert f["cost_min_total"] == 1


def test_bonus_state_dependent_flag():
    flagged = {
        b.id
        for b in BONUS_REGISTRY.values()
        if bonus_features(b)["depends_on_game_state"]
    }
    assert flagged == {5, 7, 17, 23}
    assert all(
        sum(group(bonus_features(b), "bonus_card_")) == 1
        for b in BONUS_REGISTRY.values()
    )


# --- players -----------------------------------------------------------------------------


def sample_states(n_games: int = 6, every: int = 7):
    """Every few of the states some random 2-player games ask a choice at. States with a single
    legal action are skipped, as in the dataset: they are applied, not encoded."""
    for seed in range(n_games):
        rng = random.Random(seed)
        state = initiate_state(2, seed=seed)
        step = 0
        while actions := get_actions(state):
            if len(actions) > 1:
                if step % every == 0:
                    yield state
                step += 1
            state = transition_state(state, rng.choice(actions))


def test_player_layout_is_the_same_for_every_player_and_viewer():
    names = player_feature_names()
    slots = 15 * (4 + len(bird_feature_names()))
    row_summaries = 3 * 4
    round_goal_points, goal_progress, bonus_progress, score_now = 4, 4, 2, 1
    assert (
        len(names)
        == slots
        + row_summaries
        + 5
        + 1
        + 45
        + 1
        + 32
        + round_goal_points
        + goal_progress
        + bonus_progress
        + score_now
        + 5  # cubes, turns left x3, first player
    )
    for state in sample_states(2):
        for p in (0, 1):
            for viewer in (0, 1):
                assert list(player_features(state, p, viewer)) == list(names)
                assert len(encode_player(state, p, viewer)) == len(names)


def test_player_values_are_scaled():
    for state in sample_states():
        for p in (0, 1):
            assert all(0.0 <= v <= 1.0 for v in encode_player(state, p, 0))


def test_hand_and_bonus_identities_are_hidden_from_opponents_but_sizes_are_not():
    state = initiate_state(2, seed=3)
    mine = player_features(state, 0, viewer_index=0)
    theirs = player_features(state, 0, viewer_index=1)
    assert mine["hand_size"] == theirs["hand_size"] > 0
    assert mine["bonus_card_count"] == theirs["bonus_card_count"] > 0
    assert any(v for k, v in mine.items() if k.startswith("hand_nest_"))
    assert not any(v for k, v in theirs.items() if k.startswith("hand_nest_"))
    held = lambda f: [v for k, v in f.items() if k.startswith("held_bonus_card_")]
    assert sum(held(mine)) == len(state.players[0].bonus_hand)
    assert not any(held(theirs))


def test_encoding_does_not_leak_hidden_information():
    """Re-dealing everything the viewer cannot see must not change what the viewer encodes."""
    rng = random.Random(0)
    checked = 0
    for state in sample_states():
        for viewer in (0, 1):
            other = 1 - viewer
            shuffled = redeterminize(state, viewer, rng)
            for p in (viewer, other):
                assert encode_player(state, p, viewer) == encode_player(
                    shuffled, p, viewer
                )
            checked += 1
    assert checked > 20


def test_the_leak_test_can_fail():
    """Sanity check: with full information (viewer = the player), the redeal is visible."""
    rng = random.Random(0)
    changed = 0
    for state in sample_states():
        shuffled = redeterminize(state, 0, rng)
        if encode_player(state, 1, viewer_index=1) != encode_player(
            shuffled, 1, viewer_index=1
        ):
            changed += 1
    assert changed > 0


def _row_state(row: int, birds_in_row: int):
    """Player 0 with `birds_in_row` birds (1 egg each) filled left to right in `row`, ready to
    act. A helper bird in the wetland gives lay_eggs somewhere to lay when testing rows 0-1.
    """
    state = initiate_state(2, seed=1)
    state.game_phase = GamePhase.MAIN_TURN
    state.current_player_index = 0
    roomy = [b for b, c in BIRD_REGISTRY.items() if c.egg_limit >= 3]
    for col in range(birds_in_row):
        place_bird_on_board(state, 0, row, col, roomy[col], eggs=1)
    if row != 2:
        place_bird_on_board(state, 0, 2, 4, roomy[7], eggs=1)
    return state


def test_row_summaries_match_what_the_engine_does():
    actions = ["gain_food", "lay_eggs", "draw_cards"]
    extra = [
        GamePhase.EXTRA_FOOD_ACTION,
        GamePhase.EXTRA_LAY_EGGS_ACTION,
        GamePhase.EXTRA_CARD_DRAW_ACTION,
    ]
    needed = ["food_needed", "eggs_needed", "cards_needed"]
    for row, habitat in enumerate(HABITATS):
        for k in range(6):
            state = _row_state(row, k)
            f = player_features(state, 0, 0)
            after = transition_state(state, SimpleAction(actions[row]))
            traded = after.game_phase == extra[row]
            yield_ = (
                after.action_data.base_amount
                if traded
                else getattr(after.action_data, needed[row])
            )
            assert f[f"{habitat}_birds"] == k / 5
            assert f[f"{habitat}_action_yield"] == yield_ / 4, (habitat, k)
            assert f[f"{habitat}_has_trade_option"] == float(traded), (habitat, k)


def test_next_egg_cost_follows_the_next_empty_spot():
    # engine: egg cost of playing in column 0..4 is 0, 1, 1, 2, 2; a full row has no spot
    expected = [0, 1, 1, 2, 2, 0]
    for k in range(6):
        f = player_features(_row_state(0, k), 0, 0)
        assert f["forest_next_egg_cost"] == expected[k] / 2


# --- public state -------------------------------------------------------------------------


def test_turns_left_counts_cubes_and_later_rounds():
    state = initiate_state(2, seed=5)
    state.game_phase = GamePhase.MAIN_TURN
    for round_, cubes, left in [(1, 8, 26), (2, 7, 18), (2, 1, 12), (3, 6, 11), (4, 5, 5), (4, 1, 1), (4, 0, 0)]:
        state.round, state.players[0].action_cubes = round_, cubes
        f = player_features(state, 0, 0)
        assert f["action_cubes"] == cubes / 8 and f["turns_left_game"] == left / 26
        assert f["one_turn_left_in_round"] == float(cubes == 1)
        assert f["one_turn_left_in_game"] == float(left == 1)
    state.round, state.players[0].action_cubes = 1, 9  # setup: saturates instead of leaving [0, 1]
    f = player_features(state, 0, 0)
    assert f["action_cubes"] == 1 and f["turns_left_game"] == 1


def test_cube_is_spent_when_the_main_action_completes():
    state = _row_state(0, 0)  # an empty row: no trade bonus, so a single food phase
    state.players[0].action_cubes = 5
    state = transition_state(state, SimpleAction("gain_food"))
    assert state.game_phase == GamePhase.COLLECT_FOOD
    assert state.players[0].action_cubes == 5  # still choosing: the turn in progress counts
    while state.game_phase == GamePhase.COLLECT_FOOD:
        state = transition_state(state, get_actions(state)[0])
    assert state.players[0].action_cubes == 4  # spent once the food is taken


def test_the_left_out_phases_and_kinds_are_never_a_choice():
    """PHASES, ACTION_KINDS and PAYMENT_KINDS leave out what is forced, over, or transient. Random games prove it."""
    from wingspan.ai.encoding import PAYMENT_KINDS, PHASES

    left_out = {p.value for p in GamePhase} - set(PHASES)
    assert left_out == {"game_setup", "game_over"}
    for seed in range(6):
        rng = random.Random(seed)
        state = initiate_state(2, seed=seed)
        while actions := get_actions(state):
            if len(actions) > 1:
                assert state.game_phase.value in PHASES
                assert all(action_kind(a) in ACTION_KINDS for a in actions)
                cost = state.action_data.pending_cost
                assert cost is None or cost.cost_type in PAYMENT_KINDS
            else:  # forced steps include the setup ones
                assert action_kind(actions[0]) in ACTION_KINDS or state.game_phase == GamePhase.GAME_SETUP
            state = transition_state(state, rng.choice(actions))
        assert state.game_phase.value not in PHASES


def test_goal_list_matches_the_engine():
    from wingspan.engine.core.game import _build_goal_tiles

    assert set(GOALS) == {goal for tile in _build_goal_tiles() for goal in tile}
    assert len(GOALS) == 16


def test_public_layout_and_scaling():
    names = public_feature_names()
    # tray 1+45, feeder 1+5+1, deck 1, discard 1, rounds 4, goals 4*16, scoring 1
    assert len(names) == 46 + 7 + 2 + 4 + 64 + 1
    for state in sample_states():
        assert list(public_features(state)) == list(names)
        assert all(0.0 <= v <= 1.0 for v in encode_public(state))


def test_public_block_has_one_goal_per_round_and_one_current_round():
    f = public_features(initiate_state(2, seed=5))
    for r in ROUNDS:
        assert sum(v for k, v in f.items() if k.startswith(f"goal_r{r}_")) == 1
    assert (
        sum(v for k, v in f.items() if k.startswith("round_") and k[6:].isdigit()) == 1
    )


def test_feeder_counts_and_reroll_flag():
    state = initiate_state(2, seed=5)
    state.feeder = {
        0: ["fish"],
        1: ["fish"],
        2: ["invertebrate", "seed"],
        3: ["fruit"],
        4: ["fish"],
    }
    f = public_features(state)
    assert (
        f["feeder_fish"],
        f["feeder_invertebrate"],
        f["feeder_seed"],
        f["feeder_rodent"],
    ) == (3 / 5, 1 / 5, 1 / 5, 0)
    assert f["feeder_can_reroll"] == 0
    state.feeder = {i: ["fish"] for i in range(5)}
    assert public_features(state)["feeder_can_reroll"] == 1


def test_public_block_ignores_hidden_information():
    rng = random.Random(0)
    for state in sample_states():
        for viewer in (0, 1):
            assert encode_public(state) == encode_public(
                redeterminize(state, viewer, rng)
            )


def test_banked_round_goal_points_show_up_in_the_player_block():
    state = initiate_state(2, seed=5)
    state.players[1].score.round_goals = [4, 0, 0, 0]
    f = player_features(state, 1, 0)
    assert f["round_goal_points_1"] == 4 / 7
    assert f["round_goal_points_2"] == 0


def _birds_with(nest=None, min_egg_limit=0):
    return [
        b
        for b, c in BIRD_REGISTRY.items()
        if c.nest == nest and c.egg_limit >= min_egg_limit
    ]


def test_goal_progress_counts_the_goal_and_zeroes_past_rounds():
    state = initiate_state(2, seed=5)
    state.round_goal_config.selected_goals = [
        "eggs_in_bowl", "total_birds", "birds_in_forest", "sets_of_eggs",
    ]  # fmt: skip
    for col, bird in enumerate(_birds_with("bowl", 3)[:2]):
        place_bird_on_board(state, 0, 0, col, bird, eggs=3)

    f = player_features(state, 0, 0)
    assert f["goal_progress_r1"] == 6 / 15  # 6 eggs on bowl nests
    assert f["goal_progress_r2"] == 2 / 15  # 2 birds on the board
    assert f["goal_progress_r3"] == 2 / 5  # 2 birds in the forest row

    state.round = 2  # round 1 is over: its points are banked, no progress shown
    assert player_features(state, 0, 0)["goal_progress_r1"] == 0


def test_bonus_progress_is_private_to_the_holder():
    state = initiate_state(2, seed=5)
    state.players[0].bonus_hand = [5]  # breeding manager: 1 point per bird with 4+ eggs
    for col, bird in enumerate(_birds_with("cavity", 4)[:2]):
        place_bird_on_board(state, 0, 0, col, bird, eggs=4)

    mine = player_features(state, 0, viewer_index=0)
    assert mine["bonus_progress"] == 2 / 5  # per-bird cards use a cap of 5
    assert mine["bonus_points_now"] == 2 / 8
    theirs = player_features(state, 0, viewer_index=1)
    assert theirs["bonus_progress"] == theirs["bonus_points_now"] == 0


# --- pending decision ---------------------------------------------------------------------


def group_sum(features: dict[str, float], prefix: str) -> float:
    return sum(v for k, v in features.items() if k.startswith(prefix))


def test_pending_layout_scaling_and_one_hots():
    names = pending_feature_names()
    # phase 17, 1 flag, 5 counters, 2 queue counters, power 22 + step 17, payment 3 + 1, bird 45
    assert len(names) == 17 + 1 + 5 + 2 + 22 + 17 + 3 + 1 + 45
    for state in sample_states(3, every=1):
        for viewer in (0, 1):
            f = pending_features(state, viewer)
            assert list(f) == list(names)
            assert len(encode_pending(state, viewer)) == len(names)
            assert all(0.0 <= v <= 1.0 for v in f.values())
            assert group_sum(f, "phase_") == 1
            assert group_sum(f, "active_power_template_") == 1
            assert group_sum(f, "power_step_") == 1
            assert group_sum(f, "payment_") - f["payment_egg_amount"] == 1


def test_counters_and_active_power():
    state = initiate_state(2, seed=5)
    state.game_phase = GamePhase.COLLECT_FOOD
    state.current_player_index = 0
    state.action_data.food_needed = 2
    f = pending_features(state, 0)
    assert f["phase_collect_food"] == 1 and f["phase_main_turn"] == 0
    assert f["food_needed"] == 2 / 5
    assert (
        f["viewer_owns_turn"] == 1 and pending_features(state, 1)["viewer_owns_turn"] == 0
    )

    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.action_data.execution_stack.append(
        PowerExecution(
            power_id=8,
            bird_id=1,
            spot_row=0,
            spot_col=0,
            player_index=0,
            phase="select_die",
        )
    )
    f = pending_features(state, 0)
    assert f["active_power_template_8"] == 1
    assert f["power_step_select_die"] == 1


def test_owning_the_turn_differs_from_choosing_during_someone_elses_effect():
    state = initiate_state(2, seed=5)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 1  # player 1 is asked to choose...
    state.action_data.action_player_index = 0  # ...during player 0's turn
    assert pending_features(state, 1)["viewer_owns_turn"] == 0
    assert pending_features(state, 0)["viewer_owns_turn"] == 1
    state.action_data.action_player_index = None  # no one else's effect: the chooser owns it
    assert pending_features(state, 1)["viewer_owns_turn"] == 1


def test_the_bird_being_paid_for_is_only_visible_to_the_player_choosing():
    state = initiate_state(2, seed=5)
    bird = state.players[0].bird_hand[0]
    state.game_phase = GamePhase.PAY_EGG_COST
    state.current_player_index = 0
    state.action_data.pending_cost = CostPayment(
        cost_type="egg", amount=2, callback_phase=GamePhase.PLAY_BIRD,
        callback_action=PlayBirdAction(bird, 0, 2),
    )  # fmt: skip

    mine = pending_features(state, 0)
    assert mine["payment_egg"] == 1 and mine["payment_egg_amount"] == 1.0
    assert [v for k, v in mine.items() if k.startswith("paying_for_")] == bird_table()[
        bird
    ]
    theirs = pending_features(state, 1)
    assert theirs["payment_egg"] == 1  # the payment itself is public
    assert not any(v for k, v in theirs.items() if k.startswith("paying_for_"))


# --- full observation ---------------------------------------------------------------------


def test_observation_pieces_and_sizes():
    for state in sample_states(2):
        for viewer in (0, 1):
            obs = encode_obs(state, viewer)
            n_player, n_shared = len(player_feature_names()), len(shared_feature_names())
            assert len(obs.me) == n_player
            assert [len(o) for o in obs.opponents] == [n_player]
            assert n_shared == len(public_feature_names()) + len(pending_feature_names()) + 4
            assert len(obs.shared) == n_shared
            assert len(obs.flat()) == 2 * n_player + n_shared
            assert all(0.0 <= v <= 1.0 for v in obs.flat())


def test_me_is_the_viewer_and_opponents_go_clockwise():
    state = initiate_state(3, seed=2)
    obs = encode_obs(state, viewer_index=1)
    assert obs.me == encode_player(state, 1, 1)
    assert obs.opponents == [encode_player(state, 2, 1), encode_player(state, 0, 1)]
    assert len(encode_obs(state, 0).opponents) == 2
    players = {
        k: v
        for k, v in zip(shared_feature_names(), obs.shared)
        if k.startswith("players_")
    }
    assert players == {"players_2": 0, "players_3": 1, "players_4": 0, "players_5": 0}


def _bird(habitat, nest):
    """The first bird living only in `habitat` with a `nest` nest."""
    return next(
        b for b, c in BIRD_REGISTRY.items() if list(c.habitats) == [habitat] and c.nest == nest
    )


# Two pairs with the same habitats and nests between them, bound differently
_PAIRS = [
    [_bird("grassland", "bowl"), _bird("wetland", "cavity")],
    [_bird("wetland", "bowl"), _bird("grassland", "cavity")],
]


def test_hand_and_tray_ids_keep_what_the_summed_columns_lose():
    cols = ["hand_habitat_grassland", "hand_habitat_wetland", "hand_nest_bowl", "hand_nest_cavity"]
    hands = _PAIRS
    seen = []
    for hand in hands:
        state = initiate_state(2, seed=5)
        state.players[0].bird_hand = list(reversed(hand))
        f = player_features(state, 0, 0)
        seen.append(([f[c] for c in cols], encode_obs(state, 0)))
    (summed_a, obs_a), (summed_b, obs_b) = seen
    assert summed_a == summed_b  # the bag can't tell these hands apart
    assert obs_a.hand == sorted(hands[0]) and obs_b.hand == sorted(hands[1])  # the ids can

    state = initiate_state(2, seed=5)
    assert encode_obs(state, 1).hand == sorted(state.players[1].bird_hand)
    assert encode_obs(state, 0).tray == sorted(state.bird_tray)


def test_observation_does_not_leak_hidden_information():
    rng = random.Random(1)
    checked = 0
    for state in sample_states():
        for viewer in (0, 1):
            assert encode_obs(state, viewer) == encode_obs(
                redeterminize(state, viewer, rng), viewer
            )
            checked += 1
    assert checked > 20


# --- actions ------------------------------------------------------------------------------


def legal_action_states(n_games: int = 6):
    for state in sample_states(n_games, every=3):
        yield state, get_actions(state)


def test_action_layout_scaling_and_kind():
    names = action_feature_names()
    assert len(names) == 146
    assert len(set(ACTION_KINDS)) == len(ACTION_KINDS) == 37
    for state, actions in legal_action_states():
        for action in actions:
            f = action_features(state, action)
            assert list(f) == list(names)
            assert len(encode_action(state, action)) == len(names)
            assert all(0.0 <= v <= 1.0 for v in f.values())
            assert action_kind(action) in ACTION_KINDS
            assert sum(f[f"action_{k}"] for k in ACTION_KINDS) == 1


def test_legal_actions_encode_differently_except_dice_with_the_same_food():
    for state, actions in legal_action_states():
        seen = {}
        for action in actions:
            key = tuple(encode_action(state, action))
            if key in seen:
                assert action_kind(action) == action_kind(seen[key]) == "select_die"
            seen[key] = action


def test_action_columns():
    state = initiate_state(2, seed=5)
    state.current_player_index = 0
    b1, b2 = [b for b, c in BIRD_REGISTRY.items() if c.points in (2, 7)][:2]
    pts = lambda f: f["action_bird_points"]
    row = lambda b: bird_table()[b][0]  # points column

    f = action_features(state, PlayBirdAction(b1, 1, 2))
    assert f["action_play_bird_at"] == 1 and f["action_spot_grassland_2"] == 1 / 5
    assert pts(f) == row(b1) and f["action_bird_count"] == 1 / 5

    f = action_features(state, EggMapAction("lay_eggs", ((b1, 2), (b2, 1))))
    assert f["action_egg_map_lay_eggs"] == 1 and f["action_eggs"] == 3 / 5
    assert f["action_bird_count"] == 2 / 5 and pts(f) == (2 * row(b1) + row(b2)) / 3

    f = action_features(state, FoodMapAction("pay_food", (("fish", 1), ("seed", 2))))
    assert (f["action_food_fish"], f["action_food_seed"]) == (1 / 5, 2 / 5)

    f = action_features(state, DrawCardsAction((b1, b2), 1))
    assert f["action_bird_count"] == 2 / 5 and f["action_deck_cards"] == 1 / 5

    f = action_features(state, SelectInitialAction((b1, b2), 7))
    assert f["action_select_initial_cards"] == 1 and f["action_bonus_card_7"] == 1
    assert f["action_bird_count"] == 2 / 5

    f = action_features(state, TradeAction("seed", "fish"))
    assert f["action_food_fish"] == 1 / 5 and f["action_food_given_seed"] == 1 / 5
    assert f["action_food_seed"] == 0


def test_actions_on_board_birds_name_their_spots():
    state = initiate_state(2, seed=5)
    state.current_player_index = 0
    b1, b2 = _birds_with("bowl", 3)[:2]
    place_bird_on_board(state, 0, 0, 2, b1, eggs=1)  # forest_2
    place_bird_on_board(state, 0, 2, 0, b2, eggs=0)  # wetland_0
    spots = lambda f: {k: v for k, v in f.items() if k.startswith("action_spot_") and v}

    f = action_features(state, EggMapAction("lay_eggs", ((b1, 2), (b2, 1))))
    assert spots(f) == {"action_spot_forest_2": 2 / 5, "action_spot_wetland_0": 1 / 5}
    f = action_features(state, IdAction("discard_egg_from", b1))
    assert spots(f) == {"action_spot_forest_2": 1 / 5}

    # A bird in hand has no spot; nor does a bird on the opponent's board
    in_hand = state.players[0].bird_hand[0]
    assert not spots(action_features(state, IdAction("tuck_card", in_hand)))
    state.current_player_index = 1
    assert not spots(action_features(state, IdAction("select_bird", b1)))


def test_score_now_counts_the_public_points():
    state = initiate_state(2, seed=5)
    bird = _birds_with("bowl", 3)[0]
    place_bird_on_board(state, 0, 0, 0, bird, eggs=2)
    state.players[0].score.round_goals = [3, 0, 0, 0]
    points = BIRD_REGISTRY[bird].points + 2 + 3
    assert player_features(state, 0, 0)["score_now"] == points / 120
    assert player_features(state, 0, 1)["score_now"] == points / 120  # public
    assert player_features(state, 1, 0)["score_now"] == 0


def test_action_bird_ids_keep_what_the_averaged_columns_lose():
    state = initiate_state(2, seed=5)
    cols = ["habitat_grassland", "habitat_wetland", "nest_bowl", "nest_cavity"]
    keeps = [SelectInitialAction(tuple(reversed(pair)), 7) for pair in _PAIRS]
    averaged = [[action_features(state, a)[f"action_bird_{c}"] for c in cols] for a in keeps]
    assert averaged[0] == averaged[1]  # the average can't tell these choices apart
    assert [action_bird_ids(a) for a in keeps] == [sorted(p) for p in _PAIRS]  # the ids can


def test_action_bird_ids_by_kind():
    b1, b2 = _PAIRS[0]
    assert action_bird_ids(EggMapAction("lay_eggs", ((b2, 1), (b1, 2)))) == sorted([b1, b1, b2])
    assert action_bird_ids(DrawCardsAction((b2, b1), 1)) == sorted([b1, b2])
    assert action_bird_ids(PlayBirdAction(b1, 0, 0)) == [b1]
    assert action_bird_ids(IdAction("tuck_card", b1)) == [b1]
    # ids that are not birds
    assert action_bird_ids(IdAction("power_5_bonus", 5)) == []
    assert action_bird_ids(IdAction("choose_player", 1)) == []
    assert action_bird_ids(SimpleAction("lay_eggs")) == []
    assert action_bird_ids(FoodMapAction("pay_food", (("fish", 1),))) == []


def test_ids_mean_birds_bonuses_or_players_depending_on_the_type():
    state = initiate_state(2, seed=5)
    state.current_player_index = 1
    bonus = action_features(state, IdAction("power_5_bonus", 5))
    assert bonus["action_bonus_card_5"] == 1 and bonus["action_bird_count"] == 0
    tuck = action_features(state, IdAction("tuck_card", 5))
    assert tuck["action_bird_count"] == 1 / 5 and tuck["action_bonus_card_5"] == 0
    assert (
        action_features(state, IdAction("choose_player", 1))["action_targets_self"] == 1
    )
    assert (
        action_features(state, IdAction("choose_player", 0))["action_targets_self"] == 0
    )
