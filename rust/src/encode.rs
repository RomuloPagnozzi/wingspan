//! The observation encoding of `wingspan.ai.encoding` (`encode_obs(state, viewer).flat()`), value for value,
//! so a network trained on Python-encoded data can be evaluated inside the search. Column names, scales and
//! the reasons behind them live in encoding.py; this file only reproduces the numbers, in the same order.
//! `rust/py/parity.py --encoding` checks the two against each other.

use std::sync::OnceLock;

use crate::actions::Action;
use crate::data::{data, BonusScore, Color, Nest};
use crate::rules::{count_bonus_birds, evaluate_goal, leftmost_empty, score_bonus, EGG_COST, EXTRA_RESOURCE, RESOURCE_AMOUNT};
use crate::state::{CostType, Food, Phase, Player, PowerPhase, ScoringMode, State, GOAL_NAMES};

const FOODS: [Food; 5] = [Food::Invertebrate, Food::Seed, Food::Fish, Food::Fruit, Food::Rodent];
const NESTS: [Nest; 5] = [Nest::Bowl, Nest::Cavity, Nest::Ground, Nest::Platform, Nest::Wild];
/// GamePhase in Python's declaration order, without game_setup and game_over (encoding.PHASES).
const PHASES: [Phase; 17] = [
    Phase::MainTurn, Phase::ExtraFoodAction, Phase::ExtraLayEggsAction, Phase::ExtraCardDrawAction,
    Phase::SelectInitialCards, Phase::DiscardFood, Phase::CollectFood, Phase::LayEggs, Phase::DrawCards,
    Phase::PlayBird, Phase::SelectBirdToDiscard, Phase::SelectFoodToDiscard, Phase::SelectEggToDiscard,
    Phase::PayEggCost, Phase::PayFoodCost, Phase::ActivatePowers, Phase::EndTurn,
]; // fmt: skip
/// encoding.POWER_STEPS after "none" (index 0).
const POWER_STEPS: [PowerPhase; 16] = [
    PowerPhase::SelectDie, PowerPhase::SelectCard, PowerPhase::SelectBird, PowerPhase::ChooseCache,
    PowerPhase::SelectTrade, PowerPhase::SelectHabitat, PowerPhase::SelectGain, PowerPhase::SelectFoodType,
    PowerPhase::SelectFood, PowerPhase::SelectDraw, PowerPhase::SelectDiscard, PowerPhase::SelectBonus,
    PowerPhase::ChooseStartingPlayer, PowerPhase::Choices, PowerPhase::AwaitingBirdPlay, PowerPhase::EndTurnDiscard,
]; // fmt: skip
/// encoding.ACTION_KINDS
const ACTION_KINDS: [&str; 37] = [
    "simple_gain_food", "simple_lay_eggs", "simple_draw_cards", "simple_play_bird", "simple_trade_bird",
    "simple_trade_food", "simple_trade_egg", "simple_skip_trade", "simple_reroll_all", "simple_activate_power",
    "simple_skip_power", "simple_cache_food", "simple_supply_food",
    "id_discard_bird", "id_discard_card", "id_discard_egg", "id_discard_egg_from", "id_tuck_card", "id_select_bird",
    "id_select_card", "id_power_5_bonus", "id_choose_player",
    "name_discard_food", "name_select_food", "name_select_food_type", "name_select_habitat",
    "food_map_pay_food", "food_map_gain_food_combo", "food_map_discard_food_combo",
    "egg_map_pay_eggs", "egg_map_lay_eggs", "egg_map_activate_eggs",
    "play_bird_at", "select_die", "trade_food", "draw_combo", "select_initial_cards",
]; // fmt: skip
const HABITATS: [&str; 3] = ["forest", "grassland", "wetland"];
const MAX_PENDING: f64 = 5.0;
const MAX_ACTION_BIRDS: f64 = 5.0;
const N_TEMPLATES: usize = 22;
const N_BONUS_IDS: usize = 26;
const ROUND_CUBES: [i32; 4] = [8, 7, 6, 5];
const TOTAL_TURNS: i32 = 26;

fn scaled(v: f64, cap: f64) -> f64 {
    (v / cap).min(1.0)
}

