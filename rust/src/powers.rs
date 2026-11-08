//! Bird powers: triggers (utils.py), validators, choice generators and handlers (power/*.py).
//!
//! A triggered power is queued (`QueuedPower`); activating it pushes an `Execution` on the stack. The
//! handler either finishes at once (pops itself) or sets a `PowerPhase` and waits for a choice, which
//! `choices` lists and `handle` applies. Same structure and orders as the Python engine.

use crate::actions::Action;
use crate::chance::Chance;
use crate::data::{data, food_from_str, habitat_row, Color, Kind, Nest, Power, Qty, TuckBonus};
use crate::rules::*;
use crate::state::*;

type R = Result<(), String>;

pub const PREDATOR_POWERS: [u8; 2] = [11, 15];

/// The food order of the supply in Python (`init_food`, power 16, `get_food_gain_combinations`).
const SUPPLY_ORDER: [Food; 5] = [Food::Invertebrate, Food::Seed, Food::Fish, Food::Fruit, Food::Rodent];

fn power(bird: u16) -> &'static Power {
    data().power(bird).expect("bird has no power")
}

// =============================================================================
// Triggers
// =============================================================================

/// `get_triggered_powers`: brown powers of a habitat row (right to left), or the white power of one spot.
pub fn triggered(s: &State, player: usize, color: Color, row: Option<usize>, spot: Option<(usize, usize)>) -> Vec<QueuedPower> {
    let p = &s.players[player];
    let spots: Vec<(usize, usize)> = match (spot, row) {
        (Some(sp), _) => vec![sp],
        (None, Some(r)) => (0..5).rev().map(|c| (r, c)).collect(),
        _ => vec![],
    };
    spots
        .into_iter()
        .filter_map(|(r, c)| {
            let b = p.board[r][c]?;
            let pw = data().power(b.id).filter(|pw| pw.color == color)?;
            Some(QueuedPower { power_id: pw.id, bird_id: b.id, spot_row: r as u8, spot_col: c as u8, player_index: player })
        })
        .collect()
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Pink {
    BirdPlayed(usize), // habitat row
    GainRodent,
    LayEggs,
    PredatorSuccess,
}

/// `get_triggered_pink_powers`: other players' unused pink powers, clockwise from the left of `by`.
pub fn triggered_pink(s: &State, trigger: Pink, by: usize) -> Vec<QueuedPower> {
    let n = s.players.len();
    let mut out = vec![];
    for o in 1..n {
        let i = (by + o) % n;
        let p = &s.players[i];
        for r in 0..3 {
            for c in 0..5 {
                let Some(b) = p.board[r][c] else { continue };
                let Some(pw) = data().power(b.id).filter(|pw| pw.color == Color::Pink) else { continue };
                if p.used_pink_powers.contains(&b.id) {
                    continue;
                }
                let matches = match (&pw.kind, trigger) {
                    (Kind::PinkPlayed { habitat, .. }, Pink::BirdPlayed(h)) => *habitat == h,
                    (Kind::PinkRodent, Pink::GainRodent) => true,
                    (Kind::PinkLayEgg { .. }, Pink::LayEggs) => true,
                    (Kind::PinkPredator, Pink::PredatorSuccess) => true,
                    _ => false,
                };
                if matches {
                    out.push(QueuedPower { power_id: pw.id, bird_id: b.id, spot_row: r as u8, spot_col: c as u8, player_index: i });
                }
            }
        }
    }
    out
}

/// Opponents' pink powers that react to a successful predator run right after the current power.
fn queue_predator_success(s: &mut State, player: usize) {
    let pinks = triggered_pink(s, Pink::PredatorSuccess, player);
    let at = s.action_data.current_power_index as usize + 1;
    for (i, q) in pinks.into_iter().enumerate() {
        s.action_data.powers_queue.insert(at + i, q);
    }
}

// =============================================================================
// Validators (validators.py)
// =============================================================================

/// `get_valid_birds_for_eggs`: birds with the nest type and room for an egg, in board order.
pub fn valid_birds_for_eggs(p: &Player, nest: Nest) -> Vec<u16> {
    p.birds().filter(|b| has_nest(data().bird(b.id).nest, nest) && b.eggs < data().bird(b.id).egg_limit).map(|b| b.id).collect()
}

fn cards_available(s: &State) -> usize {
    s.bird_deck.len() + s.discarded_birds.len()
}

pub fn can_execute(s: &State, q: &QueuedPower) -> bool {
    let pw = power(q.bird_id);
    let cur = s.cur();
    let (row, col) = (q.spot_row as usize, q.spot_col as usize);
    match &pw.kind {
        Kind::AllGain { card, .. } => !card || cards_available(s) >= s.players.len(),
        Kind::AllLayEggs { nest } => s.players.iter().any(|p| !valid_birds_for_eggs(p, *nest).is_empty()),
        Kind::DiscardToGain { discard_food, gain_card, gain_qty, draw } => {
            if *gain_card {
                let available = cards_available(s) + if *draw { s.bird_tray.len() } else { 0 };
                if available < *gain_qty as usize {
                    return false;
                }
            }
            match discard_food {
                None => cur.birds().any(|b| b.eggs > 0 && (*gain_card || b.id != q.bird_id)),
                Some(f) => cur.food_of(*f) > 0,
            }
        }
        Kind::Draw { amount, bonus, .. } => {
            if *bonus {
                s.bonus_deck.len() + s.discarded_bonuses.len() >= *amount as usize
            } else {
                cards_available(s) + s.bird_tray.len() >= *amount as usize
            }
        }
        Kind::DrawShare => cards_available(s) >= s.players.len() + 1,
        Kind::GainFood { supply, foods, .. } => {
            *supply || foods.iter().any(|f| s.feeder.iter().any(|(_, face)| face.foods().contains(f)))
        }
        Kind::MoveBird => {
            let bird = s.players[q.player_index].board[row][col].expect("power spot is empty");
            let rightmost = (0..5).rev().find(|&c| cur.board[row][c].is_some());
            if rightmost != Some(col) {
                return false;
            }
            data().bird(bird.id).habitat_order.iter().any(|&h| h != row && leftmost_empty(cur, h).is_some())
        }
        Kind::LayEggs { this, nest } => {
            if *this {
                return match s.players[q.player_index].board[row][col] {
                    Some(b) => b.eggs < data().bird(b.id).egg_limit,
                    None => false,
                };
            }
            match nest {
                None => cur.birds().any(|b| b.eggs < data().bird(b.id).egg_limit),
                Some(n) => !valid_birds_for_eggs(cur, *n).is_empty(),
            }
        }
        Kind::Hunt { .. } => cards_available(s) >= 1,
        Kind::PlayAnother { habitat } => {
            let target = habitat.unwrap_or(row);
            let mut any = false;
            for_playable_spots(cur, |_, r, _| {
                any = r as usize == target;
                !any
            });
            any
        }
        Kind::Fewest { card, .. } => !card || cards_available(s) + s.bird_tray.len() >= 1,
        Kind::Repeat { predator } => (0..5).any(|c| {
            let Some(b) = cur.board[row][c] else { return false };
            if b.id == q.bird_id {
                return false;
            }
            let Some(other) = data().power(b.id) else { return false };
            if *predator {
                PREDATOR_POWERS.contains(&other.id)
            } else {
                other.color == Color::Brown
                    && other.id != 14
                    && can_execute(
                        s,
                        &QueuedPower {
                            power_id: other.id,
                            bird_id: b.id,
                            spot_row: row as u8,
                            spot_col: c as u8,
                            player_index: s.current_player_index,
                        },
                    )
            }
        }),
        Kind::DiceHunt { .. } => s.feeder.len() != 5,
        Kind::Trade => !cur.food.is_empty(),
        Kind::Tuck { bonus } => {
            !cur.bird_hand.is_empty() && (*bonus != TuckBonus::Card || cards_available(s) + s.bird_tray.len() >= 1)
        }
        Kind::PinkPlayed { card, .. } => !card || !s.players[q.player_index].bird_hand.is_empty(),
        Kind::PinkLayEgg { nest } => {
            valid_birds_for_eggs(&s.players[q.player_index], *nest).iter().any(|&id| id != q.bird_id)
        }
        Kind::CacheSeed | Kind::AllGainDie | Kind::PinkRodent | Kind::PinkPredator => true,
    }
}

// =============================================================================
// Choices (choices.py)
// =============================================================================

/// `get_food_gain_combinations`: ways to gain `qty` food tokens of any types, as counts by `Food`.
fn food_gain_combinations(qty: u8) -> Vec<[u8; 5]> {
    fn gen(left: u8, start: usize, combo: &mut [u8; 5], out: &mut Vec<[u8; 5]>) {
        if left == 0 {
            out.push(*combo);
            return;
        }
        for &f in &SUPPLY_ORDER[start..] {
            let i = SUPPLY_ORDER.iter().position(|&g| g == f).unwrap();
            for n in 1..=left {
                combo[f as usize] = n;
                gen(left - n, i + 1, combo, out);
                combo[f as usize] = 0;
            }
        }
    }
    let mut out = vec![];
    gen(qty, 0, &mut [0; 5], &mut out);
    out
}

fn habitat_name(name: &str) -> &'static str {
    HABITATS[habitat_row(name)]
}

