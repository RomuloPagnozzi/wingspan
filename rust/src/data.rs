//! Card definitions, loaded once from the engine's canonical card data,
//! `src/wingspan/engine/assets/*.json` (written by `raw/generate_assets.py`, read by both engines).

use std::collections::HashMap;
use std::sync::OnceLock;

use serde::Deserialize;
use serde_json::Value;

use crate::state::Food;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Nest {
    Bowl,
    Cavity,
    Ground,
    Platform,
    Wild,
    None,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Color {
    Brown,
    White,
    Pink,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Qty {
    N(i32),
    All,
}

/// Bonus of power 17 ("tuck a card from your hand, then ...").
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum TuckBonus {
    Card,
    Egg,
    Foods(Vec<Food>), // one food: gain it; several: choose one
}

/// The 21 power templates (handlers.py), with their card details parsed.
#[derive(Clone, Debug)]
pub enum Kind {
    AllGain { card: bool, food: Option<Food> },                       // 1
    AllLayEggs { nest: Nest },                                         // 2
    CacheSeed,                                                         // 3
    DiscardToGain { discard_food: Option<Food>, gain_card: bool, gain_qty: u8, draw: bool }, // 4 (None = an egg)
    Draw { amount: u8, bonus: bool, discard: bool },                   // 5
    DrawShare,                                                         // 6
    AllGainDie,                                                        // 7
    GainFood { can_cache: bool, supply: bool, qty: Qty, foods: Vec<Food> }, // 8
    MoveBird,                                                          // 9
    LayEggs { this: bool, nest: Option<Nest> },                        // 10 (nest None = any)
    Hunt { wingspan: i32 },                                            // 11
    PlayAnother { habitat: Option<usize> },                            // 12 (None = this bird's)
    Fewest { habitat: usize, card: bool },                             // 13
    Repeat { predator: bool },                                         // 14
    DiceHunt { food: Food },                                           // 15
    Trade,                                                             // 16
    Tuck { bonus: TuckBonus },                                         // 17
    PinkPlayed { habitat: usize, card: bool, food: Option<Food> },     // 18
    PinkRodent,                                                        // 19
    PinkLayEgg { nest: Nest },                                         // 20
    PinkPredator,                                                      // 21
}

#[derive(Clone, Debug)]
pub struct Power {
    pub id: u8,
    pub color: Color,
    pub kind: Kind,
}

pub struct Bird {
    pub habitats: [bool; 3], // forest, grassland, wetland (= board rows)
    pub habitat_order: Vec<usize>, // as printed on the card
    /// Alternative cost options; within one, (food, amount) in card order. `None` food = wild.
    pub cost: Vec<Vec<(Option<Food>, u8)>>,
    /// The same options as (amount per `Food`, wild amount), for the hot affordability check.
    pub cost_counts: Vec<([u8; 5], u8)>,
    pub points: i32,
    pub nest: Nest,
    pub egg_limit: u8,
    pub wingspan: i32,
    pub power: Option<Power>,
}

/// The few card fields the rules read at almost every step, packed small so they stay in cache.
#[derive(Clone, Copy, Debug)]
pub struct Hot {
    pub egg_limit: u8,
    pub habitats: u8, // bit r = can live in board row r
    pub color: Option<Color>,
}

pub enum BonusScore {
    PerBird(i32),
    Bounds { lower: usize, upper: usize, lower_score: i32, upper_score: i32 },
}

pub struct Bonus {
    pub id: u16,
    pub valid_birds: Vec<u16>,
    pub score: BonusScore,
}

pub struct Data {
    pub birds: Vec<Option<Bird>>, // indexed by bird id
    pub hot: Vec<Hot>,            // indexed by bird id
    pub bonuses: Vec<Option<Bonus>>, // indexed by bonus id
    pub bird_ids: Vec<u16>, // registry order = the unshuffled deck
    pub bonus_ids: Vec<u16>,
}

impl Data {
    pub fn bird(&self, id: u16) -> &Bird {
        self.birds[id as usize].as_ref().expect("unknown bird id")
    }
    pub fn bonus(&self, id: u16) -> &Bonus {
        self.bonuses[id as usize].as_ref().expect("unknown bonus id")
    }
    #[inline]
    pub fn hot(&self, id: u16) -> Hot {
        self.hot[id as usize]
    }
    pub fn power(&self, id: u16) -> Option<&Power> {
        self.bird(id).power.as_ref()
    }
}

#[derive(Deserialize)]
struct BirdJson {
    id: u16,
    habitats: Vec<String>,
    cost: Vec<Vec<(String, u8)>>,
    points: i32,
    nest: Option<String>, // NaN (no nest) in the data
    egg_limit: u8,
    wingspan: i32,
}

#[derive(Deserialize)]
struct BonusJson {
    id: u16,
    valid_birds_ids: Option<Vec<u16>>, // null: scored by a rule, not a bird list
    score_params: Value,
}

pub fn food_from_str(s: &str) -> Food {
    match s {
        "fish" => Food::Fish,
        "fruit" => Food::Fruit,
        "invertebrate" => Food::Invertebrate,
        "rodent" => Food::Rodent,
        "seed" => Food::Seed,
        _ => panic!("unknown food {s}"),
    }
}

pub fn habitat_row(s: &str) -> usize {
    match s {
        "forest" => 0,
        "grassland" => 1,
        "wetland" => 2,
        _ => panic!("unknown habitat {s}"),
    }
}

fn nest_from_str(s: &str) -> Nest {
    match s {
        "bowl" => Nest::Bowl,
        "cavity" => Nest::Cavity,
        "ground" => Nest::Ground,
        "platform" => Nest::Platform,
        "wild" => Nest::Wild,
        _ => Nest::None,
    }
}

fn parse_power(v: &Value) -> Option<Power> {
    let data = v.get("data").filter(|d| d.is_object())?;
    let id = data.get("id")?.as_u64()? as u8;
    let color = match v["color"].as_str()? {
        "brown" => Color::Brown,
        "white" => Color::White,
        "pink" => Color::Pink,
        c => panic!("unknown power color {c}"),
    };
    let d = &data["details"];
    let s = |k: &str| d[k].as_str().unwrap_or("");
    let b = |k: &str| d[k].as_bool().unwrap_or(false);
    let foods = |k: &str| d[k].as_array().unwrap().iter().map(|f| food_from_str(f.as_str().unwrap())).collect::<Vec<_>>();
    let kind = match id {
        1 => match s("type") {
            "card" => Kind::AllGain { card: true, food: None },
            f => Kind::AllGain { card: false, food: Some(food_from_str(f)) },
        },
        2 => Kind::AllLayEggs { nest: nest_from_str(s("type")) },
        3 => Kind::CacheSeed,
        4 => Kind::DiscardToGain {
            discard_food: (s("discard") != "egg").then(|| food_from_str(s("discard"))),
            gain_card: s("gain") == "card",
            gain_qty: d["gain_qty"].as_u64().unwrap_or(1) as u8,
            draw: s("action") == "draw",
        },
        5 => Kind::Draw { amount: d["amount"].as_u64().unwrap() as u8, bonus: b("bonus"), discard: b("discard") },
        6 => Kind::DrawShare,
        7 => Kind::AllGainDie,
        8 => Kind::GainFood {
            can_cache: b("can_cache"),
            supply: s("source") == "supply",
            qty: match d["quantity"].as_i64() {
                Some(n) => Qty::N(n as i32),
                None => Qty::All,
            },
            foods: foods("food_types"),
        },
        9 => Kind::MoveBird,
        10 => Kind::LayEggs { this: b("this"), nest: (s("type") != "any").then(|| nest_from_str(s("type"))) },
        11 => Kind::Hunt { wingspan: d["wingspan"].as_i64().unwrap() as i32 },
        12 => Kind::PlayAnother { habitat: (s("habitat") != "this").then(|| habitat_row(s("habitat"))) },
        13 => Kind::Fewest { habitat: habitat_row(s("habitat")), card: s("item") == "card" },
        14 => Kind::Repeat { predator: s("type") == "predator" },
        15 => Kind::DiceHunt { food: food_from_str(s("type")) },
        16 => Kind::Trade,
        17 => {
            let t: Vec<&str> = d["types"].as_array().unwrap().iter().map(|x| x.as_str().unwrap()).collect();
            Kind::Tuck {
                bonus: match t[..] {
                    ["card"] => TuckBonus::Card,
                    ["egg"] => TuckBonus::Egg,
                    _ => TuckBonus::Foods(t.iter().map(|f| food_from_str(f)).collect()),
                },
            }
        }
        18 => Kind::PinkPlayed {
            habitat: habitat_row(s("habitat")),
            card: s("resource") == "card",
            food: (s("resource") != "card").then(|| food_from_str(s("resource"))),
        },
        19 => Kind::PinkRodent,
        20 => Kind::PinkLayEgg { nest: nest_from_str(s("type")) },
        21 => Kind::PinkPredator,
        _ => panic!("unknown power {id}"),
    };
    Some(Power { id, color, kind })
}

/// The card data marks missing values as NaN (Python's json writes and reads them); JSON proper has null.
fn parse<T: serde::de::DeserializeOwned>(json: &str) -> T {
    serde_json::from_str(&json.replace(": NaN", ": null")).expect("bad card data")
}

fn load() -> Data {
    let birds: Vec<BirdJson> = parse(include_str!("../../src/wingspan/engine/assets/birds.json"));
    let bonuses: Vec<BonusJson> = parse(include_str!("../../src/wingspan/engine/assets/bonuses.json"));
    let powers: HashMap<String, Value> = parse(include_str!("../../src/wingspan/engine/assets/powers.json"));
    let mut data = Data {
        birds: (0..=birds.iter().map(|b| b.id).max().unwrap()).map(|_| None).collect(),
        bonuses: (0..=bonuses.iter().map(|b| b.id).max().unwrap()).map(|_| None).collect(),
        hot: vec![],
        bird_ids: birds.iter().map(|b| b.id).collect(),
        bonus_ids: bonuses.iter().map(|b| b.id).collect(),
    };
    for b in birds {
        let habitat_order: Vec<usize> = b.habitats.iter().map(|h| habitat_row(h)).collect();
        let cost_counts = b
            .cost
            .iter()
            .map(|opt| {
                let mut c = ([0u8; 5], 0u8);
                for (f, n) in opt {
                    if f == "wild" {
                        c.1 = *n;
                    } else {
                        c.0[food_from_str(f) as usize] = *n;
                    }
                }
                c
            })
            .collect();
        data.birds[b.id as usize] = Some(Bird {
            cost_counts,
            habitats: std::array::from_fn(|r| habitat_order.contains(&r)),
            habitat_order,
            cost: b
                .cost
                .iter()
                .map(|opt| {
                    opt.iter()
                        .map(|(f, n)| (if f == "wild" { None } else { Some(food_from_str(f)) }, *n))
                        .collect()
                })
                .collect(),
            points: b.points,
            nest: nest_from_str(b.nest.as_deref().unwrap_or("")),
            egg_limit: b.egg_limit,
            wingspan: b.wingspan,
            power: powers.get(&b.id.to_string()).and_then(parse_power),
        });
    }
    data.hot = data
        .birds
        .iter()
        .map(|b| match b {
            Some(b) => Hot {
                egg_limit: b.egg_limit,
                habitats: (0..3).filter(|&r| b.habitats[r]).map(|r| 1 << r).sum(),
                color: b.power.as_ref().map(|p| p.color),
            },
            None => Hot { egg_limit: 0, habitats: 0, color: None },
        })
        .collect();
    for b in bonuses {
        let p = &b.score_params;
        let int = |k: &str| p[k].as_i64().unwrap();
        let score = if p.get("per_bird").is_some() {
            BonusScore::PerBird(int("per_bird") as i32)
        } else {
            BonusScore::Bounds {
                lower: int("lower_bound") as usize,
                upper: int("upper_bound") as usize,
                lower_score: int("lower_score") as i32,
                upper_score: int("upper_score") as i32,
            }
        };
        let mut valid_birds = b.valid_birds_ids.unwrap_or_default();
        valid_birds.sort_unstable();
        data.bonuses[b.id as usize] = Some(Bonus { id: b.id, valid_birds, score });
    }
    data
}

pub fn data() -> &'static Data {
    static DATA: OnceLock<Data> = OnceLock::new();
    DATA.get_or_init(load)
}
