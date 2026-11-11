//! The networks of `wingspan.ai.nets` evaluated in Rust, from weights written by its `export_*` functions.
//! A linear layer is stored as u32 out, u32 in, f32 weights [out][in] (PyTorch's layout), f32 bias [out];
//! everything little-endian.
//!
//! Value net (`export_value_net`): f32 margin scale, u32 number of linear layers (the trunk's, then the
//! value head, then the margin head), the layers.
//! Policy net (`export_policy_net`): u32 number of trunk layers, the trunk, the h layer, u32 number of g
//! layers, the g layers.

use std::any::Any;
use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};

use crate::actions::Action;
use crate::encode::{encode_action, encode_obs};
use crate::state::State;

struct Linear {
    n_in: usize,
    n_out: usize,
    w: Vec<f32>, // [out][in]
    b: Vec<f32>,
}

impl Linear {
    fn forward(&self, x: &[f32]) -> Vec<f32> {
        (0..self.n_out).map(|o| self.b[o] + dot(&self.w[o * self.n_in..(o + 1) * self.n_in], x)).collect()
    }
}

/// In 8 independent lanes, so the compiler can use SIMD (a single running sum must stay in order).
fn dot(a: &[f32], b: &[f32]) -> f32 {
    let mut acc = [0.0f32; 8];
    let (ca, cb) = (a.chunks_exact(8), b.chunks_exact(8));
    let tail: f32 = ca.remainder().iter().zip(cb.remainder()).map(|(x, y)| x * y).sum();
    for (x, y) in ca.zip(cb) {
        for i in 0..8 {
            acc[i] += x[i] * y[i];
        }
    }
    acc.iter().sum::<f32>() + tail
}

fn relu(mut h: Vec<f32>) -> Vec<f32> {
    h.iter_mut().for_each(|a| *a = a.max(0.0));
    h
}

/// The MLP over the observation, ReLU after every layer.
struct Trunk {
    first_t: Vec<f32>, // the first layer transposed, [in][out]: observations are mostly zeros, which it skips
    first: Linear,
    rest: Vec<Linear>,
}

impl Trunk {
    fn new(mut layers: Vec<Linear>) -> Trunk {
        let first = layers.remove(0);
        let mut first_t = vec![0.0; first.n_in * first.n_out];
        for o in 0..first.n_out {
            for i in 0..first.n_in {
                first_t[i * first.n_out + o] = first.w[o * first.n_in + i];
            }
        }
        Trunk { first_t, first, rest: layers }
    }

    fn forward(&self, obs: &[f32]) -> Vec<f32> {
        assert_eq!(obs.len(), self.first.n_in, "observation size does not match the net");
        let n = self.first.n_out;
        let mut h = self.first.b.clone();
        for (i, &x) in obs.iter().enumerate() {
            if x != 0.0 {
                for (a, w) in h.iter_mut().zip(&self.first_t[i * n..(i + 1) * n]) {
                    *a += x * w;
                }
            }
        }
        h = relu(h);
        for l in &self.rest {
            h = relu(l.forward(&h));
        }
        h
    }
}

pub struct ValueNet {
    pub margin_scale: f32,
    trunk: Trunk,
    value: Linear,
    margin: Linear,
}

impl ValueNet {
    /// (value in [-1, 1], final margin in points) for the player whose observation this is.
    pub fn evaluate(&self, obs: &[f32]) -> (f32, f32) {
        let h = self.trunk.forward(obs);
        (self.value.forward(&h)[0].tanh(), self.margin.forward(&h)[0] * self.margin_scale)
    }
}

pub struct PolicyNet {
    trunk: Trunk,
    h: Linear,
    g: Vec<Linear>,
}

impl PolicyNet {
    /// The probability of each of `actions` (the legal moves of `s`) for the player to move: softmax over
    /// h · g(move).
    pub fn priors(&self, s: &State, actions: &[Action]) -> Vec<f32> {
        let h = self.h.forward(&self.trunk.forward(&encode_obs(s, s.current_player_index)));
        let logits: Vec<f32> = actions
            .iter()
            .map(|a| {
                let mut x = encode_action(s, a);
                for (i, l) in self.g.iter().enumerate() {
                    x = l.forward(&x);
                    if i + 1 < self.g.len() {
                        x = relu(x);
                    }
                }
                dot(&h, &x)
            })
            .collect();
        let top = logits.iter().cloned().fold(f32::NEG_INFINITY, f32::max);
        let e: Vec<f32> = logits.iter().map(|l| (l - top).exp()).collect();
        let total: f32 = e.iter().sum();
        e.iter().map(|x| x / total).collect()
    }
}

struct Reader {
    bytes: Vec<u8>,
    at: usize,
}

impl Reader {
    fn word(&mut self) -> [u8; 4] {
        let v = <[u8; 4]>::try_from(&self.bytes[self.at..self.at + 4]).unwrap();
        self.at += 4;
        v
    }
    fn u32(&mut self) -> usize {
        u32::from_le_bytes(self.word()) as usize
    }
    fn f32(&mut self) -> f32 {
        f32::from_le_bytes(self.word())
    }
    fn linear(&mut self) -> Linear {
        let (n_out, n_in) = (self.u32(), self.u32());
        let w = (0..n_out * n_in).map(|_| self.f32()).collect();
        let b = (0..n_out).map(|_| self.f32()).collect();
        Linear { n_in, n_out, w, b }
    }
    fn linears(&mut self, n: usize) -> Vec<Linear> {
        (0..n).map(|_| self.linear()).collect()
    }
    fn open(path: &str) -> Reader {
        Reader { bytes: std::fs::read(path).unwrap_or_else(|e| panic!("reading net {path}: {e}")), at: 0 }
    }
    fn done(&self, path: &str) {
        assert_eq!(self.at, self.bytes.len(), "malformed net file {path}");
    }
}

fn read_value(path: &str) -> ValueNet {
    let mut r = Reader::open(path);
    let margin_scale = r.f32();
    let n = r.u32();
    assert!(n >= 3, "malformed value net file {path}");
    let mut layers = r.linears(n);
    r.done(path);
    let margin = layers.pop().unwrap();
    let value = layers.pop().unwrap();
    ValueNet { margin_scale, trunk: Trunk::new(layers), value, margin }
}

fn read_policy(path: &str) -> PolicyNet {
    let mut r = Reader::open(path);
    let n = r.u32();
    let trunk = Trunk::new(r.linears(n));
    let h = r.linear();
    let n = r.u32();
    let g = r.linears(n);
    r.done(path);
    PolicyNet { trunk, h, g }
}

/// The net in `path`, read once per process and kept for its lifetime (searches share it).
fn cached<T: Send + Sync + 'static>(path: &str, read: fn(&str) -> T) -> &'static T {
    static NETS: OnceLock<Mutex<HashMap<String, &'static (dyn Any + Send + Sync)>>> = OnceLock::new();
    let mut nets = NETS.get_or_init(Default::default).lock().unwrap();
    let net = *nets.entry(path.to_string()).or_insert_with(|| Box::leak(Box::new(read(path))));
    net.downcast_ref::<T>().unwrap_or_else(|| panic!("{path} was loaded as another kind of net"))
}

pub fn load(path: &str) -> &'static ValueNet {
    cached(path, read_value)
}

pub fn load_policy(path: &str) -> &'static PolicyNet {
    cached(path, read_policy)
}
