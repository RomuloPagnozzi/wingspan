# Roadmap

**Goal:** the strongest Wingspan player we can build with the AlphaZero recipe (search generates games, a
network learns from them, the network guides the search, repeat) on small compute (a laptop and a home
server). Research question along the way: at this scale, how much compute does bootstrapping the network
from search-generated games save over learning from self-play alone?

## Plan

1. **Data generator** (done): the tuned tree (`experiments/selfplay.yaml`) with playout cap randomization:
   10k simulations on a random 25% of decisions (the policy targets), 2k on the rest (every game's result
   is a value target). Runs on the laptop and the home server.
2. **Bootstrap dataset** (56.5k games, generation paused): new deals, decisions recorded;
   `lab/dataset.py` replays them in Rust into training arrays (`experiments/data/datasets/selfplay`).
3. **Value net** (done, `lab/train_value.py`): an MLP on the flat observation, trained on the result mixed
   with the search's value of the position. It predicts the winner better than the score gap (77% vs
   66%), but as the search's only leaf evaluation it loses clearly to random playouts: it judges who is
   ahead, not what one move changes. Mixed half and half with a playout it plays about even.
4. **Policy net** (done, `lab/train_policy.py`): scores each legal move as h · g(move) (the trunk's summary
   of the position against the move's encoding), trained on the visits of the 10k searches. It picks the
   search's top move 66% of the time (a prior on the move's kind: 51%), 79% in main turns. Set encoders
   on the cards (hand, tray, a move's birds) added nothing to either net.
5. **Network-guided search** (done): PUCT in the Rust search with the policy's priors (`mcts_rs` option
   `policy`) beats the plain tree at equal time (61%, +2.7 points per game); the policy alone, with no
   search, wins 34% (`policy_rs`). The value net at PUCT's leaves loses (alone) or ties (mixed with a
   playout): playouts stay.
6. **Self-play loop** (next): generate games with PUCT and playouts, retrain the policy and the value net,
   repeat. Each generation, rerun the leaf match (playouts, net, mix) and move to the net as it wins. One
   net with a shared trunk and both heads is a lever for the value net: the policy's features capture
   what one move changes.

Each new, stronger bot ships to the web app as an entry in `src/wingspan/ai/bots.yaml` and becomes its
`champion`.