/// Feature rows of every bird and bonus card (encoding.bird_table / bonus_table), indexed by id.
struct Tables {
    birds: Vec<Vec<f64>>,
    bonuses: Vec<Vec<f64>>,
    bird_len: usize,
    bonus_len: usize,
}

fn tables() -> &'static Tables {
    static T: OnceLock<Tables> = OnceLock::new();
    T.get_or_init(|| {
        let d = data();
        let birds: Vec<Vec<f64>> = d.birds.iter().map(|b| b.as_ref().map(bird_row).unwrap_or_default()).collect();
        let bonuses: Vec<Vec<f64>> = d.bonuses.iter().map(|b| b.as_ref().map(bonus_row).unwrap_or_default()).collect();
        let bird_len = birds.iter().map(Vec::len).max().unwrap();
        let bonus_len = bonuses.iter().map(Vec::len).max().unwrap();
        Tables { birds, bonuses, bird_len, bonus_len }
    })
}

fn bird_row(b: &crate::data::Bird) -> Vec<f64> {
    let mut v = vec![b.points as f64 / 9.0, b.egg_limit as f64 / 6.0, (b.wingspan as f64).ln() / 300f64.ln()];
    v.extend(NESTS.map(|n| (b.nest == n) as u8 as f64));
    v.extend(b.habitats.map(|h| h as u8 as f64));
    let n_opts = b.cost.len().max(1) as f64;
    let amount = |o: &Vec<(Option<crate::state::Food>, u8)>, f: Option<Food>| -> f64 {
        o.iter().filter(|(g, _)| *g == f).map(|&(_, n)| n as f64).sum()
    };
    for f in FOODS.map(Some).into_iter().chain([None]) {
        v.push(b.cost.iter().map(|o| amount(o, f)).sum::<f64>() / n_opts / 3.0);
    }
    let min_total = b.cost.iter().map(|o| o.iter().map(|&(_, n)| n as f64).sum::<f64>()).fold(f64::INFINITY, f64::min);
    v.push(if b.cost.is_empty() { 0.0 } else { min_total / 3.0 });
    v.push((b.cost.len() > 1) as u8 as f64);
    let color = b.power.as_ref().map(|p| p.color);
    v.extend([Some(Color::Brown), Some(Color::White), Some(Color::Pink), None].map(|c| (color == c) as u8 as f64));
    let template = b.power.as_ref().map_or(0, |p| p.id as usize);
    v.extend((0..N_TEMPLATES).map(|t| (t == template) as u8 as f64));
    v
}

fn bonus_row(b: &crate::data::Bonus) -> Vec<f64> {
    let mut v: Vec<f64> = (1..=N_BONUS_IDS).map(|i| (i == b.id as usize) as u8 as f64).collect();
    let (per_bird, lower, upper, lower_score, upper_score) = match b.score {
        BonusScore::PerBird(k) => (k, 0, 0, 0, 0),
        BonusScore::Bounds { lower, upper, lower_score, upper_score } => (0, lower, upper, lower_score, upper_score),
    };
    v.extend([
        per_bird as f64 / 2.0,
        lower as f64 / 9.0,
        upper as f64 / 9.0,
        lower_score as f64 / 8.0,
        upper_score as f64 / 8.0,
        b.valid_birds.is_empty() as u8 as f64,
    ]);
    v
}

/// The columns of a set of cards: their rows added up, as a fraction of `cap` cards (encoding._summed).
fn summed<'a>(out: &mut Vec<f32>, rows: impl Iterator<Item = &'a Vec<f64>>, len: usize, cap: f64) {
    let start = out.len();
    let mut acc = vec![0.0f64; len];
    for r in rows {
        for (a, x) in acc.iter_mut().zip(r) {
            *a += x;
        }
    }
    out.extend(acc.iter().map(|&a| scaled(a, cap) as f32));
    debug_assert_eq!(out.len(), start + len);
}

fn one_hot(out: &mut Vec<f32>, n: usize, hot: Option<usize>) {
    out.extend((0..n).map(|i| (Some(i) == hot) as u8 as f32));
}

