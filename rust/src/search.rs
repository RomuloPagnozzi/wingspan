//! Search: re-dealing hidden information (core/redeterminize.py) and flat Monte Carlo (ai/flat_mc.py).

use std::panic::{catch_unwind, AssertUnwindSafe};

use crate::actions::Action;
use crate::chance::{Chance, Rng};
use crate::data::data;
use crate::rules::{apply, legal_actions, total_score, update_player_scores};
use crate::state::State;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ValueFunction {
    AbsoluteScore,
    ScoreDelta,
    WinLoss,
}

impl ValueFunction {
    pub fn parse(s: &str) -> Option<ValueFunction> {
        match s {
            "absolute_score" => Some(ValueFunction::AbsoluteScore),
            "score_delta" => Some(ValueFunction::ScoreDelta),
            "win_loss" => Some(ValueFunction::WinLoss),
            _ => None,
        }
    }
}

/// `_compute_value` (mcts.py) of a finished (or cut-off) game, after refreshing the scores.
pub fn value(s: &mut State, me: usize, vf: ValueFunction) -> f64 {
    for p in &mut s.players {
        update_player_scores(p);
    }
    let mine = total_score(&s.players[me]);
    let others = || s.players.iter().enumerate().filter(move |&(i, _)| i != me).map(|(_, p)| p);
    let best_other = others().map(total_score).max().unwrap_or(0);
    match vf {
        ValueFunction::AbsoluteScore => mine as f64 / 100.0,
        ValueFunction::ScoreDelta => (mine - best_other) as f64 / 50.0,
        ValueFunction::WinLoss => {
            if mine != best_other {
                return if mine > best_other { 1.0 } else { 0.0 };
            }
            let food = |p: &crate::state::Player| p.food.iter().map(|&(_, n)| n as i32).sum::<i32>();
            let my_food = food(&s.players[me]);
            let best_food = others().map(food).max().unwrap_or(0);
            if my_food > best_food {
                1.0
            } else if my_food < best_food {
                0.0
            } else {
                0.5
            }
        }
    }
}

/// Deal the cards `me` can't see (deck orders, opponents' hands) again, uniformly from the cards that are
/// not public and not known to `me`. Same procedure as Python's `redeterminize`.
pub fn redeterminize(s: &State, me: usize, rng: &mut Rng) -> State {
    let mut w = s.clone();
    let d = data();
    let ctx_ids = |f: fn(&crate::state::Context) -> &Option<Vec<u16>>| -> Vec<u16> {
        s.action_data.execution_stack.iter().filter_map(|e| f(&e.context).clone()).flatten().collect()
    };

    // Birds
    let mut seen = vec![false; d.birds.len()];
    let placed = s.players.iter().flat_map(|p| p.birds().map(|b| b.id));
    for id in s.bird_tray.iter().chain(&s.discarded_birds).copied().chain(placed) {
        seen[id as usize] = true;
    }
    for id in s.players[me].bird_hand.iter().copied().chain(ctx_ids(|c| &c.available_cards)) {
        seen[id as usize] = true;
    }
    let mut unknown: Vec<u16> = d.bird_ids.iter().copied().filter(|&id| !seen[id as usize]).collect();
    rng.shuffle(&mut unknown);
    let mut cursor = unknown.into_iter();
    w.bird_deck = cursor.by_ref().take(s.bird_deck.len()).collect();
    for (i, p) in w.players.iter_mut().enumerate() {
        if i != me {
            let n = p.bird_hand.len();
            p.bird_hand = cursor.by_ref().take(n).collect();
            assert_eq!(p.bird_hand.len(), n, "Bird card conservation broken: unknown pool too small");
        }
    }
    assert_eq!(w.bird_deck.len(), s.bird_deck.len(), "Bird card conservation broken: unknown pool too small");

    // Bonus cards
    let mut seen = vec![false; d.bonuses.len()];
    for id in s.discarded_bonuses.iter().chain(&s.players[me].bonus_hand).copied().chain(ctx_ids(|c| &c.bonus_options)) {
        seen[id as usize] = true;
    }
    let mut unknown: Vec<u16> = d.bonus_ids.iter().copied().filter(|&id| !seen[id as usize]).collect();
    rng.shuffle(&mut unknown);
    let mut cursor = unknown.into_iter();
    w.bonus_deck = cursor.by_ref().take(s.bonus_deck.len()).collect();
    for (i, p) in w.players.iter_mut().enumerate() {
        if i != me {
            let n = p.bonus_hand.len();
            p.bonus_hand = cursor.by_ref().take(n).collect();
            assert_eq!(p.bonus_hand.len(), n, "Bonus card conservation broken: unknown pool too small");
        }
    }
    w
}

