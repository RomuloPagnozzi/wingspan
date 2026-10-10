"""Food cost payment: any 2 food tokens stand in for 1 missing food (they need not match)."""

from wingspan.engine.utils import can_afford_bird_cost, generate_food_payments


def _payments(cost: dict, food: dict) -> list[dict]:
    return sorted(
        (dict(sorted(p.items())) for p in generate_food_payments([cost], food)),
        key=str,
    )


def test_two_mixed_tokens_pay_for_one_missing_food():
    assert _payments({"fish": 1}, {"seed": 1, "fruit": 1}) == [{"fruit": 1, "seed": 1}]
    assert can_afford_bird_cost(((("fish", 1),),), {"seed": 1, "fruit": 1})


def test_one_token_cannot_pay_for_missing_food():
    assert _payments({"fish": 1}, {"seed": 1}) == []
    assert not can_afford_bird_cost(((("fish", 1),),), {"seed": 1})


def test_exact_match_used_before_trading():
    assert _payments({"fish": 1}, {"fish": 1, "seed": 2}) == [{"fish": 1}]


def test_trade_and_wild_draw_from_same_pool():
    # fish missing (2 tokens) + wild (1 token) = any 3 of the 4 held tokens
    assert _payments({"fish": 1, "wild": 1}, {"seed": 2, "fruit": 1, "rodent": 1}) == [
        {"fruit": 1, "rodent": 1, "seed": 1},
        {"fruit": 1, "seed": 2},
        {"rodent": 1, "seed": 2},
    ]
    assert not can_afford_bird_cost(
        ((("fish", 1), ("wild", 1)),), {"seed": 1, "fruit": 1}
    )
