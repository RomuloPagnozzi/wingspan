from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from game.core import GameState, Action, copy_state, redeterminize
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
    determinize: bool = False


@dataclass(slots=True)
class MCTSNode:
    """Peek-mode MCTS node: caches state, tracks untried legal actions."""

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


@dataclass(slots=True)
class ISMCTSNode:
    """IS-MCTS node: stateless. State is reconstructed per-simulation from a
    freshly determinized root by replaying actions along the path.

    `availability` counts how often this child was a legal candidate for
    selection at its parent (across all sampled worlds). It replaces the
    parent-visit count in the UCB exploration term per Cowling et al. 2012
    so children that are only sometimes-legal aren't unfairly down-weighted.
    """

    parent: ISMCTSNode | None = None
    action_taken: Action | None = None
    children: dict[Action, ISMCTSNode] = field(default_factory=dict)
    visits: int = 0
    availability: int = 0
    total_value: float = 0.0

    def ucb1_ismcts(self, exploration_constant: float) -> float:
        if self.visits == 0 or self.availability == 0:
            return float("inf")
        exploitation = self.total_value / self.visits
        exploration = exploration_constant * math.sqrt(
            math.log(self.availability) / self.visits
        )
        return exploitation + exploration


# =============================================================================
# Shared helpers
# =============================================================================


def _simulate_from_state(
    state: GameState,
    root_player_index: int,
    value_function: ValueFunction,
    rng: random.Random,
) -> float:
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


def _backpropagate(node: MCTSNode | ISMCTSNode | None, value: float) -> None:
    while node is not None:
        node.visits += 1
        node.total_value += value
        node = node.parent


# =============================================================================
# Peek MCTS algorithm
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


def _peek_iteration(
    root: MCTSNode,
    exploration_constant: float,
    value_function: ValueFunction,
    rng: random.Random,
) -> None:
    node = _select(root, exploration_constant)
    node = _expand(node, rng)
    value = _simulate_from_state(node.state, root.player_index, value_function, rng)
    _backpropagate(node, value)


# =============================================================================
# IS-MCTS algorithm (per-simulation determinization, SO-ISMCTS)
# =============================================================================


def _ismcts_iteration(
    root: ISMCTSNode,
    root_state: GameState,
    perspective_player: int,
    exploration_constant: float,
    value_function: ValueFunction,
    rng: random.Random,
) -> None:
    state = redeterminize(root_state, perspective_player, rng)
    node = root

    while True:
        legal = get_actions(state)
        if not legal:
            value = _compute_value(state, perspective_player, value_function)
            _backpropagate(node, value)
            return

        legal_set = set(legal)
        untried = [a for a in legal if a not in node.children]

        if untried:
            idx = rng.randrange(len(untried))
            action = untried[idx]
            state = transition_state(state, action)
            child = ISMCTSNode(parent=node, action_taken=action)
            node.children[action] = child
            value = _simulate_from_state(state, perspective_player, value_function, rng)
            _backpropagate(child, value)
            return

        # All legal actions have a child. Increment availability for every
        # compatible child (per IS-MCTS), then UCB-select among them.
        compatible = [(a, c) for a, c in node.children.items() if a in legal_set]
        for _, c in compatible:
            c.availability += 1
        action, child = max(
            compatible, key=lambda ac: ac[1].ucb1_ismcts(exploration_constant)
        )
        state = transition_state(state, action)
        node = child


# =============================================================================
# Strategy
# =============================================================================


@register_strategy
class MCTSStrategy(Strategy):
    """Monte Carlo Tree Search strategy.

    Single-threaded. Experiment-level parallelism (running multiple games
    concurrently) is owned by the harness, not by the strategy.
    """

    name = "mcts"

    def __init__(
        self,
        *,
        params: MCTSConfig | None = None,
        seed: int | None = None,
        **kwargs,
    ):
        if params is not None:
            self.params = params
        elif kwargs:
            params_kwargs = {
                k: v for k, v in kwargs.items() if k in MCTSConfig.__dataclass_fields__
            }
            if "value_function" in params_kwargs and isinstance(
                params_kwargs["value_function"], str
            ):
                params_kwargs["value_function"] = ValueFunction(
                    params_kwargs["value_function"]
                )
            self.params = MCTSConfig(**params_kwargs)
        else:
            self.params = MCTSConfig()
        self.seed: int = seed if seed is not None else random.randint(0, 2**31)
        self._rng = random.Random(self.seed)
        self._last_visit_counts: dict[Action, int] | None = None
        self._last_root_value: float | None = None
        self._last_action_values: dict[Action, float] | None = None

    def select_action(self, state: GameState, legal_actions: list[Action]) -> Action:
        if len(legal_actions) == 1:
            self._last_visit_counts = {legal_actions[0]: 1}
            self._last_root_value = None
            self._last_action_values = None
            return legal_actions[0]

        perspective = state.current_player_index
        root_state = copy_state(state)

        if self.params.determinize:
            ismcts_root = ISMCTSNode()
            for _ in range(self.params.simulations):
                _ismcts_iteration(
                    ismcts_root,
                    root_state,
                    perspective,
                    self.params.exploration_constant,
                    self.params.value_function,
                    self._rng,
                )
            children = ismcts_root.children
            root_visits = ismcts_root.visits
            root_total_value = ismcts_root.total_value
        else:
            peek_root = MCTSNode(state=root_state, player_index=perspective)
            for _ in range(self.params.simulations):
                _peek_iteration(
                    peek_root,
                    self.params.exploration_constant,
                    self.params.value_function,
                    self._rng,
                )
            children = peek_root.children
            root_visits = peek_root.visits
            root_total_value = peek_root.total_value

        self._last_visit_counts = {action: c.visits for action, c in children.items()}
        self._last_root_value = root_total_value / root_visits if root_visits else None
        self._last_action_values = {
            action: c.total_value / c.visits
            for action, c in children.items()
            if c.visits > 0
        }
        return max(children.items(), key=lambda x: x[1].visits)[0]

    def get_last_visit_counts(self) -> dict[Action, int] | None:
        return self._last_visit_counts

    def get_last_root_value(self) -> float | None:
        return self._last_root_value

    def get_last_action_values(self) -> dict[Action, float] | None:
        return self._last_action_values

    def __str__(self) -> str:
        mode = "ismcts" if self.params.determinize else "peek"
        return (
            f"MCTS(n={self.params.simulations}, c={self.params.exploration_constant}, "
            f"{self.params.value_function.value}, {mode})"
        )
