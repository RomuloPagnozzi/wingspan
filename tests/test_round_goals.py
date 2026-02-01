"""Test round goal scoring functionality."""

from game.core import (
    initiate_state,
    ScoringMode,
    get_bird_card,
)
from game.scoring import (
    evaluate_goal,
    _calculate_blue_score,
    _calculate_green_scores,
    update_round_goal_scores,
)
from conftest import get_registry_bird_ids_by_nest, create_placed_bird

GREEN_SCORING_TABLE = {
    1: [4, 1, 0, 0],
    2: [5, 2, 1, 0],
    3: [6, 3, 2, 0],
    4: [7, 4, 3, 0],
}


def _find_bird_id_with_nest(state, nest_type):
    """Find a bird ID in the deck with the specified nest type."""
    for bird_id in state.bird_deck:
        card = get_bird_card(bird_id)
        if card and card.nest == nest_type:
            return bird_id
    return None


class TestGoalEvaluation:
    """Tests for goal evaluation functions."""

    def test_count_eggs_in_bowl(self):
        state = initiate_state(2)
        player = state.players[0]
        bird_id = _find_bird_id_with_nest(state, "bowl")
        assert bird_id is not None
        player.board[0][0].bird = create_placed_bird(bird_id, eggs=3)

        assert evaluate_goal(state, player, "eggs_in_bowl") == 3

    def test_count_eggs_in_cavity(self):
        state = initiate_state(2)
        player = state.players[0]
        bird_id = _find_bird_id_with_nest(state, "cavity")
        assert bird_id is not None
        player.board[0][0].bird = create_placed_bird(bird_id, eggs=2)

        assert evaluate_goal(state, player, "eggs_in_cavity") == 2

    def test_count_bowl_birds_with_egg(self):
        state = initiate_state(2)
        player = state.players[0]
        # Find bowl birds from registry
        bowl_bird_ids = get_registry_bird_ids_by_nest("bowl")
        assert len(bowl_bird_ids) >= 2
        player.board[0][0].bird = create_placed_bird(bowl_bird_ids[0], eggs=2)
        player.board[0][1].bird = create_placed_bird(bowl_bird_ids[1], eggs=0)

        assert evaluate_goal(state, player, "bowl_birds_with_egg") == 1

    def test_count_birds_in_forest(self):
        state = initiate_state(2)
        player = state.players[0]
        # bird_deck contains IDs
        player.board[0][0].bird = create_placed_bird(state.bird_deck.pop())
        player.board[0][1].bird = create_placed_bird(state.bird_deck.pop())

        assert evaluate_goal(state, player, "birds_in_forest") == 2

    def test_count_birds_in_grassland(self):
        state = initiate_state(2)
        player = state.players[0]
        player.board[1][0].bird = create_placed_bird(state.bird_deck.pop())

        assert evaluate_goal(state, player, "birds_in_grassland") == 1

    def test_count_birds_in_wetland(self):
        state = initiate_state(2)
        player = state.players[0]
        player.board[2][0].bird = create_placed_bird(state.bird_deck.pop())
        player.board[2][1].bird = create_placed_bird(state.bird_deck.pop())
        player.board[2][2].bird = create_placed_bird(state.bird_deck.pop())

        assert evaluate_goal(state, player, "birds_in_wetland") == 3

    def test_count_eggs_in_forest(self):
        state = initiate_state(2)
        player = state.players[0]
        bird_id1 = state.bird_deck.pop()
        bird_id2 = state.bird_deck.pop()
        player.board[0][0].bird = create_placed_bird(bird_id1, eggs=2)
        player.board[0][1].bird = create_placed_bird(bird_id2, eggs=3)

        assert evaluate_goal(state, player, "eggs_in_forest") == 5

    def test_count_total_birds(self):
        state = initiate_state(2)
        player = state.players[0]
        player.board[0][0].bird = create_placed_bird(state.bird_deck.pop())
        player.board[1][0].bird = create_placed_bird(state.bird_deck.pop())
        player.board[2][0].bird = create_placed_bird(state.bird_deck.pop())

        assert evaluate_goal(state, player, "total_birds") == 3

    def test_count_sets_of_eggs(self):
        state = initiate_state(2)
        player = state.players[0]
        bird_id_forest = state.bird_deck.pop()
        bird_id_grassland = state.bird_deck.pop()
        bird_id_wetland = state.bird_deck.pop()
        player.board[0][0].bird = create_placed_bird(bird_id_forest, eggs=3)
        player.board[1][0].bird = create_placed_bird(bird_id_grassland, eggs=2)
        player.board[2][0].bird = create_placed_bird(bird_id_wetland, eggs=4)

        assert evaluate_goal(state, player, "sets_of_eggs") == 2

    def test_count_sets_of_eggs_zero_in_one_habitat(self):
        state = initiate_state(2)
        player = state.players[0]
        bird_id_forest = state.bird_deck.pop()
        bird_id_grassland = state.bird_deck.pop()
        player.board[0][0].bird = create_placed_bird(bird_id_forest, eggs=5)
        player.board[1][0].bird = create_placed_bird(bird_id_grassland, eggs=3)

        assert evaluate_goal(state, player, "sets_of_eggs") == 0


