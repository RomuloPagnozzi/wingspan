pub mod actions;
pub mod chance;
pub mod data;
pub mod encode;
pub mod net;
pub mod powers;
pub mod replay;
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
    use pyo3::types::{PyBytes, PyDict};

    use crate::chance::{Event, Replay};
    use crate::rules;
    use crate::state::State;

    fn parse(state_json: &str) -> PyResult<State> {
        serde_json::from_str(state_json).map_err(|e| PyValueError::new_err(format!("bad state json: {e}")))
    }

    /// Legal actions of a state (canonical JSON from wingspan.ai.rust.to_json), as Python action strings.
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

    /// IS-MCTS for the player to move (search.rs). Returns (root child move strings, visits, value for
    /// the searcher, root value); children may include moves legal only in some re-dealt world.
    #[pyfunction]
    #[pyo3(signature = (state_json, simulations, exploration, value_function, widening_k, widening_alpha, seed, value_net=None, net_mix=1.0))]
    fn ismcts(
        state_json: &str,
        simulations: usize,
        exploration: f64,
        value_function: &str,
        widening_k: Option<f64>,
        widening_alpha: f64,
        seed: u64,
        value_net: Option<&str>,
        net_mix: f64,
    ) -> PyResult<(Vec<String>, Vec<u32>, Vec<f64>, Option<f64>)> {
        let s = parse(state_json)?;
        let vf = crate::search::ValueFunction::parse(value_function)
            .ok_or_else(|| PyValueError::new_err(format!("unknown value function {value_function}")))?;
        let value_net = value_net.map(crate::net::load);
        let cfg = crate::search::MctsConfig { simulations, exploration, value_function: vf, widening_k, widening_alpha, value_net, net_mix };
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

    /// Random playouts from a state for the player to move (search.rs `rollouts`): score differences in points.
    #[pyfunction]
    fn rollouts(state_json: &str, n: usize, seed: u64) -> PyResult<Vec<f64>> {
        Ok(crate::search::rollouts(&parse(state_json)?, n, seed))
    }

    /// The observation of `viewer` (wingspan.ai.encoding `encode_obs(state, viewer).flat()`).
    #[pyfunction]
    fn encode_obs(state_json: &str, viewer: usize) -> PyResult<Vec<f32>> {
        Ok(crate::encode::encode_obs(&parse(state_json)?, viewer))
    }

    /// The value net in `path` on an observation: (value, margin in points).
    #[pyfunction]
    fn value_net(path: &str, obs: Vec<f32>) -> (f32, f32) {
        crate::net::load(path).evaluate(&obs)
    }

    /// The legal moves of a state, encoded (wingspan.ai.encoding `encode_action`, `action_bird_ids`).
    #[pyfunction]
    fn encode_actions(state_json: &str) -> PyResult<Vec<(Vec<f32>, Vec<u16>)>> {
        let s = parse(state_json)?;
        let actions = rules::legal_actions(&s);
        Ok(actions.iter().map(|a| (crate::encode::encode_action(&s, a), crate::encode::action_bird_ids(a))).collect())
    }

    type Row = (i64, Vec<String>, String, usize, Vec<(String, i64)>, Vec<(String, f64)>);

    /// Replay a recorded game from its dealt state and the Python generator's state after the deal
    /// (`rng.getstate()[1]`), encoding every recorded decision (replay.rs). Rows: (decision_idx, legal
    /// moves, move taken, player index, visits, Q). Returns a dict of the arrays; obs and act as float32 bytes.
    #[pyfunction]
    fn replay_game<'py>(py: Python<'py>, state_json: &str, rng_state: Vec<u32>, rows: Vec<Row>) -> PyResult<Bound<'py, PyDict>> {
        let rows: Vec<_> = rows
            .into_iter()
            .map(|(idx, legal, taken, player, visits, q)| crate::replay::Recorded { idx, legal, taken, player, visits, q })
            .collect();
        let mut rng = crate::chance::PyRandom::from_state(&rng_state);
        let r = crate::replay::replay(parse(state_json)?, &mut rng, &rows).map_err(PyValueError::new_err)?;
        let bytes = |v: &[f32]| PyBytes::new(py, &v.iter().flat_map(|x| x.to_le_bytes()).collect::<Vec<u8>>());
        let d = PyDict::new(py);
        d.set_item("obs", bytes(&r.obs))?;
        d.set_item("act", bytes(&r.act))?;
        d.set_item("hand", r.hand)?;
        d.set_item("tray", r.tray)?;
        d.set_item("act_birds", r.act_birds)?;
        d.set_item("n_act", r.n_act)?;
        d.set_item("taken", r.taken)?;
        d.set_item("phase", r.phase)?;
        d.set_item("visits", r.visits)?;
        d.set_item("q", r.q)?;
        Ok(d)
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
        m.add_function(wrap_pyfunction!(redeterminize, m)?)?;
        m.add_function(wrap_pyfunction!(rollouts, m)?)?;
        m.add_function(wrap_pyfunction!(encode_obs, m)?)?;
        m.add_function(wrap_pyfunction!(encode_actions, m)?)?;
        m.add_function(wrap_pyfunction!(replay_game, m)?)?;
        m.add_function(wrap_pyfunction!(value_net, m)?)?;
        m.add_function(wrap_pyfunction!(ismcts, m)?)?;
        Ok(())
    }
}
