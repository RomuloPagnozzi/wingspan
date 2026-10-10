"""Tests for game engine: state transitions, turn lifecycle, and power activation."""

from wingspan.engine.core import (
    initiate_state,
    BIRD_REGISTRY,
    PlacedBird,
    get_bird_power,
    GamePhase,
    ActionData,
    QueuedPower,
    SimpleAction,
    PlayBirdAction,
)
from wingspan.engine.engine import (
    finish_main_action,
    _check_powers_done,
)
from wingspan.engine.engine import transition_state
from wingspan.engine.actions import get_actions
from conftest import setup_power_queue


def test_finish_main_action_no_powers():
    """Main action with no triggered powers goes to MAIN_TURN."""
    state = initiate_state(2)
    first_player_idx = next(i for i, p in enumerate(state.players) if p.first_player)
    state.current_player_index = first_player_idx
    state.players[first_player_idx].action_cubes = 5

    state = finish_main_action(state, "brown", habitat="forest")

    assert state.game_phase == GamePhase.MAIN_TURN
    assert state.current_player_index == (first_player_idx + 1) % 2
    assert state.action_data is None or (
        isinstance(state.action_data, ActionData)
        and len(state.action_data.powers_queue) == 0
    )
    assert state.players[first_player_idx].action_cubes == 4


def test_finish_main_action_no_powers_explicit():
    """Main action with white power color but no white powers."""
    state = initiate_state(2)
    state.current_player_index = 0
    state.players[0].action_cubes = 5

    state = finish_main_action(state, "white")

    assert state.game_phase == GamePhase.MAIN_TURN
    assert state.players[0].action_cubes == 4


def test_check_powers_done_transitions():
    """When power queue exhausted, transition to MAIN_TURN."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.action_data = ActionData()
    state.action_data.powers_queue = [
        QueuedPower(
            power_id=1,
            bird_id=1,
            spot_row=0,
            spot_col=0,
            player_index=0,
            power_data={},
        )
    ]
    state.action_data.current_power_index = 1  # Past end of queue

    state = _check_powers_done(state)

    assert state.game_phase == GamePhase.MAIN_TURN


def test_check_powers_done_continues():
    """When powers remain, stay in ACTIVATE_POWERS."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.action_data = ActionData()
    state.action_data.powers_queue = [
        QueuedPower(
            power_id=1, bird_id=1, spot_row=0, spot_col=0, player_index=0, power_data={}
        ),
        QueuedPower(
            power_id=2, bird_id=2, spot_row=0, spot_col=0, player_index=0, power_data={}
        ),
    ]
    state.action_data.current_power_index = 0

    state = _check_powers_done(state)

    assert state.game_phase == GamePhase.ACTIVATE_POWERS
    assert len(state.action_data.powers_queue) == 2


def test_power_activation_skip():
    """Skipping a power advances the index."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    setup_power_queue(
        state,
        [
            {
                "bird_id": 1,
                "power_data": {"data": {"id": 1, "details": {"type": "seed"}}},
            },
            {
                "bird_id": 2,
                "power_data": {"data": {"id": 1, "details": {"type": "fish"}}},
            },
        ],
    )

    state = transition_state(state, SimpleAction("skip_power"))

    assert state.action_data.current_power_index == 1


def test_pink_power_decided_by_owner():
    """An opponent's pink power is decided by its owner, then the turn returns to the actor."""
    state = initiate_state(2, seed=0)
    by_name = {b.name: b.id for b in BIRD_REGISTRY.values()}
    no_power = next(
        b.id
        for b in BIRD_REGISTRY.values()
        if not get_bird_power(b.id).get("data") and b.egg_limit >= 2
    )
    bowl_bird = next(
        b.id
        for b in BIRD_REGISTRY.values()
        if b.nest == "bowl"
        and b.egg_limit > 0
        and get_bird_power(b.id).get("color") != "pink"
    )
    state.game_phase = GamePhase.MAIN_TURN
    for i, p in enumerate(state.players):
        p.first_player = i == 0
        p.action_cubes = 8
    state.current_player_index = 0
    state.players[0].food = {}  # no food -> no "trade food for egg" prompt
    state.players[0].board[1][0].bird = PlacedBird(no_power)
    state.players[1].board[1][0].bird = PlacedBird(by_name["Bronzed Cowbird"])
    state.players[1].board[1][1].bird = PlacedBird(bowl_bird)

    state = transition_state(state, SimpleAction("lay_eggs"))
    state = transition_state(state, get_actions(state)[0])

    assert state.game_phase == GamePhase.ACTIVATE_POWERS
    assert state.current_player_index == 1
    assert state.action_data.action_player_index == 0

    state = transition_state(state, SimpleAction("activate_power"))

    assert state.players[1].board[1][1].bird.state.eggs == 1
    assert state.game_phase == GamePhase.MAIN_TURN
    assert state.current_player_index == 1
    assert state.players[0].score.egg_points == 2


def test_play_bird_with_egg_cost_also_pays_food():
    """A bird played in an egg-cost column pays its egg cost and then its food cost."""
    state = initiate_state(2, seed=0)
    by_name = {b.name: b.id for b in BIRD_REGISTRY.values()}
    crossbill = by_name["Red Crossbill"]  # costs 2 seed, forest
    state.game_phase = GamePhase.MAIN_TURN
    state.current_player_index = 0
    player = state.players[0]
    player.action_cubes = 8
    player.bird_hand = [crossbill]
    player.food = {"seed": 2}
    player.board[0][0].bird = PlacedBird(by_name["Cassin's Finch"])
    player.board[0][0].bird.state.eggs = 1

    state = transition_state(state, SimpleAction("play_bird"))
    state = transition_state(
        state,
        next(a for a in get_actions(state) if a.bird_id == crossbill and a.col == 1),
    )
    assert state.game_phase == GamePhase.PAY_EGG_COST
    state = transition_state(state, get_actions(state)[0])
    assert state.game_phase == GamePhase.PAY_FOOD_COST
    state = transition_state(state, get_actions(state)[0])

    assert state.players[0].board[0][1].bird.id == crossbill
    assert state.players[0].food.get("seed", 0) == 0
    assert state.players[0].board[0][0].bird.state.eggs == 0


