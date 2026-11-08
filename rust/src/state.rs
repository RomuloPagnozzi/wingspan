//! Game state. The serde shape is the canonical JSON that `py/pystate.py` produces from a Python
//! GameState, so the two engines can be compared field by field.

use serde::{de, Deserialize, Deserializer, Serialize, Serializer};

/// Declared in alphabetical order, so sorting by Food = sorting by name (Python's `frozen_map`).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Food {
    #[default]
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

#[derive(Debug, PartialEq, Serialize, Deserialize)]
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

/// The 16 round goals; the 8 double-sided tiles are the pairs (2i, 2i + 1).
pub const GOAL_NAMES: [&str; 16] = [
    "eggs_in_bowl", "bowl_birds_with_egg", "eggs_in_cavity", "cavity_birds_with_egg",
    "eggs_in_ground", "ground_birds_with_egg", "eggs_in_platform", "platform_birds_with_egg",
    "eggs_in_forest", "birds_in_forest", "eggs_in_grassland", "birds_in_grassland",
    "eggs_in_wetland", "birds_in_wetland", "total_birds", "sets_of_eggs",
];

/// The 4 selected round goals, as indices into `GOAL_NAMES` (no heap allocation when a state is cloned).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Goals(pub [u8; 4]);

impl Goals {
    pub fn name(&self, round: usize) -> &'static str {
        GOAL_NAMES[self.0[round - 1] as usize]
    }
}

impl Serialize for Goals {
    fn serialize<S: Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        self.0.map(|g| GOAL_NAMES[g as usize]).serialize(s)
    }
}

impl<'de> Deserialize<'de> for Goals {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        let names = <[String; 4]>::deserialize(d)?;
        let mut g = [0u8; 4];
        for (i, n) in names.iter().enumerate() {
            g[i] = GOAL_NAMES.iter().position(|x| x == n).ok_or_else(|| de::Error::custom(format!("unknown goal {n}")))? as u8;
        }
        Ok(Goals(g))
    }
}

/// A copy with room to grow, so the first card drawn after cloning a state doesn't reallocate.
fn spare<T: Clone>(v: &Vec<T>, extra: usize) -> Vec<T> {
    let mut out = Vec::with_capacity(v.len() + extra);
    out.extend_from_slice(v);
    out
}

impl Clone for Player {
    fn clone(&self) -> Player {
        Player {
            id: self.id,
            bird_hand: spare(&self.bird_hand, 8),
            bonus_hand: spare(&self.bonus_hand, 2),
            food: spare(&self.food, 5 - self.food.len().min(5)),
            board: self.board,
            action_cubes: self.action_cubes,
            first_player: self.first_player,
            used_pink_powers: self.used_pink_powers.clone(),
            score: Score { bonus_scores: spare(&self.score.bonus_scores, 2), ..self.score.clone() },
        }
    }
}

impl Clone for State {
    fn clone(&self) -> State {
        State {
            players: self.players.clone(),
            bird_deck: self.bird_deck.clone(),
            discarded_birds: spare(&self.discarded_birds, 16),
            bonus_deck: self.bonus_deck.clone(),
            discarded_bonuses: spare(&self.discarded_bonuses, 4),
            bird_tray: spare(&self.bird_tray, 3 - self.bird_tray.len().min(3)),
            feeder: spare(&self.feeder, 5 - self.feeder.len().min(5)),
            round: self.round,
            current_player_index: self.current_player_index,
            game_phase: self.game_phase,
            action_data: self.action_data.clone(),
            scoring_mode: self.scoring_mode,
            selected_goals: self.selected_goals,
        }
    }
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

/// A power waiting in the activation queue (its card data is looked up from `bird_id`).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct QueuedPower {
    pub power_id: u8,
    pub bird_id: u16,
    pub spot_row: u8,
    pub spot_col: u8,
    pub player_index: usize,
}

/// Where a power on the execution stack is waiting for input (Python's `PowerExecution.phase`).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PowerPhase {
    Choices,
    SelectDiscard,
    SelectDraw,
    SelectGain,
    SelectBonus,
    SelectCard,
    ChooseStartingPlayer,
    SelectDie,
    SelectFoodType,
    ChooseCache,
    SelectHabitat,
    SelectBird,
    AwaitingBirdPlay,
    SelectTrade,
    SelectFood,
    EndTurnDiscard,
}

/// The part of Python's `PowerExecution.context` that changes during play. The rest (the card's power
/// details, copied in at activation) is looked up from the bird instead.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Context {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub activator: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub awaiting_players: Option<Vec<usize>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub draw_amount: Option<u8>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub bonus_options: Option<Vec<u16>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub available_cards: Option<Vec<u16>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub food_type: Option<Food>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub available_foods: Option<Vec<Food>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub remaining_quantity: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub valid_habitats: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub valid_bird_ids: Option<Vec<u16>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target_habitat: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub eligible_birds: Option<Vec<(u16, u8, u8)>>, // (bird, row, col)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub amount: Option<i32>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Execution {
    pub power_id: u8,
    pub bird_id: u16,
    pub spot_row: u8,
    pub spot_col: u8,
    pub player_index: usize,
    pub phase: Option<PowerPhase>,
    pub context: Context,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct EndTurnEffect {
    pub effect_type: String, // only "discard_cards"
    pub player_index: usize,
    pub amount: i32,
}

#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct ActionData {
    pub powers_queue: Vec<QueuedPower>,
    pub execution_stack: Vec<Execution>,
    pub end_turn_effects: Vec<EndTurnEffect>,
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

#[derive(Debug, PartialEq, Serialize, Deserialize)]
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
    pub selected_goals: Goals,
}

impl ActionData {
    /// `ActionData.clear()`: back to the empty state of a new turn, keeping the vectors' allocations.
    pub fn reset(&mut self) {
        let (mut q, mut e, mut t) = (
            std::mem::take(&mut self.powers_queue),
            std::mem::take(&mut self.execution_stack),
            std::mem::take(&mut self.end_turn_effects),
        );
        q.clear();
        e.clear();
        t.clear();
        *self = ActionData { powers_queue: q, execution_stack: e, end_turn_effects: t, ..ActionData::default() };
    }
}

impl State {
    pub fn cur(&self) -> &Player {
        &self.players[self.current_player_index]
    }
    pub fn cur_mut(&mut self) -> &mut Player {
        &mut self.players[self.current_player_index]
    }
}
