//! Replay a recorded game and encode its decisions, for `lab/dataset.py`: the work of its Python
//! `encode_game`, value for value. Chance comes from the Python game's own random generator (`PyRandom`),
//! so the replay reaches exactly the states the game was played in; a replay that disagrees with the
//! recording (other legal moves, another player to move) is an error.

use crate::chance::Chance;
use crate::encode::{action_bird_ids, encode_action, encode_obs, phase_index};
use crate::rules::{apply, legal_actions};
use crate::state::State;

/// One recorded decision (a row of decisions.parquet).
pub struct Recorded {
    pub idx: i64,
    pub legal: Vec<String>,
    pub taken: String,
    pub player: usize, // 0-based
    pub visits: Vec<(String, i64)>,
    pub q: Vec<(String, f64)>,
}

/// Per decision, then per legal move in the engine's order (a decision's moves are the next `n_act[i]`).
#[derive(Default)]
pub struct Replayed {
    pub obs: Vec<f32>,
    pub hand: Vec<Vec<u16>>,
    pub tray: Vec<Vec<u16>>,
    pub n_act: Vec<u32>,
    pub taken: Vec<u32>,
    pub phase: Vec<u8>,
    pub act: Vec<f32>,
    pub act_birds: Vec<Vec<u16>>,
    pub visits: Vec<i32>,
    pub q: Vec<f32>,
}

pub fn replay(mut s: State, c: &mut impl Chance, rows: &[Recorded]) -> Result<Replayed, String> {
    let mut out = Replayed::default();
    for row in rows {
        let mut actions = legal_actions(&s);
        while actions.len() == 1 {
            // forced steps are not recorded
            apply(&mut s, &actions[0], c)?;
            actions = legal_actions(&s);
        }
        let names: Vec<String> = actions.iter().map(|a| a.to_string()).collect();
        let (mut a, mut b) = (names.clone(), row.legal.clone());
        a.sort();
        b.sort();
        if a != b {
            return Err(format!("replay diverged at decision {}", row.idx));
        }
        let me = s.current_player_index;
        if me != row.player {
            return Err(format!("wrong player at decision {}", row.idx));
        }

        out.obs.extend(encode_obs(&s, me));
        let sorted = |v: &[u16]| {
            let mut v = v.to_vec();
            v.sort_unstable();
            v
        };
        out.hand.push(sorted(&s.players[me].bird_hand));
        out.tray.push(sorted(&s.bird_tray));
        for (action, name) in actions.iter().zip(&names) {
            out.act.extend(encode_action(&s, action));
            out.act_birds.push(action_bird_ids(action));
            out.visits.push(row.visits.iter().find(|(k, _)| k == name).map_or(0, |&(_, v)| v as i32));
            out.q.push(row.q.iter().find(|(k, _)| k == name).map_or(f32::NAN, |&(_, v)| v as f32));
        }
        let taken = names.iter().position(|n| *n == row.taken).ok_or(format!("unknown move at decision {}", row.idx))?;
        out.n_act.push(actions.len() as u32);
        out.taken.push(taken as u32);
        out.phase.push(phase_index(&s) as u8);
        apply(&mut s, &actions[taken], c)?;
    }
    Ok(out)
}
