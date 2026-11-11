//! Search: re-dealing hidden information (core/redeterminize.py) and IS-MCTS (ai/mcts.py, determinize=True).

use crate::actions::Action;
use crate::chance::{Chance, Rng};
use crate::data::data;
use crate::rules::{apply, legal_actions_into, total_score, update_player_scores};
use crate::encode::encode_obs;
use crate::net::{PolicyNet, ValueNet};
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

// =============================================================================
// IS-MCTS (ai/mcts.py, determinize=True): one tree over the player's information set; every
// simulation re-deals the hidden cards, walks the tree with the moves legal in that world, adds one
// node and finishes with a random rollout. Values are per player: each node is judged by whoever
// moves at its parent.
// =============================================================================

#[derive(Clone, Copy)]
pub struct MctsConfig {
    pub simulations: usize,
    pub exploration: f64,
    pub value_function: ValueFunction,
    pub widening_k: Option<f64>,
    pub widening_alpha: f64,
    /// Judge new leaves with this value net instead of (or mixed with) a random rollout: `net_mix` of the
    /// net's margin plus `1 - net_mix` of the rollout, both in score_delta units.
    pub value_net: Option<&'static ValueNet>,
    pub net_mix: f64,
    /// PUCT (AlphaZero's selection) with this policy net's priors instead of UCT with progressive widening:
    /// every legal move scores Q + exploration * P * sqrt(N) / (1 + n). A node gets its priors once it has
    /// `prior_min_visits` visits (uniform until then): the net costs several rollouts, and most nodes are
    /// visited once.
    pub policy: Option<&'static PolicyNet>,
    pub prior_min_visits: u32,
    /// Self-play exploration (AlphaZero): the root's priors are mixed with this share of Dirichlet noise,
    /// concentration 10 / legal moves, so moves the policy dislikes still get tried. 0 when playing.
    pub root_noise: f64,
}

struct Node {
    parent: usize, // usize::MAX at the root
    children: Vec<(Action, usize)>, // insertion order, as Python's dict
    visits: u32,
    availability: u32,
    total: [f64; 5], // per player
    priors: Vec<(Action, f32)>, // PUCT: the legal moves' priors, from the world they were computed in
}

const MAX_PLAYERS: usize = 5;

/// `_compute_values`: every player's value of a finished game.
fn values_all(s: &mut State, vf: ValueFunction) -> [f64; MAX_PLAYERS] {
    let mut out = [0.0; MAX_PLAYERS];
    for (i, v) in out.iter_mut().enumerate().take(s.players.len()) {
        *v = value(s, i, vf);
    }
    out
}

fn rollout(s: &mut State, vf: ValueFunction, rng: &mut Rng, buf: &mut Vec<Action>) -> [f64; MAX_PLAYERS] {
    loop {
        legal_actions_into(s, buf);
        if buf.is_empty() {
            return values_all(s, vf);
        }
        let a = buf[rng.below(buf.len())].clone();
        apply(s, &a, rng).expect("legal action failed in a rollout");
    }
}

/// `n` random playouts for the player to move, each from a fresh re-deal of what they can't see (as every
/// simulation of the search does): their final score minus the best opponent's, in points.
pub fn rollouts(s: &State, n: usize, seed: u64) -> Vec<f64> {
    let me = s.current_player_index;
    let (mut rng, mut buf) = (Rng::new(seed), Vec::new());
    (0..n)
        .map(|_| 50.0 * rollout(&mut redeterminize(s, me, &mut rng), ValueFunction::ScoreDelta, &mut rng, &mut buf)[me])
        .collect()
}

/// The value of a new leaf for every player: a random rollout, or the value net's estimate of the final
/// margin for the player to move (after any forced steps, as the net only saw decisions), or a mix.
fn leaf_value(s: &mut State, cfg: &MctsConfig, rng: &mut Rng, buf: &mut Vec<Action>) -> [f64; MAX_PLAYERS] {
    let Some(net) = cfg.value_net else {
        return rollout(s, cfg.value_function, rng, buf);
    };
    loop {
        legal_actions_into(s, buf);
        if buf.len() != 1 {
            break;
        }
        let a = buf[0].clone();
        apply(s, &a, rng).expect("legal action failed at a leaf");
    }
    if buf.is_empty() {
        return values_all(s, cfg.value_function);
    }
    let me = s.current_player_index;
    let margin = net.evaluate(&encode_obs(s, me)).1 as f64 / 50.0; // score_delta units
    let mut v = [0.0; MAX_PLAYERS];
    for (i, x) in v.iter_mut().enumerate().take(s.players.len()) {
        *x = if i == me { margin } else { -margin };
    }
    if cfg.net_mix < 1.0 {
        let r = rollout(s, cfg.value_function, rng, buf);
        for (x, r) in v.iter_mut().zip(r) {
            *x = cfg.net_mix * *x + (1.0 - cfg.net_mix) * r;
        }
    }
    v
}