pub fn choices(s: &State, e: &Execution) -> Vec<Action> {
    use Action::*;
    let ctx = &e.context;
    let cur = s.cur();
    let phase = e.phase.expect("power execution has no phase");
    match (&power(e.bird_id).kind, phase) {
        (_, PowerPhase::SelectDraw) => card_draw_actions(s, ctx.draw_amount.unwrap() as usize),
        (Kind::AllLayEggs { nest }, PowerPhase::Choices) => {
            let amount = if Some(s.current_player_index) == ctx.activator { 2 } else { 1 };
            // At most 1 egg per bird: the activator's second egg goes on an additional bird
            let items: Vec<(u16, u8)> = valid_birds_for_eggs(cur, *nest).into_iter().map(|id| (id, 1)).collect();
            egg_distribution_actions(&items, amount, "activate_eggs")
        }
        (Kind::DiscardToGain { discard_food, gain_card, .. }, PowerPhase::SelectDiscard) => match discard_food {
            None => cur
                .birds()
                .filter(|b| b.eggs > 0 && (*gain_card || b.id != e.bird_id))
                .map(|b| Id("discard_egg_from", b.id))
                .collect(),
            Some(f) => vec![Name("discard_food", f.name())],
        },
        (Kind::DiscardToGain { gain_qty, .. }, PowerPhase::SelectGain) => {
            food_gain_combinations(*gain_qty).into_iter().map(|c| FoodMap("gain_food_combo", food_map(c))).collect()
        }
        (Kind::Draw { .. }, PowerPhase::SelectBonus) => {
            ctx.bonus_options.iter().flatten().map(|&id| Id("power_5_bonus", id)).collect()
        }
        (Kind::DrawShare, PowerPhase::SelectCard) => {
            ctx.available_cards.iter().flatten().map(|&id| Id("select_card", id)).collect()
        }
        (Kind::AllGainDie, PowerPhase::ChooseStartingPlayer) => {
            (0..s.players.len()).map(|i| Id("choose_player", i as u16)).collect()
        }
        (Kind::AllGainDie | Kind::Fewest { .. } | Kind::PinkPredator, PowerPhase::SelectDie) => collect_food_actions(s),
        (Kind::GainFood { .. }, PowerPhase::SelectFoodType) => {
            ctx.available_foods.iter().flatten().map(|f| Name("select_food_type", f.name())).collect()
        }
        (Kind::GainFood { .. }, PowerPhase::SelectDie) => {
            let all = collect_food_actions(s);
            match ctx.food_type {
                None => all,
                Some(ft) => all.into_iter().filter(|a| !matches!(a, SelectDie { food, .. } if *food != ft)).collect(),
            }
        }
        (Kind::GainFood { .. }, PowerPhase::ChooseCache) => vec![Simple("cache_food"), Simple("supply_food")],
        (Kind::MoveBird, PowerPhase::SelectHabitat) => {
            ctx.valid_habitats.iter().flatten().map(|h| Name("select_habitat", habitat_name(h))).collect()
        }
        (Kind::LayEggs { .. } | Kind::PinkLayEgg { .. }, PowerPhase::SelectBird) => {
            ctx.valid_bird_ids.iter().flatten().map(|&id| Id("select_bird", id)).collect()
        }
        (Kind::Repeat { .. }, PowerPhase::SelectBird) => {
            ctx.eligible_birds.iter().flatten().map(|&(id, _, _)| Id("select_bird", id)).collect()
        }
        (Kind::Trade, PowerPhase::SelectTrade) => cur
            .food
            .iter()
            .flat_map(|&(from, _)| SUPPLY_ORDER.iter().filter(move |&&to| to != from).map(move |&to| Trade { from, to }))
            .collect(),
        (Kind::Tuck { .. }, PowerPhase::SelectCard) => cur.bird_hand.iter().map(|&id| Id("tuck_card", id)).collect(),
        (Kind::Tuck { bonus: TuckBonus::Foods(foods) }, PowerPhase::SelectFood) => {
            foods.iter().map(|f| Name("select_food", f.name())).collect()
        }
        (Kind::PinkPlayed { .. }, PowerPhase::SelectCard) => {
            s.players[e.player_index].bird_hand.iter().map(|&id| Id("tuck_card", id)).collect()
        }
        (k, ph) => panic!("no choices for power {k:?} in phase {ph:?}"),
    }
}

