"""Shared game simulation logic."""

from datetime import datetime

from game.core import initiate_state
from game.actions import get_actions
from game.engine import transition_state
from lab.strategies import Strategy

from lab.data import (
    GameResult,
    PlayerResult,
    GameDecisions,
    DecisionRecord,
    generate_game_id,
)


def simulate_game(
    strategies: list[Strategy],
    game_seed: int,
    record_decisions: bool = False,
) -> tuple[GameResult, GameDecisions | None]:
    """Run a single game and return the result.

    Args:
        strategies: List of strategies, one per player
        game_seed: Seed for game state (cards, dice, etc.)
        record_decisions: Whether to record per-decision data for RL training

    Returns:
        Tuple of (GameResult, optional GameDecisions)
    """
    game_id = generate_game_id()
    state = initiate_state(len(strategies), seed=game_seed)

    game_decisions = (
        GameDecisions(
            game_id=game_id,
            game_seed=game_seed,
            player_outcomes={},
            decisions=[],
        )
        if record_decisions
        else None
    )

    total_decisions = 0
    while actions := get_actions(state):
        total_decisions += 1
        player_idx = state.current_player_index
        strategy = strategies[player_idx]
        action = strategy.select_action(state, actions)

        if game_decisions is not None and len(actions) > 1:
            config = strategy.config_for_storage
            visit_counts = strategy.get_last_visit_counts()
            root_value = strategy.get_last_root_value()
            action_values = strategy.get_last_action_values()
            game_decisions.add_decision(
                DecisionRecord(
                    player_position=player_idx + 1,
                    strategy_seed=config.get("strategy_seed", 0),
                    round=state.round,
                    game_phase=state.game_phase.value,
                    action_taken=str(action),
                    legal_actions=[str(a) for a in actions],
                    visit_counts=(
                        {str(k): v for k, v in visit_counts.items()}
                        if visit_counts
                        else None
                    ),
                    mcts_root_value=root_value,
                    mcts_action_values=(
                        {str(k): v for k, v in action_values.items()}
                        if action_values
                        else None
                    ),
                )
            )

        state = transition_state(state, action)

    first_player_idx = next(i for i, p in enumerate(state.players) if p.first_player)
    scores = [
        (p.score.total, sum(p.food.values()), i) for i, p in enumerate(state.players)
    ]
    scores.sort(key=lambda x: (x[0], x[1]), reverse=True)
    winner_idx = (
        scores[0][2]
        if scores[0][0] > scores[1][0] or scores[0][1] > scores[1][1]
        else None
    )

    players = []
    for i, player in enumerate(state.players):
        config = strategies[i].config_for_storage
        players.append(
            PlayerResult(
                player_position=i + 1,
                is_first_player=(i == first_player_idx),
                is_winner=(i == winner_idx),
                strategy_name=strategies[i].name,
                simulations=config.get("simulations"),
                exploration_constant=config.get("exploration_constant"),
                value_function=config.get("value_function"),
                strategy_seed=config.get("strategy_seed"),
                total_score=player.score.total,
                bird_points=player.score.bird_points,
                egg_points=player.score.egg_points,
                cached_food=player.score.cached_food,
                tucked_cards=player.score.tucked_cards,
                round_goals=sum(player.score.round_goals),
                bonus_scores=sum(player.score.bonus_scores.values()),
                food_tokens=sum(player.food.values()),
            )
        )

    if game_decisions is not None:
        for i in range(len(strategies)):
            if i == winner_idx:
                game_decisions.player_outcomes[i + 1] = 1.0
            elif winner_idx is None:
                game_decisions.player_outcomes[i + 1] = 0.0
            else:
                game_decisions.player_outcomes[i + 1] = -1.0

    return (
        GameResult(
            game_id=game_id,
            timestamp=datetime.now(),
            player_count=len(strategies),
            players=players,
            game_seed=game_seed,
            total_decisions=total_decisions,
        ),
        game_decisions,
    )