/// Play `a` in `world`, then random moves to the end; `me`'s value, or None if `a` is illegal there.
/// `chance` draws the dice and shuffles, `choices` picks the random moves.
fn playout(world: &State, a: &Action, me: usize, vf: ValueFunction, chance: &mut Rng, choices: &mut Rng) -> Option<f64> {
    let mut s = world.clone();
    // A move legal in the real state may not be in a re-dealt world (Python catches the exception)
    let ok = catch_unwind(AssertUnwindSafe(|| apply(&mut s, a, chance).is_ok())).unwrap_or(false);
    if !ok {
        return None;
    }
    loop {
        let actions = legal_actions(&s);
        if actions.is_empty() {
            return Some(value(&mut s, me, vf));
        }
        let a = &actions[choices.below(actions.len())];
        apply(&mut s, a, chance).expect("legal action failed in a rollout");
    }
}

/// Flat Monte Carlo for the player to move: `budget` playouts split evenly over the legal moves. With
/// `paired`, each re-dealt world and random seed is shared by every move (common random numbers).
/// Returns (legal action strings, total value per move, playouts that counted per move).
pub fn flat_mc(s: &State, budget: usize, paired: bool, vf: ValueFunction, seed: u64) -> (Vec<Action>, Vec<f64>, Vec<u32>) {
    let mut rng = Rng::new(seed);
    let me = s.current_player_index;
    let legal = legal_actions(s);
    let n = legal.len();
    let (mut totals, mut counts) = (vec![0.0; n], vec![0u32; n]);
    let mut world = s.clone();
    let mut world_seeds = (0, 0);
    for _ in 0..(budget / n.max(1)).max(1) {
        if paired {
            world = redeterminize(s, me, &mut rng);
            world_seeds = (rng.next_u64(), rng.next_u64());
        }
        for (i, a) in legal.iter().enumerate() {
            if !paired {
                world = redeterminize(s, me, &mut rng);
                world_seeds = (rng.next_u64(), rng.next_u64());
            }
            let (mut chance, mut choices) = (Rng::new(world_seeds.0), Rng::new(world_seeds.1));
            if let Some(v) = playout(&world, a, me, vf, &mut chance, &mut choices) {
                totals[i] += v;
                counts[i] += 1;
            }
        }
    }
    (legal, totals, counts)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::rules::initiate;
    use crate::state::ScoringMode;

    /// Random states from random games: (state, game seed, step).
    fn random_states(n_games: u64) -> Vec<State> {
        let mut out = vec![];
        for g in 0..n_games {
            let mut rng = Rng::new(g);
            let mut s = initiate(2, ScoringMode::Green, &mut rng);
            loop {
                let actions = legal_actions(&s);
                if actions.is_empty() {
                    break;
                }
                if actions.len() > 1 && rng.below(10) == 0 {
                    out.push(s.clone());
                }
                let a = &actions[rng.below(actions.len())];
                apply(&mut s, a, &mut rng).unwrap();
            }
        }
        out
    }

    #[test]
    fn redeterminize_keeps_what_the_player_sees() {
        let mut rng = Rng::new(7);
        for s in random_states(30) {
            let me = s.current_player_index;
            let w = redeterminize(&s, me, &mut rng);
            assert_eq!(w.players[me], s.players[me]);
            assert_eq!((&w.bird_tray, &w.discarded_birds, &w.feeder), (&s.bird_tray, &s.discarded_birds, &s.feeder));
            assert_eq!(w.bird_deck.len(), s.bird_deck.len());
            assert_eq!(w.bonus_deck.len(), s.bonus_deck.len());
            for (a, b) in w.players.iter().zip(&s.players) {
                assert_eq!((a.bird_hand.len(), a.bonus_hand.len(), a.board), (b.bird_hand.len(), b.bonus_hand.len(), b.board));
            }
            // No card twice among deck, hands, tray, discards and boards
            let mut ids: Vec<u16> = w.bird_deck.iter().chain(&w.bird_tray).chain(&w.discarded_birds).copied().collect();
            for p in &w.players {
                ids.extend(&p.bird_hand);
                ids.extend(p.birds().map(|b| b.id));
            }
            let n = ids.len();
            ids.sort_unstable();
            ids.dedup();
            assert_eq!(ids.len(), n);
        }
    }

    #[test]
    fn flat_mc_counts_every_move() {
        for s in random_states(3).into_iter().take(40) {
            let (legal, totals, counts) = flat_mc(&s, 200, true, ValueFunction::AbsoluteScore, 1);
            assert_eq!(legal.len(), totals.len());
            assert!(counts.iter().all(|&c| c as usize <= (200 / legal.len()).max(1)));
            assert!(counts.iter().any(|&c| c > 0));
        }
    }
}
