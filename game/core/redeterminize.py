import random

from .custom_copy import copy_state
from .game import GameState
from .models import BIRD_REGISTRY, BONUS_REGISTRY, init_registries

# Power execution context keys whose values are lists of bird/bonus card IDs
# currently drawn-but-unresolved. See power/handlers.py: Power 5 (bonus_options),
# Power 6 (available_cards).
_BIRD_CONTEXT_KEYS = ("available_cards",)
_BONUS_CONTEXT_KEYS = ("bonus_options",)


def _collect_context_ids(state: GameState, keys: tuple[str, ...]) -> list[int]:
    ids: list[int] = []
    for execution in state.action_data.execution_stack:
        for key in keys:
            value = execution.context.get(key)
            if value:
                ids.extend(value)
    return ids


def _collect_placed_bird_ids(state: GameState) -> list[int]:
    return [
        spot.bird.id
        for player in state.players
        for row in player.board
        for spot in row
        if spot.bird is not None
    ]


def _redeterminize_birds(
    new_state: GameState, perspective_player: int, rng: random.Random
) -> None:
    perspective = new_state.players[perspective_player]

    public = (
        set(new_state.bird_tray)
        | set(new_state.discarded_birds)
        | set(_collect_placed_bird_ids(new_state))
    )
    known = set(perspective.bird_hand) | set(
        _collect_context_ids(new_state, _BIRD_CONTEXT_KEYS)
    )

    # Iterate the registry in insertion order for cross-PYTHONHASHSEED determinism;
    # set membership checks against int-keyed sets are hash-stable.
    unknown = [bid for bid in BIRD_REGISTRY if bid not in public and bid not in known]
    rng.shuffle(unknown)

    deck_size = len(new_state.bird_deck)
    opponent_hand_sizes = [
        len(p.bird_hand)
        for i, p in enumerate(new_state.players)
        if i != perspective_player
    ]
    assert len(unknown) >= deck_size + sum(
        opponent_hand_sizes
    ), "Bird card conservation broken: unknown pool too small"

    cursor = 0
    new_state.bird_deck = unknown[cursor : cursor + deck_size]
    cursor += deck_size
    for i, opp in enumerate(new_state.players):
        if i == perspective_player:
            continue
        hand_size = len(opp.bird_hand)
        opp.bird_hand = unknown[cursor : cursor + hand_size]
        cursor += hand_size
    # Remainder (unknown[cursor:]) corresponds to tucked/lost cards — discarded.


def _redeterminize_bonuses(
    new_state: GameState, perspective_player: int, rng: random.Random
) -> None:
    perspective = new_state.players[perspective_player]

    public = set(new_state.discarded_bonuses)
    known = set(perspective.bonus_hand) | set(
        _collect_context_ids(new_state, _BONUS_CONTEXT_KEYS)
    )

    unknown = [bid for bid in BONUS_REGISTRY if bid not in public and bid not in known]
    rng.shuffle(unknown)

    deck_size = len(new_state.bonus_deck)
    opponent_hand_sizes = [
        len(p.bonus_hand)
        for i, p in enumerate(new_state.players)
        if i != perspective_player
    ]
    assert len(unknown) >= deck_size + sum(
        opponent_hand_sizes
    ), "Bonus card conservation broken: unknown pool too small"

    cursor = 0
    new_state.bonus_deck = unknown[cursor : cursor + deck_size]
    cursor += deck_size
    for i, opp in enumerate(new_state.players):
        if i == perspective_player:
            continue
        hand_size = len(opp.bonus_hand)
        opp.bonus_hand = unknown[cursor : cursor + hand_size]
        cursor += hand_size


def redeterminize(
    state: GameState,
    perspective_player: int,
    rng: random.Random,
) -> GameState:
    """Return a new state consistent with perspective_player's information set.

    Re-samples the four hidden-info channels:
      - bird_deck order
      - bonus_deck order
      - opponents' bird_hand identities (sizes preserved)
      - opponents' bonus_hand identities (sizes preserved)
    and reseeds state.rng from `rng` so future stochastic events (dice, feeder
    re-rolls) draw fresh outcomes.

    The perspective player's information set is preserved exactly: their hand,
    board, food, score, action_cubes, and all public state (tray, discards,
    feeder, round_goals, ...) are unchanged.

    Cards drawn-but-unresolved in power execution contexts (Power 5's
    bonus_options, Power 6's available_cards) are treated as known to the
    perspective player — at any sub-phase where MCTS is actually invoked,
    the current player has seen those cards.
    """
    init_registries()
    new_state = copy_state(state)
    _redeterminize_birds(new_state, perspective_player, rng)
    _redeterminize_bonuses(new_state, perspective_player, rng)
    new_state.rng = random.Random(rng.getrandbits(64))
    return new_state
