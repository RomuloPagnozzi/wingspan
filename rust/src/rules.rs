//! The rules: setup, legal actions, transitions, scoring. A port of engine/{actions,engine,phase_handlers,
//! effects,utils,scoring}.py that keeps the same orders (of actions, of draws, of dict iteration), because
//! rollouts pick moves by index and the action strings are data keys.
//!
//! M1: bird powers are not implemented yet. `triggered_powers` is the one place they hook in; until then it
//! returns nothing, which matches the Python engine with its power lookups patched out (see py/nopowers.py).

use crate::actions::Action;
use crate::chance::{Chance, Rng};
use crate::data::{data, BonusScore, Nest};
use crate::state::*;

// Board layout (models.py `_build_board_layout`). Rows: forest, grassland, wetland.
const RESOURCE_AMOUNT: [[i32; 5]; 3] = [[1, 1, 2, 2, 3], [2, 2, 3, 3, 4], [1, 1, 2, 2, 3]];
const EXTRA_RESOURCE: [bool; 5] = [false, true, false, true, false];
const EGG_COST: [u8; 5] = [0, 1, 1, 2, 2];
const HABITATS: [&str; 3] = ["forest", "grassland", "wetland"];

type R = Result<(), String>;

// =============================================================================
// Setup
// =============================================================================

fn new_player(id: u8) -> Player {
    use Food::*;
    Player {
        id,
        bird_hand: vec![],
        bonus_hand: vec![],
        food: vec![(Invertebrate, 1), (Seed, 1), (Fish, 1), (Fruit, 1), (Rodent, 1)],
        board: [[None; 5]; 3],
        action_cubes: 9,
        first_player: false,
        used_pink_powers: vec![],
        score: Score {
            bird_points: 0,
            egg_points: 0,
            cached_food: 0,
            tucked_cards: 0,
            round_goals: [0; 4],
            bonus_scores: vec![],
        },
    }
}

fn roll_feeder(c: &mut impl Chance) -> Vec<(u8, Face)> {
    (0..5).map(|i| (i, Face(c.roll_die()))).collect()
}

/// Same steps as Python's `initiate_state`, with this engine's own RNG.
pub fn initiate(n_players: usize, mode: ScoringMode, rng: &mut Rng) -> State {
    let d = data();
    let mut bird_deck = d.bird_ids.clone();
    let mut bonus_deck = d.bonus_ids.clone();
    rng.shuffle(&mut bird_deck);
    rng.shuffle(&mut bonus_deck);
    let feeder = roll_feeder(rng);

    let mut tiles: Vec<(String, String)> = ["bowl", "cavity", "ground", "platform"]
        .iter()
        .map(|n| (format!("eggs_in_{n}"), format!("{n}_birds_with_egg")))
        .chain(HABITATS.iter().map(|h| (format!("eggs_in_{h}"), format!("birds_in_{h}"))))
        .collect();
    tiles.push(("total_birds".into(), "sets_of_eggs".into()));
    let selected_goals = (0..4)
        .map(|i| {
            let j = i + rng.below(tiles.len() - i); // sample 4 tiles without replacement
            tiles.swap(i, j);
            let (a, b) = &tiles[i];
            if rng.below(2) == 0 { a.clone() } else { b.clone() }
        })
        .collect();

    let mut s = State {
        players: (1..=n_players as u8).map(new_player).collect(),
        bird_tray: vec![],
        bird_deck,
        discarded_birds: vec![],
        bonus_deck,
        discarded_bonuses: vec![],
        feeder,
        round: 1,
        current_player_index: 0,
        game_phase: Phase::GameSetup,
        action_data: ActionData::default(),
        scoring_mode: mode,
        selected_goals,
    };
    for _ in 0..3 {
        let b = s.bird_deck.pop().unwrap();
        s.bird_tray.push(b);
    }
    let first = rng.below(n_players);
    for i in 0..n_players {
        let birds: Vec<u16> = (0..5).map(|_| s.bird_deck.pop().unwrap()).collect();
        let bonuses: Vec<u16> = (0..2).map(|_| s.bonus_deck.pop().unwrap()).collect();
        let p = &mut s.players[i];
        p.first_player = i == first;
        p.bird_hand = birds;
        p.bonus_hand = bonuses;
    }
    s.current_player_index = first;
    s
}

// =============================================================================
// Helpers (utils.py)
// =============================================================================

fn first_player_index(s: &State) -> usize {
    s.players.iter().position(|p| p.first_player).unwrap()
}

