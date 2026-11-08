# wingspan.ai

Game-playing strategies: `Strategy.select_action(state, legal_actions) -> Action`. Built by name with
`create_strategy(name, **params)` (configs do this); each class registers itself with `@register_strategy`.

| File | Role |
|------|------|
| `base.py` | `Strategy`, `ValueFunction`, the registry, `create_strategy` |
| `random.py` | uniform random moves (`random`) |
| `mcts.py` | MCTS in Python (`mcts`): UCB1, progressive widening, IS-MCTS determinization; the web app's bot |
| `rust.py` | the tree search run by the Rust engine (`mcts_rs`, tuned params as defaults) and the state export it uses; imported when the extension is built |
| `bots.yaml`, `bots.py` | the web app's bot roster; `champion` is the one new games face |
| `encoding.py`, `nets.py` | observation and action encoding for the networks; the networks |

Fixed seeds make every strategy deterministic: same game seed and strategy seed, same moves.
