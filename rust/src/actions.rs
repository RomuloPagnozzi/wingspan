//! Actions, printed exactly like the Python dataclass reprs (they are keys in decisions.parquet).

use std::fmt;

use crate::state::Food;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Action {
    Simple(&'static str),
    Id(&'static str, u16),
    Name(&'static str, Food),
    PlayBird { bird: u16, row: u8, col: u8 },
    SelectDie { die: u8, food: Food },
    FoodMap(&'static str, Vec<(Food, u8)>), // sorted by food
    EggMap(&'static str, Vec<(u16, u8)>),   // sorted by bird id
    DrawCards { tray: Vec<u16>, deck: u8 },
    SelectInitial { kept: Vec<u16>, bonus: u16 },
}

/// A Python tuple repr: `()`, `(x,)`, `(x, y)`.
fn tuple<T>(f: &mut fmt::Formatter, items: &[T], item: impl Fn(&mut fmt::Formatter, &T) -> fmt::Result) -> fmt::Result {
    write!(f, "(")?;
    for (i, x) in items.iter().enumerate() {
        if i > 0 {
            write!(f, ", ")?;
        }
        item(f, x)?;
    }
    write!(f, "{})", if items.len() == 1 { "," } else { "" })
}

impl fmt::Display for Action {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match self {
            Action::Simple(t) => write!(f, "SimpleAction(type='{t}')"),
            Action::Id(t, id) => write!(f, "IdAction(type='{t}', id={id})"),
            Action::Name(t, food) => write!(f, "NameAction(type='{t}', name='{}')", food.name()),
            Action::PlayBird { bird, row, col } => write!(f, "PlayBirdAction(bird_id={bird}, row={row}, col={col})"),
            Action::SelectDie { die, food } => {
                write!(f, "SelectDieAction(die_index={die}, food_type='{}')", food.name())
            }
            Action::FoodMap(t, items) => {
                write!(f, "FoodMapAction(type='{t}', items=")?;
                tuple(f, items, |f, (food, n)| write!(f, "('{}', {n})", food.name()))?;
                write!(f, ")")
            }
            Action::EggMap(t, items) => {
                write!(f, "EggMapAction(type='{t}', items=")?;
                tuple(f, items, |f, (id, n)| write!(f, "({id}, {n})"))?;
                write!(f, ")")
            }
            Action::DrawCards { tray, deck } => {
                write!(f, "DrawCardsAction(tray_birds=")?;
                tuple(f, tray, |f, id| write!(f, "{id}"))?;
                write!(f, ", deck_count={deck})")
            }
            Action::SelectInitial { kept, bonus } => {
                write!(f, "SelectInitialAction(kept_birds=")?;
                tuple(f, kept, |f, id| write!(f, "{id}"))?;
                write!(f, ", kept_bonus={bonus})")
            }
        }
    }
}
