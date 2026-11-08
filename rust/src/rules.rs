//! The rules: setup, legal actions, transitions, scoring. A port of engine/{actions,engine,phase_handlers,
//! effects,utils,scoring}.py that keeps the same orders (of actions, of draws, of dict iteration), because
//! rollouts pick moves by index and the action strings are data keys.
//! Bird powers live in powers.rs; this file runs their queue (engine.py `activate_powers`, end of turn).

use crate::actions::{Action, Arr, EggItems, FoodItems};
use crate::chance::{Chance, Rng};
use crate::data::{data, BonusScore, Color, Nest};
use crate::powers::{self, Pink};
use crate::state::*;

// Board layout (models.py `_build_board_layout`). Rows: forest, grassland, wetland.
const RESOURCE_AMOUNT: [[i32; 5]; 3] = [[1, 1, 2, 2, 3], [2, 2, 3, 3, 4], [1, 1, 2, 2, 3]];
const EXTRA_RESOURCE: [bool; 5] = [false, true, false, true, false];
const EGG_COST: [u8; 5] = [0, 1, 1, 2, 2];
pub const HABITATS: [&str; 3] = ["forest", "grassland", "wetland"];

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

/// Roll all 5 dice into the feeder (in place, keeping its allocation).
pub fn roll_feeder(feeder: &mut Vec<(u8, Face)>, c: &mut impl Chance) {
    feeder.clear();
    feeder.extend((0..5).map(|i| (i, Face(c.roll_die()))));
}