/// `get_current_player_index`: the first player, unless someone has already used a cube this round.
fn next_player_index(s: &State) -> usize {
    let n = s.players.len();
    let first = first_player_index(s);
    if s.players.iter().all(|p| p.action_cubes == s.players[0].action_cubes) {
        return first;
    }
    let first_cubes = s.players[first].action_cubes;
    (1..n).map(|o| (first + o) % n).find(|&i| s.players[i].action_cubes != first_cubes).unwrap_or(first)
}

fn leftmost_empty(p: &Player, row: usize) -> Option<usize> {
    p.board[row].iter().position(|b| b.is_none())
}

fn has_nest(nest: Nest, wanted: Nest) -> bool {
    nest == wanted || nest == Nest::Wild
}

fn has_egg_room(p: &Player) -> bool {
    p.birds().any(|b| b.eggs < data().bird(b.id).egg_limit)
}

fn total_eggs(p: &Player) -> u32 {
    p.birds().map(|b| b.eggs as u32).sum()
}

/// Powers that would trigger (brown on a row, white on a played bird, pink on another player's action).
/// M1: none. Kept as a hook so the call sites already mirror `finish_main_action`.
fn triggered_powers(_s: &State) -> Vec<()> {
    vec![]
}

fn can_afford(cost: &[Vec<(Option<Food>, u8)>], food: [u8; 5]) -> bool {
    if cost.is_empty() {
        return true;
    }
    cost.iter().any(|option| {
        let mut remaining = food;
        let (mut deficit, mut wild) = (0u32, 0u32);
        for &(f, amount) in option {
            match f {
                None => wild = amount as u32,
                Some(f) => {
                    let used = remaining[f as usize].min(amount);
                    remaining[f as usize] -= used;
                    deficit += (amount - used) as u32;
                }
            }
        }
        remaining.iter().map(|&n| n as u32).sum::<u32>() >= 2 * deficit + wild
    })
}

/// `generate_playable_bird_spots`: calls `f(bird, row, col)` in hand order, then row order, until it
/// returns false.
fn for_playable_spots(p: &Player, mut f: impl FnMut(u16, u8, u8) -> bool) {
    if p.bird_hand.is_empty() {
        return;
    }
    let eggs = total_eggs(p);
    let spots: [Option<usize>; 3] =
        std::array::from_fn(|r| leftmost_empty(p, r).filter(|&c| EGG_COST[c] as u32 <= eggs));
    if spots.iter().all(Option::is_none) {
        return;
    }
    let food = p.food_counts();
    for &id in &p.bird_hand {
        let bird = data().bird(id);
        if !can_afford(&bird.cost, food) {
            continue;
        }
        for (r, c) in spots.iter().enumerate() {
            if let Some(c) = c {
                if bird.habitats[r] && !f(id, r as u8, *c as u8) {
                    return;
                }
            }
        }
    }
}

fn can_play_a_bird(p: &Player) -> bool {
    let mut any = false;
    for_playable_spots(p, |_, _, _| {
        any = true;
        false
    });
    any
}

/// itertools.combinations(range(n), k), in its (lexicographic) order.
fn combinations(n: usize, k: usize, mut f: impl FnMut(&[usize])) {
    if k > n {
        return;
    }
    let mut idx: Vec<usize> = (0..k).collect();
    loop {
        f(&idx);
        let mut i = k;
        while i > 0 && idx[i - 1] == i - 1 + n - k {
            i -= 1;
        }
        if i == 0 {
            return;
        }
        idx[i - 1] += 1;
        for j in i..k {
            idx[j] = idx[j - 1] + 1;
        }
    }
}

/// itertools.combinations_with_replacement(range(n), k).
fn combinations_with_replacement(n: usize, k: usize, mut f: impl FnMut(&[usize])) {
    if n == 0 && k > 0 {
        return;
    }
    let mut idx = vec![0; k];
    loop {
        f(&idx);
        let mut i = k;
        while i > 0 && idx[i - 1] == n - 1 {
            i -= 1;
        }
        if i == 0 {
            return;
        }
        let v = idx[i - 1] + 1;
        for x in &mut idx[i - 1..] {
            *x = v;
        }
    }
}

fn food_map(counts: [u8; 5]) -> Vec<(Food, u8)> {
    Food::ALL.iter().filter(|f| counts[**f as usize] > 0).map(|&f| (f, counts[f as usize])).collect()
}

