# Game elements


- Rounds
    - Each game has 4 rounds. During each round, players take turns, until each player has used all of their available action cubes
    - When the round is over:
        - Score the end-of-round-goal
        - If: round 4 is over, go to end scoring
        - Otherwise:
        - All players lose an action cube
        - Discard birds that were on the tray
        - Pass first player clockwise
- Turns
    - Each turn a player uses an action cube to take one of the following 4 actions:
        - Play one bird
            - Player hand
            - Player mat
        - Gain food
            - Birdfeeder
            - Player resources
        - Lay eggs
            - Player mat
            - Birds on the mat
            - Birds' egg limit
        - Draw cards
            - Bird tray
            - Bird deck
            - Player's hand


# Play a bird
- check if player has action cube
- check if there are birds in players hand, if there are, get them
- for each row check if it is an allowed habitat
- if it is from left to right check if there is an empty spot
- if it is get the egg cost of playing a bird there and if player has enough eggs on other birds
- check if the bird food cost is also met
- if selected
- paying the cost
- choose from which bird to remove egg, and remove said egg
- check if there is more than one option to pay bird cost
- if there is choose which cost to pay
- add bird to selected spot
- remove bird from players hand
- check if bird has "when played" type power
- if there is, trigger power action
- remove player action cube

# Gain food
- check if player has action cube
- check the amount of birds in forest to see amount of food to be gained
- for each food:
- if there is only option, reroll can be chosen
- choose a die from the birdfeeder and remove it
- gain a food token matching the face of the die
- check if leftmost empty spot in forest allows for trading an extra card for extra food
- if that is allowed and player has at least one bird in their hand
- if so choose if wanna discard for extra token
- if so choose what bird should be discarded
- add bird to discard pile and remove from hand
- repeat actions under "for each food"
- from right to left check if there is a bird in players' forest
- if there is, check if bird has a brown power
- if there is choose if activate
- if chosen to activate do power action
- remove player action cube

# Lay eggs
- check if player has action cube
- check that there are birds with egg space left
- check the amount of birds in grassland to see amount of eggs to be layed
- for each egg:
- get all birds with empty egg space
- choose a bird to put egg
- check if player has at least one food token
- check if leftmost empty spot in frassland allows for paying food token for extra egg
- if so choose if player wanna pay a food token for an extra egg
- if so choose which food token to pay and remove it
- repeat "for each egg"
- from right to left check if there is a bird in players' grassland
- if there is, check if bird has a brown power
- if there is choose if activate
- if chosen to activate do power action
- remove player action cube

# Draw bird cards
- check if player has action cube
- check the amount of birds in wetland to see amount of cards to be drawn
- for each card:
- if tray is not empty
- choose if wanna draw from tray
- else draw from deck
- check if leftmost empty spot allows for paying an extra egg to draw another card
- if so check if player wants to do trade
- if so player chooses which bird that has more than one egg to remove an egg
- remove egg from selected bird
- do "for each card" action
- from right to left check if there is a bird in players' wetland
- if there is, check if bird has a brown power
- if there is choose if activate
- if chosen to activate do power action
- remove player action cube