/// Same steps as Python's `initiate_state`, with this engine's own RNG.
pub fn initiate(n_players: usize, mode: ScoringMode, rng: &mut Rng) -> State {
    let d = data();
    let mut bird_deck = d.bird_ids.clone();
    let mut bonus_deck = d.bonus_ids.clone();
    rng.shuffle(&mut bird_deck);
    rng.shuffle(&mut bonus_deck);
    let mut feeder = Vec::with_capacity(5);
    roll_feeder(&mut feeder, rng);

    let mut tiles: [u8; 8] = std::array::from_fn(|i| i as u8);
    let mut goals = [0u8; 4];
    for i in 0..4 {
        let j = i + rng.below(8 - i); // sample 4 tiles without replacement, then a side of each
        tiles.swap(i, j);
        goals[i] = 2 * tiles[i] + rng.below(2) as u8;
    }
    let selected_goals = Goals(goals);

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

pub fn leftmost_empty(p: &Player, row: usize) -> Option<usize> {
    p.board[row].iter().position(|b| b.is_none())
}

pub fn has_nest(nest: Nest, wanted: Nest) -> bool {
    nest == wanted || nest == Nest::Wild
}

fn has_egg_room(p: &Player) -> bool {
    let d = data();
    p.birds().any(|b| b.eggs < d.hot(b.id).egg_limit)
}

fn total_eggs(p: &Player) -> u32 {
    p.birds().map(|b| b.eggs as u32).sum()
}

/// `can_afford_bird_cost`: some option is payable, each missing food replaced by any 2 tokens, wild by any 1.
fn can_afford(cost: &[([u8; 5], u8)], food: [u8; 5]) -> bool {
    if cost.is_empty() {
        return true;
    }
    let total: u32 = food.iter().map(|&n| n as u32).sum();
    cost.iter().any(|(need, wild)| {
        let (mut used, mut deficit) = (0u32, 0u32);
        for i in 0..5 {
            let u = need[i].min(food[i]);
            used += u as u32;
            deficit += (need[i] - u) as u32;
        }
        total - used >= 2 * deficit + *wild as u32
    })
}

/// `generate_playable_bird_spots`: calls `f(bird, row, col)` in hand order, then row order, until it
/// returns false.
pub fn for_playable_spots(p: &Player, mut f: impl FnMut(u16, u8, u8) -> bool) {
    if p.bird_hand.is_empty() {
        return;
    }
    let eggs = total_eggs(p);
    let spots: [Option<usize>; 3] =
        std::array::from_fn(|r| leftmost_empty(p, r).filter(|&c| EGG_COST[c] as u32 <= eggs));
    let open: u8 = (0..3).filter(|&r| spots[r].is_some()).map(|r| 1 << r).sum();
    if open == 0 {
        return;
    }
    let food = p.food_counts();
    let d = data();
    for &id in &p.bird_hand {
        // Cheap habitat test first; it doesn't change which spots are yielded
        if d.hot(id).habitats & open == 0 {
            continue;
        }
        let bird = d.bird(id);
        if !can_afford(&bird.cost_counts, food) {
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

pub fn food_map(counts: [u8; 5]) -> FoodItems {
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
fn egg_combinations(items: &[(u16, u8)], total: u32, emit: &mut dyn FnMut(EggItems)) {
    fn dfs(items: &[(u16, u8)], suffix: &[u32], i: usize, left: u32, cur: &mut EggItems, out: &mut dyn FnMut(EggItems)) {
        if left == 0 {
            let mut v = *cur;
            v.sort_unstable();
            out(v);
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
    let mut suffix = [0u32; 16];
    for i in (0..items.len()).rev() {
        suffix[i] = suffix[i + 1] + items[i].1 as u32;
    }
    dfs(items, &suffix, 0, total, &mut EggItems::new(), emit);
}

// =============================================================================
// Legal actions (actions.py)
// =============================================================================

pub fn legal_actions(s: &State) -> Vec<Action> {
    let mut out = vec![];
    legal_actions_into(s, &mut out);
    out
}

/// `legal_actions` into a reused buffer (rollouts call this at every step).
pub fn legal_actions_into(s: &State, out: &mut Vec<Action>) {
    use Action::*;
    out.clear();
    let p = s.cur();
    let ad = &s.action_data;
    match s.game_phase {
        Phase::GameSetup => out.push(Simple(if p.action_cubes == 9 { "start_setup" } else { "end_setup" })),
        Phase::SelectInitialCards => {
            assert!(p.bird_hand.len() == 5 && p.bonus_hand.len() == 2, "setup needs 5 birds and 2 bonuses");
            for &bonus in &p.bonus_hand {
                for k in 0..=5 {
                    combinations(5, k, |idx| {
                        out.push(SelectInitial { kept: idx.iter().map(|&i| p.bird_hand[i]).collect(), bonus })
                    });
                }
            }
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
            out.extend(seen.into_iter().map(|c| FoodMap("discard_food_combo", food_map(c))));
        }
        Phase::MainTurn => {
            if p.action_cubes == 0 {
                return;
            }
            // With no room for eggs the action is only worth taking for its brown powers
            if has_egg_room(p) || powers::has_brown_power(p, 1) {
                out.push(Simple("lay_eggs"));
            }
            if can_play_a_bird(p) {
                out.push(Simple("play_bird"));
            }
            out.push(Simple("gain_food"));
            if s.bird_deck.len() + s.discarded_birds.len() + s.bird_tray.len() > 0 {
                out.push(Simple("draw_cards"));
            }
        }
        Phase::ExtraFoodAction => out.extend([Simple("trade_bird"), Simple("skip_trade")]),
        Phase::ExtraLayEggsAction => out.extend([Simple("trade_food"), Simple("skip_trade")]),
        Phase::ExtraCardDrawAction => out.extend([Simple("trade_egg"), Simple("skip_trade")]),
        Phase::CollectFood => collect_food_actions(s, out),
        Phase::LayEggs => {
            assert!(ad.eggs_needed > 0, "no eggs needed");
            let items: EggItems = p
                .birds()
                .filter_map(|b| {
                    let limit = data().hot(b.id).egg_limit;
                    (b.eggs < limit).then(|| (b.id, limit - b.eggs))
                })
                .collect();
            egg_distribution_actions(&items, ad.eggs_needed as u32, "lay_eggs", out)
        }
        Phase::DrawCards => card_draw_actions(s, ad.cards_needed as usize, out),
        Phase::SelectBirdToDiscard => out.extend(p.bird_hand.iter().map(|&id| Id("discard_bird", id))),
        Phase::SelectFoodToDiscard => out.extend(p.food.iter().map(|&(f, _)| Name("discard_food", f.name()))),
        Phase::SelectEggToDiscard => out.extend(p.birds().filter(|b| b.eggs > 0).map(|b| Id("discard_egg", b.id))),
        Phase::PlayBird => {
            // A bird played by a power (12) must go in that power's habitat
            let target = ad
                .execution_stack
                .last()
                .filter(|e| e.power_id == 12)
                .and_then(|e| e.context.target_habitat.as_deref())
                .map(crate::data::habitat_row);
            for_playable_spots(p, |bird, row, col| {
                if target.map_or(true, |t| t == row as usize) {
                    out.push(PlayBird { bird, row, col });
                }
                true
            });
        }
        Phase::PayEggCost => {
            let pending = ad.pending_cost.as_ref().filter(|c| c.cost_type == CostType::Egg).expect("no egg cost pending");
            let items: EggItems = p.birds().filter(|b| b.eggs > 0).map(|b| (b.id, b.eggs)).collect();
            egg_combinations(&items, pending.amount.unwrap() as u32, &mut |c| out.push(EggMap("pay_eggs", c)));
        }
        Phase::PayFoodCost => {
            let pending = ad.pending_cost.as_ref().filter(|c| c.cost_type == CostType::Food).expect("no food cost pending");
            let cost = &data().bird(pending.callback_action.bird).cost;
            out.extend(food_payments(cost, p.food_counts()).into_iter().map(|c| FoodMap("pay_food", food_map(c))));
        }
        Phase::ActivatePowers => match ad.execution_stack.last() {
            None => {
                let q = ad.powers_queue.get(ad.current_power_index as usize).expect("no power in queue");
                out.push(Simple("skip_power"));
                if powers::can_execute(s, q) {
                    out.push(Simple("activate_power"));
                }
            }
            Some(e) => powers::choices(s, e, out),
        },
        Phase::EndTurn => {
            if let Some(e) = ad.execution_stack.last().filter(|e| e.phase == Some(PowerPhase::EndTurnDiscard)) {
                out.extend(s.players[e.player_index].bird_hand.iter().map(|&id| Id("discard_card", id)));
            }
        }
        Phase::GameOver => {}
    }
}

/// `get_collect_food_actions`: every food on every die, plus a reroll if all dice show the same face.
pub fn collect_food_actions(s: &State, out: &mut Vec<Action>) {
    out.extend(s.feeder.iter().flat_map(|&(die, face)| face.foods().iter().map(move |&food| Action::SelectDie { die, food })));
    if !s.feeder.is_empty() && s.feeder.iter().all(|&(_, f)| f == s.feeder[0].1) {
        out.push(Action::Simple("reroll_all"));
    }
}

/// `get_egg_distribution_combinations` over (bird, capacity) items.
pub fn egg_distribution_actions(items: &[(u16, u8)], eggs: u32, ty: &'static str, out: &mut Vec<Action>) {
    assert!(eggs > 0 && !items.is_empty(), "no eggs to lay or no birds with egg capacity");
    let capacity: u32 = items.iter().map(|&(_, c)| c as u32).sum();
    if eggs >= capacity {
        let mut all: EggItems = items.iter().copied().collect();
        all.sort_unstable();
        out.push(Action::EggMap(ty, all));
        return;
    }
    egg_combinations(items, eggs, &mut |c| out.push(Action::EggMap(ty, c)));
}

/// `get_card_draw_combinations`: tray/deck mixes, partial if fewer cards remain.
pub fn card_draw_actions(s: &State, needed: usize, out: &mut Vec<Action>) {
    assert!(needed > 0, "no cards needed");
    let tray = &s.bird_tray;
    let deck = s.bird_deck.len() + s.discarded_birds.len();
    let available = tray.len() + deck;
    assert!(available > 0, "no cards to draw");
    let actual = needed.min(available);
    for t in 0..=actual.min(tray.len()) {
        let from_deck = actual - t;
        if from_deck > deck {
            continue;
        }
        combinations(tray.len(), t, |idx| {
            out.push(Action::DrawCards { tray: idx.iter().map(|&i| tray[i]).collect(), deck: from_deck as u8 })
        });
    }
}

// =============================================================================
// Transitions (phase_handlers.py, engine.py, effects.py)
// =============================================================================

pub fn ensure_bird_deck(s: &mut State, c: &mut impl Chance, count: usize) {
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

pub fn draw_cards(s: &mut State, c: &mut impl Chance, i: usize, tray: &[u16], deck: usize) {
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

/// `select_die_effect`: take one food from a die; an emptied feeder is rerolled.
pub fn select_die(s: &mut State, c: &mut impl Chance, die: u8, food: Food, player: usize) -> R {
    let Some(pos) = s.feeder.iter().position(|&(d, _)| d == die) else {
        return Err(format!("die {die} not in feeder"));
    };
    if !s.feeder[pos].1.foods().contains(&food) {
        return Err(format!("die {die} doesn't have {}", food.name()));
    }
    s.players[player].gain_food(food, 1);
    s.feeder.remove(pos);
    if s.feeder.is_empty() {
        roll_feeder(&mut s.feeder, c);
    }
    Ok(())
}

/// `lay_eggs_effect`: add eggs to birds of `player`, up to their egg limit.
pub fn lay_eggs_effect(s: &mut State, player: usize, items: &[(u16, u8)]) {
    let p = &mut s.players[player];
    for &(id, n) in items {
        if let Some(b) = p.bird_mut(id) {
            b.eggs = (b.eggs + n).min(data().hot(id).egg_limit);
        }
    }
}

/// `tuck_cards_effect`: tuck cards from the deck under a bird of the current player.
pub fn tuck_cards(s: &mut State, c: &mut impl Chance, bird: u16, count: usize) -> R {
    let cur = s.current_player_index;
    if s.players[cur].bird_mut(bird).is_none() {
        return Err(format!("Bird {bird} not found on current player's board"));
    }
    ensure_bird_deck(s, c, count);
    let n = count.min(s.bird_deck.len());
    s.bird_deck.truncate(s.bird_deck.len() - n);
    s.players[cur].bird_mut(bird).unwrap().tucked += n as u8;
    Ok(())
}

/// Complete a main action: use a cube, then queue the powers it triggers (pink ones of the other
/// players first), or end the turn if there are none.
fn finish_main_action(
    s: &mut State,
    c: &mut impl Chance,
    color: Color,
    row: Option<usize>,
    spot: Option<(usize, usize)>,
    skip_cube: bool,
    pink: Option<Pink>,
) -> R {
    if !skip_cube {
        s.cur_mut().action_cubes -= 1;
    }
    let cur = s.current_player_index;
    let mut queue = std::mem::take(&mut s.action_data.powers_queue); // reuse its allocation
    queue.clear();
    if let Some(t) = pink {
        powers::triggered_pink(s, t, cur, &mut queue);
    }
    powers::triggered(s, cur, color, row, spot, &mut queue);
    if queue.is_empty() {
        s.action_data.powers_queue = queue;
        finalize_turn(s, c);
        return Ok(());
    }
    s.game_phase = Phase::ActivatePowers;
    s.current_player_index = queue[0].player_index;
    s.action_data.powers_queue = queue;
    s.action_data.current_power_index = 0;
    s.action_data.action_player_index = Some(cur);
    Ok(())
}

/// engine.py `activate_powers`: skip or activate the next queued power, or answer the running one.
fn activate_powers(s: &mut State, c: &mut impl Chance, a: &Action) -> R {
    let ad = &mut s.action_data;
    if ad.execution_stack.is_empty() {
        match a {
            Action::Simple("skip_power") => {
                ad.current_power_index += 1;
                return check_powers_done(s, c);
            }
            Action::Simple("activate_power") => {
                let q = *ad.powers_queue.get(ad.current_power_index as usize).ok_or("No power to activate")?;
                if data().power(q.bird_id).map(|p| p.color) == Some(Color::Pink) {
                    let used = &mut s.players[q.player_index].used_pink_powers;
                    if let Err(i) = used.binary_search(&q.bird_id) {
                        used.insert(i, q.bird_id);
                    }
                }
                s.action_data.execution_stack.push(Execution {
                    power_id: q.power_id,
                    bird_id: q.bird_id,
                    spot_row: q.spot_row,
                    spot_col: q.spot_col,
                    player_index: q.player_index,
                    phase: None,
                    context: Context::default(),
                });
                powers::activate(s, c)?;
                if s.action_data.execution_stack.is_empty() {
                    s.action_data.current_power_index += 1;
                    return check_powers_done(s, c);
                }
                return Ok(());
            }
            _ => return Err(format!("Unknown action with empty stack: {a}")),
        }
    }
    powers::handle(s, c, a)?;
    loop {
        match s.action_data.execution_stack.last() {
            None => {
                s.action_data.current_power_index += 1;
                return check_powers_done(s, c);
            }
            // A power pushed by another (14 repeating a brown power) starts right away
            Some(e) if e.phase.is_none() => powers::activate(s, c)?,
            Some(_) => return Ok(()),
        }
    }
}

fn check_powers_done(s: &mut State, c: &mut impl Chance) -> R {
    let ad = &s.action_data;
    match ad.powers_queue.get(ad.current_power_index as usize) {
        Some(q) => {
            s.current_player_index = q.player_index;
            Ok(())
        }
        None => {
            if let Some(i) = ad.action_player_index {
                s.current_player_index = i;
            }
            s.game_phase = Phase::EndTurn;
            handle_end_turn(s, c, None)
        }
    }
}

/// engine.py `handle_end_turn`: deferred "discard a card at the end of turn" effects, then the turn ends.
fn handle_end_turn(s: &mut State, c: &mut impl Chance, mut a: Option<&Action>) -> R {
    loop {
        let Some(effect) = s.action_data.end_turn_effects.first().cloned() else {
            finalize_turn(s, c);
            return Ok(());
        };
        if effect.effect_type != "discard_cards" {
            return Ok(());
        }
        let waiting = s.action_data.execution_stack.last().is_some_and(|e| e.phase == Some(PowerPhase::EndTurnDiscard));
        if !waiting {
            // Later powers may have used up the drawn card; nothing left to discard
            if s.players[effect.player_index].bird_hand.is_empty() {
                s.action_data.end_turn_effects.remove(0);
                a = None;
                continue;
            }
            s.action_data.execution_stack.push(Execution {
                power_id: 0,
                bird_id: 0,
                spot_row: 0,
                spot_col: 0,
                player_index: effect.player_index,
                phase: Some(PowerPhase::EndTurnDiscard),
                context: Context { amount: Some(effect.amount), ..Context::default() },
            });
            return Ok(());
        }
        let Some(Action::Id(_, id)) = a else { return Err(format!("expected a card to discard, got {a:?}")) };
        let p = &mut s.players[effect.player_index];
        if let Some(pos) = p.bird_hand.iter().position(|b| b == id) {
            p.bird_hand.remove(pos);
            s.discarded_birds.push(*id);
        }
        s.action_data.end_turn_effects.remove(0);
        s.action_data.execution_stack.pop();
        a = None;
    }
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
            s.action_data.reset();
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
    s.action_data.reset();
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
    let pink = Some(Pink::BirdPlayed(row));
    if s.action_data.execution_stack.last().is_some_and(|e| e.power_id == 12) {
        s.action_data.execution_stack.pop();
        s.game_phase = Phase::ActivatePowers;
        return finish_main_action(s, c, Color::White, None, Some((row, col)), true, pink);
    }
    finish_main_action(s, c, Color::White, None, Some((row, col)), false, pink)
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
            s.action_data.reset();
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
                        return finish_main_action(s, c, Color::Brown, Some(1), None, false, Some(Pink::LayEggs));
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
            select_die(s, c, *die, *food, s.current_player_index)?;
            s.action_data.food_needed -= 1;
            if *food == Food::Rodent {
                s.action_data.gained_rodent = true;
            }
            if s.action_data.food_needed == 0 {
                let pink = s.action_data.gained_rodent.then_some(Pink::GainRodent);
                return finish_main_action(s, c, Color::Brown, Some(0), None, false, pink);
            }
        }
        (Phase::CollectFood, Simple("reroll_all")) => roll_feeder(&mut s.feeder, c),
        (Phase::LayEggs, EggMap(_, items)) => {
            lay_eggs_effect(s, s.current_player_index, items);
            return finish_main_action(s, c, Color::Brown, Some(1), None, false, Some(Pink::LayEggs));
        }
        (Phase::DrawCards, DrawCards { tray, deck }) => {
            draw_cards(s, c, s.current_player_index, tray, *deck as usize);
            return finish_main_action(s, c, Color::Brown, Some(2), None, false, None);
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
            let f = &crate::data::food_from_str(f);
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
        (Phase::ActivatePowers, _) => return activate_powers(s, c, a),
        (Phase::EndTurn, _) => return handle_end_turn(s, c, Some(a)),
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
    let (mut points, mut eggs, mut food, mut tucked) = (0, 0, 0, 0);
    for b in p.birds() {
        points += d.bird(b.id).points;
        eggs += b.eggs as i32;
        food += b.food as i32;
        tucked += b.tucked as i32;
    }
    let sc = &mut p.score;
    (sc.bird_points, sc.egg_points, sc.cached_food, sc.tucked_cards) = (points, eggs, food, tucked);
    for i in 0..p.bonus_hand.len() {
        let id = p.bonus_hand[i];
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
    let goal = s.selected_goals.name(r);
    let counts: Arr<i32, 5> = s.players.iter().map(|p| evaluate_goal(p, goal)).collect();
    let scores: Arr<i32, 5> = match s.scoring_mode {
        ScoringMode::Blue => counts.iter().map(|&c| c.min(5)).collect(),
        ScoringMode::Green => {
            const TABLE: [[i32; 4]; 4] = [[4, 1, 0, 0], [5, 2, 1, 0], [6, 3, 2, 0], [7, 4, 3, 0]];
            let table = TABLE[r - 1];
            let mut order: Arr<usize, 5> = (0..counts.len()).collect();
            order.sort_by(|&a, &b| counts[b].cmp(&counts[a])); // stable, like Python's sort
            let mut scores: Arr<i32, 5> = counts.iter().map(|_| 0).collect();
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
    for (p, &v) in s.players.iter_mut().zip(scores.iter()) {
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
