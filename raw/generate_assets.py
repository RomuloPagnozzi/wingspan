"""Builds the card data both engines use (src/wingspan/engine/assets/*.json) from the source spreadsheet.

    uv run python raw/generate_assets.py

JSON keeps the exact values: missing cells stay NaN (written as the NaN token, which Python's json reads
back), bird costs and habitats are lists that the engine turns back into tuples, bonus bird sets are lists.
"""

import json
import re
from pathlib import Path

import pandas as pd

ASSETS = Path(__file__).parent.parent / "src/wingspan/engine/assets"


def _write(name: str, data) -> None:
    with open(ASSETS / f"{name}.json", "w") as f:
        json.dump(data, f, indent=1)
        f.write("\n")



def _freeze_cost(cost: list[dict[str, int]]) -> tuple:
    """Convert mutable cost structure to immutable tuple."""
    return tuple(tuple(sorted(c.items())) for c in cost)

def convert_row(row):
    result = []
    if pd.notna(row["or"]):
        for col in [
            "invertebrate",
            "seed",
            "fish",
            "fruit",
            "rodent",
            "wild",
        ]:
            if pd.notna(row[col]):
                result.append({col: int(row[col])})
    else:
        combined_dict = {}
        for col in [
            "invertebrate",
            "seed",
            "fish",
            "fruit",
            "rodent",
            "wild",
        ]:
            if pd.notna(row[col]):
                combined_dict[col] = int(row[col])
        if combined_dict:
            result.append(combined_dict)
    return result

def parse_text(power_text):
    match power_text:
        case text if "All players draw" in text or "All players gain" in text:
            return {
                "id": 1,
                "details": {
                    "type": text.split("[")[1].split("]")[0]
                }
            }
        case text if "All players lay" in text:
            return {
                "id": 2,
                "details": {
                    "type": text.split("[")[2].split("]")[0]
                }
            }
        case text if "Cache" in text:
            return {"id": 3}
        case text if "Discard" in text:
            # Extract all [resource] patterns and their preceding numbers
            # Pattern: "Discard X [resource] ... to (gain/tuck/draw) Y [resource]"
            parts = text.split("[")

            # Get discard resource (first bracketed item)
            discard_resource = parts[1].split("]")[0]
            # Get discard quantity (number before first bracket)
            discard_match = re.search(r'Discard (\d+)', text)
            discard_qty = int(discard_match.group(1)) if discard_match else 1

            # Get gain resource (second bracketed item)
            gain_resource = parts[2].split("]")[0]
            # Get gain quantity (look for number before second bracket)
            # Search for pattern like "to gain/tuck/draw X" or "to gain/tuck/draw X [resource]"
            gain_match = re.search(r'to (?:gain|tuck|draw) (\d+)', text)
            gain_qty = int(gain_match.group(1)) if gain_match else 1

            # Determine the action type (gain, tuck, or draw)
            action = "gain"
            if "tuck" in text:
                action = "tuck"
            elif "draw" in text:
                action = "draw"

            return {
                "id": 4,
                "details": {
                    "discard": discard_resource,
                    "discard_qty": discard_qty,
                    "gain": gain_resource,
                    "gain_qty": gain_qty,
                    "action": action
                }
            }
        case text if "Draw" in text:
            if len(text) < 100:
                return {
                    "id": 5,
                    "details": {
                        "amount": int(text[5]),
                        "discard": True if len(text) > 20 else False,
                        "bonus": True if "bonus" in text else False,
                    }

                }
            else:
                return {"id": 6}
        case text if "Each" in text:
            return {"id": 7}
        case text if "Gain" in text:
            food_types = re.findall(r'\[([^\]]+)\]', text)
            source = "birdfeeder" if "birdfeeder" in text else "supply"
            can_cache = "cache" in text
            # Extract quantity: "all" or a number
            if "Gain all" in text:
                quantity = "all"
            else:
                # Extract number after "Gain"
                qty_match = re.search(r'Gain (\d+)', text)
                quantity = int(qty_match.group(1)) if qty_match else 1
            return {
                "id": 8,
                "details": {
                    "food_types": food_types,
                    "source": source,
                    "can_cache": can_cache,
                    "quantity": quantity
                }
            }
        case text if "move" in text:
            return {"id": 9}
        case text if "Lay" in text:
            this = "this" in text
            any = "any" in text
            type = ""
            if not this and not any:
                type = text.split("[")[2].split("]")[0]
            return {
                "id": 10,
                "details": {
                    "this": this,
                    "type": "any" if any else type
                }
            }
        case text if "Look" in text:
            return {
                "id": 11,
                "details": {
                    "wingspan": int(m.group(1)) if (m := re.search(r'(\d+)cm', text)) else 0
                }
            }
        case text if "Play an" in text:
            return {
                "id": 12,
                "details": {
                    "habitat": m.group(1) if '[' in text and (m := re.search(r'\[([^\]]+)\]', text)) else "this"
                }
            }
        case text if "Player(s)" in text:
            habitat, item = re.findall(r'\[([^\]]+)\]', text)
            return {
                "id": 13,
                "details": {
                    "habitat": habitat,
                    "item": item
                }
            }
        case text if "Repeat" in text:
            return {
                "id": 14,
                "details": {
                    "type": "predator" if "[predator]" in text else "brown"
                }
            }
        case text if "Roll all" in text:
            return {
                "id": 15,
                "details": {
                    "type": "fish" if "[fish]" in text else "rodent"
                }
            }
        case text if "Trade 1 [wild]" in text:
            return {"id": 16}
        case text if "Tuck" in text:
            return {
                "id": 17,
                "details": {
                    "types": re.findall(r'\[([^\]]+)\]', text)[1:]
                }
            }
        case text if "When another player plays" in text:
            habitat, resource = re.findall(r'\[([^\]]+)\]', text)
            return {
                "id": 18,
                "details": {
                    "habitat": habitat,
                    "resource": resource
                }
            }
        case text if 'When another player takes the "gain food"' in text:
            return {"id": 19, "details": {"type": "rodent"}}
        case text if 'When another player takes the "lay eggs"' in text:
            return {
                "id": 20,
                "details": {
                    "type": re.findall(r'\[([^\]]+)\]', text)[1]
                }
            }
        case text if "When another player's [predator]" in text:
            return {
                "id": 21,
                "details": {"resource": "die"}
            }
        case _:
            return 0