class TestBlueScoring:
    """Tests for blue (friendly) scoring mode."""

    def test_blue_score_capped_at_5(self):
        state = initiate_state(2)
        player = state.players[0]
        for i in range(5):
            player.board[0][i].bird = create_placed_bird(state.bird_deck.pop())

        assert _calculate_blue_score(state, player, "birds_in_forest") == 5

    def test_blue_score_partial(self):
        state = initiate_state(2)
        player = state.players[0]
        player.board[0][0].bird = create_placed_bird(state.bird_deck.pop())
        player.board[0][1].bird = create_placed_bird(state.bird_deck.pop())

        assert _calculate_blue_score(state, player, "birds_in_forest") == 2

    def test_blue_score_zero(self):
        state = initiate_state(2)
        player = state.players[0]

        assert _calculate_blue_score(state, player, "birds_in_forest") == 0


class TestGreenScoring:
    """Tests for green (competitive) scoring mode."""

    def test_green_no_ties(self):
        state = initiate_state(3, ScoringMode.GREEN)
        state.players[0].board[0][0].bird = create_placed_bird(state.bird_deck.pop())
        state.players[0].board[0][1].bird = create_placed_bird(state.bird_deck.pop())
        state.players[0].board[0][2].bird = create_placed_bird(state.bird_deck.pop())

        state.players[1].board[0][0].bird = create_placed_bird(state.bird_deck.pop())
        state.players[1].board[0][1].bird = create_placed_bird(state.bird_deck.pop())

        state.players[2].board[0][0].bird = create_placed_bird(state.bird_deck.pop())

        scores = _calculate_green_scores(state, "birds_in_forest", round_num=1)

        assert scores[1] == 4
        assert scores[2] == 1
        assert scores[3] == 0

    def test_green_tie_for_first(self):
        state = initiate_state(3, ScoringMode.GREEN)
        state.players[0].board[0][0].bird = create_placed_bird(state.bird_deck.pop())
        state.players[0].board[0][1].bird = create_placed_bird(state.bird_deck.pop())

        state.players[1].board[0][0].bird = create_placed_bird(state.bird_deck.pop())
        state.players[1].board[0][1].bird = create_placed_bird(state.bird_deck.pop())

        state.players[2].board[0][0].bird = create_placed_bird(state.bird_deck.pop())

        scores = _calculate_green_scores(state, "birds_in_forest", round_num=2)

        assert scores[1] == 3
        assert scores[2] == 3
        assert scores[3] == 1

    def test_green_three_way_tie(self):
        state = initiate_state(3, ScoringMode.GREEN)
        state.players[0].board[0][0].bird = create_placed_bird(state.bird_deck.pop())
        state.players[1].board[0][0].bird = create_placed_bird(state.bird_deck.pop())
        state.players[2].board[0][0].bird = create_placed_bird(state.bird_deck.pop())

        scores = _calculate_green_scores(state, "birds_in_forest", round_num=3)

        assert scores[1] == 3
        assert scores[2] == 3
        assert scores[3] == 3

    def test_green_different_rounds_different_scores(self):
        state = initiate_state(2, ScoringMode.GREEN)
        state.players[0].board[0][0].bird = create_placed_bird(state.bird_deck.pop())
        state.players[0].board[0][1].bird = create_placed_bird(state.bird_deck.pop())
        state.players[1].board[0][0].bird = create_placed_bird(state.bird_deck.pop())

        scores_r1 = _calculate_green_scores(state, "birds_in_forest", round_num=1)
        scores_r4 = _calculate_green_scores(state, "birds_in_forest", round_num=4)

        assert scores_r1[1] == 4
        assert scores_r1[2] == 1
        assert scores_r4[1] == 7
        assert scores_r4[2] == 4


