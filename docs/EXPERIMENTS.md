# What we know

What experiments have established, and what is open. When a finding changes, edit it here; this file is
the current state, not a log.

## How results are measured

Paired comparisons: every arm plays the same deals, each deal twice with the seats swapped, arms
interleaved deal by deal (`lab`, modes `vs_reference` / `paired`). The precise readout is the score
difference averaged per deal over both seats (`lab.summary`, "per-seed diff"): ~300 deals give ±0.7 points
at 95%. Win rate is the coarser second readout. Every run records its decisions, so any result can be
explained afterwards from visits and Q per move.

## Engines

- The Rust engine plays the same game as the Python one: identical legal moves, in the same order, and
  an identical next state for every legal action from every state, over thousands of random games with
  2-4 players, every bird power reached (`rust/py/parity.py`).
- Rust search runs ~30× faster per decision than Python search.
- The Rust encodings (observation, legal moves) match `wingspan.ai.encoding` value for value
  (`rust/py/encoding_parity.py`), and a game replays in Rust from its seed alone (Python's random generator
  ported). A dataset built in Rust equals the Python build bit for bit, but for one float16 rounding in
  10⁸ values; it builds ~56k games in ~7 minutes.

## Search

- **Tuned tree** (`TUNED_TREE` in `src/wingspan/ai/rust.py`, the `mcts_rs` defaults): IS-MCTS, value
  `score_delta`, c ≈ 1.14, widening α ≈ 0.63, k ≈ 1.41, tuned with Optuna at 1500 simulations.
  `score_delta` clearly beat `win_loss` and `absolute_score` (chosen by 55 of 60 trials).
- **More simulations make the tree clearly stronger**: 10k beats 1500 by +3.6 ± 1.0 points per game
  (same deals). At ~21 s per seat per game, self-play at 10k makes ~600 games/hour on 7 workers (Apple M1).
- **The tree beats flat Monte Carlo** (every legal move played out in the same re-dealt worlds, no tree): even
  at 1500 (−0.3 ± 0.7, the tree costing ~1.7× per seat), ahead at 10k each (+1.3 ± 1.0, ~1.3× per seat),
  and it gains more from more budget (+3.6 vs +2.0). Most of its edge is round goals (+1.7 points per game at
  10k): they are a race against the opponent, which the tree models and random playouts don't. So the codebase
  keeps only the tree.
- The tree's root visits concentrate as simulations grow: main turns' top-move share 0.43 at 1.5k → 0.54 at
  10k → 0.63 at 30k (0.31 = uniform). Q gap between the best and second move: ~0.8 points in main turns,
  ~0.5 in power activations, under 0.25 in food, egg and payment choices (`rust/py/visits.py`).
- In low-stakes choices (food dice, egg placement, payments) the tree's per-move values are noisy: each move
  is valued in different re-dealt worlds, so it is more confident than the true gaps (a few hundredths of a
  point) warrant. Harmless to strength; noise in policy targets there.
- At setup, with enough simulations, the tree keeps a single bird 54% of the time (at 1500 it gets ~23
  simulations per option of 64, and its setup picks are mostly noise).

## Value net

- **Recipe** (`lab/train_value.py` defaults): an MLP on the flat observation (1935 → 512 → 256, a value
  and a margin head), 16 positions per game, dropout 0.3, learning rate 3e-4 with cosine decay, 8 epochs.
  Validated on unseen deals.
- **On 56.5k self-play games it predicts the winner 77% of the time** (rounds 1-4: 65/76/82/86%), against
  66% (52/62/72/80%) for a line on the current score gap. From 25k to 56k games: +2 points, in every
  round. Random playouts as an evaluation do far worse (1 / 16 / 256 playouts: 59 / 63 / 63%).
- **Targets: half the result, half the search's value of the position** (λ 0.5; 0.75 ties). The result is
  the better target in round 1 (the search judges a distant end poorly: λ 1 drops to 62%), the search's
  value in round 4 (the result only adds luck: λ 0 drops to 84%). Search values in the targets also stop
  the net memorizing games: on results alone it is best after one epoch.
- **Dropout 0.3 is what keeps it from memorizing**: validation error stays flat after epoch 2 (MSE 0.608
  → 0.595); stronger weight decay adds nothing. Training error keeps falling well below validation's.
- **Set encoders add nothing, to either net** (each card through a shared small net φ, summed per set,
  next to the summed card columns; tried and removed). Value net with the hand and tray encoded: MSE 0.595
  and 78% (rounds 66/76/82/86), the same. Self-play hands hold 1.2 birds on average, so the sums rarely mix
  cards, and the tray says little about who is ahead. Policy with each move's birds encoded: +1-2 points
  of top-move agreement on initial cards and draws with 16 decisions per game, within noise with all of
  them (and −2 on egg moves).