fn bonus_cap(id: u16) -> f64 {
    match data().bonus(id).score {
        BonusScore::Bounds { upper, .. } => upper as f64,
        BonusScore::PerBird(_) => 5.0,
    }
}

fn player(out: &mut Vec<f32>, s: &State, pi: usize, viewer: usize) {
    let p: &Player = &s.players[pi];
    let t = tables();
    let visible = pi == viewer;
    for r in 0..3 {
        for c in 0..5 {
            let b = p.board[r][c];
            out.push(b.is_some() as u8 as f32);
            out.push(b.map_or(0.0, |b| b.eggs as f64 / 6.0) as f32);
            out.push(b.map_or(0.0, |b| scaled(b.food as f64, 6.0)) as f32);
            out.push(b.map_or(0.0, |b| scaled(b.tucked as f64, 6.0)) as f32);
            summed(out, b.iter().map(|b| &t.birds[b.id as usize]), t.bird_len, 1.0);
        }
        let next = leftmost_empty(p, r);
        out.push((p.board[r].iter().flatten().count() as f64 / 5.0) as f32);
        out.push((RESOURCE_AMOUNT[r][next.unwrap_or(4)] as f64 / 4.0) as f32);
        out.push(next.map_or(true, |c| EXTRA_RESOURCE[c]) as u8 as f32);
        out.push(next.map_or(0.0, |c| EGG_COST[c] as f64 / 2.0) as f32);
    }
    for f in FOODS {
        out.push(scaled(p.food_of(f) as f64, 8.0) as f32);
    }
    out.push(scaled(p.bird_hand.len() as f64, 12.0) as f32);
    let hand: &[u16] = if visible { &p.bird_hand } else { &[] };
    summed(out, hand.iter().map(|&b| &t.birds[b as usize]), t.bird_len, 12.0);
    out.push(scaled(p.bonus_hand.len() as f64, 4.0) as f32);
    let bonuses: &[u16] = if visible { &p.bonus_hand } else { &[] };
    summed(out, bonuses.iter().map(|&b| &t.bonuses[b as usize]), t.bonus_len, 1.0);
    let progress: f64 = bonuses.iter().map(|&b| count_bonus_birds(b, p) as f64 / bonus_cap(b)).sum();
    out.push(scaled(progress, 1.0) as f32);
    out.push(scaled(bonuses.iter().map(|&b| score_bonus(b, p)).sum::<i32>() as f64, 8.0) as f32);
    for &pts in &p.score.round_goals {
        out.push(scaled(pts as f64, 7.0) as f32);
    }
    for r in 1..=4usize {
        let goal = s.selected_goals.name(r);
        let scored = (r as i32) < s.round || s.game_phase == Phase::GameOver;
        let count = if scored { 0 } else { evaluate_goal(p, goal) };
        out.push(scaled(count as f64, goal_cap(goal)) as f32);
    }
    let on_board: i32 = p.birds().map(|b| data().bird(b.id).points + (b.eggs + b.food + b.tucked) as i32).sum();
    out.push(scaled((on_board + p.score.round_goals.iter().sum::<i32>()) as f64, 120.0) as f32);
    let cubes = p.action_cubes;
    let later: i32 = ((s.round + 1).max(1)..=4).map(|r| ROUND_CUBES[r as usize - 1]).sum();
    let turns_left = cubes.min(8) + later;
    out.push(scaled(cubes as f64, 8.0) as f32);
    out.push((turns_left as f64 / TOTAL_TURNS as f64) as f32);
    out.push((cubes == 1) as u8 as f32);
    out.push((turns_left == 1) as u8 as f32);
    out.push(p.first_player as u8 as f32);
}

fn goal_cap(goal: &str) -> f64 {
    if goal.starts_with("eggs_in_") {
        15.0
    } else if goal.ends_with("_birds_with_egg") {
        8.0
    } else if goal.starts_with("birds_in_") {
        5.0
    } else if goal == "total_birds" {
        15.0
    } else {
        10.0
    }
}

