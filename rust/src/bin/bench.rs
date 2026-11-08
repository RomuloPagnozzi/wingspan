//! cargo run --release --bin bench [n_games]
fn main() {
    let n: usize = std::env::args().nth(1).map_or(2000, |a| a.parse().unwrap());
    wingspan_rs::bench(10, 0); // warm up (loads the card data)
    let (steps, secs) = wingspan_rs::bench(n, 1);
    println!("{n} games, {steps} decisions in {secs:.3}s: {:.0} games/s, {:.2} us/decision",
        n as f64 / secs, secs * 1e6 / steps as f64);
}