- **As the search's only leaf evaluation it loses clearly** (`experiments/value_net_match.yaml`: the
  tree at 2000 simulations against the tree with net leaves at equal time, 300 deals from both seats, no
  policy prior): net only (1000 simulations) wins 25%, −9.5 ± 1.0 points per game; half net, half
  playout (750) 49%, −0.5 ± 0.8. The better net helped (the 25k-game, unregularized one: 14%, −13.9), so
  the net's quality reaches play, but not its failure: it judges who is ahead, not what one move changes.
  In round 4 it rates gaining food above laying eggs, and ends games with 6.3 unused food (the tree: 1.4)
  and 5 fewer egg points. Winner accuracy doesn't measure this.

## Policy net

- **Recipe** (`lab/train_policy.py` defaults): move logit h · g(move), h the trunk's summary of the
  position (MLP 1935 → 512 → 256 → 128), g a small MLP on the move's encoding (146 → 128 → 128); softmax
  over the legal moves, cross-entropy to the visit shares of every full-budget (10k) decision, ~2.2M;
  dropout 0.1, learning rate 3e-4 with cosine decay, 8 epochs. Validated on unseen deals.
- **It picks the search's most visited move 66% of the time**, against 51% for a prior on the move's kind
  alone (per phase, the average visit share of that kind of move) and 36% for uniform. Where the choice
  matters it learned most: main turn 79% (kind prior 59%), which bird to play 79% (40%), initial cards
  30% of 64 moves (2%), draws 50% (19%). Food, egg and payment choices barely beat the baselines (31-42%
  against 26-34%): there the search's own preferences are noise.
- **More decisions help**: 16 per game (~800k) loses 2-4 points in those phases. Training and validation
  error stay within 0.004 and validation still falls at epoch 8: no memorizing, room for more.
- The visit targets are flat (KL from uniform 0.14 in main turns, 0.07 overall): top-move agreement says
  more than the loss.
- **The search agrees with itself 75% of the time** (12k full-budget positions from validation games,
  searched again at 10k with a new seed); the policy matches it 67%. Food, eggs and initial cards are near
  that ceiling (the search itself: 32-48%, near a coin flip). Where the choice matters the gap is real:
  main turn 90% vs 79%, which bird to play 95% vs 82%, draws 61% vs 51%. The policy matches a rerun as
  well as the recorded search: it learned the search's preferences, not one run's noise.
- **Alone, with no search, it wins 34% against the tree at 2000 simulations** (`policy_rs`,
  `experiments/policy_match.yaml`, the value-net match's 300 deals from both seats): −4.6 ± 0.8 points per
  game, at ~0.1 ms per move. It plays eggs and food much as the tree does; most of the gap is round goals
  (−3.2), a race against the opponent that needs look-ahead.

## Network-guided search

- **PUCT with the policy's priors beats the plain tree at equal time: 61%, +2.7 ± 0.7 points per game**
  (`experiments/puct_match.yaml`: 1380 simulations against 2000, 24.9 vs 24.1 ms per decision, random
  playouts at the leaves in both; 300 deals from both seats). For scale, 10k simulations over 1500 is
  worth +3.6 at 6.7× the time. The points come from eggs, cached food, tucked cards (+1.9 together) and
  round goals (+0.7), where the policy alone lost.
- **Its exploration constant c is 0.5** (`experiments/puct_c.yaml`, 100 other deals: c 0.05 / 0.15 / 0.5 /
  1.5 → −6.0 / −1.0 / +2.2 / +1.2). Its bonus c · P · √N / (1 + n) is much larger than UCT's at these
  budgets, against Q gaps of ~0.02 (a point): too small a c and the search ignores what the prior
  doesn't favor, too large and it just follows the prior.
- **Priors cost**: a policy call costs a few playouts. Computed once per node, at nodes with 4+ visits
  (uniform before), a PUCT simulation costs 1.45× a plain one (1.1× from 16 visits, 2.3× from 1).
  Computing them again whenever another re-dealt world shows a new legal move made it 4-6×.

## Open questions

1. **Root pairing**: value the root moves in shared re-dealt worlds (common random numbers), as flat MC did,
   while keeping the tree below them. Does it make the tree's low-stakes picks precise and its strength
   higher at equal cost?
2. The tree's params at 10k simulations (tuned at 1500). A partial study (`experiments/tune_tree_10k.yaml`,
   21 trials, stopped for data generation; rerunning resumes it) has a smaller c winning: 0.2-0.6 against
   the tuned 1.14 (best 62%: c 0.40, α 0.48, k 0.79, over 100 deals from both seats).
3. How far simulations keep paying (30k+), and whether a per-phase budget shaped for the tree (e.g. more at
   setup) helps.
