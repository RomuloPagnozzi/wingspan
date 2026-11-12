# Self-play loop: one iteration

The checklist run each time a generation of self-play games is complete. Generation N is the games played
by the search guided by the **champion** policy (`experiments/data/models/policy.bin`, what
`experiments/selfplay.yaml` loads), in `experiments/data/selfplay_gN` (laptop) and `selfplay_gN_homelab`.
An iteration trains a **candidate** on them, tests it against the champion, and the winner guides
generation N+1. Results go to `EXPERIMENTS.md`, edited in place.

Two rules for the whole loop:
- **Only matches say a net is stronger.** Every generation changes the targets (a sharper search is easier
  to imitate), so offline numbers of two generations don't compare. Offline checks say the training
  worked; matches say whether it helped.
- **Fixed references.** Same match deals, same anchors, same match configs every time, so results compare
  across iterations. The recipe and the search params can change, early on especially: a low-hanging fruit
  is tested soon, as its own A/B against the current default (the same matches), and becomes the default
  when it clearly wins. Changes are tested one at a time, so a gain can be attributed.

## 1. Stop and collect

Start when the generation has **~20k games (~900k full-budget decisions)**: with the window of step 3 the
policy trains on ~1.8M, and at 800k it lost 2-4 points of top-move agreement.

- [ ] Laptop: Ctrl+C once (in-flight games finish, files close).
- [ ] Home server: `docker update --restart=no wingspan-selfplay && docker kill --signal=INT wingspan-selfplay`;
      wait for `docker logs --tail 5 wingspan-selfplay` to show RESULTS.
- [ ] Fetch: `rsync -az homelab:~/wingspan-data/selfplay_gN/ experiments/data/selfplay_gN_homelab/`
- [ ] Delete what crashed runs left: `*.tmp` parts (unreadable: a part is renamed when closed) and run
      folders without a parquet. On the server they belong to root: delete from a container
      (`docker run --rm -v ~/wingspan-data/selfplay_gN:/d --entrypoint sh rust:1.90 -c "find /d -name '*.tmp' -delete"`).

## 2. Check the data (before training)

A generation of bad games costs a day; these catch it before it costs a training too.

