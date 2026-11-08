pub mod actions;
pub mod chance;
pub mod data;
pub mod powers;
pub mod rules;
pub mod search;
pub mod state;

use std::time::Instant;

/// Play `n_games` random games; returns (total decisions, seconds).
pub fn bench(n_games: usize, seed: u64) -> (usize, f64) {
    let mut rng = chance::Rng::new(seed);
    let t = Instant::now();
    let steps = (0..n_games).map(|_| rules::play_random_game(&mut rng)).sum();
    (steps, t.elapsed().as_secs_f64())
}

#[cfg(feature = "python")]
mod python {
    use std::collections::VecDeque;

    use pyo3::exceptions::PyValueError;
    use pyo3::prelude::*;

    use crate::chance::{Event, Replay};
    use crate::rules;
    use crate::state::State;

    fn parse(state_json: &str) -> PyResult<State> {
        serde_json::from_str(state_json).map_err(|e| PyValueError::new_err(format!("bad state json: {e}")))
    }

    /// Legal actions of a state (canonical JSON from py/pystate.py), as Python action strings.
    #[pyfunction]
    fn legal_actions(state_json: &str) -> PyResult<Vec<String>> {
        Ok(rules::legal_actions(&parse(state_json)?).iter().map(|a| a.to_string()).collect())
    }

    /// Apply legal action number `index`, replaying the recorded chance `events`
    /// (("die", [face]) or ("shuffle", deck_after)). Returns (new state json, unused events).
    #[pyfunction]
    fn apply(state_json: &str, index: usize, events: Vec<(String, Vec<u16>)>) -> PyResult<(String, usize)> {
        let mut s = parse(state_json)?;
        let actions = rules::legal_actions(&s);
        let a = actions.get(index).ok_or_else(|| PyValueError::new_err("action index out of range"))?;
        let mut replay = Replay(
            events
                .into_iter()
                .map(|(kind, v)| match kind.as_str() {
                    "die" => Event::Die(v[0] as u8),
                    _ => Event::Shuffle(v),
                })
                .collect::<VecDeque<_>>(),
        );
        rules::apply(&mut s, a, &mut replay).map_err(PyValueError::new_err)?;
        Ok((serde_json::to_string(&s).unwrap(), replay.0.len()))
    }

    /// Flat Monte Carlo for the player to move (see search.rs). Returns (legal action strings, total value
    /// per move, counted playouts per move), moves in the engine's legal order.
    #[pyfunction]
    fn flat_mc(
        state_json: &str,
        budget: usize,
        paired: bool,
        value_function: &str,
        seed: u64,
    ) -> PyResult<(Vec<String>, Vec<f64>, Vec<u32>)> {
        let s = parse(state_json)?;
        let vf = crate::search::ValueFunction::parse(value_function)
            .ok_or_else(|| PyValueError::new_err(format!("unknown value function {value_function}")))?;
        let (legal, totals, counts) = crate::search::flat_mc(&s, budget, paired, vf, seed);
        Ok((legal.iter().map(|a| a.to_string()).collect(), totals, counts))
    }

    /// IS-MCTS for the player to move (search.rs). Returns (root child move strings, visits, value for
    /// the searcher, root value); children may include moves legal only in some re-dealt world.
    #[pyfunction]
    #[pyo3(signature = (state_json, simulations, exploration, value_function, widening_k, widening_alpha, seed))]
    fn ismcts(
        state_json: &str,
        simulations: usize,
        exploration: f64,
        value_function: &str,
        widening_k: Option<f64>,
        widening_alpha: f64,
        seed: u64,
    ) -> PyResult<(Vec<String>, Vec<u32>, Vec<f64>, Option<f64>)> {
        let s = parse(state_json)?;
        let vf = crate::search::ValueFunction::parse(value_function)
            .ok_or_else(|| PyValueError::new_err(format!("unknown value function {value_function}")))?;
        let cfg = crate::search::MctsConfig { simulations, exploration, value_function: vf, widening_k, widening_alpha };
        let r = crate::search::ismcts(&s, &cfg, seed);
        Ok((r.actions.iter().map(|a| a.to_string()).collect(), r.visits, r.values, r.root_value))
    }

    /// Re-deal the cards `me` can't see; returns the new state json.
    #[pyfunction]
    fn redeterminize(state_json: &str, me: usize, seed: u64) -> PyResult<String> {
        let s = parse(state_json)?;
        let w = crate::search::redeterminize(&s, me, &mut crate::chance::Rng::new(seed));
        Ok(serde_json::to_string(&w).unwrap())
    }

    /// Random games from fresh deals, timed inside Rust: (total decisions, seconds).
    #[pyfunction]
    fn bench_games(n_games: usize, seed: u64) -> (usize, f64) {
        crate::bench(n_games, seed)
    }

    #[pymodule]
    fn wingspan_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add_function(wrap_pyfunction!(legal_actions, m)?)?;
        m.add_function(wrap_pyfunction!(apply, m)?)?;
        m.add_function(wrap_pyfunction!(bench_games, m)?)?;
        m.add_function(wrap_pyfunction!(flat_mc, m)?)?;
        m.add_function(wrap_pyfunction!(redeterminize, m)?)?;
        m.add_function(wrap_pyfunction!(ismcts, m)?)?;
        Ok(())
    }
}
