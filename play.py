"""WIP: minimal Textual TUI for interactively testing the game engine."""

from game.core import (
    initiate_state,
    get_bird_card,
    get_bonus_card,
    SimpleAction,
    SelectInitialAction,
)
from game.actions import get_actions
from game.engine import transition_state

from textual.app import App, ComposeResult
from textual.widgets import (
    Header,
    Footer,
    ListView,
    ListItem,
    Label,
    SelectionList,
    RadioSet,
    Button,
)
from textual.widgets.selection_list import Selection


class WingspanApp(App):

    def __init__(self):
        super().__init__()
        self.state = initiate_state(2)
        self.actions = get_actions(self.state)
        if self.actions == [SimpleAction("start_setup")]:
            self.state = transition_state(self.state, SimpleAction("start_setup"))
            self.actions = get_actions(self.state)

    def compose(self) -> ComposeResult:
        yield Header()

        if self.actions and self._is_setup_action(self.actions[0]):
            bird_ids, bonus_ids = self._parse_setup_options()
            yield SelectionList(
                *[
                    Selection(card.name, b)
                    for b in bird_ids
                    if (card := get_bird_card(b))
                ]
            )
            yield RadioSet(
                *[card.name for b in bonus_ids if (card := get_bonus_card(b))]
            )
            yield Button("Confirm Selection", id="confirm")
        else:
            yield ListView(id="actions")

        yield Footer()

    def _is_setup_action(self, action) -> bool:
        return isinstance(action, SelectInitialAction)

    def _parse_setup_options(self):
        birds, bonuses = set(), set()
        for action in self.actions:
            assert isinstance(action, SelectInitialAction)
            birds.update(action.kept_birds)
            bonuses.add(action.kept_bonus)
        return sorted(birds), sorted(bonuses)

    def on_mount(self) -> None:
        if not self._is_setup_phase():
            self.refresh_actions()

    def _is_setup_phase(self) -> bool:
        return bool(self.actions and self._is_setup_action(self.actions[0]))

    def refresh_actions(self) -> None:
        list_view = self.query_one("#actions", ListView)
        list_view.clear()
        for action in self.actions:
            list_view.append(ListItem(Label(str(action))))

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        selected_index = event.list_view.index
        if selected_index is None:
            return
        self.state = transition_state(self.state, self.actions[selected_index])
        self.actions = get_actions(self.state)

        if self._is_setup_phase():
            await self.recompose()
        else:
            self.refresh_actions()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bird_list = self.query_one(SelectionList)
        radio_set = self.query_one(RadioSet)

        selected_bird_ids = bird_list.selected
        current_player = self.state.players[self.state.current_player_index]
        selected_birds = [
            bird_id
            for bird_id in current_player.bird_hand
            if bird_id in selected_bird_ids
        ]

        selected_bonus_index = radio_set.pressed_index

        if selected_bonus_index is None or selected_bonus_index < 0:
            self.notify("Please select a bonus card", severity="warning")
            return

        _, bonuses = self._parse_setup_options()
        selected_bonus = bonuses[selected_bonus_index]

        action = SelectInitialAction(tuple(selected_birds), selected_bonus)

        if action not in self.actions:
            self.notify("Invalid selection", severity="error")
            return

        self.state = transition_state(self.state, action)
        self.actions = get_actions(self.state)
        await self.recompose()

        if not self._is_setup_phase():
            self.refresh_actions()


if __name__ == "__main__":
    app = WingspanApp()
    app.run()