df = pd.read_excel("raw/wingspan-20221201.xlsx")
df = df.rename(lambda x: x.replace(" ", "_").lower(), axis="columns")
names = {
    "common_name": "name",
    "victory_points": "points",
    "nest_type": "nest",
    "wild_(food)": "wild",
    "/_(food_cost)": "or",
}
df = df.rename(columns=names)
df["habitats"] = df[["forest", "grassland", "wetland"]].apply(
    lambda x: [col for col, val in x.items() if val == "X"], axis=1
)
df["cost"] = df[
    ["invertebrate", "seed", "fish", "fruit", "rodent", "wild", "or"]
].apply(convert_row, axis=1)
df = df[(df.swift_start.isna()) & (df.set == 'core')].sort_values(by='name')
df['id'] = range(1, len(df) + 1)

power_triggers = {
    "white": "when played",
    "brown": "when activated",
    "pink": "once between turns"
}

birds_list = []
for index, row in df.iterrows():
    birds_list.append({
        "id": int(row['id']),
        "name": row['name'],
        "habitats": list(row['habitats']),
        "cost": [[list(item) for item in option] for option in _freeze_cost(row['cost'])],
        "points": int(row['points']),
        "nest": row['nest'],
        "egg_limit": int(row['egg_limit']),
        "wingspan": int(row['wingspan']),
    })
_write("birds", birds_list)

bonus = pd.read_excel("raw/wingspan-20221201.xlsx", sheet_name="Bonus")
bonus.columns = bonus.columns.str.lower()
bonus = bonus.map(lambda x: x.lower() if isinstance(x, str) else x)
bonus = bonus.rename(lambda x: x.replace(" ", "_").lower(), axis="columns")
bonus = bonus[(bonus.set == 'core') | (bonus.set == 'core, asia')]
bonus = bonus.drop(columns=["set", "automa"])
bonus['id'] = range(1, len(bonus) + 1)
cols = bonus.columns.to_list()
cols.pop(-1)
cols = ['id'] + cols
bonus = bonus[cols]
bonus['bonus_card'] = bonus.bonus_card.str.replace(" ", "_").str.removesuffix('_[swift_start_asia]')
df = df.iloc[:, -29:].drop(columns=["cost", "habitats", "small_clutch_specialist", 'bird_bander', 'diet_specialist', 'endangered_species_protector'])
cols = df.columns.to_list()
cols.pop(-1)
cols = ['id'] + cols
df = df[cols]
df = df.rename(columns={'omnivore_expert': 'omnivore_specialist'})
bonus['birds'] = None
common = set(bonus['bonus_card']).intersection(df.columns)
for index, row in bonus.iterrows():
    if row['bonus_card'] in common:
        bonus.at[index, 'birds'] = set(df.loc[df[row['bonus_card']].notna(), 'id'].tolist())  # type: ignore[index]