fn backpropagate(nodes: &mut [Node], mut i: usize, v: &[f64; MAX_PLAYERS]) {
    while i != usize::MAX {
        let n = &mut nodes[i];
        n.visits += 1;
        for (t, x) in n.total.iter_mut().zip(v) {
            *t += x;
        }
        i = n.parent;
    }
}

/// `_can_expand` (progressive widening: at most k * visits^alpha children).
fn can_expand(node: &Node, untried: usize, cfg: &MctsConfig) -> bool {
    if untried == 0 {
        return false;
    }
    match cfg.widening_k {
        None => true,
        Some(k) => node.children.len() < ((k * (node.visits as f64).powf(cfg.widening_alpha)).floor() as usize).max(1),
    }
}

/// A uniform draw in (0, 1).
fn unit(rng: &mut Rng) -> f64 {
    ((rng.next_u64() >> 11) as f64 + 0.5) / (1u64 << 53) as f64
}

/// A Gamma(alpha, 1) draw (Marsaglia and Tsang; alpha < 1 through Gamma(alpha + 1) * U^(1 / alpha)).
fn gamma(alpha: f64, rng: &mut Rng) -> f64 {
    if alpha < 1.0 {
        return gamma(alpha + 1.0, rng) * unit(rng).powf(1.0 / alpha);
    }
    let d = alpha - 1.0 / 3.0;
    let c = 1.0 / (9.0 * d).sqrt();
    loop {
        let x = (-2.0 * unit(rng).ln()).sqrt() * (std::f64::consts::TAU * unit(rng)).cos(); // standard normal
        let v = (1.0 + c * x).powi(3);
        if v > 0.0 && unit(rng).ln() < 0.5 * x * x + d - d * v + d * v.ln() {
            return d * v;
        }
    }
}

/// PUCT: the legal move to follow from `node` (index into `legal`), computing its priors when due.
fn puct(nodes: &mut [Node], node: usize, s: &State, legal: &[Action], cfg: &MctsConfig, rng: &mut Rng) -> usize {
    let n = &nodes[node];
    let player = s.current_player_index;
    if let Some(policy) = cfg.policy {
        // Once per node, in the world it is due in; moves legal only in other worlds get the uniform share
        if n.visits >= cfg.prior_min_visits && n.priors.is_empty() {
            let mut p = policy.priors(s, legal);
            if node == 0 && cfg.root_noise > 0.0 {
                let noise: Vec<f64> = legal.iter().map(|_| gamma(10.0 / legal.len() as f64, rng)).collect();
                let total: f64 = noise.iter().sum();
                for (x, e) in p.iter_mut().zip(noise) {
                    *x = ((1.0 - cfg.root_noise) * *x as f64 + cfg.root_noise * e / total) as f32;
                }
            }
            nodes[node].priors = legal.iter().cloned().zip(p).collect();
        }
    }
    let n = &nodes[node];
    let parent_q = if n.visits > 0 { n.total[player] / n.visits as f64 } else { 0.0 };
    let sqrt_n = (n.visits.max(1) as f64).sqrt();
    let uniform = 1.0 / legal.len() as f32;
    let (mut best, mut best_score) = (0, f64::NEG_INFINITY);
    for (i, a) in legal.iter().enumerate() {
        let prior = n.priors.iter().find(|(b, _)| b == a).map_or(uniform, |&(_, p)| p) as f64;
        let (q, visits) = match n.children.iter().find(|(b, _)| b == a) {
            Some(&(_, c)) if nodes[c].visits > 0 => (nodes[c].total[player] / nodes[c].visits as f64, nodes[c].visits),
            _ => (parent_q, 0),
        };
        let score = q + cfg.exploration * prior * sqrt_n / (1 + visits) as f64;
        if score > best_score {
            (best, best_score) = (i, score);
        }
    }
    best
}

fn ucb(n: &Node, c: f64, player: usize) -> f64 {
    if n.visits == 0 || n.availability == 0 {
        return f64::INFINITY;
    }
    n.total[player] / n.visits as f64 + c * ((n.availability as f64).ln() / n.visits as f64).sqrt()
}

/// Root statistics after the search: (root child moves, their visits, their value for the searcher),
/// plus the root value. Children may include moves legal only in some re-dealt world.
pub struct MctsResult {
    pub actions: Vec<Action>,
    pub visits: Vec<u32>,
    pub values: Vec<f64>,
    pub root_value: Option<f64>,
}