/// `generate_food_payments`: every way to pay one of the cost options, deduplicated, first seen first.
fn food_payments(cost: &[Vec<(Option<Food>, u8)>], food: [u8; 5]) -> Vec<[u8; 5]> {
    if cost.is_empty() {
        return vec![[0; 5]];
    }
    let mut out: Vec<[u8; 5]> = vec![];
    for option in cost {
        let mut remaining = food;
        let mut exact = [0u8; 5];
        let (mut missing, mut wild) = (0usize, 0usize);
        for &(f, amount) in option {
            match f {
                None => wild = amount as usize,
                Some(f) => {
                    let used = remaining[f as usize].min(amount);
                    exact[f as usize] = used;
                    remaining[f as usize] -= used;
                    missing += (amount - used) as usize;
                }
            }
        }
        // Each missing food is replaced by any 2 tokens, and wild by any 1.
        let wild_count = 2 * missing + wild;
        if remaining.iter().map(|&n| n as usize).sum::<usize>() < wild_count {
            continue;
        }
        let pool: Vec<usize> = (0..5).filter(|&i| remaining[i] > 0).collect(); // sorted by name
        combinations_with_replacement(pool.len(), wild_count, |sel| {
            let mut usage = [0u8; 5];
            for &i in sel {
                usage[pool[i]] += 1;
            }
            if (0..5).all(|i| usage[i] <= remaining[i]) {
                let mut pay = exact;
                for i in 0..5 {
                    pay[i] += usage[i];
                }
                if !out.contains(&pay) {
                    out.push(pay);
                }
            }
        });
    }
    out
}

/// Shared DFS of `get_egg_payment_combinations` / `get_egg_distribution_combinations`.
fn egg_combinations(items: &[(u16, u8)], total: u32) -> Vec<Vec<(u16, u8)>> {
    fn dfs(items: &[(u16, u8)], suffix: &[u32], i: usize, left: u32, cur: &mut Vec<(u16, u8)>, out: &mut Vec<Vec<(u16, u8)>>) {
        if left == 0 {
            let mut v = cur.clone();
            v.sort_unstable();
            out.push(v);
            return;
        }
        if left > suffix[i] {
            return;
        }
        let (id, cap) = items[i];
        dfs(items, suffix, i + 1, left, cur, out);
        for n in 1..=(cap as u32).min(left) {
            cur.push((id, n as u8));
            dfs(items, suffix, i + 1, left - n, cur, out);
            cur.pop();
        }
    }
    let mut suffix = vec![0u32; items.len() + 1];
    for i in (0..items.len()).rev() {
        suffix[i] = suffix[i + 1] + items[i].1 as u32;
    }
    let mut out = vec![];
    dfs(items, &suffix, 0, total, &mut vec![], &mut out);
    out
}

// =============================================================================
// Legal actions (actions.py)
// =============================================================================