fn shared(out: &mut Vec<f32>, s: &State, viewer: usize) {
    let t = tables();
    // public_features
    out.push((s.bird_tray.len() as f64 / 3.0) as f32);
    summed(out, s.bird_tray.iter().map(|&b| &t.birds[b as usize]), t.bird_len, 3.0);
    out.push((s.feeder.len() as f64 / 5.0) as f32);
    for f in FOODS {
        out.push((s.feeder.iter().filter(|(_, face)| face.foods().contains(&f)).count() as f64 / 5.0) as f32);
    }
    let same = s.feeder.iter().all(|(_, face)| *face == s.feeder[0].1);
    out.push((!s.feeder.is_empty() && same) as u8 as f32);
    out.push(scaled(s.bird_deck.len() as f64, 170.0) as f32);
    out.push(scaled(s.discarded_birds.len() as f64, 60.0) as f32);
    one_hot(out, 4, (1..=4).contains(&s.round).then(|| s.round as usize - 1));
    for r in 0..4 {
        one_hot(out, GOAL_NAMES.len(), Some(s.selected_goals.0[r] as usize));
    }
    out.push((s.scoring_mode == ScoringMode::Green) as u8 as f32);

    // pending_features
    let ad = &s.action_data;
    one_hot(out, PHASES.len(), PHASES.iter().position(|&p| p == s.game_phase));
    out.push((ad.action_player_index.unwrap_or(s.current_player_index) == viewer) as u8 as f32);
    for n in [ad.food_needed, ad.eggs_needed, ad.cards_needed, ad.amount_to_discard, ad.base_amount] {
        out.push(scaled(n as f64, 5.0) as f32);
    }
    out.push(scaled((ad.powers_queue.len() as i32 - ad.current_power_index) as f64, 5.0) as f32);
    out.push(scaled(ad.end_turn_effects.len() as f64, 2.0) as f32);
    let running = ad.execution_stack.last();
    let queued = usize::try_from(ad.current_power_index).ok().and_then(|i| ad.powers_queue.get(i));
    let template = running.map(|e| e.power_id).or(queued.map(|q| q.power_id)).unwrap_or(0);
    one_hot(out, N_TEMPLATES, Some(template as usize));
    let step = running.and_then(|e| e.phase).map_or(0, |ph| 1 + POWER_STEPS.iter().position(|&x| x == ph).unwrap());
    one_hot(out, 1 + POWER_STEPS.len(), Some(step));
    let cost = ad.pending_cost.as_ref();
    let payment = match cost.map(|c| c.cost_type) {
        None => Some(0),
        Some(CostType::Egg) => Some(1),
        Some(CostType::Food) => Some(2),
        Some(_) => None,
    };
    one_hot(out, 3, payment);
    let egg_amount = cost.filter(|c| c.cost_type == CostType::Egg).map_or(0.0, |c| scaled(c.amount.unwrap_or(0) as f64, 2.0));
    out.push(egg_amount as f32);
    let paying_for = cost.filter(|_| s.current_player_index == viewer).map(|c| &t.birds[c.callback_action.bird as usize]);
    summed(out, paying_for.into_iter(), t.bird_len, 1.0);
    one_hot(out, 4, (2..=5).contains(&s.players.len()).then(|| s.players.len() - 2));
}

/// `encode_obs(state, viewer).flat()`: viewer, then opponents clockwise, then the shared columns.
pub fn encode_obs(s: &State, viewer: usize) -> Vec<f32> {
    let n = s.players.len();
    let mut out = Vec::with_capacity(2048);
    player(&mut out, s, viewer, viewer);
    for k in 1..n {
        player(&mut out, s, (viewer + k) % n, viewer);
    }
    shared(&mut out, s, viewer);
    out
}

fn action_kind(a: &Action) -> String {
    match a {
        Action::Simple(t) => format!("simple_{t}"),
        Action::Id(t, _) => format!("id_{t}"),
        Action::Name(t, _) => format!("name_{t}"),
        Action::FoodMap(t, _) => format!("food_map_{t}"),
        Action::EggMap(t, _) => format!("egg_map_{t}"),
        Action::Trade { .. } => "trade_food".into(),
        Action::PlayBird { .. } => "play_bird_at".into(),
        Action::SelectDie { .. } => "select_die".into(),
        Action::DrawCards { .. } => "draw_combo".into(),
        Action::SelectInitial { .. } => "select_initial_cards".into(),
    }
}

