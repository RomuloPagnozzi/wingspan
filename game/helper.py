def print_board_resources(board):
    """
    Prints a visualization of the board showing resource details for each spot.
    Format: [resource_amount(+extra)/egg_cost]
    """
    print("RESOURCES VIEW - Format: [resources(+extra)/egg_cost]")
    habitat_names = {0: "Forest ", 1: "Grass  ", 2: "Wetland"}

    for row in range(3):
        print(f"\n{habitat_names[row]}: ", end="")
        for spot in board[row]:
            extra = "+" if spot.extra_resource else " "
            print(f"[{spot.resource_amount}{extra}/{spot.egg_cost}] ", end="")
    print("\n")


def print_board_birds(board):
    """
    Prints a visualization of the board showing which spots have birds.
    Format: [name eggs/cards/food] or [empty]
    """
    print("BIRDS VIEW - Format: [name eggs/cards/food]")
    habitat_names = {0: "Forest ", 1: "Grass  ", 2: "Wetland"}

    for row in range(3):
        print(f"\n{habitat_names[row]}: ", end="")
        for spot in board[row]:
            if spot.bird:
                bird = spot.bird
                print(
                    f"[{bird.name[:8]:8} {bird.eggs}/{bird.tucked_cards}/{bird.stashed_food}] ",
                    end="",
                )
            else:
                print("[     blank    ] ", end="")
    print("\n")


def print_board_bird_stats(board):
    """
    Prints a visualization of the board showing bird stats.
    Format: [name points/egg_limit/wingspan] or [empty]
    """
    print("BIRD STATS VIEW - Format: [name points/egg_limit/wingspan]")
    habitat_names = {0: "Forest ", 1: "Grass  ", 2: "Wetland"}

    for row in range(3):
        print(f"\n{habitat_names[row]}: ", end="")
        for spot in board[row]:
            if spot.bird:
                bird = spot.bird
                print(
                    f"[{bird.name[:8]:8} {bird.points}/{bird.egg_limit}/{bird.wingspan:03d}] ",
                    end="",
                )
            else:
                print("[      blank     ] ", end="")
    print("\n")
