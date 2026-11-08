//! Game state. The serde shape is the canonical JSON that `py/pystate.py` produces from a Python
//! GameState, so the two engines can be compared field by field.

use serde::{de, Deserialize, Deserializer, Serialize, Serializer};

/// Declared in alphabetical order, so sorting by Food = sorting by name (Python's `frozen_map`).
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Food {
    Fish,
    Fruit,
    Invertebrate,
    Rodent,
    Seed,
}

impl Food {
    pub const ALL: [Food; 5] = [Food::Fish, Food::Fruit, Food::Invertebrate, Food::Rodent, Food::Seed];
    pub fn name(self) -> &'static str {
        match self {
            Food::Fish => "fish",
            Food::Fruit => "fruit",
            Food::Invertebrate => "invertebrate",
            Food::Rodent => "rodent",
            Food::Seed => "seed",
        }
    }
}

/// The six die faces, in the order of Python's `roll_feeder`.
pub const FACES: [&[Food]; 6] = [
    &[Food::Fish],
    &[Food::Fruit],
    &[Food::Rodent],
    &[Food::Invertebrate],
    &[Food::Seed],
    &[Food::Invertebrate, Food::Seed],
];

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Face(pub u8);

impl Face {
    pub fn foods(self) -> &'static [Food] {
        FACES[self.0 as usize]
    }
}

impl Serialize for Face {
    fn serialize<S: Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        self.foods().serialize(s)
    }
}

impl<'de> Deserialize<'de> for Face {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        let v = Vec::<Food>::deserialize(d)?;
        FACES
            .iter()
            .position(|f| *f == v.as_slice())
            .map(|i| Face(i as u8))
            .ok_or_else(|| de::Error::custom("unknown die face"))
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Phase {
    GameSetup,
    MainTurn,
    ExtraFoodAction,
    ExtraLayEggsAction,
    ExtraCardDrawAction,
    SelectInitialCards,
    DiscardFood,
    CollectFood,
    LayEggs,
    DrawCards,
    PlayBird,
    SelectBirdToDiscard,
    SelectFoodToDiscard,
    SelectEggToDiscard,
    PayEggCost,
    PayFoodCost,
    ActivatePowers,
    EndTurn,
    GameOver,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ScoringMode {
    Blue,
    Green,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct PlacedBird {
    pub id: u16,
    pub eggs: u8,
    pub food: u8, // cached food
    pub tucked: u8,
}

pub type Board = [[Option<PlacedBird>; 5]; 3];

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Score {
    pub bird_points: i32,
    pub egg_points: i32,
    pub cached_food: i32,
    pub tucked_cards: i32,
    pub round_goals: [i32; 4],
    pub bonus_scores: Vec<(u16, i32)>, // sorted by bonus id
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Player {
    pub id: u8, // 1-based, as in Python
    pub bird_hand: Vec<u16>,
    pub bonus_hand: Vec<u16>,
    /// Insertion-ordered like the Python dict (order decides some action orders); no zero entries.
    pub food: Vec<(Food, u8)>,
    pub board: Board,
    pub action_cubes: i32,
    pub first_player: bool,
    pub used_pink_powers: Vec<u16>,
    pub score: Score,
}

impl Player {
    pub fn food_of(&self, f: Food) -> u8 {
        self.food.iter().find(|(g, _)| *g == f).map_or(0, |(_, n)| *n)
    }
    pub fn food_counts(&self) -> [u8; 5] {
        let mut c = [0; 5];
        for &(f, n) in &self.food {
            c[f as usize] = n;
        }
        c
    }
    pub fn gain_food(&mut self, f: Food, n: u8) {
        match self.food.iter_mut().find(|(g, _)| *g == f) {
            Some((_, m)) => *m += n,
            None => self.food.push((f, n)),
        }
    }
    pub fn pay_food(&mut self, f: Food, n: u8) {
        let i = self.food.iter().position(|(g, _)| *g == f).expect("paying food the player lacks");
        self.food[i].1 -= n;
        if self.food[i].1 == 0 {
            self.food.remove(i);
        }
    }
    pub fn birds(&self) -> impl Iterator<Item = &PlacedBird> {
        self.board.iter().flatten().flatten()
    }
    pub fn bird_mut(&mut self, id: u16) -> Option<&mut PlacedBird> {
        self.board.iter_mut().flatten().flatten().find(|b| b.id == id)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CostType {
    Egg,
    Food,
    EggPaid,
    FoodPaid,
}

/// The play-bird action a cost payment returns to (always a PlayBirdAction).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PlayCallback {
    pub bird: u16,
    pub row: u8,
    pub col: u8,
}

impl Serialize for PlayCallback {
    fn serialize<S: Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&format!("PlayBirdAction(bird_id={}, row={}, col={})", self.bird, self.row, self.col))
    }
}

impl<'de> Deserialize<'de> for PlayCallback {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        let s = String::deserialize(d)?;
        let inner = s
            .strip_prefix("PlayBirdAction(")
            .and_then(|r| r.strip_suffix(')'))
            .ok_or_else(|| de::Error::custom(format!("not a PlayBirdAction: {s}")))?;
        let nums: Vec<u16> = inner
            .split(", ")
            .map(|kv| kv.split_once('=').and_then(|(_, v)| v.parse().ok()))
            .collect::<Option<_>>()
            .ok_or_else(|| de::Error::custom(format!("bad PlayBirdAction: {s}")))?;
        match nums[..] {
            [bird, row, col] => Ok(PlayCallback { bird, row: row as u8, col: col as u8 }),
            _ => Err(de::Error::custom(format!("bad PlayBirdAction: {s}"))),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct PendingCost {
    pub cost_type: CostType,
    pub amount: Option<i32>, // egg cost; None for a food cost (that is the bird's cost)
    pub callback_phase: Phase,
    pub callback_action: PlayCallback,
}

#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct ActionData {
    pub current_power_index: i32,
    pub action_player_index: Option<usize>,
    pub food_needed: i32,
    pub eggs_needed: i32,
    pub cards_needed: i32,
    pub base_amount: i32,
    pub gained_rodent: bool,
    pub amount_to_discard: i32,
    pub pending_cost: Option<PendingCost>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct State {
    pub players: Vec<Player>,
    pub bird_deck: Vec<u16>, // top of the deck = last element
    pub discarded_birds: Vec<u16>,
    pub bonus_deck: Vec<u16>,
    pub discarded_bonuses: Vec<u16>,
    pub bird_tray: Vec<u16>,
    pub feeder: Vec<(u8, Face)>, // (die index, face), insertion-ordered like the Python dict
    pub round: i32,
    pub current_player_index: usize,
    pub game_phase: Phase,
    pub action_data: ActionData,
    pub scoring_mode: ScoringMode,
    pub selected_goals: Vec<String>,
}

impl State {
    pub fn cur(&self) -> &Player {
        &self.players[self.current_player_index]
    }
    pub fn cur_mut(&mut self) -> &mut Player {
        &mut self.players[self.current_player_index]
    }
}