pub fn legal_actions(s: &State) -> Vec<Action> {
    use Action::*;
    let p = s.cur();
    let ad = &s.action_data;
    match s.game_phase {
        Phase::GameSetup => vec![Simple(if p.action_cubes == 9 { "start_setup" } else { "end_setup" })],
        Phase::SelectInitialCards => {
            assert!(p.bird_hand.len() == 5 && p.bonus_hand.len() == 2, "setup needs 5 birds and 2 bonuses");
            let mut out = vec![];
            for &bonus in &p.bonus_hand {
                for k in 0..=5 {
                    combinations(5, k, |idx| {
                        out.push(SelectInitial { kept: idx.iter().map(|&i| p.bird_hand[i]).collect(), bonus })
                    });
                }
            }
            out
        }
        Phase::DiscardFood => {
            let need = ad.amount_to_discard as usize;
            assert!(need > 0, "no food to discard");
            let tokens: Vec<Food> = p.food.iter().flat_map(|&(f, n)| std::iter::repeat(f).take(n as usize)).collect();
            assert!(tokens.len() >= need, "not enough food to discard");
            let mut seen: Vec<[u8; 5]> = vec![];
            combinations(tokens.len(), need, |idx| {
                let mut c = [0u8; 5];
                for &i in idx {
                    c[tokens[i] as usize] += 1;
                }
                if !seen.contains(&c) {
                    seen.push(c);
                }
            });
            seen.into_iter().map(|c| FoodMap("discard_food_combo", food_map(c))).collect()
        }
        Phase::MainTurn => {
            if p.action_cubes == 0 {
                return vec![];
            }
            let mut out = vec![];
            // With no room for eggs the action is only worth taking for its brown powers (none in M1)
            if has_egg_room(p) {
                out.push(Simple("lay_eggs"));
            }
            if can_play_a_bird(p) {
                out.push(Simple("play_bird"));
            }
            out.push(Simple("gain_food"));
            if s.bird_deck.len() + s.discarded_birds.len() + s.bird_tray.len() > 0 {
                out.push(Simple("draw_cards"));
            }
            out
        }
        Phase::ExtraFoodAction => vec![Simple("trade_bird"), Simple("skip_trade")],
        Phase::ExtraLayEggsAction => vec![Simple("trade_food"), Simple("skip_trade")],
        Phase::ExtraCardDrawAction => vec![Simple("trade_egg"), Simple("skip_trade")],
        Phase::CollectFood => {
            let mut out: Vec<Action> = s
                .feeder
                .iter()
                .flat_map(|&(die, face)| face.foods().iter().map(move |&food| SelectDie { die, food }))
                .collect();
            if !s.feeder.is_empty() && s.feeder.iter().all(|&(_, f)| f == s.feeder[0].1) {
                out.push(Simple("reroll_all"));
            }
            out
        }
        Phase::LayEggs => {
            assert!(ad.eggs_needed > 0, "no eggs needed");
            let items: Vec<(u16, u8)> = p
                .birds()
                .filter_map(|b| {
                    let limit = data().bird(b.id).egg_limit;
                    (b.eggs < limit).then(|| (b.id, limit - b.eggs))
                })
                .collect();
            assert!(!items.is_empty(), "no birds with egg capacity");
            let capacity: u32 = items.iter().map(|&(_, c)| c as u32).sum();
            if ad.eggs_needed as u32 >= capacity {
                let mut all = items;
                all.sort_unstable();
                return vec![EggMap("lay_eggs", all)];
            }
            egg_combinations(&items, ad.eggs_needed as u32).into_iter().map(|c| EggMap("lay_eggs", c)).collect()
        }
        Phase::DrawCards => {
            let needed = ad.cards_needed as usize;
            assert!(needed > 0, "no cards needed");
            let tray = &s.bird_tray;
            let deck = s.bird_deck.len() + s.discarded_birds.len();
            let available = tray.len() + deck;
            assert!(available > 0, "no cards to draw");
            let actual = needed.min(available);
            let mut out = vec![];
            for t in 0..=actual.min(tray.len()) {
                let from_deck = actual - t;
                if from_deck > deck {
                    continue;
                }
                combinations(tray.len(), t, |idx| {
                    out.push(DrawCards { tray: idx.iter().map(|&i| tray[i]).collect(), deck: from_deck as u8 })
                });
            }
            out
        }
        Phase::SelectBirdToDiscard => p.bird_hand.iter().map(|&id| Id("discard_bird", id)).collect(),
        Phase::SelectFoodToDiscard => p.food.iter().map(|&(f, _)| Name("discard_food", f)).collect(),
        Phase::SelectEggToDiscard => p.birds().filter(|b| b.eggs > 0).map(|b| Id("discard_egg", b.id)).collect(),
        Phase::PlayBird => {
            let mut out = vec![];
            for_playable_spots(p, |bird, row, col| {
                out.push(PlayBird { bird, row, col });
                true
            });
            out
        }
        Phase::PayEggCost => {
            let pending = ad.pending_cost.as_ref().filter(|c| c.cost_type == CostType::Egg).expect("no egg cost pending");
            let items: Vec<(u16, u8)> = p.birds().filter(|b| b.eggs > 0).map(|b| (b.id, b.eggs)).collect();
            egg_combinations(&items, pending.amount.unwrap() as u32).into_iter().map(|c| EggMap("pay_eggs", c)).collect()
        }
        Phase::PayFoodCost => {
            let pending = ad.pending_cost.as_ref().filter(|c| c.cost_type == CostType::Food).expect("no food cost pending");
            let cost = &data().bird(pending.callback_action.bird).cost;
            food_payments(cost, p.food_counts()).into_iter().map(|c| FoodMap("pay_food", food_map(c))).collect()
        }
        Phase::ActivatePowers | Phase::EndTurn => unimplemented!("powers are not implemented yet (M1)"),
        Phase::GameOver => vec![],
    }
}

// =============================================================================
// Transitions (phase_handlers.py, engine.py, effects.py)
// =============================================================================

fn ensure_bird_deck(s: &mut State, c: &mut impl Chance, count: usize) {
    if s.bird_deck.len() < count && !s.discarded_birds.is_empty() {
        s.bird_deck.append(&mut s.discarded_birds);
        c.shuffle(&mut s.bird_deck);
    }
}

fn refresh_bird_tray(s: &mut State, c: &mut impl Chance) {
    while s.bird_tray.len() < 3 {
        ensure_bird_deck(s, c, 1);
        match s.bird_deck.pop() {
            Some(b) => s.bird_tray.push(b),
            None => break,
        }
    }
}

fn restock_bird_tray(s: &mut State, c: &mut impl Chance) {
    s.discarded_birds.append(&mut s.bird_tray);
    ensure_bird_deck(s, c, 3);
    let n = s.bird_deck.len().min(3);
    for _ in 0..n {
        let b = s.bird_deck.pop().unwrap();
        s.bird_tray.push(b);
    }
}

