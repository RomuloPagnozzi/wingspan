"""Shared test fixtures and utilities."""

from game.core import (
    PlacedBird,
    BirdState,
    ActionData,
    QueuedPower,
    Spot,
    init_registries,
    BIRD_REGISTRY,
)


def get_registry_bird_ids_by_nest(nest_type: str) -> list[int]:
    """Find all bird IDs with the specified nest type."""
    init_registries()
    return [
        bird_id for bird_id, card in BIRD_REGISTRY.items() if card.nest == nest_type
    ]


def get_registry_bird_ids_by_habitat(habitat: str) -> list[int]:
    """Find all bird IDs that can be played in the specified habitat."""
    init_registries()
    return [
        bird_id for bird_id, card in BIRD_REGISTRY.items() if habitat in card.habitats
    ]


def create_placed_bird(
    bird_id: int, eggs: int = 0, stashed_food: int = 0, tucked_cards: int = 0
) -> PlacedBird:
    """Create a PlacedBird with specified state."""
    return PlacedBird(
        id=bird_id,
        state=BirdState(
            eggs=eggs, stashed_food=stashed_food, tucked_cards=tucked_cards
        ),
    )


def place_bird_on_board(
    state, player_index: int, row: int, col: int, bird_id: int, **bird_state_kwargs
) -> PlacedBird:
    """Place a bird on the board and optionally remove from hand."""
    player = state.players[player_index]
    placed = create_placed_bird(bird_id, **bird_state_kwargs)
    player.board[row][col].bird = placed
    # Remove from hand if present
    if bird_id in player.bird_hand:
        player.bird_hand.remove(bird_id)
    return placed


def filter_bird_ids_by_nest(
    bird_ids: list[int],
    nest_type: str,
    min_egg_limit: int = 0,
    exclude_ids: set[int] | None = None,
) -> list[int]:
    """Filter a list of bird IDs by nest type and egg limit."""
    init_registries()
    exclude = exclude_ids or set()
    return [
        bird_id
        for bird_id in bird_ids
        if bird_id not in exclude
        and BIRD_REGISTRY[bird_id].nest == nest_type
        and BIRD_REGISTRY[bird_id].egg_limit > min_egg_limit
    ]


def filter_bird_ids_with_capacity(
    bird_ids: list[int], exclude_ids: set[int] | None = None
) -> list[int]:
    """Filter bird IDs to those with egg capacity > 0."""
    init_registries()
    exclude = exclude_ids or set()
    return [
        bird_id
        for bird_id in bird_ids
        if bird_id not in exclude and BIRD_REGISTRY[bird_id].egg_limit > 0
    ]


def get_bird_egg_limit(bird_id: int) -> int:
    """Get the egg limit for a bird ID."""
    init_registries()
    return BIRD_REGISTRY[bird_id].egg_limit


def get_bird_nest_type(bird_id: int) -> str:
    """Get the nest type for a bird ID."""
    init_registries()
    return BIRD_REGISTRY[bird_id].nest


def setup_power_queue(state, power_entries):
    """Set up powers queue with new ActionData structure.

    Args:
        state: GameState
        power_entries: list of dicts with bird_id, power_id, power_data, spot (optional)
    """
    state.action_data = ActionData()
    state.action_data.powers_queue = []
    for entry in power_entries:
        spot = entry.get("spot")
        state.action_data.powers_queue.append(
            QueuedPower(
                power_id=entry.get("power_id", entry["power_data"]["data"]["id"]),
                bird_id=entry["bird_id"],
                spot_row=spot.config.row if spot else 0,
                spot_col=spot.config.col if spot else 0,
                player_index=entry.get("player_index", state.current_player_index),
                power_data=entry["power_data"],
            )
        )
    state.action_data.current_power_index = 0


def setup_power_execution(
    state,
    power_id: int,
    bird_id: int,
    spot: Spot | None = None,
    player_index: int | None = None,
    power_data: dict | None = None,
) -> None:
    """Set up power execution with ActionData and QueuedPower.

    Args:
        state: GameState to modify
        power_id: The power ID to execute
        bird_id: The bird ID with this power
        spot: The Spot where the bird is placed (None defaults to 0,0)
        player_index: Player index (defaults to current player)
        power_data: Power data dict (defaults to {"data": {"id": power_id}})
    """
    if player_index is None:
        player_index = state.current_player_index
    if power_data is None:
        power_data = {"data": {"id": power_id}}

    assert isinstance(player_index, int)

    state.action_data = ActionData()
    state.action_data.powers_queue = [
        QueuedPower(
            power_id=power_id,
            bird_id=bird_id,
            spot_row=spot.config.row if spot else 0,
            spot_col=spot.config.col if spot else 0,
            player_index=player_index,
            power_data=power_data,
        )
    ]
    state.action_data.current_power_index = 0
