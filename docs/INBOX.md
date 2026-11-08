# Inbox

Ideas and pending work, unprioritized. An idea becomes an experiment when it's run; its result goes to
`EXPERIMENTS.md`.

## Pending

- **Web app's bot.** It still runs the Python MCTS (`src/wingspan/ai/mcts.py`) as `mcts-v1`, with params
  older than the tuned ones. To do together: a bot on the current best search, under an id without a
  version (migrate the stats on the server: the id is stored with every game); the web image building the
  Rust extension; then delete the Python search and rename `mcts_rs` to `mcts`.
- **Cloud runner** (`lab/cloud.py`, `lab/cloud_agent.py`): written for the Python engine on Vultr. Update it
  to the Rust engine (the server builds the extension) and to the provider we end up using.
- **Explainer** (`lab/explainer/`): the interactive page explaining the encoder and the nets. Refresh it with
  current data (its build read games that no longer exist) and the networks as they are.
- **Lab UI**: a browser UI for experiments, runs and data exploration, built like the game's UI, to replace
  reading tables in the terminal. Big; start from scratch.

## Ideas

### Rollout truncation and a cheap evaluation
Random playouts to the end of the game are mostly noise in the late tail. Cut them at a fixed depth and
score the position cheaply (the current score difference is a strong baseline; the value net later).
Biasing playout moves toward immediate points is a second, separate lever.

### Action canonicalization
Payments and egg placements enumerate every assignment, even when many are equivalent (paying an egg from
bird A or bird B when no power cares). Collapsing equivalent moves before search shrinks the branching
factor where it carries no decision, so simulations go to choices that matter.

### Explicit chance nodes
IS-MCTS samples all future chance (dice, draws) once per simulation, which converges but slowly on
chance-heavy decisions. Chance nodes with probability-weighted children would reduce that variance; worth it
only if experiments show slow convergence there.

### Complexity benchmark
Branching factor per phase, game length, state-space estimates across player counts: a table that places
Wingspan among the games in the game-AI literature.

### Set-encoded cards
Summing raw card features over a hand or a multi-bird move loses which properties belong to the same card
(grassland-bowl + wetland-cavity looks like wetland-bowl + grassland-cavity). A set encoder (each card
through a shared small net, then summed) keeps it. Compare the two on the observation (main-turn choice,
value) and on multi-bird moves (initial cards, draws); single-bird moves are a control where no gain is
expected. The encoder already exposes the card ids for it (`wingspan.ai.encoding`).

### 3+ player experiments
Paired comparisons assume two players. With more: how many seats the reference takes, how wins are
attributed with several losers, how seats rotate. Worth designing when a multi-player question comes up.
