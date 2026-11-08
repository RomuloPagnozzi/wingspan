# Roadmap

**Goal:** the strongest Wingspan player we can build with the AlphaZero recipe (search generates games, a
network learns from them, the network guides the search, repeat) on small compute (a laptop and a home
server). Research question along the way: at this scale, how much compute does bootstrapping the network
from search-generated games save over learning from self-play alone?

## Plan

1. **Settle the data generator.** Answer the open questions in `EXPERIMENTS.md` (flat MC's value function,
   the tree at high budgets): pick the generator with the best strength per compute for labels.
2. **Generate the bootstrap dataset** with it: unique deals, decisions recorded.
3. **Train the networks**: the value net (`lab/train_value.py`), then a policy net over legal moves
   (scoring each move from `wingspan.ai.encoding`). Ship a policy-only bot to the web app.
4. **Network-guided search**: PUCT with the policy as prior and the value net instead of random playouts,
   in the Rust search.
5. **Self-play loop**: generate games with the network-guided search, retrain, repeat.

Each new, stronger bot ships to the web app as an entry in `src/wingspan/ai/bots.yaml` and becomes its
`champion`.
