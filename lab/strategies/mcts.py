from __future__ import annotations

import math
import multiprocessing as mp
from multiprocessing.pool import Pool
import random
import signal
from dataclasses import dataclass, field
from typing import Any

from game.core import GameState, Action, copy_state, init_registries
from game.actions import get_actions
from game.engine import transition_state

from .base import Strategy, ValueFunction, register_strategy

# =============================================================================
# Data structures
# =============================================================================


@dataclass(frozen=True, slots=True)
class MCTSConfig:
    """Configuration for MCTS strategy."""

    simulations: int = 1000
    exploration_constant: float = 1.41
    value_function: ValueFunction = ValueFunction.SCORE_DELTA
    num_workers: int = 1


@dataclass(slots=True)
class MCTSNode:
    """A node in the MCTS tree."""

    state: GameState
    player_index: int
    parent: MCTSNode | None = None
    action_taken: Action | None = None
    children: dict[Action, MCTSNode] = field(default_factory=dict)
    visits: int = 0
    total_value: float = 0.0
    untried_actions: list[Action] = field(default_factory=list)

    def __post_init__(self):
        if not self.untried_actions:
            self.untried_actions = get_actions(self.state)

    @property
    def is_terminal(self) -> bool:
        return len(self.untried_actions) == 0 and len(self.children) == 0

    @property
    def is_fully_expanded(self) -> bool:
        return len(self.untried_actions) == 0

    def ucb1(self, exploration_constant: float) -> float:
        if self.visits == 0:
            return float("inf")
        if self.parent is None:
            raise ValueError("UCB1 cannot be computed on the root node (no parent)")
        exploitation = self.total_value / self.visits
        exploration = exploration_constant * math.sqrt(
            math.log(self.parent.visits) / self.visits
        )
        return exploitation + exploration


# =============================================================================
# MCTS algorithm
# =============================================================================


def _select(node: MCTSNode, exploration_constant: float) -> MCTSNode:
    while not node.is_terminal and node.is_fully_expanded:
        node = max(node.children.values(), key=lambda n: n.ucb1(exploration_constant))
    return node


def _expand(node: MCTSNode, rng: random.Random) -> MCTSNode:
    if node.is_terminal or not node.untried_actions:
        return node

    idx = rng.randrange(len(node.untried_actions))
    action = node.untried_actions[idx]
    node.untried_actions[idx] = node.untried_actions[-1]
    node.untried_actions.pop()

    new_state = transition_state(node.state, action)
    child = MCTSNode(
        state=new_state,
        player_index=new_state.current_player_index,
        parent=node,
        action_taken=action,
    )
    node.children[action] = child
    return child


def _simulate(
    node: MCTSNode,
    root_player_index: int,
    value_function: ValueFunction,
    rng: random.Random,
) -> float:
    state = node.state
    while actions := get_actions(state):
        action = rng.choice(actions)
        state = transition_state(state, action)
    return _compute_value(state, root_player_index, value_function)


def _compute_value(
    state: GameState,
    player_index: int,
    value_function: ValueFunction,
) -> float:
    player = state.players[player_index]
    player_score = player.score.total

    opponent_scores = [
        p.score.total for i, p in enumerate(state.players) if i != player_index
    ]
    max_opponent_score = max(opponent_scores) if opponent_scores else 0

    match value_function:
        case ValueFunction.ABSOLUTE_SCORE:
            return player_score / 100.0
        case ValueFunction.SCORE_DELTA:
            return (player_score - max_opponent_score) / 50.0
        case ValueFunction.WIN_LOSS:
            if player_score > max_opponent_score:
                return 1.0
            elif player_score < max_opponent_score:
                return 0.0
            else:
                player_food = sum(player.food.values())
                opponent_foods = [
                    sum(p.food.values())
                    for i, p in enumerate(state.players)
                    if i != player_index
                ]
                max_opponent_food = max(opponent_foods) if opponent_foods else 0
                if player_food > max_opponent_food:
                    return 1.0
                elif player_food < max_opponent_food:
                    return 0.0
                return 0.5
        case _:
            raise ValueError(f"Unknown value function: {value_function}")


def _backpropagate(node: MCTSNode | None, value: float) -> None:
    while node is not None:
        node.visits += 1
        node.total_value += value
        node = node.parent


# =============================================================================
# Parallel worker infrastructure
# =============================================================================


def _worker_init():
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    init_registries()


def _run_mcts_worker(args: tuple) -> dict[Action, tuple[int, float]]:
    state, player_index, simulations, exploration_constant, value_function, seed = args
    rng = random.Random(seed)

    root = MCTSNode(state=state, player_index=player_index)

    for _ in range(simulations):
        node = _select(root, exploration_constant)
        node = _expand(node, rng)
        value = _simulate(node, player_index, value_function, rng)
        _backpropagate(node, value)

    return {
        action: (child.visits, child.total_value)
        for action, child in root.children.items()
    }


