//! The value net (`wingspan.ai.nets.ValueNet`, an MLP) evaluated in Rust, from weights written by
//! `wingspan.ai.nets.export_value_net`. File layout, little-endian: f32 margin scale, u32 number of linear
//! layers (the trunk's, then the value head, then the margin head), and per layer u32 out, u32 in,
//! f32 weights [out][in] (PyTorch's layout), f32 bias [out].

use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};

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

pub struct ValueNet {
    pub margin_scale: f32,
    first_t: Vec<f32>, // the first layer transposed, [in][out]: observations are mostly zeros, which it skips
    first: Linear,
    rest: Vec<Linear>,
    value: Linear,
    margin: Linear,
}

impl ValueNet {
    pub fn n_obs(&self) -> usize {
        self.first.n_in
    }

    /// (value in [-1, 1], final margin in points) for the player whose observation this is.
    pub fn evaluate(&self, obs: &[f32]) -> (f32, f32) {
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
        h.iter_mut().for_each(|a| *a = a.max(0.0));
        for l in &self.rest {
            h = l.forward(&h);
            h.iter_mut().for_each(|a| *a = a.max(0.0));
        }
        (self.value.forward(&h)[0].tanh(), self.margin.forward(&h)[0] * self.margin_scale)
    }
}

fn read(path: &str) -> ValueNet {
    let bytes = std::fs::read(path).unwrap_or_else(|e| panic!("reading value net {path}: {e}"));
    let mut at = 0;
    let mut word = || {
        let v = <[u8; 4]>::try_from(&bytes[at..at + 4]).unwrap();
        at += 4;
        v
    };
    let margin_scale = f32::from_le_bytes(word());
    let n_layers = u32::from_le_bytes(word()) as usize;
    let mut layers: Vec<Linear> = (0..n_layers)
        .map(|_| {
            let n_out = u32::from_le_bytes(word()) as usize;
            let n_in = u32::from_le_bytes(word()) as usize;
            let w = (0..n_out * n_in).map(|_| f32::from_le_bytes(word())).collect();
            let b = (0..n_out).map(|_| f32::from_le_bytes(word())).collect();
            Linear { n_in, n_out, w, b }
        })
        .collect();
    assert!(n_layers >= 3 && at == bytes.len(), "malformed value net file {path}");
    let margin = layers.pop().unwrap();
    let value = layers.pop().unwrap();
    let first = layers.remove(0);
    let mut first_t = vec![0.0; first.n_in * first.n_out];
    for o in 0..first.n_out {
        for i in 0..first.n_in {
            first_t[i * first.n_out + o] = first.w[o * first.n_in + i];
        }
    }
    ValueNet { margin_scale, first_t, first, rest: layers, value, margin }
}

/// The net in `path`, read once per process and kept for its lifetime (searches share it).
pub fn load(path: &str) -> &'static ValueNet {
    static NETS: OnceLock<Mutex<HashMap<String, &'static ValueNet>>> = OnceLock::new();
    let mut nets = NETS.get_or_init(Default::default).lock().unwrap();
    nets.entry(path.to_string()).or_insert_with(|| Box::leak(Box::new(read(path))))
}