/// encoding.action_bird_ids: the birds a move names, sorted, once per egg for an egg distribution.
pub fn action_bird_ids(a: &Action) -> Vec<u16> {
    let mut v: Vec<u16> = match a {
        Action::Id("power_5_bonus" | "choose_player", _) => vec![], // bonus and player ids, not birds
        Action::Id(_, i) | Action::PlayBird { bird: i, .. } => vec![*i],
        Action::EggMap(_, items) => items.iter().flat_map(|&(b, n)| std::iter::repeat_n(b, n as usize)).collect(),
        Action::DrawCards { tray, .. } => tray.to_vec(),
        Action::SelectInitial { kept, .. } => kept.to_vec(),
        _ => vec![],
    };
    v.sort_unstable();
    v
}

/// encoding.encode_action: one legal move of the player to move.
pub fn encode_action(s: &State, a: &Action) -> Vec<f32> {
    let t = tables();
    let birds = action_bird_ids(a);
    let food = |f: Food| FOODS.iter().position(|&x| x == f).unwrap();
    let (mut spots, mut foods, mut given) = ([0u32; 15], [0u32; 5], [0u32; 5]);
    let (mut bonus, mut habitat, mut eggs, mut deck_cards, mut targets_self) = (None, None, 0, 0, false);
    match a {
        Action::Id("power_5_bonus", i) => bonus = Some(*i),
        Action::Id("choose_player", i) => targets_self = *i as usize == s.current_player_index,
        Action::Name("select_habitat", h) => habitat = HABITATS.iter().position(|x| x == h),
        Action::Name(_, name) => {
            if let Some(i) = FOODS.iter().position(|f| f.name() == *name) {
                foods[i] += 1;
            }
        }
        Action::PlayBird { row, col, .. } => spots[*row as usize * 5 + *col as usize] += 1,
        Action::SelectDie { food: f, .. } => foods[food(*f)] += 1,
        Action::Trade { from, to } => {
            given[food(*from)] += 1;
            foods[food(*to)] += 1;
        }
        Action::FoodMap(_, items) => items.iter().for_each(|&(f, n)| foods[food(f)] += n as u32),
        Action::EggMap(..) => eggs = birds.len(),
        Action::DrawCards { deck, .. } => deck_cards = *deck,
        Action::SelectInitial { bonus: b, .. } => bonus = Some(*b),
        _ => {}
    }
    // Birds on the mover's board are also located by spot
    let mover = &s.players[s.current_player_index];
    for &b in &birds {
        for r in 0..3 {
            for c in 0..5 {
                if mover.board[r][c].is_some_and(|x| x.id == b) {
                    spots[r * 5 + c] += 1;
                }
            }
        }
    }

    let mut out = Vec::with_capacity(146);
    one_hot(&mut out, ACTION_KINDS.len(), ACTION_KINDS.iter().position(|&k| k == action_kind(a)));
    summed(&mut out, birds.iter().map(|&b| &t.birds[b as usize]), t.bird_len, birds.len().max(1) as f64);
    let mut unique = birds.clone();
    unique.dedup();
    out.push(scaled(unique.len() as f64, MAX_ACTION_BIRDS) as f32);
    let bonus = bonus.filter(|&b| b != 0); // Python: `if bonus_id`
    summed(&mut out, bonus.iter().map(|&b| &t.bonuses[b as usize]), t.bonus_len, 1.0);
    out.extend(spots.map(|n| scaled(n as f64, MAX_PENDING) as f32));
    one_hot(&mut out, 3, habitat);
    out.extend(foods.map(|n| scaled(n as f64, MAX_PENDING) as f32));
    out.extend(given.map(|n| scaled(n as f64, MAX_PENDING) as f32));
    out.push(scaled(eggs as f64, MAX_PENDING) as f32);
    out.push(scaled(deck_cards as f64, MAX_PENDING) as f32);
    out.push(targets_self as u8 as f32);
    out
}

/// Index of the phase in encoding.PHASES (the dataset's `phase` column).
pub fn phase_index(s: &State) -> usize {
    PHASES.iter().position(|&p| p == s.game_phase).expect("a decision is never in game_setup or game_over")
}
