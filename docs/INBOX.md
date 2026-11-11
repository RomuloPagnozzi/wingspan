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
- **Moves the value net can't tell apart.** Winner accuracy doesn't measure what search needs: ranking the
  positions one move apart. An offline check (does the net order sibling moves as the search's Q does?)
  would score value nets for search before a match.
- **Self-play generation 1 is running** (`experiments/selfplay.yaml`, PUCT): laptop into
  `experiments/data/selfplay_g1`, home server (container `wingspan-selfplay`, `~/wingspan-data/run.sh`,
  1 worker: with 3 it overheated and shut down, with 2 it reached 87°C) into `~/wingspan-data/selfplay_g1`, rsynced to `experiments/data/selfplay_g1_homelab`. To
  pause the server: `docker update --restart=no` and `docker kill --signal=INT`.

## Ideas

### Policy net training
- **Longer training**: validation still falls at epoch 8 on all decisions.

### Network-guided search
- **PUCT tuning**: c between 0.5 and 1.5 (only 4 values tried), `prior_min_visits`, normalizing Q to the
  tree's range (it isn't: c absorbs the score_delta scale).
- **Priors at the opponent's nodes** read the re-dealt world they are computed in (its hand is a guess);
  averaging over worlds, or encoding the opponent's hand as unknown, would be cleaner.

### Value net training
- **More positions per game with mixed targets.** 16 per game was chosen with result-only targets, when
  a game's positions shared one label. With search values each has its own, and the net no longer
  memorizes: 32 per game may help (its gathered observations, ~7 GB, approach the laptop's memory).
- **Seat augmentation.** Two players, zero-sum on the score difference: each position, encoded from the
  opponent's seat with the negated targets, is a second honest example. Doubles storage, or needs the
  Rust encoder at training time.
- **Smaller net, weight averaging (SWA/EMA)**: cheap checks on the regularized recipe.

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

### 3+ player experiments
Paired comparisons assume two players. With more: how many seats the reference takes, how wins are
attributed with several losers, how seats rotate. Worth designing when a multi-player question comes up.
