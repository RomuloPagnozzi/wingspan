from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .player import Spot
    from .constants import GamePhase
    from .game import GameState


@dataclass(slots=True)
class PowerExecution:
    """A power currently being executed on the execution stack."""

    power_id: int
    bird_id: int
    spot_row: int
    spot_col: int
    player_index: int
    phase: str | None
    context: dict[str, Any] = field(default_factory=dict)

    def get_spot(self, state: GameState) -> Spot:
        """Resolve spot reference from the state."""
        return state.players[self.player_index].board[self.spot_row][self.spot_col]


@dataclass(slots=True)
class QueuedPower:
    """A power waiting in the activation queue."""

    power_id: int
    bird_id: int
    spot_row: int
    spot_col: int
    player_index: int
    power_data: dict[str, Any]


@dataclass(slots=True)
class CostPayment:
    """Context for paying egg or food cost."""

    cost_type: str
    amount: int | dict[str, int] | list[dict[str, int]]
    callback_phase: GamePhase
    callback_action: str


@dataclass(slots=True)
class EndTurnEffect:
    """A deferred end-of-turn effect."""

    effect_type: str
    player_index: int
    amount: int = 0


@dataclass(slots=True)
class ActionData:
    """This structure holds all transient state needed during action resolution,
    power execution, and turn management.
    """

    powers_queue: list[QueuedPower] = field(default_factory=list)
    current_power_index: int = 0
    action_player_index: int | None = None
    execution_stack: list[PowerExecution] = field(default_factory=list)
    pending_cost: CostPayment | None = None
    end_turn_effects: list[EndTurnEffect] = field(default_factory=list)
    food_needed: int = 0
    eggs_needed: int = 0
    cards_needed: int = 0
    base_amount: int = 0
    gained_rodent: bool = False
    amount_to_discard: int = 0
    pending_callback: tuple[GamePhase, str] | None = None

    def clear(self) -> None:
        """Reset to empty state for new turn."""
        self.powers_queue.clear()
        self.current_power_index = 0
        self.action_player_index = None
        self.execution_stack.clear()
        self.pending_cost = None
        self.end_turn_effects.clear()
        self.food_needed = 0
        self.eggs_needed = 0
        self.cards_needed = 0
        self.base_amount = 0
        self.gained_rodent = False
        self.amount_to_discard = 0
        self.pending_callback = None

    def get_current_queued_power(self) -> QueuedPower | None:
        """Get the current power from the queue, if any."""
        if self.current_power_index < len(self.powers_queue):
            return self.powers_queue[self.current_power_index]
        return None

    def get_current_execution(self) -> PowerExecution | None:
        """Get the top of the execution stack, if any."""
        if self.execution_stack:
            return self.execution_stack[-1]
        return None
