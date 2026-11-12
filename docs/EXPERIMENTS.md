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
- **What the search needs is ranking sibling moves, and there the net is biased** (`lab/sibling_values.py`:
  each legal move of a 10k decision applied, the resulting position scored, the order compared to the
  search's Q per move; 200 unseen generation-2 games, 27.8k pairs of moves whose Q differ by ≥ 0.5 points).
  Pairwise accuracy: net 62%, as good as 16 random playouts (62%; 1 playout 55%, 64 playouts 66%, the score
  gap after the move 51%). But a playout's error is noise, which the search averages away over hundreds of
  leaves per move, while the net's is bias, the same every call: where it is wrong, more simulations don't
  help. It is wrong where the leaf matches lose points: main turn 61% (64 playouts 74%), which bird to
  play 61% (83%), and the choice to lay an extra egg 34%, below chance (68%): it prefers not to lay it. It
  beats playouts on paying food (74% vs 54%), where random play wastes food anyway. This is why net leaves
  lose and the half-and-half mix only ties.
- **More games don't fix it**: on all 76.8k games (generations 0 and 1) instead of the 40k window, the same
  validation MSE (0.60), winner accuracy (77%) and sibling ranking (62%). The bias is in what the net sees
  or is trained toward, not in the amount of data.

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
- **Alone, with no search, it wins 36% against the tree at 2000 simulations** (`policy_rs`,
  `experiments/policy_match.yaml`, the value-net match's 300 deals from both seats): −3.9 ± 0.8 points per
  game, at ~0.1 ms per move (the policy trained on generation 0 alone: −4.6, 34%). It plays eggs and food
  much as the tree does; most of the gap is round goals, a race against the opponent that needs look-ahead.
- **16 epochs instead of 8 gain nothing offline** (validation cross-entropy 1.033 vs 1.032; the last
  epochs' drop is the learning rate annealing, at any length) and nothing clear in the search (PUCT +0.0 ±
  0.7, 300 deals), though the policy alone gains (+0.9 ± 0.4): 8 stays the default; see docs/INBOX.md.

## Network-guided search

- **PUCT with the policy's priors beats the plain tree at equal time: 65%, +3.8 ± 0.8 points per game**
  (`experiments/puct_match.yaml`: 1380 simulations against 2000, ~25 ms per decision each, random
  playouts at the leaves in both; 300 deals from both seats; the policy trained on generation 0 alone gave
  +2.7, 61%). For scale, 10k simulations over 1500 is worth +3.6 at 6.7× the time. The points come from
  birds, cached food, tucked cards and round goals, where the policy alone loses.
- **Its exploration constant c is 0.5** (`experiments/puct_c.yaml`, 100 other deals: c 0.05 / 0.15 / 0.5 /
  1.5 → −6.0 / −1.0 / +2.2 / +1.2). Its bonus c · P · √N / (1 + n) is much larger than UCT's at these
  budgets, against Q gaps of ~0.02 (a point): too small a c and the search ignores what the prior
  doesn't favor, too large and it just follows the prior.
- **The value net at PUCT's leaves doesn't help** (`experiments/puct_value_match.yaml`: against PUCT with
  playouts at equal time, 300 deals): net only (730 simulations against 1380) −3.0 ± 0.8, with the same
  signature as without a prior (2.7 unused food against 1.3, −1.0 eggs, −1.7 round goals); half net, half
  playout (575) −0.7 ± 0.7. Nets trained on generation 0 alone did the same (−3.8, +0.0). Why: "Value net",
  sibling ranking. The prior hides much of the net's blind spot (without one it lost by 9.5 to
  the plain tree), but Q still comes from the leaves. The mix runs both a net call and a playout per leaf
  (41 µs per simulation, 2.3× a playout leaf): it ties, so no cheaper either.
- **In self-play the search still overrules its prior** (`lab/prior_vs_search.py`, 300 generation-1
  games, 13.7k full-budget decisions; root noise 0.25): its most visited move is the policy's top move 64%
  of the time (main turn 73%, play bird 82%, draws 49%), about as often as the plain tree agreed with the
  policy. When it agrees it sharpens: main turn, prior 0.51 on that move, visits 0.68. No sign of the loop
  reinforcing itself; watch the agreement and the prior's confidence across generations.
- **Priors cost**: a policy call costs a few playouts. Computed once per node, at nodes with 4+ visits
  (uniform before), a PUCT simulation costs 1.45× a plain one (1.1× from 16 visits, 2.3× from 1).
  Computing them again whenever another re-dealt world shows a new legal move made it 4-6×.

## Self-play loop

One iteration (`docs/SELFPLAY_LOOP.md`): games from the search guided by the champion policy, a candidate
trained on a sliding window, matches against the champion and fixed anchors.

- **Generation 1 made the policy stronger.** 20.3k games of PUCT guided by the generation-0 policy (183
  worker-hours: 33 s per game against the plain tree's 20, priors cost 1.45× per simulation); window: all
  of them plus the 19.7k newest generation-0 games, 1.79M full-budget decisions. The candidate beat the
  generation-0 policy in PUCT by **+1.2 ± 0.4 points per deal** (55%, 1000 deals; the first 300 alone said
  +0.7 ± 0.7) and alone by +1.2 ± 0.4, and gained on both anchors (above). Promoted: it guides generation 2.
- **The gain holds at the generator's budget, a little smaller**: PUCT at 10k simulations, the same two
  policies, +0.8 ± 0.5 (54%, 500 deals, 28 worker-hours). With more simulations the search corrects more of
  its prior's mistakes, so a better prior matters less. Whether PUCT at 10k beats the plain tree at equal
  time is open (docs/INBOX.md): bootstrapping pays only if it does.
- **Generation-1 games score more**: 71.3 points per player against 68.8 (birds, tucked cards, bonus; food
  left 1.3 vs 1.5), seats even (50.0%).
- **PUCT's visit targets are much sharper than the plain tree's** (KL from uniform 0.45 against 0.07):
  priors concentrate the visits, which is not the loop confirming itself (the search kept the policy's top
  move 64%, as before). Later generations compare to 0.45. Policy agreement with the search is 65% on both
  generations' validation games (main turn 75%, play bird 75%, draws 49%).

## Open questions

1. **Root pairing**: value the root moves in shared re-dealt worlds (common random numbers), as flat MC did,
   while keeping the tree below them. Does it make the tree's low-stakes picks precise and its strength
   higher at equal cost?
2. The tree's params at 10k simulations (tuned at 1500). A partial study (`experiments/tune_tree_10k.yaml`,
   21 trials, stopped for data generation; rerunning resumes it) has a smaller c winning: 0.2-0.6 against
   the tuned 1.14 (best 62%: c 0.40, α 0.48, k 0.79, over 100 deals from both seats).
3. How far simulations keep paying (30k+), and whether a per-phase budget shaped for the tree (e.g. more at
   setup) helps.