class TestIntegration:
    """Integration tests for round goal scoring."""

    def test_initiate_with_blue_scoring(self):
        state = initiate_state(2, ScoringMode.BLUE)
        assert state.round_goal_config is not None
        assert state.round_goal_config.scoring_mode == ScoringMode.BLUE
        assert len(state.round_goal_config.selected_goals) == 4

    def test_default_scoring_mode_is_green(self):
        state = initiate_state(2)
        assert state.round_goal_config
        assert state.round_goal_config.scoring_mode == ScoringMode.GREEN

    def test_update_round_goal_scores_blue(self):
        state = initiate_state(2, ScoringMode.BLUE)
        assert state.round_goal_config
        state.round_goal_config.selected_goals[0] = "total_birds"

        state.players[0].board[0][0].bird = create_placed_bird(state.bird_deck.pop())
        state.players[0].board[0][1].bird = create_placed_bird(state.bird_deck.pop())
        state.players[1].board[0][0].bird = create_placed_bird(state.bird_deck.pop())

        update_round_goal_scores(state)

        assert state.players[0].score.round_goals[0] == 2
        assert state.players[1].score.round_goals[0] == 1

    def test_update_round_goal_scores_green(self):
        state = initiate_state(2, ScoringMode.GREEN)
        assert state.round_goal_config
        state.round_goal_config.selected_goals[0] = "total_birds"

        state.players[0].board[0][0].bird = create_placed_bird(state.bird_deck.pop())
        state.players[0].board[0][1].bird = create_placed_bird(state.bird_deck.pop())
        state.players[1].board[0][0].bird = create_placed_bird(state.bird_deck.pop())

        update_round_goal_scores(state)

        assert state.players[0].score.round_goals[0] == 4
        assert state.players[1].score.round_goals[0] == 1

    def test_update_round_goal_scores_later_round(self):
        state = initiate_state(2, ScoringMode.GREEN)
        state.round = 3
        assert state.round_goal_config
        state.round_goal_config.selected_goals[2] = "birds_in_forest"

        state.players[0].board[0][0].bird = create_placed_bird(state.bird_deck.pop())
        state.players[1].board[0][0].bird = create_placed_bird(state.bird_deck.pop())
        state.players[1].board[0][1].bird = create_placed_bird(state.bird_deck.pop())

        update_round_goal_scores(state)

        # Round 3 scores are [6, 3, 2, 0], player 1 has 1 bird, player 2 has 2 birds
        # Player 2 is 1st (6 pts), Player 1 is 2nd (3 pts)
        assert state.players[0].score.round_goals[2] == 3
        assert state.players[1].score.round_goals[2] == 6

    def test_selected_goals_are_valid(self):
        valid_goals = {
            "eggs_in_bowl",
            "eggs_in_cavity",
            "eggs_in_ground",
            "eggs_in_platform",
            "bowl_birds_with_egg",
            "cavity_birds_with_egg",
            "ground_birds_with_egg",
            "platform_birds_with_egg",
            "eggs_in_forest",
            "eggs_in_grassland",
            "eggs_in_wetland",
            "birds_in_forest",
            "birds_in_grassland",
            "birds_in_wetland",
            "total_birds",
            "sets_of_eggs",
        }
        state = initiate_state(2)
        assert state.round_goal_config
        for goal in state.round_goal_config.selected_goals:
            assert goal in valid_goals
