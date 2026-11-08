//! cargo run --release --bin bench [random|flatmc] [n]
//!   random: n random games from fresh deals (default 2000)
//!   flatmc: flat MC (budget 300, paired) on n fixed mid-game states (default 150), the self-play workload
use std::time::Instant;

use wingspan_rs::chance::Rng;
use wingspan_rs::rules::{apply, initiate, legal_actions};
use wingspan_rs::search::{flat_mc, ismcts, MctsConfig, ValueFunction};
use wingspan_rs::state::{ScoringMode, State};

fn states(n: usize) -> Vec<State> {
    let mut rng = Rng::new(12345);
    let mut out = vec![];
    while out.len() < n {
        let mut s = initiate(2, ScoringMode::Green, &mut rng);
        loop {
            let actions = legal_actions(&s);
            if actions.is_empty() {
                break;
            }
            if actions.len() > 1 && rng.below(25) == 0 && out.len() < n {
                out.push(s.clone());
            }
            let a = &actions[rng.below(actions.len())];
            apply(&mut s, a, &mut rng).unwrap();
        }
    }
    out
}

fn main() {
    let mode = std::env::args().nth(1).unwrap_or("random".into());
    let n: Option<usize> = std::env::args().nth(2).map(|a| a.parse().unwrap());
    match mode.as_str() {
        "random" => {
            let n = n.unwrap_or(2000);
            wingspan_rs::bench(10, 0); // warm up (loads the card data)
            let (steps, secs) = wingspan_rs::bench(n, 1);
            println!(
                "{n} games, {steps} decisions in {secs:.3}s: {:.0} games/s, {:.3} us/decision",
                n as f64 / secs,
                secs * 1e6 / steps as f64
            );
        }
        "flatmc" => {
            let states = states(n.unwrap_or(150));
            let t = Instant::now();
            let mut checksum = 0.0;
            for (i, s) in states.iter().enumerate() {
                let (_, totals, _) = flat_mc(s, 300, true, ValueFunction::AbsoluteScore, i as u64);
                checksum += totals.iter().sum::<f64>();
            }
            let secs = t.elapsed().as_secs_f64();
            println!(
                "flat MC on {} states: {secs:.3}s, {:.2} ms/decision (checksum {checksum:.4})",
                states.len(),
                secs * 1e3 / states.len() as f64
            );
        }
        "ismcts" => {
            // the tuned tree (TUNED_TREE in src/wingspan/ai/rust.py) at 1000 simulations
            let states = states(n.unwrap_or(60));
            let cfg = MctsConfig {
                simulations: 1000,
                exploration: 1.1354669047764545,
                value_function: ValueFunction::ScoreDelta,
                widening_k: Some(1.412915005594185),
                widening_alpha: 0.6303665309124046,
            };
            let t = Instant::now();
            let mut visits = 0u64;
            for (i, s) in states.iter().enumerate() {
                visits += ismcts(s, &cfg, i as u64).visits.iter().map(|&v| v as u64).sum::<u64>();
            }
            let secs = t.elapsed().as_secs_f64();
            println!("IS-MCTS 1000 sims on {} states: {:.2} ms/decision, {:.1} us/simulation (root visits {visits})",
                states.len(), secs * 1e3 / states.len() as f64, secs * 1e6 / (1000.0 * states.len() as f64));
        }
        "phases" => {
            // legal_actions cost by phase, over the states random games pass through
            let mut rng = Rng::new(3);
            let mut by_phase: std::collections::BTreeMap<String, Vec<State>> = Default::default();
            for _ in 0..300 {
                let mut s = initiate(2, ScoringMode::Green, &mut rng);
                loop {
                    let actions = legal_actions(&s);
                    if actions.is_empty() {
                        break;
                    }
                    by_phase.entry(format!("{:?}", s.game_phase)).or_default().push(s.clone());
                    let a = &actions[rng.below(actions.len())];
                    apply(&mut s, a, &mut rng).unwrap();
                }
            }
            let total_states: usize = by_phase.values().map(|v| v.len()).sum();
            let mut buf = vec![];
            let mut rows = vec![];
            for (phase, states) in &by_phase {
                let t = Instant::now();
                for _ in 0..20 {
                    for s in states {
                        wingspan_rs::rules::legal_actions_into(s, &mut buf);
                    }
                }
                let ns = t.elapsed().as_nanos() as f64 / (20 * states.len()) as f64;
                rows.push((ns * states.len() as f64, phase.clone(), states.len(), ns));
            }
            let all: f64 = rows.iter().map(|r| r.0).sum();
            rows.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap());
            for (w, phase, n, ns) in rows {
                println!("{phase:<22} {:5.1}% of states  {ns:7.1} ns/call  {:5.1}% of legal_actions time", 100.0 * n as f64 / total_states as f64, 100.0 * w / all);
            }
        }
        _ => panic!("mode: random | flatmc | ismcts | phases"),
    }
}