All three from `uv run python -m lab.summary experiments/data/selfplay_gN experiments/data/selfplay_gN_homelab`
(and the same on generation N−1's folders, to compare):

- [ ] **Integrity** (its first line): as many deals as games (no deal played twice); the worker-hours are
      the generation's compute. Every run's `config.yaml` is the same but for `num_workers` and
      `seeds.start`. Full-budget decisions (25% of all) are counted by step 4's policy training.
- [ ] **Seats**: seat_a against seat_b is 50% and ±0 points within noise, and their rows of the second
      table match. Both seats run the same search: anything else is a bug.
- [ ] **How the games look, next to generation N−1** (the second table): mean score and its parts (birds,
      eggs, cached food, tucked cards, round goals, bonus), unused food at the end, decisions per game,
      the first player's win rate. Scores aren't zero-sum, so stronger play should score more; a part
      that moves alone (food hoarded, eggs dropped) is a change of style to explain before training on it.
- [ ] **Does the search still overrule its prior?**
      `uv run python -m lab.prior_vs_search experiments/data/selfplay_gN --games 300`: how often the
      search's most visited move is the policy's top move, the prior on it, the visits on it. Healthy: the
      search disagrees often where the choice matters (main turn, play bird, draws) and sharpens when it
      agrees (visits above the prior). Alarm: agreement near 90% while the prior grows confident, rising
      generation after generation: the loop is confirming itself. Raise `root_noise` or c.

## 3. Build the training window

**All of generation N, then earlier generations, newest first, up to 40k games** (two generations'
worth). New games alone are too few (step 1); more old games than new and the stale search dominates the
targets. Generation 0 (the plain tree) leaves the window at generation 2.

- [ ] **Archive the outgoing nets** before anything overwrites them (training replaces `value.bin`, a
      promotion `policy.bin`). With the drive connected (`ls "/Volumes/External Drive/wingspan"`; stop if
      it isn't), into `generation_M/` for the nets trained on generation M = N−1: the models and the three
      match runs that measured them.
      `G="/Volumes/External Drive/wingspan/generation_M"; mkdir -p "$G/matches" && cp -R experiments/data/models "$G/" && cp -R experiments/data/{policy_match,puct_match,puct_value_match} "$G/matches/"`
      Then `rm -r experiments/data/{policy_match,puct_match,puct_value_match}` (step 6 reruns them).
- [ ] `rm -r experiments/data/datasets/selfplay` (the previous window, with its training cache; ~0.85 GB per
      1k games, and two windows don't fit on the laptop's disk). It can be rebuilt from the games.
- [ ] Build, sources newest first (`--max-games` fills in source order):
      `uv run python -m lab.dataset experiments/data/selfplay_gN/* experiments/data/selfplay_gN_homelab/* <generation N−1's folders>/* --max-games 40000 --out experiments/data/datasets/selfplay`
      Every game is replayed in Rust and a replay that disagrees with the recording stops the build: it is
      also the check that the engine and the recordings still match.

## 4. Train the candidates

From scratch, default recipes: minutes at this size, and no net inherits another's history.

- [ ] `uv run --group train python -m lab.train_policy experiments/data/datasets/selfplay --out experiments/data/models/policy_candidate.pt`
- [ ] `uv run --group train python -m lab.train_value experiments/data/datasets/selfplay`
      (straight to `value.bin`: the value net isn't in the generator, so it has no champion to protect.)

## 5. Check the training (from its printouts)

Validation is 10% of the window's deals. Both reports end with a line per folder of games: read the
newest generation's, the net's future inputs; the older folders' lines say what the window still carries.

**Policy**
- [ ] Training and validation cross-entropy stay together (a gap above ~0.01 is memorizing). Validation
      still falling at the last epoch is fine.
- [ ] Top-move agreement per phase beats the kind prior clearly where the choice matters: main turn, which
      bird to play, draws. Food, egg and payment choices near the baselines are normal: there the search's
      own preferences are noise.
- [ ] How sharp the targets are: the `uniform` column of KL (visits against uniform). It should rise a
      little with a better prior; a jump is the same alarm as step 2's.

**Value**
- [ ] It beats the line on the score gap in every round, in MSE and winner accuracy; validation MSE doesn't
      climb after the first epochs (memorizing).
- [ ] Compare it to that line, not to the last generation's accuracy: stronger players make closer games,
      which are harder to call for any predictor.
- [ ] None of this measures what the search needs: ranking positions one move apart. The sibling check
      does, in minutes, on games no net trained on (the generation being played):
      `uv run --group train python -m lab.sibling_values experiments/data/selfplay_gN+1 --games 200`
      (or the newest finished generation). Pairwise accuracy against 16 and 64 playouts, overall and in
      main turn, play bird, lay eggs and the extra-egg choice. A net that doesn't close the gap to 64
      playouts there won't help the search: skip step 6's leaf match.

## 6. Matches

All on deals 90001+ (never in self-play), from both seats; the readout is the per-seed score difference
(`lab.summary`; ±0.7 points at 300 deals), then the win rate. For every match, also where the points come
from (the score's parts and unused food: `lab.summary`'s second table). Delete a match's previous run before
rerunning it into the same folder.

- [ ] **Policy alone, candidate vs champion** (`experiments/candidate_policy_match.yaml`, seconds). A sanity
      check, not the decision: a clear loss means look at the training before spending on the next match.
- [ ] **PUCT, candidate vs champion** (`experiments/candidate_puct_match.yaml`): the decision.
      - interval above 0: **promote**;
      - interval below 0: **reject**;
      - interval includes 0: add 700 deals (`seeds: {start: 90301, count: 700}`, same output folder: ±0.4),
        then promote if the difference is ≥ 0. A tie still moves the generator to a net trained on the newer
        search; a loss is not a step.
      The generator searches at 10k simulations and the match at 1380: a proxy, 7× cheaper.
- [ ] **If promoted, the anchors**: `mv` the candidate's `.pt` and `.bin` over `policy.pt` / `policy.bin`,
      then rerun `experiments/policy_match.yaml` and `experiments/puct_match.yaml` (against the tree at 2000
      simulations, which never changes). These are the loop's absolute scale: strength per generation
      against compute spent, and the guard against a candidate that only beats its parent.
- [ ] **Value net at the leaves** (`experiments/puct_value_match.yaml`, with the policy that won): net only
      and half net, half playout, against playouts at equal time (check s/game). Its known failure: food
      left unused, fewer eggs and round goals. When the mix clearly beats playouts, the value net enters
      `selfplay.yaml`, and from then on it is a candidate with a champion, like the policy.

## 7. Start generation N+1

Promoted: new folders (`selfplay_gN+1`). Rejected: the same folders; generation N grows (to ~30k games)
and the iteration is run again. The offline checks and the decisions of the lost match say where to look.

- [ ] Laptop: `caffeinate -dis uv run python -m lab -c experiments/selfplay.yaml --record-decisions --rotate-every 50 -o experiments/data/selfplay_gN+1`
- [ ] Home server (container `wingspan-selfplay`, `~/wingspan-data/run.sh`; 2 workers with the lid open, 3
      overheat it): sync the code and the policy, set the output folder in `run.sh`, start.
      `rsync -az --exclude .git --exclude .venv --exclude rust/target --exclude experiments/data ./ homelab:~/wingspan/`
      `rsync -az experiments/data/models/policy.bin homelab:~/wingspan/experiments/data/models/`
      `ssh homelab 'docker update --restart=unless-stopped wingspan-selfplay && docker start wingspan-selfplay'`
- [ ] **After ~300 games (an hour), step 2's seats and prior-vs-search checks, and the mean score.** A broken
      generation shows here, not a day later.

## 8. Record

- [ ] `EXPERIMENTS.md`: findings edited in place, and one row for the generation: games, full-budget
      decisions, compute hours; search-vs-prior agreement; policy top-move agreement (all, main turn);
      value accuracy against the score-gap line; candidate vs champion; the anchors; the leaf match.
- [ ] `ROADMAP.md` if the plan changed. Delete the data of matches that were rerun.
- [ ] Back up to the external drive (`/Volumes/External Drive/wingspan/`: slow, and not always connected, so
      nothing reads from it): the games are days of compute and can't be rebuilt.
      `rsync -a --delete --exclude datasets --exclude .DS_Store experiments/data/ "/Volumes/External Drive/wingspan/data/"`
