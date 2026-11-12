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
- **Lab UI**: a browser UI for experiments, runs and data exploration, to replace reading tables in the
  terminal. A prototype exists (`lab/ui`: loop progress, matches, nets, a job queue, `lab/ledger.py` for the
  history), far from what we want: the real one is still to design.

## Ideas

### Policy net training
- **Longer training** (16 epochs against 8, generation-1 window): no offline gain (validation CE 1.033 vs
  1.032, train/validation gap 0.023 vs 0.012), a clear gain alone (+0.9 ± 0.4 over 1000 deals) and an
  unresolved one inside the search (PUCT +0.0 ± 0.7 over 300 deals: not extended). To settle: retrain and
  extend the PUCT match by 700 deals; also compare the two nets' confidence (prior entropy), the suspected
  reason a net can gain alone but not in the search. Validation spiked at epochs 5, 7, 9 (to 1.074): try a
  lower peak learning rate too.

### Network-guided search
- **Does the network still help at 10k simulations?** The only evidence that PUCT beats the plain tree is at
  ~2000 simulations' worth of time (+3.8). Gen 0's data came from the plain tree at 10k: bootstrapping
  pays only if the guided search beats it at the generator's budget. Match: PUCT + champion at 10k vs the
  plain tree at equal time (~14.5k: a PUCT simulation costs ~1.45×), 300 deals, ~17 worker-hours. The
  same budget's gap between the policy alone and the 10k search it imitates is a third readout.
- **PUCT tuning**: c between 0.5 and 1.5 (only 4 values tried), `prior_min_visits`, normalizing Q to the
  tree's range (it isn't: c absorbs the score_delta scale).
- **Priors at the opponent's nodes** read the re-dealt world they are computed in (its hand is a guess);
  averaging over worlds, or encoding the opponent's hand as unknown, would be cleaner.

### Value net training
Score every idea with `lab/sibling_values.py` first (minutes, on games no net trained on): pairwise accuracy
overall and in main turn, play bird, lay eggs and the extra-egg choice, against 16 and 64 playouts. Only a
net that closes the gap to 64 playouts there is worth a leaf match. Ideas, most promising first:
- **Targets that carry what a move changes.** Half of each target is the game's result, shared by every
  position of a game: it teaches the level (who is ahead), not the slope between siblings. The search's Q
  differs between sibling positions. Retune the mix (`--q-mix`: 0.5 was chosen on winner accuracy, the
  wrong metric), and take Q only from the 10k decisions (the 2k ones' Q is noisier; ~55 per game, 16 used).
- **Train on sibling positions directly.** The decisions parquet holds Q for every visited move: encode the
  position after each move (the dataset now encodes only decision positions) and train toward each move's
  Q, or with a ranking loss over the siblings. The loss then is the readout the search needs.
- **One net with the policy's trunk.** The policy's features already capture what one move changes (79% top
  move in main turns); a value head on that trunk, or a Q head next to the policy head (h · g(move) -> each
  move's Q), reads them. Its Q per move could also seed the search's new children.
- **Features for what it misjudges.** It keeps food it won't spend and skips eggs: little in the
  observation says how many turns remain, what food the hand can still use, or how many eggs fit. Read the
  failing decisions (main turn, extra egg) to find what's missing.
- **Use it only where it's right.** Per phase, net or playout at the leaf (food payments: net; eggs and main
  turn: playouts), or a mix that shifts with the round. Needs a Rust option; the sibling check per phase says
  where.
- **Truncated playouts** (below): a few random moves, then the net, so the net judges a position after the
  move's consequences have played out.
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