bonus.loc[0, 'vp'] = '2 to 3 birds: 3; 4+ birds: 7'
vp_dict = {'2 to 3 birds: 3; 4+ birds: 7': {"lower_bound": 2, "upper_bound": 4, "lower_score": 3, "upper_score": 7},
           '5 to 6 birds: 3; 6+ birds: 6': {"lower_bound": 5, "upper_bound": 7, "lower_score": 3, "upper_score": 6},
           '5 to 7 birds: 3; 8+ birds: 7': {"lower_bound": 5, "upper_bound": 8, "lower_score": 3, "upper_score": 7},
           '4 to 5 birds: 4; 6+ birds: 7': {"lower_bound": 4, "upper_bound": 6, "lower_score": 4, "upper_score": 7},
           '2 to 3 birds: 3; 4+ birds: 8': {"lower_bound": 2, "upper_bound": 4, "lower_score": 3, "upper_score": 8},
           '3 to 4 birds: 4; 5 birds: 8': {"lower_bound": 3, "upper_bound": 5, "lower_score": 4, "upper_score": 8},
           '4 to 5 birds: 3; 6+ birds: 6': {"lower_bound": 4, "upper_bound": 6, "lower_score": 3, "upper_score": 6},
           '7 to 8 birds: 3; 9+ birds: 6': {"lower_bound": 7, "upper_bound": 9, "lower_score": 3, "upper_score": 6},
           '5 to 7 birds: 4; 8+ birds: 7': {"lower_bound": 5, "upper_bound": 8, "lower_score": 4, "upper_score": 7},
           '3 to 4 birds: 3; 5 birds: 7': {"lower_bound": 3, "upper_bound": 5, "lower_score": 3, "upper_score": 7},
           '1 per bird': {"per_bird": 1},
           '2 per bird': {"per_bird": 2}}
bonus["score_params"] = bonus.vp.apply(lambda x: vp_dict.get(x, None))

bonus_list = []
for index, row in bonus.iterrows():
    bonus_list.append({
        "id": int(row['id']),
        "name": row['bonus_card'],
        "condition": row['condition'],
        "score_params": row['score_params'],
        "valid_birds_ids": None if row['birds'] is None else sorted(int(b) for b in row['birds']),
    })
_write("bonuses", bonus_list)

# Generate powers from the original dataframe
df_powers = pd.read_excel("raw/wingspan-20221201.xlsx")
df_powers = df_powers.rename(lambda x: x.replace(" ", "_").lower(), axis="columns")
df_powers = df_powers.rename(columns={
    "common_name": "name",
    "victory_points": "points",
    "nest_type": "nest",
    "wild_(food)": "wild",
    "/_(food_cost)": "or",
})
df_powers = df_powers[(df_powers.swift_start.isna()) & (df_powers.set == 'core')].sort_values(by='name')
df_powers['id'] = range(1, len(df_powers) + 1)

powers_data = []
for index, row in df_powers.iterrows():
    power_dict = {
        "text": row["power_text"],
        "color": row["color"],
        "trigger": power_triggers.get(row["color"])
    }
    powers_data.append(power_dict)

powers = pd.DataFrame(powers_data)
powers["bird_id"] = [i for i in range(1, len(powers_data) + 1)]
powers["data"] = powers.text.apply(lambda x: parse_text(x) if pd.notna(x) else None)
powers = powers[["bird_id", "text", "color", "trigger", "data"]]
powers_dict = powers.set_index('bird_id').to_dict('index')
_write("powers", {str(bird_id): power for bird_id, power in powers_dict.items()})