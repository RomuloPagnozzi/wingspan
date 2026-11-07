"""Builds wingspan-tensors.html: an interactive explainer of the encoder and the planned nets.

Replays decisions #115 to #118 of one mcts_joint_v2 game, encodes them with
`wingspan.ai.encoding`, and inlines the result into template.html.

    uv run python lab/explainer/screenshots.py   # optional: web UI screenshots (needs Chrome)
    uv run python lab/explainer/build.py
"""

import base64
import json
from pathlib import Path
import numpy as np
import pandas as pd
from wingspan.engine.core import initiate_state, BIRD_REGISTRY, BONUS_REGISTRY, init_registries, get_bonus_card
from wingspan.engine.actions import get_actions
from wingspan.engine.engine import transition_state
from wingspan.ai import encoding as E
from wingspan.web.session import catalog

init_registries()
D = 'experiments/tuning/mcts_joint_v2/'
d = pd.read_parquet(D + 'decisions.parquet')
games = pd.read_parquet(D + 'games.parquet')
gid = d.game_id.iloc[200000]
gd = d[d.game_id == gid].sort_values('decision_idx')
gg = games[games.game_id == gid]
WANT = {115, 116, 117, 118}

def r2(v): return [round(x, 3) for x in v]

def board_of(state, p):
    pl = state.players[p]
    out = []
    for h, row in zip(E.HABITATS, pl.board):
        for s in row:
            b = s.bird
            out.append(None if b is None else dict(id=b.id, name=b.card.name, eggs=b.state.eggs,
                       limit=b.card.egg_limit, cached=b.state.stashed_food, tucked=b.state.tucked_cards,
                       points=b.card.points, nest=b.card.nest if isinstance(b.card.nest, str) else None,
                       slot=f"{h}_{s.config.col}"))
    return out

def snapshot(state, viewer, row):
    acts = get_actions(state)
    by = {str(a): a for a in acts}
    visits = dict(row.visit_counts); qs = dict(row.mcts_action_values)
    obs = E.encode_obs(state, viewer)
    opp = 1 - viewer
    return dict(
        idx=int(row.decision_idx), phase=row.game_phase, round=int(row.round), viewer=viewer,
        taken=row.action_taken, root_value=round(float(row.mcts_root_value), 3), outcome=float(row.outcome),
        me=r2(obs.me), opp=r2(obs.opponents[0]), shared=r2(obs.shared),
        actions=[dict(s=s, kind=E.action_kind(a), vec=r2(E.encode_action(state, a)), visits=int(visits.get(s, 0)), q=round(float(qs.get(s, float("nan"))), 4))
                 for s, a in by.items()],
        boards=[board_of(state, viewer), board_of(state, opp)],
        hands=[[BIRD_REGISTRY[b].name for b in state.players[viewer].bird_hand], len(state.players[opp].bird_hand)],
        bonus=[[get_bonus_card(b).name for b in state.players[viewer].bonus_hand], len(state.players[opp].bonus_hand)],
        food=[dict(state.players[viewer].food), dict(state.players[opp].food)],
        tray=[BIRD_REGISTRY[b].name for b in state.bird_tray],
        feeder=[list(v) for v in state.feeder.values()],
        goals=list(state.round_goal_config.selected_goals),
        cubes=[state.players[viewer].action_cubes, state.players[opp].action_cubes],
        deck=len(state.bird_deck),
    )

s = initiate_state(2, seed=int(gd.game_seed.iloc[0]))
rows = iter(gd.itertuples()); r = next(rows); snaps = []
while (acts := get_actions(s)):
    if len(acts) == 1: s = transition_state(s, acts[0]); continue
    if r.decision_idx in WANT: snaps.append(snapshot(s, s.current_player_index, r))
    s = transition_state(s, {str(a): a for a in acts}[r.action_taken]); r = next(rows, None)
    if r is None: break

final = {int(x.player_position) - 1: dict(score=int(x.total_score), winner=bool(x.is_winner)) for x in gg.itertuples()}
birds = [dict(id=i, name=c.name, vec=r2(E.bird_table()[i])) for i, c in sorted(BIRD_REGISTRY.items())]
# The birds' 45 features projected to 3D with PCA: the directions along which birds differ most
X = np.array([b['vec'] for b in birds])
U, S_, Vt = np.linalg.svd(X - X.mean(0), full_matrices=False)
coords = U[:, :3] * S_[:3]
pca = dict(
    coords={b['id']: [round(float(v), 3) for v in c] for b, c in zip(birds, coords)},
    var=[round(float(v), 3) for v in (S_**2 / (S_**2).sum())[:3]],
    # the features that weigh most on each axis, with their sign
    axes=[[(E.bird_feature_names()[i], round(float(Vt[k, i]), 2)) for i in np.argsort(-abs(Vt[k]))[:3]] for k in range(3)],
)

out = dict(
    pca=pca,
    names=dict(player=E.player_feature_names(), shared=E.shared_feature_names(), action=E.action_feature_names(),
               bird=E.bird_feature_names(), bonus=E.bonus_feature_names()),
    birds=birds, snaps=snaps, final=final, game_id=gid,
    # What the web app draws: its card catalog and icons (src/wingspan/web/static)
    cards=catalog()['birds'],
    icons={f.stem: 'data:image/png;base64,' + base64.b64encode(f.read_bytes()).decode()
           for f in sorted(Path('src/wingspan/web/static/icons').glob('*.png'))},
    stats=dict(games=int(d.game_id.nunique()), decisions=len(d)),
)
HERE = Path(__file__).parent
# Screenshots of the web UI, if screenshots.py has been run: decision idx -> data URI
shots = {int(f.stem.split('-')[1]): 'data:image/webp;base64,' + base64.b64encode(f.read_bytes()).decode()
         for f in sorted((HERE / 'shots').glob('decision-*.webp'))}
page = ((HERE / 'template.html').read_text()
        .replace('/*__DATA__*/null', json.dumps(out, separators=(',', ':')))
        .replace('/*__SHOTS__*/null', json.dumps(shots or None)))
(HERE / 'wingspan-tensors.html').write_text(page)
print({k: len(v) for k, v in out['names'].items()}, [ (x['idx'], x['phase'], len(x['actions'])) for x in snaps], final)