fn draw_cards(s: &mut State, c: &mut impl Chance, tray: &[u16], deck: usize) {
    let i = s.current_player_index;
    for &id in tray {
        if let Some(pos) = s.bird_tray.iter().position(|&b| b == id) {
            s.bird_tray.remove(pos);
            s.players[i].bird_hand.push(id);
        }
    }
    ensure_bird_deck(s, c, deck);
    for _ in 0..deck.min(s.bird_deck.len()) {
        let b = s.bird_deck.pop().unwrap();
        s.players[i].bird_hand.push(b);
    }
}

fn finish_main_action(s: &mut State, c: &mut impl Chance, skip_cube: bool) -> R {
    if !skip_cube {
        s.cur_mut().action_cubes -= 1;
    }
    let powers = triggered_powers(s);
    assert!(powers.is_empty());
    finalize_turn(s, c);
    Ok(())
}

fn finalize_turn(s: &mut State, c: &mut impl Chance) {
    if s.players.iter().all(|p| p.action_cubes == 0) {
        update_round_goal_scores(s);
        restock_bird_tray(s, c);
        let first = first_player_index(s);
        s.players[first].first_player = false;
        let n = s.players.len();
        s.players[(first + 1) % n].first_player = true;

        let next_round = s.round + 1;
        if next_round > 4 {
            for p in &mut s.players {
                update_player_scores(p);
            }
            s.game_phase = Phase::GameOver;
            s.action_data = ActionData::default();
            return;
        }
        for p in &mut s.players {
            p.action_cubes = 9 - next_round;
        }
        s.round = next_round;
        s.current_player_index = first_player_index(s);
    } else {
        refresh_bird_tray(s, c);
        s.current_player_index = next_player_index(s);
    }
    s.game_phase = Phase::MainTurn;
    s.action_data = ActionData::default();
    // "Once between turns": a pink power is only refreshed by its owner's own turn
    s.cur_mut().used_pink_powers.clear();
}

fn play_bird(s: &mut State, c: &mut impl Chance, pb: PlayCallback) -> R {
    let (row, col) = (pb.row as usize, pb.col as usize);
    if row >= 3 || col >= 5 {
        return Err(format!("invalid spot {row},{col}"));
    }
    // Costs are paid eggs first, then food; this handler re-runs after each payment
    let paid = s.action_data.pending_cost.as_ref().map(|p| p.cost_type);
    let egg_cost = EGG_COST[col];
    if egg_cost > 0 && !matches!(paid, Some(CostType::EggPaid | CostType::FoodPaid)) {
        s.action_data.pending_cost = Some(PendingCost {
            cost_type: CostType::Egg,
            amount: Some(egg_cost as i32),
            callback_phase: s.game_phase,
            callback_action: pb,
        });
        s.game_phase = Phase::PayEggCost;
        return Ok(());
    }
    if !s.cur().bird_hand.contains(&pb.bird) {
        return Err(format!("bird {} not in hand", pb.bird));
    }
    if !data().bird(pb.bird).cost.is_empty() && paid != Some(CostType::FoodPaid) {
        s.action_data.pending_cost = Some(PendingCost {
            cost_type: CostType::Food,
            amount: None,
            callback_phase: s.game_phase,
            callback_action: pb,
        });
        s.game_phase = Phase::PayFoodCost;
        return Ok(());
    }
    let p = s.cur_mut();
    if p.board[row][col].is_some() {
        return Err(format!("spot {row},{col} is occupied"));
    }
    p.board[row][col] = Some(PlacedBird { id: pb.bird, eggs: 0, food: 0, tucked: 0 });
    let pos = p.bird_hand.iter().position(|&b| b == pb.bird).unwrap();
    p.bird_hand.remove(pos);
    s.action_data.pending_cost = None; // costs settled; a chained play must pay its own
    finish_main_action(s, c, false)
}

/// After a cost is paid, mark it and return to the play-bird handler (Python's `pending_callback`).
fn resume_play_bird(s: &mut State, c: &mut impl Chance, paid: CostType) -> R {
    let Some(pending) = s.action_data.pending_cost.take() else { return Ok(()) };
    s.action_data.pending_cost = Some(PendingCost { cost_type: paid, amount: Some(0), ..pending });
    s.game_phase = pending.callback_phase;
    play_bird(s, c, pending.callback_action)
}

