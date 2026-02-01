from typing import List, Dict, Callable, Tuple
import json
import random

from ..core import (
    GameState,
    PowerExecution,
    PinkTrigger,
    EndTurnEffect,
    QueuedPower,
    GamePhase,
    get_bird_power,
    get_bird_card,
    roll_feeder,
)
from ..effects import (
    draw_cards_effect,
    lay_eggs_effect,
    select_die_effect,
    gain_food_effect,
    pay_eggs_effect,
    pay_food_effect,
    tuck_cards_effect,
    parse_select_die_action,
)
from ..utils import (
    get_valid_birds_for_eggs,
    find_leftmost_empty_spot,
    get_triggered_pink_powers,
    ensure_bird_deck,
)
from .validators import can_execute_power

PowerHandler = Callable[[GameState, List[PowerExecution], str], GameState]
_POWER_HANDLERS: Dict[Tuple[int, str | None], PowerHandler] = {}


def power_handler(power_id: int, phase: str | None = None):
    """Decorator to register a power handler."""

    def decorator(func: PowerHandler) -> PowerHandler:
        _POWER_HANDLERS[(power_id, phase)] = func
        return func

    return decorator


def get_power_handler(power_id: int, phase: str | None) -> PowerHandler | None:
    """Get the handler for a specific power and phase."""
    return _POWER_HANDLERS.get((power_id, phase))


# =============================================================================
# Power 1: All players gain 1 resource
# =============================================================================


@power_handler(1)
def _power_1_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """All players gain 1 resource of specified type."""
    current = stack[-1]
    power_data = current.context["power_data"]
    resource_type = power_data["data"]["details"].get("type")

    if resource_type == "card":
        for i in range(len(state.players)):
            state = draw_cards_effect(
                state, tray_bird_ids=[], deck_count=1, player_index=i
            )
    else:
        for i in range(len(state.players)):
            state = gain_food_effect(state, resource_type, amount=1, player_index=i)

    stack.pop()
    return state


# =============================================================================
# Power 2: All players lay eggs on nest type
# =============================================================================


@power_handler(2)
def _power_2_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Set up multi-player egg laying on nest type."""
    current = stack[-1]
    power_data = current.context["power_data"]
    details = power_data["data"].get("details", {})
    nest_type = details.get("type")
    activator = current.player_index

    player_order = [activator] + [
        i for i in range(len(state.players)) if i != activator
    ]
    awaiting = [
        i for i in player_order if get_valid_birds_for_eggs(state.players[i], nest_type)
    ]

    if not awaiting:
        stack.pop()
        return state

    current.phase = "choices"
    current.context["activator"] = activator
    current.context["awaiting_players"] = awaiting
    current.context["nest_type"] = nest_type
    state.current_player_index = awaiting[0]

    return state


@power_handler(2, "choices")
def _power_2_choices(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Handle a player's egg distribution choice."""
    current = stack[-1]
    choice_data = action.replace("activate_", "")
    egg_distribution = {int(k): v for k, v in json.loads(choice_data).items()}
    state = lay_eggs_effect(
        state, egg_distribution, player_index=state.current_player_index
    )

    awaiting = current.context["awaiting_players"]
    awaiting.remove(state.current_player_index)

    if awaiting:
        current.context["awaiting_players"] = awaiting
        state.current_player_index = awaiting[0]
        return state

    state.current_player_index = current.context["activator"]
    stack.pop()
    return state


# =============================================================================
# Power 3: Cache seed on this bird
# =============================================================================


@power_handler(3)
def _power_3_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Cache 1 seed on the activating bird."""
    current = stack[-1]
    spot = current.get_spot(state)
    assert spot.bird
    spot.bird.stashed_food += 1
    stack.pop()
    return state


# =============================================================================
# Power 4: Discard resource to gain resource/cards
# =============================================================================


@power_handler(4)
def _power_4_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Set up discard-to-gain power."""
    current = stack[-1]
    power_data = current.context["power_data"]
    details = power_data["data"]["details"]

    current.phase = "select_discard"
    current.context["discard_type"] = details.get("discard")
    current.context["gain_type"] = details.get("gain")
    current.context["gain_qty"] = details.get("gain_qty", 1)
    current.context["action_type"] = details.get("action")

    return state