// =============================================================================
// Handlers (handlers.py)
// =============================================================================

fn top(s: &mut State) -> &mut Execution {
    s.action_data.execution_stack.last_mut().unwrap()
}

fn pop(s: &mut State) {
    s.action_data.execution_stack.pop();
}

fn spot_bird<'a>(s: &'a mut State, e: &Execution) -> &'a mut PlacedBird {
    s.players[e.player_index].board[e.spot_row as usize][e.spot_col as usize].as_mut().expect("power spot is empty")
}

fn await_draw(s: &mut State, amount: u8) {
    let t = top(s);
    t.phase = Some(PowerPhase::SelectDraw);
    t.context.draw_amount = Some(amount);
}

/// Remove the first occurrence of `x` (Python's `list.remove`).
fn remove_first<T: PartialEq>(v: &mut Vec<T>, x: &T) {
    let i = v.iter().position(|y| y == x).expect("list.remove(x): x not in list");
    v.remove(i);
}

/// The current player is done with a multi-player power: pass on, or return to the activator and finish.
fn next_awaiting(s: &mut State) {
    let cur = s.current_player_index;
    let t = top(s);
    let awaiting = t.context.awaiting_players.as_mut().unwrap();
    remove_first(awaiting, &cur);
    if let Some(&next) = awaiting.first() {
        s.current_player_index = next;
    } else {
        s.current_player_index = t.context.activator.unwrap();
        pop(s);
    }
}

