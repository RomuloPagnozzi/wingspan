"""End-to-end tests for pink ("once between turns") powers.

Each test drives the real engine through "lay eggs" turns with a Bronzed Cowbird
(pink: lays 1 egg on a bowl bird when another player takes the lay eggs action).
"""

from wingspan.engine.core import (
    initiate_state,
    BIRD_REGISTRY,
    PlacedBird,
    PinkTrigger,
    get_bird_power,
    init_registries,
    GamePhase,
    SimpleAction,
)
from wingspan.engine.engine import transition_state
from wingspan.engine.actions import get_actions
from wingspan.engine.utils import get_triggered_pink_powers

init_registries()
BY_NAME = {b.name: b.id for b in BIRD_REGISTRY.values()}
COWBIRD = BY_NAME["Bronzed Cowbird"]
PLAIN = [  # no power, room for eggs, and not a nest the cowbird can lay in
    b.id
    for b in BIRD_REGISTRY.values()
    if not get_bird_power(b.id).get("data")
    and b.egg_limit >= 2
    and b.nest in ("ground", "cavity")
]
HOSTS = [  # bowl nests for the cowbird to lay in
    b.id
    for b in BIRD_REGISTRY.values()
    if b.nest == "bowl"
    and b.egg_limit >= 3
    and get_bird_power(b.id).get("color") != "pink"
]


def make_state(n_players: int, owner: int, cubes: list[int], first: int = 0):
    """Every player has a plain grassland bird; `owner` also has a cowbird + host."""
    state = initiate_state(n_players, seed=0)
    state.game_phase = GamePhase.MAIN_TURN
    for i, p in enumerate(state.players):
        p.first_player = i == first
        p.action_cubes = cubes[i]
        p.food = {}  # no "pay food for an extra egg" prompt
        p.board[1][0].bird = PlacedBird(PLAIN[i])
    state.players[owner].board[0][0].bird = PlacedBird(COWBIRD)
    state.players[owner].board[0][1].bird = PlacedBird(HOSTS[0])
    return state


def host_eggs(state, owner: int) -> int:
    return state.players[owner].board[0][1].bird.state.eggs


def lay_eggs(state, pink: str | None):
    """Current player takes "lay eggs". `pink` is the owner's answer if prompted,
    or None to assert the cowbird is not offered at all."""
    actor = state.current_player_index
    state = transition_state(state, SimpleAction("lay_eggs"))
    if state.game_phase == GamePhase.LAY_EGGS:
        state = transition_state(state, get_actions(state)[0])
    if pink is None:
        assert state.game_phase != GamePhase.ACTIVATE_POWERS
        return state
    assert state.game_phase == GamePhase.ACTIVATE_POWERS
    assert state.current_player_index != actor
    assert SimpleAction(pink) in get_actions(state)
    return transition_state(state, SimpleAction(pink))


def test_triggers_once_until_owners_next_turn_with_three_players():
    # Turn order from here: 1, 2, then 0 (the owner), then 1 again
    state = make_state(3, owner=0, cubes=[7, 8, 8])
    state.current_player_index = 1

    state = lay_eggs(state, "activate_power")
    assert host_eggs(state, 0) == 1

    assert state.current_player_index == 2
    state = lay_eggs(state, None)  # already used since owner's last turn
    assert host_eggs(state, 0) == 1

    assert state.current_player_index == 0
    state = lay_eggs(state, None)  # own action never triggers own pink power

    assert state.current_player_index == 1
    state = lay_eggs(state, "activate_power")  # refreshed by the owner's turn
    assert host_eggs(state, 0) == 2


def test_declining_does_not_use_it_up():
    state = make_state(3, owner=0, cubes=[7, 8, 8])
    state.current_player_index = 1

    state = lay_eggs(state, "skip_power")
    assert host_eggs(state, 0) == 0

    state = lay_eggs(state, "activate_power")
    assert host_eggs(state, 0) == 1


def test_not_refreshed_by_a_new_round():
    """2p: the last player of a round is the first of the next, so they act twice
    in a row. The opponent's pink power must not fire on both turns."""
    state = make_state(2, owner=0, cubes=[0, 1], first=0)
    state.current_player_index = 1

    state = lay_eggs(state, "activate_power")
    assert state.round == 2
    assert state.current_player_index == 1  # first player token rotated
    assert host_eggs(state, 0) == 1

    state = lay_eggs(state, None)
    assert host_eggs(state, 0) == 1

    assert state.current_player_index == 0
    assert not state.players[0].used_pink_powers  # refreshed on the owner's turn


def test_fires_once_between_rounds_if_unused():
    state = make_state(2, owner=0, cubes=[0, 1], first=0)
    state.current_player_index = 1

    state = lay_eggs(state, "skip_power")
    assert state.round == 2
    state = lay_eggs(state, "activate_power")
    assert host_eggs(state, 0) == 1


def test_triggers_when_actor_has_no_room_for_eggs():
    """Taking the action is the trigger, even if the actor lays nothing."""
    state = make_state(2, owner=0, cubes=[7, 8])
    state.current_player_index = 1
    actor = state.players[1]
    actor.board[1][0].bird = PlacedBird(  # a brown power, so the action is offered
        next(
            b.id
            for b in BIRD_REGISTRY.values()
            if "grassland" in b.habitats
            and b.egg_limit > 0
            and get_bird_power(b.id).get("color") == "brown"
        )
    )
    full = actor.board[1][0].bird
    full.state.eggs = full.card.egg_limit

    assert SimpleAction("lay_eggs") in get_actions(state)
    state = lay_eggs(state, "activate_power")
    assert host_eggs(state, 0) == 1
    assert full.card.egg_limit == state.players[1].board[1][0].bird.state.eggs


def test_owner_with_no_legal_target_can_only_skip():
    state = make_state(2, owner=0, cubes=[7, 8])
    state.current_player_index = 1
    host = state.players[0].board[0][1].bird
    host.state.eggs = host.card.egg_limit

    state = transition_state(state, SimpleAction("lay_eggs"))
    state = transition_state(state, get_actions(state)[0])
    assert get_actions(state) == [SimpleAction("skip_power")]


def test_multiple_owners_resolve_clockwise_from_the_active_player():
    state = make_state(3, owner=0, cubes=[8, 8, 8])
    other_cowbird = BY_NAME["Brown-Headed Cowbird"]
    state.players[2].board[0][0].bird = PlacedBird(other_cowbird)
    state.players[2].board[0][1].bird = PlacedBird(HOSTS[1])

    order = [
        p["player_index"]
        for p in get_triggered_pink_powers(state, PinkTrigger.LAY_EGGS, 1)
    ]
    assert order == [2, 0]

    # And end to end: each owner decides for themselves, in that order
    state.players[0].action_cubes = 7
    state.current_player_index = 1
    state = transition_state(state, SimpleAction("lay_eggs"))
    state = transition_state(state, get_actions(state)[0])
    assert state.current_player_index == 2
    state = transition_state(state, SimpleAction("activate_power"))
    assert state.current_player_index == 0
    state = transition_state(state, SimpleAction("activate_power"))
    assert state.players[2].board[0][1].bird.state.eggs == 1
    assert host_eggs(state, 0) == 1
    assert state.game_phase == GamePhase.MAIN_TURN
    assert state.current_player_index == 2
