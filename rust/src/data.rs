//! Card definitions, loaded once from the JSON that `py/export_data.py` writes from the Python pickles.

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
    Other,
}

pub struct Bird {
    pub habitats: [bool; 3], // forest, grassland, wetland (= board rows)
    /// Alternative cost options; within one, (food, amount) in card order. `None` food = wild.
    pub cost: Vec<Vec<(Option<Food>, u8)>>,
    pub points: i32,
    pub nest: Nest,
    pub egg_limit: u8,
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
}

#[derive(Deserialize)]
struct BirdJson {
    id: u16,
    habitats: Vec<String>,
    cost: Vec<Vec<(String, u8)>>,
    points: i32,
    nest: String,
    egg_limit: u8,
    color: Option<String>,
}

#[derive(Deserialize)]
struct BonusJson {
    id: u16,
    valid_birds: Vec<u16>,
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

fn load() -> Data {
    let birds: Vec<BirdJson> = serde_json::from_str(include_str!("../data/birds.json")).unwrap();
    let bonuses: Vec<BonusJson> = serde_json::from_str(include_str!("../data/bonuses.json")).unwrap();
    let mut data = Data {
        birds: (0..=birds.iter().map(|b| b.id).max().unwrap()).map(|_| None).collect(),
        bonuses: (0..=bonuses.iter().map(|b| b.id).max().unwrap()).map(|_| None).collect(),
        bird_ids: birds.iter().map(|b| b.id).collect(),
        bonus_ids: bonuses.iter().map(|b| b.id).collect(),
    };
    for b in birds {
        let habitat = |h: &str| b.habitats.iter().any(|x| x == h);
        data.birds[b.id as usize] = Some(Bird {
            habitats: [habitat("forest"), habitat("grassland"), habitat("wetland")],
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
            nest: match b.nest.as_str() {
                "bowl" => Nest::Bowl,
                "cavity" => Nest::Cavity,
                "ground" => Nest::Ground,
                "platform" => Nest::Platform,
                "wild" => Nest::Wild,
                _ => Nest::None,
            },
            egg_limit: b.egg_limit,
            color: b.color.map(|c| match c.as_str() {
                "brown" => Color::Brown,
                "white" => Color::White,
                "pink" => Color::Pink,
                _ => Color::Other,
            }),
        });
    }
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
        data.bonuses[b.id as usize] = Some(Bonus { id: b.id, valid_birds: b.valid_birds, score });
    }
    data
}

pub fn data() -> &'static Data {
    static DATA: OnceLock<Data> = OnceLock::new();
    DATA.get_or_init(load)
}
