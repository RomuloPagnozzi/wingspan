//! Every random event in the rules goes through `Chance`. Real runs use `Rng`; parity tests use `Replay`,
//! which plays back the outcomes the Python engine actually drew (die faces, shuffled decks), so the two
//! engines can be compared without sharing a random number generator.

use std::collections::VecDeque;

pub trait Chance {
    /// Index into `state::FACES`.
    fn roll_die(&mut self) -> u8;
    fn shuffle(&mut self, v: &mut Vec<u16>);
}

/// xoshiro256**: small, fast, good enough for games.
#[derive(Clone)]
pub struct Rng([u64; 4]);

impl Rng {
    pub fn new(seed: u64) -> Rng {
        let mut z = seed;
        let mut next = || {
            // splitmix64, to spread the seed over the state
            z = z.wrapping_add(0x9E3779B97F4A7C15);
            let mut x = z;
            x = (x ^ (x >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
            x = (x ^ (x >> 27)).wrapping_mul(0x94D049BB133111EB);
            x ^ (x >> 31)
        };
        Rng([next(), next(), next(), next()])
    }

    pub fn next_u64(&mut self) -> u64 {
        let s = &mut self.0;
        let result = s[1].wrapping_mul(5).rotate_left(7).wrapping_mul(9);
        let t = s[1] << 17;
        s[2] ^= s[0];
        s[3] ^= s[1];
        s[1] ^= s[2];
        s[0] ^= s[3];
        s[2] ^= t;
        s[3] = s[3].rotate_left(45);
        result
    }

    /// Uniform in 0..n (multiply-shift; the bias is negligible for game-sized n).
    pub fn below(&mut self, n: usize) -> usize {
        ((self.next_u64() as u128 * n as u128) >> 64) as usize
    }
}

impl Chance for Rng {
    fn roll_die(&mut self) -> u8 {
        self.below(6) as u8
    }
    fn shuffle(&mut self, v: &mut Vec<u16>) {
        for i in (1..v.len()).rev() {
            v.swap(i, self.below(i + 1));
        }
    }
}

pub enum Event {
    Die(u8),
    Shuffle(Vec<u16>), // the deck after shuffling
}

pub struct Replay(pub VecDeque<Event>);

impl Chance for Replay {
    fn roll_die(&mut self) -> u8 {
        match self.0.pop_front() {
            Some(Event::Die(i)) => i,
            _ => panic!("replay: expected a die roll"),
        }
    }
    fn shuffle(&mut self, v: &mut Vec<u16>) {
        match self.0.pop_front() {
            Some(Event::Shuffle(after)) => {
                let (mut a, mut b) = (v.clone(), after.clone());
                a.sort_unstable();
                b.sort_unstable();
                assert_eq!(a, b, "replay: shuffle of a different deck");
                *v = after;
            }
            _ => panic!("replay: expected a shuffle"),
        }
    }
}