pub fn apply(s: &mut State, a: &Action, c: &mut impl Chance) -> R {
    use Action::*;
    let phase = s.game_phase;
    let bad = move || Err(format!("invalid action {a} in phase {phase:?}"));
    match (s.game_phase, a) {
        (Phase::GameSetup, Simple("start_setup")) => s.game_phase = Phase::SelectInitialCards,
        (Phase::GameSetup, Simple("end_setup")) => {
            s.game_phase = Phase::MainTurn;
            s.round = 1;
        }
        (Phase::SelectInitialCards, SelectInitial { kept, bonus }) => {
            let p = s.cur_mut();
            let (keep, drop): (Vec<u16>, Vec<u16>) = p.bird_hand.iter().copied().partition(|b| kept.contains(b));
            p.bird_hand = keep;
            p.bonus_hand.retain(|b| b == bonus);
            s.discarded_birds.extend(drop);
            if !kept.is_empty() {
                s.action_data.amount_to_discard = kept.len() as i32;
                s.game_phase = Phase::DiscardFood;
            } else {
                s.cur_mut().action_cubes = 8;
                s.game_phase = Phase::GameSetup;
                s.current_player_index = next_player_index(s);
            }
        }
        (Phase::DiscardFood, FoodMap(_, items)) => {
            let p = s.cur_mut();
            if items.iter().any(|&(f, n)| p.food_of(f) < n) {
                return Err(format!("not enough food to discard {a}"));
            }
            for &(f, n) in items {
                p.pay_food(f, n);
            }
            p.action_cubes = 8;
            s.action_data = ActionData::default();
            s.game_phase = Phase::GameSetup;
            s.current_player_index = next_player_index(s);
        }
        (Phase::MainTurn, Simple(t)) => {
            let p = s.cur();
            match *t {
                "gain_food" => {
                    let spot = leftmost_empty(p, 0);
                    let base = spot.map_or(3, |c| RESOURCE_AMOUNT[0][c]);
                    if !p.bird_hand.is_empty() && spot.map_or(true, |c| EXTRA_RESOURCE[c]) {
                        s.game_phase = Phase::ExtraFoodAction;
                        s.action_data.base_amount = base;
                    } else {
                        s.game_phase = Phase::CollectFood;
                        s.action_data.food_needed = base;
                    }
                }
                "play_bird" => s.game_phase = Phase::PlayBird,
                "lay_eggs" => {
                    if !has_egg_room(p) {
                        return finish_main_action(s, c, false);
                    }
                    let spot = leftmost_empty(p, 1);
                    let base = spot.map_or(4, |c| RESOURCE_AMOUNT[1][c]);
                    if !p.food.is_empty() && spot.map_or(true, |c| EXTRA_RESOURCE[c]) {
                        s.game_phase = Phase::ExtraLayEggsAction;
                        s.action_data.base_amount = base;
                    } else {
                        s.game_phase = Phase::LayEggs;
                        s.action_data.eggs_needed = base;
                    }
                }
                "draw_cards" => {
                    let spot = leftmost_empty(p, 2);
                    let base = spot.map_or(3, |c| RESOURCE_AMOUNT[2][c]);
                    if total_eggs(p) > 0 && spot.map_or(true, |c| EXTRA_RESOURCE[c]) {
                        s.game_phase = Phase::ExtraCardDrawAction;
                        s.action_data.base_amount = base;
                    } else {
                        s.game_phase = Phase::DrawCards;
                        s.action_data.cards_needed = base;
                    }
                }
                _ => return bad(),
            }
        }
        (Phase::CollectFood, SelectDie { die, food }) => {
            let Some(pos) = s.feeder.iter().position(|(d, _)| d == die) else {
                return Err(format!("die {die} not in feeder"));
            };
            if !s.feeder[pos].1.foods().contains(food) {
                return Err(format!("die {die} doesn't have {}", food.name()));
            }
            s.cur_mut().gain_food(*food, 1);
            s.feeder.remove(pos);
            if s.feeder.is_empty() {
                s.feeder = roll_feeder(c);
            }
            s.action_data.food_needed -= 1;
            if *food == Food::Rodent {
                s.action_data.gained_rodent = true;
            }
            if s.action_data.food_needed == 0 {
                return finish_main_action(s, c, false);
            }
        }
        (Phase::CollectFood, Simple("reroll_all")) => s.feeder = roll_feeder(c),
        (Phase::LayEggs, EggMap(_, items)) => {
            let p = s.cur_mut();
            for &(id, n) in items {
                if let Some(b) = p.bird_mut(id) {
                    b.eggs = (b.eggs + n).min(data().bird(id).egg_limit);
                }
            }
            return finish_main_action(s, c, false);
        }
        (Phase::DrawCards, DrawCards { tray, deck }) => {
            draw_cards(s, c, tray, *deck as usize);
            return finish_main_action(s, c, false);
        }
        (Phase::ExtraFoodAction, Simple("trade_bird")) => s.game_phase = Phase::SelectBirdToDiscard,
        (Phase::ExtraFoodAction, Simple("skip_trade")) => {
            s.game_phase = Phase::CollectFood;
            s.action_data.food_needed = s.action_data.base_amount;
        }
        (Phase::ExtraLayEggsAction, Simple("trade_food")) => s.game_phase = Phase::SelectFoodToDiscard,
        (Phase::ExtraLayEggsAction, Simple("skip_trade")) => {
            s.game_phase = Phase::LayEggs;
            s.action_data.eggs_needed = s.action_data.base_amount;
        }
        (Phase::ExtraCardDrawAction, Simple("trade_egg")) => s.game_phase = Phase::SelectEggToDiscard,
        (Phase::ExtraCardDrawAction, Simple("skip_trade")) => {
            s.game_phase = Phase::DrawCards;
            s.action_data.cards_needed = s.action_data.base_amount;
        }
        (Phase::SelectBirdToDiscard, Id("discard_bird", id)) => {
            let p = s.cur_mut();
            let Some(pos) = p.bird_hand.iter().position(|b| b == id) else {
                return Err(format!("bird {id} not in hand"));
            };
            p.bird_hand.remove(pos);
            s.discarded_birds.push(*id);
            s.game_phase = Phase::CollectFood;
            s.action_data.food_needed = s.action_data.base_amount + 1;
        }
        (Phase::SelectFoodToDiscard, Name("discard_food", f)) => {
            let p = s.cur_mut();
            if p.food_of(*f) == 0 {
                return Err(format!("no {} to discard", f.name()));
            }
            p.pay_food(*f, 1);
            s.game_phase = Phase::LayEggs;
            s.action_data.eggs_needed = s.action_data.base_amount + 1;
        }
        (Phase::SelectEggToDiscard, Id("discard_egg", id)) => {
            match s.cur_mut().bird_mut(*id) {
                Some(b) if b.eggs > 0 => b.eggs -= 1,
                _ => return Err(format!("bird {id} not on board or has no eggs")),
            }
            s.game_phase = Phase::DrawCards;
            s.action_data.cards_needed = s.action_data.base_amount + 1;
        }
        (Phase::PlayBird, PlayBird { bird, row, col }) => {
            return play_bird(s, c, PlayCallback { bird: *bird, row: *row, col: *col })
        }
        (Phase::PayEggCost, EggMap(_, items)) => {
            let p = s.cur_mut();
            for &(id, n) in items {
                match p.bird_mut(id) {
                    Some(b) if b.eggs >= n => {}
                    _ => return Err(format!("can't pay {n} eggs from bird {id}")),
                }
            }
            for &(id, n) in items {
                p.bird_mut(id).unwrap().eggs -= n;
            }
            return resume_play_bird(s, c, CostType::EggPaid);
        }
        (Phase::PayFoodCost, FoodMap(_, items)) => {
            let p = s.cur_mut();
            if items.iter().any(|&(f, n)| p.food_of(f) < n) {
                return Err("not enough food to pay food cost".into());
            }
            for &(f, n) in items {
                p.pay_food(f, n);
            }
            return resume_play_bird(s, c, CostType::FoodPaid);
        }
        _ => return bad(),
    }
    Ok(())
}