# =============================================================================
# Strategy
# =============================================================================


@register_strategy
class MCTSStrategy(Strategy):
    """Monte Carlo Tree Search strategy."""

    name = "mcts"

    def __init__(
        self,
        *,
        config: MCTSConfig | None = None,
        seed: int | None = None,
        **kwargs,
    ):
        if config is not None:
            self.config = config
        elif kwargs:
            config_kwargs = {
                k: v for k, v in kwargs.items() if k in MCTSConfig.__dataclass_fields__
            }
            if "value_function" in config_kwargs and isinstance(
                config_kwargs["value_function"], str
            ):
                config_kwargs["value_function"] = ValueFunction(
                    config_kwargs["value_function"]
                )
            self.config = MCTSConfig(**config_kwargs)
        else:
            self.config = MCTSConfig()
        self._seed: int = seed if seed is not None else random.randint(0, 2**31)
        self._rng = random.Random(self._seed)
        self._last_visit_counts: dict[Action, int] | None = None
        self._last_root_value: float | None = None
        self._last_action_values: dict[Action, float] | None = None
        self._pool: Pool | None = None

    def __enter__(self) -> MCTSStrategy:
        if self.config.num_workers > 1 and self._pool is None:
            ctx = mp.get_context("spawn")
            self._pool = ctx.Pool(self.config.num_workers, initializer=_worker_init)
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: object,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._pool is not None:
            self._pool.terminate()
            self._pool.join()
            self._pool = None

    def select_action(self, state: GameState, legal_actions: list[Action]) -> Action:
        if len(legal_actions) == 1:
            self._last_visit_counts = {legal_actions[0]: 1}
            self._last_root_value = None
            self._last_action_values = None
            return legal_actions[0]

        if self.config.num_workers > 1:
            return self._select_action_parallel(state)
        return self._select_action_sequential(state)

    def _select_action_sequential(self, state: GameState) -> Action:
        root = MCTSNode(
            state=copy_state(state), player_index=state.current_player_index
        )

        for _ in range(self.config.simulations):
            node = _select(root, self.config.exploration_constant)
            node = _expand(node, self._rng)
            value = _simulate(
                node, root.player_index, self.config.value_function, self._rng
            )
            _backpropagate(node, value)

        self._last_visit_counts = {
            action: child.visits for action, child in root.children.items()
        }
        self._last_root_value = root.total_value / root.visits if root.visits else None
        self._last_action_values = {
            action: child.total_value / child.visits
            for action, child in root.children.items()
            if child.visits > 0
        }
        return max(root.children.items(), key=lambda x: x[1].visits)[0]

    def _select_action_parallel(self, state: GameState) -> Action:
        num_workers = self.config.num_workers
        base_sims = self.config.simulations // num_workers
        remainder = self.config.simulations % num_workers
        worker_seeds = [self._rng.randint(0, 2**31) for _ in range(num_workers)]

        worker_args = [
            (
                copy_state(state),
                state.current_player_index,
                base_sims + (1 if i < remainder else 0),
                self.config.exploration_constant,
                self.config.value_function,
                worker_seeds[i],
            )
            for i in range(num_workers)
        ]

        if self._pool is None:
            ctx = mp.get_context("spawn")
            self._pool = ctx.Pool(num_workers, initializer=_worker_init)

        results = self._pool.map(_run_mcts_worker, worker_args)

        merged_visits: dict[Action, int] = {}
        merged_values: dict[Action, float] = {}
        for worker_result in results:
            for action, (visits, total_value) in worker_result.items():
                merged_visits[action] = merged_visits.get(action, 0) + visits
                merged_values[action] = merged_values.get(action, 0.0) + total_value

        self._last_visit_counts = merged_visits
        total_visits = sum(merged_visits.values())
        total_value = sum(merged_values.values())
        self._last_root_value = total_value / total_visits if total_visits else None
        self._last_action_values = {
            action: merged_values[action] / merged_visits[action]
            for action in merged_visits
            if merged_visits[action] > 0
        }
        return max(merged_visits.items(), key=lambda x: x[1])[0]

    @property
    def config_for_storage(self) -> dict[str, Any]:
        return {
            "simulations": self.config.simulations,
            "value_function": self.config.value_function.value,
            "exploration_constant": self.config.exploration_constant,
            "num_workers": self.config.num_workers,
            "strategy_seed": self._seed,
        }

    def get_last_visit_counts(self) -> dict[Action, int] | None:
        return self._last_visit_counts

    def get_last_root_value(self) -> float | None:
        return self._last_root_value

    def get_last_action_values(self) -> dict[Action, float] | None:
        return self._last_action_values

    def __str__(self) -> str:
        return f"MCTS(n={self.config.simulations}, c={self.config.exploration_constant}, {self.config.value_function.value})"