pub fn ismcts(root_state: &State, cfg: &MctsConfig, seed: u64) -> MctsResult {
    if cfg.value_net.is_some() {
        // The net's margin is "me minus the opponent", which is score_delta for two players only
        assert!(root_state.players.len() == 2 && matches!(cfg.value_function, ValueFunction::ScoreDelta));
    }
    let mut rng = Rng::new(seed);
    let me = root_state.current_player_index;
    let vf = cfg.value_function;
    let new_node = |parent| Node { parent, children: vec![], visits: 0, availability: 0, total: [0.0; 5], priors: vec![] };
    let mut nodes = vec![new_node(usize::MAX)];
    let (mut legal, mut buf) = (Vec::with_capacity(96), Vec::with_capacity(96));
    let mut untried: Vec<usize> = vec![];
    let mut compatible: Vec<usize> = vec![]; // indices into the node's children
    for _ in 0..cfg.simulations {
        let mut s = redeterminize(root_state, me, &mut rng);
        let mut node = 0;
        loop {
            legal_actions_into(&s, &mut legal);
            if legal.is_empty() {
                let v = values_all(&mut s, vf);
                backpropagate(&mut nodes, node, &v);
                break;
            }
            if cfg.policy.is_some() {
                let i = puct(&mut nodes, node, &s, &legal, cfg, &mut rng);
                let a = legal[i].clone();
                apply(&mut s, &a, &mut rng).expect("legal action failed in the tree");
                if let Some(&(_, c)) = nodes[node].children.iter().find(|(b, _)| *b == a) {
                    node = c;
                    continue;
                }
                let child = nodes.len();
                nodes.push(new_node(node));
                nodes[node].children.push((a, child));
                let v = leaf_value(&mut s, cfg, &mut rng, &mut buf);
                backpropagate(&mut nodes, child, &v);
                break;
            }
            let children = &nodes[node].children;
            untried.clear();
            compatible.clear();
            for (i, a) in legal.iter().enumerate() {
                if !children.iter().any(|(b, _)| b == a) {
                    untried.push(i);
                }
            }
            for (ci, (b, _)) in children.iter().enumerate() {
                if legal.contains(b) {
                    compatible.push(ci);
                }
            }
            if !untried.is_empty() && (compatible.is_empty() || can_expand(&nodes[node], untried.len(), cfg)) {
                let a = legal[untried[rng.below(untried.len())]].clone();
                apply(&mut s, &a, &mut rng).expect("legal action failed in the tree");
                let child = nodes.len();
                nodes.push(new_node(node));
                nodes[node].children.push((a, child));
                let v = leaf_value(&mut s, cfg, &mut rng, &mut buf);
                backpropagate(&mut nodes, child, &v);
                break;
            }
            // Every legal move has a child: count availability for each, then UCB from the mover's view
            let player = s.current_player_index;
            let (mut best, mut best_ucb) = (usize::MAX, f64::NEG_INFINITY);
            for &ci in &compatible {
                let c = nodes[node].children[ci].1;
                nodes[c].availability += 1;
                let u = ucb(&nodes[c], cfg.exploration, player);
                if u > best_ucb {
                    (best, best_ucb) = (ci, u);
                }
            }
            let (a, c) = nodes[node].children[best].clone();
            apply(&mut s, &a, &mut rng).expect("legal action failed in the tree");
            node = c;
        }
    }
    let root = &nodes[0];
    let mut out = MctsResult {
        actions: vec![],
        visits: vec![],
        values: vec![],
        root_value: (root.visits > 0).then(|| root.total[me] / root.visits as f64),
    };
    for (a, c) in &root.children {
        let n = &nodes[*c];
        out.actions.push(a.clone());
        out.visits.push(n.visits);
        out.values.push(if n.visits > 0 { n.total[me] / n.visits as f64 } else { f64::NAN });
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::rules::{initiate, legal_actions};
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
    fn gamma_has_mean_and_variance_alpha() {
        let mut rng = Rng::new(3);
        for alpha in [0.15, 1.0, 3.3] {
            let x: Vec<f64> = (0..200_000).map(|_| gamma(alpha, &mut rng)).collect();
            let mean = x.iter().sum::<f64>() / x.len() as f64;
            let var = x.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / x.len() as f64;
            assert!((mean - alpha).abs() < 0.02 * alpha.max(1.0), "alpha {alpha}: mean {mean}");
            assert!((var - alpha).abs() < 0.05 * alpha.max(1.0), "alpha {alpha}: variance {var}");
        }
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
}