// =============================================================================
// Scoring (scoring.py)
// =============================================================================

fn count_bonus_birds(bonus_id: u16, p: &Player) -> usize {
    let bonus = data().bonus(bonus_id);
    if !bonus.valid_birds.is_empty() {
        return p.birds().filter(|b| bonus.valid_birds.binary_search(&b.id).is_ok()).count();
    }
    match bonus.id {
        5 => p.birds().filter(|b| b.eggs >= 4).count(),
        7 => (0..3).map(|r| p.board[r].iter().flatten().count()).min().unwrap(),
        17 => p.birds().filter(|b| b.eggs >= 1).count(),
        23 => p.bird_hand.len(),
        id => panic!("bonus {id} has no scoring rule"),
    }
}

fn score_bonus(bonus_id: u16, p: &Player) -> i32 {
    let n = count_bonus_birds(bonus_id, p);
    if n == 0 {
        return 0;
    }
    match data().bonus(bonus_id).score {
        BonusScore::PerBird(k) => k * n as i32,
        BonusScore::Bounds { lower, upper, lower_score, upper_score } => {
            if n >= upper {
                upper_score
            } else if n >= lower {
                lower_score
            } else {
                0
            }
        }
    }
}

pub fn update_player_scores(p: &mut Player) {
    let d = data();
    let sc = Score {
        bird_points: p.birds().map(|b| d.bird(b.id).points).sum(),
        egg_points: p.birds().map(|b| b.eggs as i32).sum(),
        cached_food: p.birds().map(|b| b.food as i32).sum(),
        tucked_cards: p.birds().map(|b| b.tucked as i32).sum(),
        round_goals: p.score.round_goals,
        bonus_scores: p.score.bonus_scores.clone(),
    };
    p.score = sc;
    for id in p.bonus_hand.clone() {
        let v = score_bonus(id, p);
        let bs = &mut p.score.bonus_scores;
        match bs.binary_search_by_key(&id, |&(k, _)| k) {
            Ok(i) => bs[i].1 = v,
            Err(i) => bs.insert(i, (id, v)),
        }
    }
}

