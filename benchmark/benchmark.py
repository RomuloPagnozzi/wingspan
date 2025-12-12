from game.data import initiate_state
from game.actions import get_actions
from game.engine import transition_state
import random

ITERATIONS = 100


def play_game(players: int):
    curr_state = initiate_state(players)
    while True:
        actions = get_actions(curr_state)
        if not actions:
            break
        curr_state = transition_state(curr_state, random.choice(actions))


def main():
    for i in range(ITERATIONS):
        if i % 10 == 0:
            print(f"Progress: {i}/{ITERATIONS} games")
        play_game(2)


if __name__ == "__main__":
    main()
