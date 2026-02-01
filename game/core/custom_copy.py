import copy

from .player import Player, ScoreState, BirdState, PlacedBird, Spot
from .turn_data import QueuedPower, CostPayment, ActionData
from .game import GameState


def _copy_bird_state(bs: BirdState) -> BirdState:
    """Copy a BirdState (just 3 ints)."""
    return BirdState(bs.eggs, bs.stashed_food, bs.tucked_cards)


def _copy_placed_bird(pb: PlacedBird | None) -> PlacedBird | None:
    """Copy a PlacedBird (card_id + state)."""
    if pb is None:
        return None
    return PlacedBird(pb.card_id, _copy_bird_state(pb.state))


def _copy_spot(spot: Spot) -> Spot:
    """Copy a Spot with its bird."""
    new_spot = object.__new__(Spot)
    new_spot.row = spot.row
    new_spot.col = spot.col
    new_spot.habitat = spot.habitat
    new_spot.resource = spot.resource
    new_spot.resource_amount = spot.resource_amount
    new_spot.extra_resource = spot.extra_resource
    new_spot.egg_cost = spot.egg_cost
    if spot.bird is None:
        new_spot.bird = None
    else:
        new_spot.bird = _copy_placed_bird(spot.bird)
    return new_spot


def _copy_score_state(score: ScoreState) -> ScoreState:
    """Copy a ScoreState."""
    new_score = object.__new__(ScoreState)
    new_score.bird_points = score.bird_points
    new_score.egg_points = score.egg_points
    new_score.cached_food = score.cached_food
    new_score.tucked_cards = score.tucked_cards
    new_score.round_goals = list(score.round_goals)
    new_score.bonus_scores = dict(score.bonus_scores)
    return new_score


def _copy_player(player: Player) -> Player:
    """Copy a Player with all nested state."""
    new_player = object.__new__(Player)
    new_player.id = player.id
    new_player.bird_hand = list(player.bird_hand)
    new_player.bonus_hand = list(player.bonus_hand)
    new_player.food = dict(player.food)
    new_player.action_cubes = player.action_cubes
    new_player.first_player = player.first_player
    new_player.used_pink_powers = set(player.used_pink_powers)
    new_player.board = [[_copy_spot(spot) for spot in row] for row in player.board]
    new_player.score = _copy_score_state(player.score)
    return new_player


def _copy_queued_power(qp: QueuedPower) -> QueuedPower:
    """Copy a QueuedPower."""
    return QueuedPower(
        power_id=qp.power_id,
        bird_id=qp.bird_id,
        spot_row=qp.spot_row,
        spot_col=qp.spot_col,
        player_index=qp.player_index,
        power_data=qp.power_data,
    )


def _copy_cost_payment(cp: CostPayment | None) -> CostPayment | None:
    """Copy a CostPayment."""
    if cp is None:
        return None
    if isinstance(cp.amount, int):
        new_amount = cp.amount
    elif isinstance(cp.amount, dict):
        new_amount = dict(cp.amount)
    else:
        new_amount = [dict(d) for d in cp.amount]
    return CostPayment(
        cost_type=cp.cost_type,
        amount=new_amount,
        callback_phase=cp.callback_phase,
        callback_action=cp.callback_action,
    )


def _copy_action_data(ad: ActionData) -> ActionData:
    """Copy ActionData with all nested structures."""
    new_ad = object.__new__(ActionData)
    new_ad.powers_queue = [_copy_queued_power(qp) for qp in ad.powers_queue]
    new_ad.current_power_index = ad.current_power_index
    new_ad.action_player_index = ad.action_player_index
    new_ad.execution_stack = [copy.deepcopy(pe) for pe in ad.execution_stack]
    new_ad.pending_cost = _copy_cost_payment(ad.pending_cost)
    new_ad.end_turn_effects = list(ad.end_turn_effects)
    new_ad.food_needed = ad.food_needed
    new_ad.eggs_needed = ad.eggs_needed
    new_ad.cards_needed = ad.cards_needed
    new_ad.base_amount = ad.base_amount
    new_ad.gained_rodent = ad.gained_rodent
    new_ad.amount_to_discard = ad.amount_to_discard
    new_ad.pending_callback = ad.pending_callback
    return new_ad


def copy_state(state: GameState) -> GameState:
    """Fast state copy without deepcopy overhead."""
    new_state = object.__new__(GameState)
    new_state.players = [_copy_player(p) for p in state.players]
    new_state.bird_deck = list(state.bird_deck)
    new_state.discarded_birds = list(state.discarded_birds)
    new_state.bonus_deck = list(state.bonus_deck)
    new_state.discarded_bonuses = list(state.discarded_bonuses)
    new_state.bird_tray = list(state.bird_tray)
    new_state.feeder = {k: list(v) for k, v in state.feeder.items()}
    new_state.round = state.round
    new_state.current_player_index = state.current_player_index
    new_state.game_phase = state.game_phase
    new_state.action_data = _copy_action_data(state.action_data)
    new_state.round_goal_config = state.round_goal_config
    return new_state