pub fn total_score(p: &Player) -> i32 {
    let s = &p.score;
    s.bird_points + s.egg_points + s.cached_food + s.tucked_cards + s.round_goals.iter().sum::<i32>()
        + s.bonus_scores.iter().map(|&(_, v)| v).sum::<i32>()
}

fn evaluate_goal(p: &Player, goal: &str) -> i32 {
    let d = data();
    let nest = |n: &str| match n {
        "bowl" => Nest::Bowl,
        "cavity" => Nest::Cavity,
        "ground" => Nest::Ground,
        _ => Nest::Platform,
    };
    let row = |h: &str| HABITATS.iter().position(|x| *x == h).unwrap();
    let eggs_in_row = |r: usize| p.board[r].iter().flatten().map(|b| b.eggs as i32).sum::<i32>();
    if let Some(n) = goal.strip_prefix("eggs_in_").filter(|n| !HABITATS.contains(n)) {
        let n = nest(n);
        return p.birds().filter(|b| has_nest(d.bird(b.id).nest, n)).map(|b| b.eggs as i32).sum();
    }
    if let Some(n) = goal.strip_suffix("_birds_with_egg") {
        let n = nest(n);
        return p.birds().filter(|b| has_nest(d.bird(b.id).nest, n) && b.eggs >= 1).count() as i32;
    }
    if let Some(h) = goal.strip_prefix("eggs_in_") {
        return eggs_in_row(row(h));
    }
    if let Some(h) = goal.strip_prefix("birds_in_") {
        return p.board[row(h)].iter().flatten().count() as i32;
    }
    match goal {
        "total_birds" => p.birds().count() as i32,
        "sets_of_eggs" => (0..3).map(eggs_in_row).min().unwrap(),
        _ => panic!("unknown goal {goal}"),
    }
}

fn update_round_goal_scores(s: &mut State) {
    let r = s.round as usize;
    let goal = s.selected_goals[r - 1].clone();
    let counts: Vec<i32> = s.players.iter().map(|p| evaluate_goal(p, &goal)).collect();
    let scores: Vec<i32> = match s.scoring_mode {
        ScoringMode::Blue => counts.iter().map(|&c| c.min(5)).collect(),
        ScoringMode::Green => {
            const TABLE: [[i32; 4]; 4] = [[4, 1, 0, 0], [5, 2, 1, 0], [6, 3, 2, 0], [7, 4, 3, 0]];
            let table = TABLE[r - 1];
            let mut order: Vec<usize> = (0..counts.len()).collect();
            order.sort_by(|&a, &b| counts[b].cmp(&counts[a])); // stable, like Python's sort
            let mut scores = vec![0; counts.len()];
            let mut pos = 0;
            while pos < order.len() {
                let count = counts[order[pos]];
                let end = (pos..order.len()).find(|&i| counts[order[i]] != count).unwrap_or(order.len());
                let total: i32 = (pos..end.min(table.len())).map(|i| table[i]).sum();
                let share = total.div_euclid((end - pos) as i32);
                for &i in &order[pos..end] {
                    // Players with none of the targeted item score 0
                    scores[i] = if count != 0 { share } else { 0 };
                }
                pos = end;
            }
            scores
        }
    };
    for (p, v) in s.players.iter_mut().zip(scores) {
        p.score.round_goals[r - 1] = v;
    }
}

// =============================================================================
// Random play (benchmark)
// =============================================================================

/// One random 2-player game from a fresh deal; returns the number of decisions.
pub fn play_random_game(rng: &mut Rng) -> usize {
    let mut s = initiate(2, ScoringMode::Green, rng);
    let mut steps = 0;
    loop {
        let actions = legal_actions(&s);
        if actions.is_empty() {
            return steps;
        }
        let a = &actions[rng.below(actions.len())];
        apply(&mut s, a, rng).expect("legal action failed");
        steps += 1;
    }
}