fn matching_dice(s: &State, f: Food) -> Vec<u8> {
    s.feeder.iter().filter(|(_, face)| face.foods().contains(&f)).map(|&(d, _)| d).collect()
}

fn reroll(s: &mut State, c: &mut impl Chance) {
    s.feeder = roll_feeder(c);
}

/// Run the power on top of the stack, which has just been pushed (phase None).
pub fn activate(s: &mut State, c: &mut impl Chance) -> R {
    let e = s.action_data.execution_stack.last().unwrap().clone();
    let n = s.players.len();
    let cur = s.current_player_index;
    match &power(e.bird_id).kind {
        Kind::AllGain { card, food } => {
            for i in 0..n {
                if *card {
                    draw_cards(s, c, i, &[], 1);
                } else {
                    s.players[i].gain_food(food.unwrap(), 1);
                }
            }
            pop(s);
        }
        Kind::AllLayEggs { nest } => {
            let act = e.player_index;
            let order = std::iter::once(act).chain((0..n).filter(|&i| i != act));
            let awaiting: Vec<usize> = order.filter(|&i| !valid_birds_for_eggs(&s.players[i], *nest).is_empty()).collect();
            if awaiting.is_empty() {
                pop(s);
            } else {
                s.current_player_index = awaiting[0];
                let t = top(s);
                t.phase = Some(PowerPhase::Choices);
                t.context.activator = Some(act);
                t.context.awaiting_players = Some(awaiting);
            }
        }
        Kind::CacheSeed | Kind::PinkRodent => {
            spot_bird(s, &e).food += 1;
            pop(s);
        }
        Kind::DiscardToGain { .. } => top(s).phase = Some(PowerPhase::SelectDiscard),
        Kind::Draw { amount, bonus, .. } => {
            if !bonus {
                await_draw(s, *amount);
            } else {
                if s.bonus_deck.len() < *amount as usize {
                    s.bonus_deck.append(&mut s.discarded_bonuses);
                    c.shuffle(&mut s.bonus_deck);
                }
                let drawn: Vec<u16> =
                    (0..*amount).map(|_| s.bonus_deck.pop().ok_or("bonus deck is empty")).collect::<Result<_, _>>()?;
                let t = top(s);
                t.context.bonus_options = Some(drawn);
                t.phase = Some(PowerPhase::SelectBonus);
            }
        }
        Kind::DrawShare => {
            let act = e.player_index;
            ensure_bird_deck(s, c, n + 1);
            let actual = (n + 1).min(s.bird_deck.len());
            if actual == 0 {
                pop(s);
                return Ok(());
            }
            let drawn: Vec<u16> = (0..actual).map(|_| s.bird_deck.pop().unwrap()).collect();
            let mut order: Vec<usize> = (0..n).map(|i| (act + i) % n).collect();
            let picks = actual.min(n + 1);
            if picks > n {
                order.push(act);
            } else {
                order.truncate(picks);
            }
            s.current_player_index = order[0];
            let t = top(s);
            t.phase = Some(PowerPhase::SelectCard);
            t.context.activator = Some(act);
            t.context.awaiting_players = Some(order);
            t.context.available_cards = Some(drawn);
        }
        Kind::AllGainDie => {
            let t = top(s);
            t.phase = Some(PowerPhase::ChooseStartingPlayer);
            t.context.activator = Some(e.player_index);
        }
        Kind::GainFood { can_cache, supply, qty, foods } => {
            if *can_cache && *qty != Qty::N(1) {
                return Err("Invalid power 8: can_cache=True requires quantity=1".into());
            }
            if !can_cache && foods.len() == 1 && *supply {
                let Qty::N(q) = qty else { return Err("supply quantity 'all'".into()) };
                s.players[cur].gain_food(foods[0], *q as u8);
                pop(s);
                return Ok(());
            }
            if !can_cache && foods.len() == 1 && !supply && *qty == Qty::All {
                for d in matching_dice(s, foods[0]) {
                    select_die(s, c, d, foods[0], cur)?;
                }
                pop(s);
                return Ok(());
            }
            if *supply && *can_cache {
                s.players[cur].gain_food(foods[0], 1);
                let t = top(s);
                t.phase = Some(PowerPhase::ChooseCache);
                t.context.food_type = Some(foods[0]);
                return Ok(());
            }
            if !supply {
                let mut available: Vec<Food> =
                    foods.iter().copied().filter(|f| s.feeder.iter().any(|(_, face)| face.foods().contains(f))).collect();
                available.sort_unstable();
                available.dedup();
                if foods.len() > 1 && available.len() > 1 {
                    let t = top(s);
                    t.phase = Some(PowerPhase::SelectFoodType);
                    t.context.available_foods = Some(available);
                    return Ok(());
                }
                let food = if foods.len() == 1 { foods[0] } else { *available.first().ok_or("no food available")? };
                top(s).context.food_type = Some(food);
                let dice = matching_dice(s, food);
                if *qty == Qty::N(1) && dice.len() == 1 && !can_cache {
                    select_die(s, c, dice[0], food, cur)?;
                    pop(s);
                    return Ok(());
                }
                let t = top(s);
                t.phase = Some(PowerPhase::SelectDie);
                if let Qty::N(q) = qty {
                    if *q != 1 {
                        t.context.remaining_quantity = Some(*q);
                    }
                }
                return Ok(());
            }
            pop(s);
        }
        Kind::MoveBird => {
            let p = &s.players[e.player_index];
            let (row, col) = (e.spot_row as usize, e.spot_col as usize);
            let bird = p.board[row][col].expect("power spot is empty");
            let valid: Vec<usize> =
                data().bird(bird.id).habitat_order.iter().copied().filter(|&h| h != row && leftmost_empty(p, h).is_some()).collect();
            if valid.len() == 1 {
                let to = leftmost_empty(p, valid[0]).unwrap();
                let p = &mut s.players[e.player_index];
                p.board[row][col] = None;
                p.board[valid[0]][to] = Some(bird);
                pop(s);
            } else {
                let t = top(s);
                t.phase = Some(PowerPhase::SelectHabitat);
                t.context.valid_habitats = Some(valid.iter().map(|&h| HABITATS[h].to_string()).collect());
            }
        }
        Kind::LayEggs { this, nest } => {
            if *this {
                if let Some(b) = s.players[e.player_index].board[e.spot_row as usize][e.spot_col as usize] {
                    lay_eggs_effect(s, cur, &[(b.id, 1)]);
                }
                pop(s);
                return Ok(());
            }
            if let Some(nest) = nest {
                let birds: Vec<(u16, u8)> =
                    valid_birds_for_eggs(&s.players[e.player_index], *nest).into_iter().map(|id| (id, 1)).collect();
                lay_eggs_effect(s, cur, &birds);
                pop(s);
                return Ok(());
            }
            let valid: Vec<u16> = s.players[e.player_index]
                .birds()
                .filter(|b| b.eggs < data().bird(b.id).egg_limit)
                .map(|b| b.id)
                .collect();
            if valid.len() == 1 {
                lay_eggs_effect(s, cur, &[(valid[0], 1)]);
                pop(s);
            } else {
                let t = top(s);
                t.phase = Some(PowerPhase::SelectBird);
                t.context.valid_bird_ids = Some(valid);
            }
        }
        Kind::Hunt { wingspan } => {
            ensure_bird_deck(s, c, 1);
            let drawn = s.bird_deck.pop().ok_or("bird deck is empty")?;
            if data().bird(drawn).wingspan < *wingspan {
                spot_bird(s, &e).tucked += 1;
                queue_predator_success(s, e.player_index);
            } else {
                s.discarded_birds.push(drawn);
            }
            pop(s);
        }
        Kind::PlayAnother { habitat } => {
            let target = habitat.unwrap_or(e.spot_row as usize);
            s.game_phase = Phase::PlayBird;
            let t = top(s);
            t.context.target_habitat = Some(HABITATS[target].to_string());
            t.phase = Some(PowerPhase::AwaitingBirdPlay);
        }
        Kind::Fewest { habitat, card } => {
            let counts: Vec<usize> = s.players.iter().map(|p| p.board[*habitat].iter().flatten().count()).collect();
            let min = *counts.iter().min().unwrap();
            // Clockwise from the activator, so on a tie the activator picks first
            let fewest: Vec<usize> = (0..n).map(|i| (e.player_index + i) % n).filter(|&i| counts[i] == min).collect();
            if *card {
                await_draw(s, 1);
            } else {
                top(s).phase = Some(PowerPhase::SelectDie);
            }
            s.current_player_index = fewest[0];
            let t = top(s);
            t.context.awaiting_players = Some(fewest);
            t.context.activator = Some(e.player_index);
        }
        Kind::Repeat { predator } => {
            let row = e.spot_row as usize;
            let p = &s.players[e.player_index];
            let mut eligible = vec![];
            for col in 0..5 {
                let Some(b) = p.board[row][col] else { continue };
                if b.id == e.bird_id {
                    continue;
                }
                let Some(other) = data().power(b.id) else { continue };
                let q = QueuedPower { power_id: other.id, bird_id: b.id, spot_row: row as u8, spot_col: col as u8, player_index: e.player_index };
                let ok = if *predator {
                    PREDATOR_POWERS.contains(&other.id)
                } else {
                    other.color == Color::Brown && other.id != 14 && can_execute(s, &q)
                };
                if ok {
                    eligible.push((b.id, row as u8, col as u8));
                }
            }
            if eligible.is_empty() {
                return Err("No eligible birds found".into());
            }
            let t = top(s);
            t.phase = Some(PowerPhase::SelectBird);
            t.context.eligible_birds = Some(eligible);
        }
        Kind::DiceHunt { food } => {
            let roll: Vec<u8> = (0..5 - s.feeder.len()).map(|_| c.roll_die()).collect();
            if roll.iter().any(|&f| Face(f).foods().contains(food)) {
                spot_bird(s, &e).food += 1;
                queue_predator_success(s, e.player_index);
            }
            pop(s);
        }
        Kind::Trade => top(s).phase = Some(PowerPhase::SelectTrade),
        Kind::Tuck { .. } => top(s).phase = Some(PowerPhase::SelectCard),
        Kind::PinkPlayed { card, food, .. } => {
            if *card {
                top(s).phase = Some(PowerPhase::SelectCard);
            } else {
                s.players[e.player_index].gain_food(food.unwrap(), 1);
                pop(s);
            }
        }
        Kind::PinkLayEgg { nest } => {
            let valid: Vec<u16> =
                valid_birds_for_eggs(&s.players[e.player_index], *nest).into_iter().filter(|&id| id != e.bird_id).collect();
            if valid.len() == 1 {
                lay_eggs_effect(s, e.player_index, &[(valid[0], 1)]);
                pop(s);
            } else {
                let t = top(s);
                t.phase = Some(PowerPhase::SelectBird);
                t.context.valid_bird_ids = Some(valid);
            }
        }
        Kind::PinkPredator => top(s).phase = Some(PowerPhase::SelectDie),
    }
    Ok(())
}

