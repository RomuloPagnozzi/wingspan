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
4. **Set encoders on the observation** (next): each card of the hand and tray through a shared small net φ,
   then summed, next to the summed columns (`docs/INBOX.md`, "Set-encoded cards"). Measured on the value
   net first: regularized, it has capacity to spare, so its inputs are the suspect.
5. **Policy net**: scores each legal move as h · aₖ (the trunk's summary of the position against the
   move's encoding), trained on the visits of the 10k searches; set encoders on multi-bird moves are
   compared here. Ship a policy-only bot to the web app.
6. **Network-guided search**: PUCT in the Rust search with the policy as prior, Q normalized to the tree's
   range, and the value net at the leaves, alone or mixed with playouts. In place: the observation and move
   encodings in Rust (`rust/src/encode.rs`), the value net's forward pass (`rust/src/net.rs`) and net leaves
   (`mcts_rs` options `value_net`, `net_mix`).
7. **Self-play loop**: one net with a shared trunk and both heads; generate games with the network-guided
   search, retrain, repeat.

Each new, stronger bot ships to the web app as an entry in `src/wingspan/ai/bots.yaml` and becomes its
`champion`.
