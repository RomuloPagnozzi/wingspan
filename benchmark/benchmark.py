from game.data import initiate_state, GamePhase
from game.actions import get_actions
from game.engine import transition_state
import random
import pandas as pd
import json

ITERATIONS = 1000


def play_game(players: int, game_num: int = 0) -> dict:
    curr_state = initiate_state(players)
    action_counts = [0] * players
    total_actions = 0
    last_action = None
    last_phase = None

    while True:
        actions = get_actions(curr_state)
        if not actions:
            return {
                "scores": [p.score.total for p in curr_state.players],
                "final_round": curr_state.round,
                "total_actions": total_actions,
                "action_counts": action_counts,
                "final_phase": curr_state.game_phase.value,
                "last_action": last_action,
                "last_phase": last_phase,
                "player_cubes": [p.action_cubes for p in curr_state.players],
                "action_data": str(curr_state.action_data),
                "game_num": game_num,
            }

        last_phase = curr_state.game_phase.value

        if "activate_power" in actions:
            last_action = "activate_power"
            curr_state = transition_state(curr_state, "activate_power")
        else:
            chosen = random.choice(actions)
            last_action = chosen
            curr_state = transition_state(curr_state, chosen)
            action_counts[curr_state.current_player_index] += 1
            total_actions += 1


def main():
    num_players = 5
    all_results = []
    improper_endings = []

    for i in range(ITERATIONS):
        if i % 10 == 0:
            print(f"Progress: {i}/{ITERATIONS} games")
        result = play_game(num_players, game_num=i)

        # Track improper endings
        if result["final_phase"] != "game_over":
            improper_endings.append(result)

        row = {
            **{f"player_{j}_score": result["scores"][j] for j in range(num_players)},
            **{
                f"player_{j}_actions": result["action_counts"][j]
                for j in range(num_players)
            },
            "final_round": result["final_round"],
            "total_actions": result["total_actions"],
            "final_phase": result["final_phase"],
        }
        all_results.append(row)

    df = pd.DataFrame(all_results)
    df.to_csv("benchmark/results.csv", index=False)
    print(f"Results saved to benchmark/results.csv")

    # Save improper endings for debugging
    if improper_endings:
        with open("benchmark/improper_endings.json", "w") as f:
            json.dump(improper_endings, f, indent=2)
        print(
            f"Improper endings saved to benchmark/improper_endings.json ({len(improper_endings)} games)"
        )

    # Print summary stats
    print(f"\nSummary:")
    print(f"  Total games: {len(all_results)}")
    print(f"  Proper endings (game_over): {len(all_results) - len(improper_endings)}")
    print(f"  Improper endings: {len(improper_endings)}")
    print(f"  Avg final round: {df['final_round'].mean():.2f}")
    print(f"  Avg total actions: {df['total_actions'].mean():.2f}")
    for j in range(num_players):
        print(
            f"  Avg player_{j} score: {df[f'player_{j}_score'].mean():.2f}, actions: {df[f'player_{j}_actions'].mean():.2f}"
        )


if __name__ == "__main__":
    main()