@power_handler(4, "select_discard")
def _power_4_select_discard(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Handle discard selection."""
    current = stack[-1]
    discard_type = current.context["discard_type"]
    gain_type = current.context["gain_type"]
    gain_qty = current.context["gain_qty"]
    action_type = current.context["action_type"]

    if discard_type == "egg":
        bird_id = int(action.split("_")[-1])
        state = pay_eggs_effect(state, {bird_id: 1})
    else:
        food_type = action.split("_")[-1]
        state = pay_food_effect(state, {food_type: 1})

    if gain_type == "card":
        if action_type == "draw":
            state = draw_cards_effect(state, tray_bird_ids=[], deck_count=gain_qty)
        elif action_type == "tuck":
            state = tuck_cards_effect(state, current.bird_id, gain_qty)
        stack.pop()
        return state

    if gain_type == "wild":
        current.phase = "select_gain"
        return state

    state = gain_food_effect(state, gain_type, amount=gain_qty)
    stack.pop()
    return state


@power_handler(4, "select_gain")
def _power_4_select_gain(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Handle wild resource gain selection."""
    food_gain_str = action.replace("gain_", "")
    food_distribution = json.loads(food_gain_str)

    for food_type, amount in food_distribution.items():
        state = gain_food_effect(state, food_type, amount=amount)

    stack.pop()
    return state


# =============================================================================
# Power 5: Draw cards or bonus cards
# =============================================================================


@power_handler(5)
def _power_5_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Draw bird cards or bonus cards."""
    current = stack[-1]
    power_data = current.context["power_data"]
    details = power_data["data"].get("details", {})
    amount = details.get("amount")
    discard = details.get("discard")
    bonus = details.get("bonus")

    if not bonus:
        state = draw_cards_effect(state, [], amount)
        if discard:
            state.action_data.end_turn_effects.append(
                EndTurnEffect(
                    effect_type="discard_cards",
                    player_index=state.current_player_index,
                    amount=1,
                )
            )
        stack.pop()
        return state

    # bonus_deck now contains IDs
    drawn_card_ids = [state.bonus_deck.pop() for _ in range(amount)]
    current.context["bonus_options"] = drawn_card_ids
    current.phase = "select_bonus"
    return state


@power_handler(5, "select_bonus")
def _power_5_select_bonus(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Handle bonus card selection."""
    current = stack[-1]
    bonus_id = int(action.split("_")[-1])
    drawn_card_ids = current.context["bonus_options"]

    # bonus_options now contains IDs
    if bonus_id not in drawn_card_ids:
        raise ValueError("Invalid bonus selection")

    state.players[state.current_player_index].bonus_hand.append(bonus_id)

    for card_id in drawn_card_ids:
        if card_id != bonus_id:
            state.discarded_bonuses.append(card_id)

    stack.pop()
    return state


# =============================================================================
# Power 6: Draw N+1 cards, all players select one
# =============================================================================


@power_handler(6)
def _power_6_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Draw cards for all players to select from."""
    current = stack[-1]
    activator = current.player_index
    num_players = len(state.players)
    cards_to_draw = num_players + 1

    ensure_bird_deck(state, cards_to_draw)
    actual_draw = min(cards_to_draw, len(state.bird_deck))
    if actual_draw == 0:
        stack.pop()
        return state

    drawn_card_ids = [state.bird_deck.pop() for _ in range(actual_draw)]

    player_order = [activator]
    for i in range(1, num_players):
        player_order.append((activator + i) % num_players)

    players_to_pick = min(actual_draw, num_players + 1)
    if players_to_pick > num_players:
        player_order.append(activator)
    else:
        player_order = player_order[:players_to_pick]

    current.phase = "select_card"
    current.context["activator"] = activator
    current.context["awaiting_players"] = player_order.copy()
    current.context["available_cards"] = drawn_card_ids
    state.current_player_index = player_order[0]

    return state


@power_handler(6, "select_card")
def _power_6_select_card(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Handle player's card selection."""
    current = stack[-1]
    card_id = int(action.split("_")[-1])
    available_card_ids = current.context["available_cards"]

    if card_id not in available_card_ids:
        raise ValueError(f"Card {card_id} not in available cards")

    state.players[state.current_player_index].bird_hand.append(card_id)
    available_card_ids.remove(card_id)

    awaiting = current.context["awaiting_players"]
    awaiting.remove(state.current_player_index)

    if awaiting:
        current.context["awaiting_players"] = awaiting
        state.current_player_index = awaiting[0]
        return state

    state.current_player_index = current.context["activator"]
    stack.pop()
    return state


# =============================================================================
# Power 7: Each player gains 1 die from birdfeeder
# =============================================================================


@power_handler(7)
def _power_7_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Set up die selection for all players."""
    current = stack[-1]
    current.phase = "choose_starting_player"
    current.context["activator"] = current.player_index
    return state


@power_handler(7, "choose_starting_player")
def _power_7_choose_starting_player(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Handle activator's choice of starting player."""
    current = stack[-1]
    starting_player_index = int(action.split("_")[-1])

    if starting_player_index < 0 or starting_player_index >= len(state.players):
        raise ValueError(f"Invalid player index: {starting_player_index}")

    num_players = len(state.players)
    player_order = [
        (starting_player_index + i) % num_players for i in range(num_players)
    ]

    current.phase = "select_die"
    current.context["awaiting_players"] = player_order
    state.current_player_index = player_order[0]

    return state


@power_handler(7, "select_die")
def _power_7_select_die(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Handle player's die selection."""
    current = stack[-1]

    if action == "reroll_all":
        state.feeder = roll_feeder()
        return state

    die_index, food_type = parse_select_die_action(action)
    state = select_die_effect(
        state, die_index, food_type, player_index=state.current_player_index
    )

    awaiting = current.context["awaiting_players"]
    awaiting.remove(state.current_player_index)

    if awaiting:
        current.context["awaiting_players"] = awaiting
        state.current_player_index = awaiting[0]
        return state

    state.current_player_index = current.context["activator"]
    stack.pop()
    return state


# =============================================================================
# Power 8: Gain food with optional caching
# =============================================================================


@power_handler(8)
def _power_8_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Set up food gain from birdfeeder or supply."""
    current = stack[-1]
    power_data = current.context["power_data"]
    details = power_data["data"].get("details", {})
    can_cache = details["can_cache"]
    source = details["source"]
    quantity = details["quantity"]
    food_types = details["food_types"]

    current.context["can_cache"] = can_cache
    current.context["source"] = source
    current.context["quantity"] = quantity
    current.context["food_types"] = food_types

    if can_cache and quantity != 1:
        raise ValueError(f"Invalid power 8: can_cache=True requires quantity=1")

    if not can_cache and len(food_types) == 1 and source == "supply":
        food_type = food_types[0]
        gain_food_effect(state, food_type, quantity, state.current_player_index)
        stack.pop()
        return state

    if (
        not can_cache
        and len(food_types) == 1
        and source == "birdfeeder"
        and quantity == "all"
    ):
        food_type = food_types[0]
        indices = [
            die_idx for die_idx, face in state.feeder.items() if food_type in face
        ]
        for die_idx in indices:
            select_die_effect(state, die_idx, food_type, state.current_player_index)
        stack.pop()
        return state

    if source == "supply" and can_cache:
        food_type = food_types[0]
        gain_food_effect(state, food_type, 1, state.current_player_index)
        current.phase = "choose_cache"
        current.context["food_type"] = food_type
        return state

    if source == "birdfeeder":
        available_foods = {
            food
            for food in food_types
            for face in state.feeder.values()
            if food in face
        }

        if len(food_types) > 1 and len(available_foods) > 1:
            current.phase = "select_food_type"
            current.context["available_foods"] = list(available_foods)
            return state

        food_type = food_types[0] if len(food_types) == 1 else list(available_foods)[0]
        current.context["food_type"] = food_type

        matching_dice = [
            die_idx for die_idx, face in state.feeder.items() if food_type in face
        ]

        if quantity == 1 and len(matching_dice) == 1 and not can_cache:
            select_die_effect(
                state, matching_dice[0], food_type, state.current_player_index
            )
            stack.pop()
            return state

        current.phase = "select_die"
        if quantity != 1 and quantity != "all":
            current.context["remaining_quantity"] = quantity
        return state

    stack.pop()
    return state


@power_handler(8, "select_food_type")
def _power_8_select_food_type(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Handle food type selection."""
    current = stack[-1]
    food_type = action.replace("select_food_type_", "")
    current.context["food_type"] = food_type

    quantity = current.context["quantity"]
    can_cache = current.context["can_cache"]

    matching_dice = [
        die_idx for die_idx, foods in state.feeder.items() if food_type in foods
    ]

    if quantity == "all":
        for die_idx in matching_dice:
            select_die_effect(state, die_idx, food_type, state.current_player_index)
        stack.pop()
        return state

    if quantity == 1 and len(matching_dice) == 1 and not can_cache:
        select_die_effect(
            state, matching_dice[0], food_type, state.current_player_index
        )
        stack.pop()
        return state

    current.phase = "select_die"
    if quantity > 1:
        current.context["remaining_quantity"] = quantity
    return state


@power_handler(8, "select_die")
def _power_8_select_die(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Handle die selection."""
    current = stack[-1]

    if action == "reroll_all":
        state.feeder = roll_feeder()

        food_type = current.context.get("food_type")
        if food_type:
            matching_dice = [
                die_idx for die_idx, face in state.feeder.items() if food_type in face
            ]
            if not matching_dice:
                stack.pop()
        return state

    die_index, food_type = parse_select_die_action(action)
    state = select_die_effect(state, die_index, food_type, state.current_player_index)

    if "remaining_quantity" in current.context:
        current.context["remaining_quantity"] -= 1
        if current.context["remaining_quantity"] > 0:
            return state

    if current.context.get("can_cache"):
        current.phase = "choose_cache"
        return state

    stack.pop()
    return state


@power_handler(8, "choose_cache")
def _power_8_choose_cache(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Handle cache vs supply decision."""
    current = stack[-1]
    food_type = current.context["food_type"]
    player = state.players[state.current_player_index]

    if action == "cache_food":
        player.food[food_type] -= 1
        if player.food[food_type] == 0:
            del player.food[food_type]

        spot = current.get_spot(state)
        assert spot.bird
        spot.bird.stashed_food += 1

    stack.pop()
    return state


# =============================================================================
# Power 9: Move bird to another habitat
# =============================================================================


@power_handler(9)
def _power_9_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Set up habitat move for rightmost bird."""
    current = stack[-1]
    spot = current.get_spot(state)
    bird = spot.bird
    assert bird
    current_habitat = spot.habitat

    habitat_map = {"forest": 0, "grassland": 1, "wetland": 2}
    player = state.players[current.player_index]
    valid_habitats = []

    for habitat in bird.habitats:
        if habitat != current_habitat:
            target_row = player.board[habitat_map[habitat]]
            if find_leftmost_empty_spot(target_row):
                valid_habitats.append(habitat)

    if len(valid_habitats) == 1:
        target_habitat = valid_habitats[0]
        target_row = player.board[habitat_map[target_habitat]]
        new_spot = find_leftmost_empty_spot(target_row)
        spot.bird = None
        assert new_spot
        new_spot.bird = bird
        stack.pop()
        return state

    current.phase = "select_habitat"
    current.context["valid_habitats"] = valid_habitats
    current.context["current_habitat"] = current_habitat
    return state


@power_handler(9, "select_habitat")
def _power_9_select_habitat(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Handle habitat selection."""
    current = stack[-1]
    habitat = action.split("_")[2]
    current_habitat = current.context["current_habitat"]

    habitat_map = {"forest": 0, "grassland": 1, "wetland": 2}
    player = state.players[current.player_index]

    old_spot = current.get_spot(state)
    bird = old_spot.bird

    target_row = player.board[habitat_map[habitat]]
    new_spot = find_leftmost_empty_spot(target_row)
    if not new_spot:
        raise ValueError("Target spot not available")

    old_spot.bird = None
    new_spot.bird = bird

    stack.pop()
    return state


# =============================================================================
# Power 10: Lay eggs on birds
# =============================================================================


@power_handler(10)
def _power_10_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Lay eggs on specific nest type or this bird."""
    current = stack[-1]
    power_data = current.context["power_data"]
    details = power_data["data"].get("details", {})
    is_this = details.get("this", False)
    nest_type = details.get("type", "")

    player = state.players[current.player_index]

    if is_this:
        spot = current.get_spot(state)
        if spot and spot.bird:
            state = lay_eggs_effect(state, {spot.bird.id: 1})
        stack.pop()
        return state

    if nest_type != "any":
        valid_birds = get_valid_birds_for_eggs(player, nest_type)
        if valid_birds:
            egg_distribution = {bird.id: 1 for bird in valid_birds}
            state = lay_eggs_effect(state, egg_distribution)
        stack.pop()
        return state

    valid_birds = []
    for row in player.board:
        for spot in row:
            if spot.bird is not None and spot.bird.eggs < spot.bird.egg_limit:
                valid_birds.append(spot.bird)

    if len(valid_birds) == 1:
        state = lay_eggs_effect(state, {valid_birds[0].id: 1})
        stack.pop()
        return state

    current.phase = "select_bird"
    current.context["valid_bird_ids"] = [bird.id for bird in valid_birds]
    return state


@power_handler(10, "select_bird")
def _power_10_select_bird(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Handle bird selection for egg laying."""
    bird_id = int(action.split("_")[-1])
    state = lay_eggs_effect(state, {bird_id: 1})
    stack.pop()
    return state


# =============================================================================
# Power 11: Predator - draw and tuck if wingspan < threshold
# =============================================================================


@power_handler(11)
def _power_11_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Execute predator power."""
    current = stack[-1]
    power_data = current.context["power_data"]
    details = power_data["data"].get("details", {})
    wingspan_threshold = details["wingspan"]

    spot = current.get_spot(state)
    activating_bird = spot.bird
    assert activating_bird

    ensure_bird_deck(state, 1)
    drawn_bird_id = state.bird_deck.pop()
    drawn_bird_card = get_bird_card(drawn_bird_id)

    if drawn_bird_card and drawn_bird_card.wingspan < wingspan_threshold:
        activating_bird.tucked_cards += 1

        pink_powers = get_triggered_pink_powers(
            state,
            PinkTrigger.PREDATOR_SUCCESS,
            current.player_index,
        )
        if pink_powers:

            queue = state.action_data.powers_queue
            insert_index = state.action_data.current_power_index + 1
            for i, pp in enumerate(pink_powers):
                queued = QueuedPower(
                    power_id=pp["power_data"]["data"]["id"],
                    bird_id=pp["bird_id"],
                    spot_row=pp["spot"].row,
                    spot_col=pp["spot"].col,
                    player_index=pp["player_index"],
                    power_data=pp["power_data"],
                )
                queue.insert(insert_index + i, queued)
    else:
        state.discarded_birds.append(drawn_bird_id)

    stack.pop()
    return state


# =============================================================================
# Power 12: Play additional bird in habitat
# =============================================================================


@power_handler(12)
def _power_12_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Set up playing additional bird."""
    current = stack[-1]
    power_data = current.context["power_data"]
    details = power_data["data"].get("details", {})
    habitat_spec = details.get("habitat", "")

    if habitat_spec == "this":
        spot = current.get_spot(state)
        target_habitat = spot.habitat
    else:
        target_habitat = habitat_spec

    state.action_data.execution_stack[-1].context["target_habitat"] = target_habitat

    state.game_phase = GamePhase.PLAY_BIRD
    current.phase = "awaiting_bird_play"

    return state


@power_handler(12, "awaiting_bird_play")
def _power_12_awaiting_bird_play(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Called after bird is played - complete the power."""
    stack.pop()
    return state


# =============================================================================
# Power 13: Give resources to players with fewest birds in habitat
# =============================================================================


@power_handler(13)
def _power_13_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Give resources to players with fewest birds."""
    current = stack[-1]
    power_data = current.context["power_data"]
    details = power_data["data"].get("details", {})
    habitat = details.get("habitat")
    item = details.get("item")

    habitat_map = {"forest": 0, "grassland": 1, "wetland": 2}
    habitat_row = habitat_map[habitat]

    bird_counts = {}
    for i, player in enumerate(state.players):
        count = len(
            [spot for spot in player.board[habitat_row] if spot.bird is not None]
        )
        bird_counts[i] = count

    min_count = min(bird_counts.values())
    players_with_fewest = [
        idx for idx, count in bird_counts.items() if count == min_count
    ]

    if item == "card":
        for player_idx in players_with_fewest:
            state = draw_cards_effect(
                state, tray_bird_ids=[], deck_count=1, player_index=player_idx
            )
        stack.pop()
        return state

    current.phase = "select_die"
    current.context["awaiting_players"] = players_with_fewest[:]
    current.context["activator"] = current.player_index
    state.current_player_index = players_with_fewest[0]
    return state


@power_handler(13, "select_die")
def _power_13_select_die(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Handle die selection for Power 13."""
    current = stack[-1]

    if action == "reroll_all":
        state.feeder = roll_feeder()
        return state

    die_index, food_type = parse_select_die_action(action)
    state = select_die_effect(
        state, die_index, food_type, player_index=state.current_player_index
    )

    awaiting = current.context["awaiting_players"]
    awaiting.remove(state.current_player_index)

    if awaiting:
        current.context["awaiting_players"] = awaiting
        state.current_player_index = awaiting[0]
        return state

    state.current_player_index = current.context["activator"]
    stack.pop()
    return state


# =============================================================================
# Power 14: Repeat another bird's power in this habitat
# =============================================================================


@power_handler(14)
def _power_14_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Set up bird selection for power repeat."""
    current = stack[-1]
    power_data = current.context["power_data"]
    details = power_data["data"].get("details", {})
    repeat_type = details.get("type")

    spot = current.get_spot(state)
    player = state.players[current.player_index]
    habitat_row = player.board[spot.row]

    eligible_birds = []

    for other_spot in habitat_row:
        if other_spot.bird is None:
            continue
        if other_spot.bird.id == current.bird_id:
            continue

        other_power = get_bird_power(other_spot.bird.id)
        if not other_power or not other_power.get("data"):
            continue

        if repeat_type == "predator":
            if other_power["data"].get("id") == 11:
                eligible_birds.append(
                    {
                        "bird_id": other_spot.bird.id,
                        "spot_row": other_spot.row,
                        "spot_col": other_spot.col,
                        "power_data": other_power,
                    }
                )

        elif repeat_type == "brown":
            if other_power.get("color") == "brown":
                if other_power["data"].get("id") == 14:
                    continue
                power_entry_candidate = {
                    "bird_id": other_spot.bird.id,
                    "spot": other_spot,
                    "power_data": other_power,
                    "player_index": current.player_index,
                }
                if can_execute_power(state, power_entry_candidate):
                    eligible_birds.append(
                        {
                            "bird_id": other_spot.bird.id,
                            "spot_row": other_spot.row,
                            "spot_col": other_spot.col,
                            "power_data": other_power,
                        }
                    )

    if not eligible_birds:
        raise ValueError("No eligible birds found")

    current.phase = "select_bird"
    current.context["eligible_birds"] = eligible_birds
    current.context["repeat_type"] = repeat_type
    return state


@power_handler(14, "select_bird")
def _power_14_select_bird(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Handle bird selection - push the repeated power onto the stack."""
    current = stack[-1]
    selected_bird_id = int(action.split("_")[-1])
    eligible_birds = current.context["eligible_birds"]

    selected = next(
        (b for b in eligible_birds if b["bird_id"] == selected_bird_id), None
    )
    if not selected:
        raise ValueError(f"Bird {selected_bird_id} not in eligible birds")

    stack.pop()

    stack.append(
        PowerExecution(
            power_id=selected["power_data"]["data"]["id"],
            bird_id=selected["bird_id"],
            spot_row=selected["spot_row"],
            spot_col=selected["spot_col"],
            player_index=current.player_index,
            phase=None,
            context={"power_data": selected["power_data"]},
        )
    )

    return state


# =============================================================================
# Power 15: Roll dice not in birdfeeder
# =============================================================================


@power_handler(15)
def _power_15_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Roll dice not in birdfeeder, cache if matching."""
    current = stack[-1]
    power_data = current.context["power_data"]
    food_type = power_data["data"]["details"].get("type")

    n_dice = 5 - len(state.feeder)
    faces = [
        ["fish"],
        ["fruit"],
        ["rodent"],
        ["invertebrate"],
        ["seed"],
        ["invertebrate", "seed"],
    ]
    roll = [random.choice(faces) for _ in range(n_dice)]

    for face in roll:
        if food_type in face:
            spot = current.get_spot(state)
            assert spot.bird
            spot.bird.stashed_food += 1
            break

    stack.pop()
    return state


# =============================================================================
# Power 16: Trade food for another type
# =============================================================================


@power_handler(16)
def _power_16_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Set up food trade."""
    current = stack[-1]
    current.phase = "select_trade"
    return state


@power_handler(16, "select_trade")
def _power_16_select_trade(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Handle trade selection."""
    parts = action.split("_")
    from_type = parts[1]
    to_type = parts[3]

    state = pay_food_effect(state, {from_type: 1})
    state = gain_food_effect(state, to_type, amount=1)

    stack.pop()
    return state


# =============================================================================
# Power 17: Tuck card for bonus
# =============================================================================


@power_handler(17)
def _power_17_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Set up card tuck."""
    current = stack[-1]
    power_data = current.context["power_data"]
    details = power_data["data"].get("details", {})

    current.phase = "select_card"
    current.context["types"] = details.get("types", [])
    return state


@power_handler(17, "select_card")
def _power_17_select_card(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Handle card selection for tucking."""
    current = stack[-1]
    card_id = int(action.split("_")[-1])
    player = state.players[state.current_player_index]
    bonus_types = current.context["types"]
    spot = current.get_spot(state)

    if card_id not in player.bird_hand:
        raise ValueError(f"Card {card_id} not in hand")

    player.bird_hand.remove(card_id)
    assert spot.bird
    spot.bird.tucked_cards += 1

    if bonus_types == ["card"]:
        state = draw_cards_effect(state, tray_bird_ids=[], deck_count=1)
        stack.pop()
        return state
    elif bonus_types == ["egg"]:
        state = lay_eggs_effect(state, {current.bird_id: 1})
        stack.pop()
        return state
    elif len(bonus_types) == 1:
        state = gain_food_effect(state, bonus_types[0], amount=1)
        stack.pop()
        return state
    else:
        current.phase = "select_food"
        current.context["food_types"] = bonus_types
        return state


@power_handler(17, "select_food")
def _power_17_select_food(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Handle food selection for tuck bonus."""
    food_type = action.replace("select_food_", "")
    state = gain_food_effect(state, food_type, amount=1)
    stack.pop()
    return state


# =============================================================================
# Power 18: Pink - gain resource when opponent plays in habitat
# =============================================================================


@power_handler(18)
def _power_18_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Gain resource or tuck card."""
    current = stack[-1]
    power_data = current.context["power_data"]
    details = power_data["data"].get("details", {})
    resource = details.get("resource")

    if resource == "card":
        current.phase = "select_card"
        return state

    state = gain_food_effect(
        state, resource, amount=1, player_index=current.player_index
    )
    stack.pop()
    return state


@power_handler(18, "select_card")
def _power_18_select_card(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Handle card selection for tucking."""
    current = stack[-1]
    card_id = int(action.split("_")[-1])
    player = state.players[current.player_index]
    spot = current.get_spot(state)

    if card_id not in player.bird_hand:
        raise ValueError(f"Card {card_id} not in hand")

    player.bird_hand.remove(card_id)
    assert spot.bird
    spot.bird.tucked_cards += 1

    stack.pop()
    return state


# =============================================================================
# Power 19: Pink - cache rodent when opponent gains rodent
# =============================================================================


@power_handler(19)
def _power_19_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Cache rodent on this bird."""
    current = stack[-1]
    spot = current.get_spot(state)
    assert spot.bird
    spot.bird.stashed_food += 1
    stack.pop()
    return state


# =============================================================================
# Power 20: Pink - lay egg when opponent lays eggs
# =============================================================================


@power_handler(20)
def _power_20_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Lay egg on nest type."""
    current = stack[-1]
    power_data = current.context["power_data"]
    details = power_data["data"].get("details", {})
    nest_type = details.get("type")

    player = state.players[current.player_index]
    valid_birds = get_valid_birds_for_eggs(player, nest_type)
    valid_birds = [b for b in valid_birds if b.id != current.bird_id]

    if len(valid_birds) == 1:
        state = lay_eggs_effect(
            state, {valid_birds[0].id: 1}, player_index=current.player_index
        )
        stack.pop()
        return state

    current.phase = "select_bird"
    current.context["valid_bird_ids"] = [bird.id for bird in valid_birds]
    return state


@power_handler(20, "select_bird")
def _power_20_select_bird(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Handle bird selection for egg laying."""
    current = stack[-1]
    bird_id = int(action.split("_")[-1])
    state = lay_eggs_effect(state, {bird_id: 1}, player_index=current.player_index)
    stack.pop()
    return state


# =============================================================================
# Power 21: Pink - gain die when opponent's predator succeeds
# =============================================================================


@power_handler(21)
def _power_21_activate(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Set up die selection."""
    current = stack[-1]
    current.phase = "select_die"
    return state


@power_handler(21, "select_die")
def _power_21_select_die(
    state: GameState, stack: List[PowerExecution], action: str
) -> GameState:
    """Handle die selection."""
    current = stack[-1]

    if action == "reroll_all":
        state.feeder = roll_feeder()
        return state

    die_index, food_type = parse_select_die_action(action)
    state = select_die_effect(
        state, die_index, food_type, player_index=current.player_index
    )

    stack.pop()
    return state