def test_chained_additional_bird_plays_each_pay_their_costs():
    """Birds played through chained "play an additional bird" powers still pay eggs and food."""
    state = initiate_state(2, seed=0)
    by_name = {b.name: b.id for b in BIRD_REGISTRY.values()}
    chain = [
        by_name[n] for n in ("Red-Eyed Vireo", "Downy Woodpecker", "Tufted Titmouse")
    ]
    no_power = next(
        b.id
        for b in BIRD_REGISTRY.values()
        if not get_bird_power(b.id).get("data") and "grassland" in b.habitats
    )
    state.game_phase = GamePhase.MAIN_TURN
    state.current_player_index = 0
    player = state.players[0]
    player.action_cubes = 8
    player.bird_hand = list(chain)
    player.food = {"invertebrate": 3}
    player.board[1][0].bird = PlacedBird(no_power)
    player.board[1][
        0
    ].bird.state.eggs = 2  # covers the egg cost of forest columns 2 and 3

    state = transition_state(state, SimpleAction("play_bird"))
    food_steps = 0
    while (
        state.game_phase != GamePhase.MAIN_TURN
        or state.current_player_index == 0
        and chain[-1] in state.players[0].bird_hand
    ):
        actions = get_actions(state)
        food_steps += state.game_phase == GamePhase.PAY_FOOD_COST
        plays = [a for a in actions if isinstance(a, PlayBirdAction)]
        if plays:
            state = transition_state(
                state, next(a for a in plays if a.bird_id in chain and a.row == 0)
            )
        elif SimpleAction("activate_power") in actions:
            state = transition_state(state, SimpleAction("activate_power"))
        else:
            state = transition_state(state, actions[0])

    assert [
        s.bird.id if s.bird else None for s in state.players[0].board[0][:3]
    ] == chain
    assert food_steps == 3
    assert state.players[0].food.get("invertebrate", 0) == 0
    assert state.players[0].board[1][0].bird.state.eggs == 0


def test_fifth_slot_has_no_trade():
    """Trades sit on slots 2 and 4 and on the full row, not on the 5th slot."""
    from wingspan.engine.core.models import BOARD_LAYOUT

    for row in BOARD_LAYOUT:
        assert [cfg.extra_resource for cfg in row] == [False, True, False, True, False]


def test_setup_discards_go_to_discard_pile():
    state = initiate_state(2, seed=0)
    state = transition_state(state, SimpleAction("start_setup"))
    hand = list(state.players[state.current_player_index].bird_hand)
    action = next(a for a in get_actions(state) if len(a.kept_birds) == 2)
    state = transition_state(state, action)
    assert sorted(state.discarded_birds) == sorted(set(hand) - set(action.kept_birds))


def test_final_scores_are_fresh_for_all_players():
    """Eggs gained on other players' turns must be in the final score."""
    import random
    from wingspan.engine.scoring import update_player_scores

    for seed in range(40):
        rng = random.Random(seed)
        state = initiate_state(2, seed=seed)
        while actions := get_actions(state):
            state = transition_state(state, rng.choice(actions))
        totals = [p.score.total for p in state.players]
        for p in state.players:
            update_player_scores(p)
        assert totals == [p.score.total for p in state.players]


def _full_board_state(grassland_bird_id):
    state = initiate_state(2, seed=0)
    state.game_phase = GamePhase.MAIN_TURN
    player = state.players[state.current_player_index]
    player.action_cubes = 8
    player.board[1][0].bird = PlacedBird(grassland_bird_id)
    player.board[1][0].bird.state.eggs = BIRD_REGISTRY[grassland_bird_id].egg_limit
    return state, player


def test_lay_eggs_not_offered_when_it_would_do_nothing():
    plain = next(
        b.id
        for b in BIRD_REGISTRY.values()
        if not get_bird_power(b.id).get("data") and "grassland" in b.habitats
    )
    state, _ = _full_board_state(plain)
    assert SimpleAction("lay_eggs") not in get_actions(state)


def test_lay_eggs_with_no_room_only_activates_brown_powers():
    brown = next(
        b.id
        for b in BIRD_REGISTRY.values()
        if get_bird_power(b.id).get("color") == "brown"
        and "grassland" in b.habitats
        and b.egg_limit > 0
    )
    state, player = _full_board_state(brown)
    actor = state.current_player_index
    player.food = {"seed": 1}  # would pay for an extra egg if there were room
    assert SimpleAction("lay_eggs") in get_actions(state)

    state = transition_state(state, SimpleAction("lay_eggs"))
    assert state.game_phase == GamePhase.ACTIVATE_POWERS  # no egg or trade prompt
    assert state.action_data.get_current_queued_power().bird_id == brown
    state = transition_state(state, SimpleAction("skip_power"))

    assert state.players[actor].action_cubes == 7
    assert state.players[actor].food == {"seed": 1}
    bird = state.players[actor].board[1][0].bird
    assert bird.state.eggs == bird.card.egg_limit
