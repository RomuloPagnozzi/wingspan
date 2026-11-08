//! Actions, printed exactly like the Python dataclass reprs (they are keys in decisions.parquet).

use std::fmt;

use crate::state::Food;

/// A small inline vector (no heap allocation), for action payloads: at most N items.
#[derive(Clone, Copy)]
pub struct Arr<T: Copy + Default, const N: usize> {
    len: u8,
    items: [T; N],
}

impl<T: Copy + Default, const N: usize> Arr<T, N> {
    pub fn new() -> Self {
        Arr { len: 0, items: [T::default(); N] }
    }
    pub fn push(&mut self, x: T) {
        self.items[self.len as usize] = x;
        self.len += 1;
    }
    pub fn pop(&mut self) {
        self.len -= 1;
    }
}

impl<T: Copy + Default, const N: usize> std::ops::Deref for Arr<T, N> {
    type Target = [T];
    fn deref(&self) -> &[T] {
        &self.items[..self.len as usize]
    }
}

impl<T: Copy + Default, const N: usize> std::ops::DerefMut for Arr<T, N> {
    fn deref_mut(&mut self) -> &mut [T] {
        &mut self.items[..self.len as usize]
    }
}

impl<T: Copy + Default, const N: usize> FromIterator<T> for Arr<T, N> {
    fn from_iter<I: IntoIterator<Item = T>>(iter: I) -> Self {
        let mut a = Arr::new();
        for x in iter {
            a.push(x);
        }
        a
    }
}

impl<'a, T: Copy + Default, const N: usize> IntoIterator for &'a Arr<T, N> {
    type Item = &'a T;
    type IntoIter = std::slice::Iter<'a, T>;
    fn into_iter(self) -> Self::IntoIter {
        self.iter()
    }
}

impl<T: Copy + Default + PartialEq, const N: usize> PartialEq for Arr<T, N> {
    fn eq(&self, other: &Self) -> bool {
        **self == **other
    }
}

impl<T: Copy + Default + Eq, const N: usize> Eq for Arr<T, N> {}

impl<T: Copy + Default + fmt::Debug, const N: usize> fmt::Debug for Arr<T, N> {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        (**self).fmt(f)
    }
}

pub type FoodItems = Arr<(Food, u8), 5>; // sorted by food
pub type EggItems = Arr<(u16, u8), 15>; // sorted by bird id; a board has 15 spots

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Action {
    Simple(&'static str),
    Id(&'static str, u16),
    Name(&'static str, &'static str),
    Trade { from: Food, to: Food },
    PlayBird { bird: u16, row: u8, col: u8 },
    SelectDie { die: u8, food: Food },
    FoodMap(&'static str, FoodItems),
    EggMap(&'static str, EggItems),
    DrawCards { tray: Arr<u16, 3>, deck: u8 },
    SelectInitial { kept: Arr<u16, 5>, bonus: u16 },
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
            Action::Name(t, name) => write!(f, "NameAction(type='{t}', name='{name}')"),
            Action::Trade { from, to } => write!(f, "TradeAction(from_type='{}', to_type='{}')", from.name(), to.name()),
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