/// Apply a choice to the power on top of the stack (which is waiting in some phase).
pub fn handle(s: &mut State, c: &mut impl Chance, a: &Action) -> R {
    use Action::*;
    let e = s.action_data.execution_stack.last().unwrap().clone();
    let cur = s.current_player_index;
    let phase = e.phase.ok_or("power execution has no phase")?;
    let bad = || Err(format!("invalid action {a} for power {} in phase {phase:?}", e.power_id));
    match (&power(e.bird_id).kind, phase, a) {
        (kind, PowerPhase::SelectDraw, DrawCards { tray, deck }) => {
            draw_cards(s, c, cur, tray, *deck as usize);
            match kind {
                Kind::Draw { discard, .. } => {
                    if *discard {
                        s.action_data.end_turn_effects.push(EndTurnEffect {
                            effect_type: "discard_cards".into(),
                            player_index: cur,
                            amount: 1,
                        });
                    }
                    pop(s);
                }
                Kind::Fewest { .. } => {
                    if cards_available(s) + s.bird_tray.len() == 0 {
                        top(s).context.awaiting_players = Some(vec![cur]);
                    }
                    next_awaiting(s);
                }
                _ => pop(s),
            }
        }
        (Kind::AllLayEggs { .. }, PowerPhase::Choices, EggMap(_, items)) => {
            lay_eggs_effect(s, cur, items);
            next_awaiting(s);
        }
        (Kind::DiscardToGain { discard_food, gain_card, gain_qty, draw }, PowerPhase::SelectDiscard, _) => {
            match (discard_food, a) {
                (None, Id(_, id)) => match s.players[cur].bird_mut(*id) {
                    Some(b) if b.eggs > 0 => b.eggs -= 1,
                    _ => return Err(format!("bird {id} has no egg to discard")),
                },
                (Some(_), Name(_, f)) => {
                    let f = food_from_str(f);
                    if s.players[cur].food_of(f) == 0 {
                        return Err(format!("no {} to discard", f.name()));
                    }
                    s.players[cur].pay_food(f, 1);
                }
                _ => return bad(),
            }
            if *gain_card {
                if *draw {
                    await_draw(s, *gain_qty);
                    return Ok(());
                }
                tuck_cards(s, c, e.bird_id, *gain_qty as usize)?;
                pop(s);
            } else {
                top(s).phase = Some(PowerPhase::SelectGain);
            }
        }
        (Kind::DiscardToGain { .. }, PowerPhase::SelectGain, FoodMap(_, items)) => {
            for &(f, n) in items {
                s.players[cur].gain_food(f, n);
            }
            pop(s);
        }
        (Kind::Draw { .. }, PowerPhase::SelectBonus, Id(_, id)) => {
            let options = e.context.bonus_options.clone().unwrap_or_default();
            if !options.contains(id) {
                return Err("Invalid bonus selection".into());
            }
            s.players[cur].bonus_hand.push(*id);
            s.discarded_bonuses.extend(options.into_iter().filter(|b| b != id));
            pop(s);
        }
        (Kind::DrawShare, PowerPhase::SelectCard, Id(_, id)) => {
            let t = top(s);
            let available = t.context.available_cards.as_mut().unwrap();
            if !available.contains(id) {
                return Err(format!("Card {id} not in available cards"));
            }
            remove_first(available, id);
            s.players[cur].bird_hand.push(*id);
            next_awaiting(s);
        }
        (Kind::AllGainDie, PowerPhase::ChooseStartingPlayer, Id(_, start)) => {
            let n = s.players.len();
            let start = *start as usize;
            if start >= n {
                return Err(format!("Invalid player index: {start}"));
            }
            let order: Vec<usize> = (0..n).map(|i| (start + i) % n).collect();
            s.current_player_index = order[0];
            let t = top(s);
            t.phase = Some(PowerPhase::SelectDie);
            t.context.awaiting_players = Some(order);
        }
        (Kind::AllGainDie | Kind::Fewest { .. } | Kind::PinkPredator | Kind::GainFood { .. }, PowerPhase::SelectDie, Simple("reroll_all")) => {
            reroll(s, c);
            if let (Kind::GainFood { .. }, Some(ft)) = (&power(e.bird_id).kind, e.context.food_type) {
                if matching_dice(s, ft).is_empty() {
                    pop(s);
                }
            }
        }
        (Kind::AllGainDie | Kind::Fewest { .. }, PowerPhase::SelectDie, SelectDie { die, food }) => {
            select_die(s, c, *die, *food, cur)?;
            next_awaiting(s);
        }
        (Kind::PinkPredator, PowerPhase::SelectDie, SelectDie { die, food }) => {
            select_die(s, c, *die, *food, e.player_index)?;
            pop(s);
        }
        (Kind::GainFood { qty, can_cache, .. }, PowerPhase::SelectFoodType, Name(_, f)) => {
            let food = food_from_str(f);
            top(s).context.food_type = Some(food);
            let dice = matching_dice(s, food);
            if *qty == Qty::All {
                for d in dice {
                    select_die(s, c, d, food, cur)?;
                }
                pop(s);
                return Ok(());
            }
            if *qty == Qty::N(1) && dice.len() == 1 && !can_cache {
                select_die(s, c, dice[0], food, cur)?;
                pop(s);
                return Ok(());
            }
            let t = top(s);
            t.phase = Some(PowerPhase::SelectDie);
            if let Qty::N(q) = qty {
                if *q > 1 {
                    t.context.remaining_quantity = Some(*q);
                }
            }
        }
        (Kind::GainFood { can_cache, .. }, PowerPhase::SelectDie, SelectDie { die, food }) => {
            select_die(s, c, *die, *food, cur)?;
            let t = top(s);
            if let Some(r) = t.context.remaining_quantity.as_mut() {
                *r -= 1;
                if *r > 0 {
                    return Ok(());
                }
            }
            if *can_cache {
                t.phase = Some(PowerPhase::ChooseCache);
            } else {
                pop(s);
            }
        }
        (Kind::GainFood { .. }, PowerPhase::ChooseCache, Simple(choice)) => {
            if *choice == "cache_food" {
                s.players[cur].pay_food(e.context.food_type.unwrap(), 1);
                spot_bird(s, &e).food += 1;
            }
            pop(s);
        }
        (Kind::MoveBird, PowerPhase::SelectHabitat, Name(_, h)) => {
            let row = habitat_row(h);
            let (r0, c0) = (e.spot_row as usize, e.spot_col as usize);
            let p = &mut s.players[e.player_index];
            let to = leftmost_empty(p, row).ok_or("Target spot not available")?;
            p.board[row][to] = p.board[r0][c0].take();
            pop(s);
        }
        (Kind::LayEggs { .. }, PowerPhase::SelectBird, Id(_, id)) => {
            lay_eggs_effect(s, cur, &[(*id, 1)]);
            pop(s);
        }
        (Kind::PinkLayEgg { .. }, PowerPhase::SelectBird, Id(_, id)) => {
            lay_eggs_effect(s, e.player_index, &[(*id, 1)]);
            pop(s);
        }
        (Kind::Repeat { .. }, PowerPhase::SelectBird, Id(_, id)) => {
            let &(bird, row, col) = e
                .context
                .eligible_birds
                .iter()
                .flatten()
                .find(|(b, _, _)| b == id)
                .ok_or(format!("Bird {id} not in eligible birds"))?;
            pop(s);
            s.action_data.execution_stack.push(Execution {
                power_id: power(bird).id,
                bird_id: bird,
                spot_row: row,
                spot_col: col,
                player_index: e.player_index,
                phase: None,
                context: Context::default(),
            });
        }
        (Kind::Trade, PowerPhase::SelectTrade, Trade { from, to }) => {
            s.players[cur].pay_food(*from, 1);
            s.players[cur].gain_food(*to, 1);
            pop(s);
        }
        (Kind::Tuck { bonus }, PowerPhase::SelectCard, Id(_, id)) => {
            let p = &mut s.players[cur];
            if !p.bird_hand.contains(id) {
                return Err(format!("Card {id} not in hand"));
            }
            remove_first(&mut p.bird_hand, id);
            spot_bird(s, &e).tucked += 1;
            match bonus {
                TuckBonus::Card => await_draw(s, 1),
                TuckBonus::Egg => {
                    lay_eggs_effect(s, cur, &[(e.bird_id, 1)]);
                    pop(s);
                }
                TuckBonus::Foods(foods) if foods.len() == 1 => {
                    s.players[cur].gain_food(foods[0], 1);
                    pop(s);
                }
                TuckBonus::Foods(_) => top(s).phase = Some(PowerPhase::SelectFood),
            }
        }
        (Kind::Tuck { .. }, PowerPhase::SelectFood, Name(_, f)) => {
            s.players[cur].gain_food(food_from_str(f), 1);
            pop(s);
        }
        (Kind::PinkPlayed { .. }, PowerPhase::SelectCard, Id(_, id)) => {
            let p = &mut s.players[e.player_index];
            if !p.bird_hand.contains(id) {
                return Err(format!("Card {id} not in hand"));
            }
            remove_first(&mut p.bird_hand, id);
            spot_bird(s, &e).tucked += 1;
            pop(s);
        }
        _ => return bad(),
    }
    Ok(())
}
