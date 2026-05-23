"""HTML report builder for parquet game results.

Usage:
    uv run python -m lab.analysis                                  # experiments/data/games.parquet → report.html
    uv run python -m lab.analysis path/to/games.parquet            # explicit path
    uv run python -m lab.analysis path/to/games.parquet -o out.html

All aggregations key on `arm_label` — the human-chosen identifier stamped at
write time by the runner. Position is a secondary axis (FPA sanity check).
"""

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import base64
from io import BytesIO
from datetime import datetime


def fig_to_base64(fig):
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=100)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return b64


def get_colors(n: int, palette: str = "mako") -> list[str]:
    colors = sns.color_palette(palette, n)
    return [f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}" for r, g, b in colors]


PALETTE = "mako"


def generate_report(parquet_path: str, output_path: str = "report.html"):
    df = pd.read_parquet(parquet_path)
    plots = []

    sns.set_theme(style="white")
    sns.set_context("notebook", font_scale=1.1)

    arms = sorted(df["arm_label"].unique())
    has_multi_arm = len(arms) > 1
    arm_colors = get_colors(len(arms), PALETTE)
    arm_palette = dict(zip(arms, arm_colors))

    player_positions = sorted(df["player_position"].unique())
    num_players = len(player_positions)

    score_components = [
        "bird_points",
        "egg_points",
        "cached_food",
        "tucked_cards",
        "round_goals",
        "bonus_scores",
    ]

    # === ARM STATS ===
    arm_stats = (
        df.groupby("arm_label")
        .agg(
            games=("game_id", "count"),
            wins=("is_winner", "sum"),
            mean_score=("total_score", "mean"),
            std_score=("total_score", "std"),
            min_score=("total_score", "min"),
            max_score=("total_score", "max"),
        )
        .reset_index()
        .sort_values("arm_label")
    )
    arm_stats["win_rate"] = arm_stats["wins"] / arm_stats["games"]

    # === SUMMARY STATS ===
    all_scores = df["total_score"]
    score_mean = all_scores.mean()
    score_std = all_scores.std()
    score_min = all_scores.min()
    score_max = all_scores.max()
    score_p25 = all_scores.quantile(0.25)
    score_p50 = all_scores.quantile(0.50)
    score_p75 = all_scores.quantile(0.75)
    score_p90 = all_scores.quantile(0.90)

    first_player_win_rate = df[df["is_first_player"]]["is_winner"].mean()

    # margin of victory per game
    game_scores = df.groupby("game_id")["total_score"].agg(
        lambda s: s.nlargest(2).iloc[0] - s.nlargest(2).iloc[1] if len(s) > 1 else 0
    )
    diff_p25 = game_scores.quantile(0.25)
    diff_p50 = game_scores.quantile(0.50)
    diff_p75 = game_scores.quantile(0.75)
    diff_p90 = game_scores.quantile(0.90)
    diff_max = game_scores.max()

    # === PLOTS ===

    # Win rate by arm
    if has_multi_arm:
        fig, ax = plt.subplots(figsize=(8, 5))
        bars = ax.bar(
            arm_stats["arm_label"],
            arm_stats["win_rate"],
            color=[arm_palette[a] for a in arm_stats["arm_label"]],
        )
        ax.set_ylabel("Win Rate")
        ax.set_xlabel("Arm")
        ax.set_title("Win Rate by Arm")
        ax.set_ylim(0, 1)
        for bar, rate in zip(bars, arm_stats["win_rate"]):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.02,
                f"{rate:.1%}",
                ha="center",
                fontsize=11,
            )
        sns.despine()
        plots.append(("Win Rate by Arm", fig_to_base64(fig)))

        # Score distribution by arm (box)
        fig, ax = plt.subplots(figsize=(8, 5))
        sns.boxplot(
            data=df,
            x="arm_label",
            y="total_score",
            hue="arm_label",
            palette=arm_palette,
            legend=False,
            order=arms,
            ax=ax,
        )
        ax.set_title("Score Distribution by Arm")
        ax.set_xlabel("Arm")
        ax.set_ylabel("Total Score")
        sns.despine()
        plots.append(("Score by Arm", fig_to_base64(fig)))

        # Score distribution by arm (KDE)
        fig, ax = plt.subplots(figsize=(8, 5))
        sns.kdeplot(
            data=df,
            x="total_score",
            hue="arm_label",
            hue_order=arms,
            palette=arm_palette,
            fill=True,
            common_norm=False,
            alpha=0.5,
            linewidth=0,
            ax=ax,
        )
        ax.set_title("Score Distribution by Arm (KDE)")
        sns.despine()
        plots.append(("Score Distribution by Arm", fig_to_base64(fig)))

    # First-player-advantage sanity check: win rate by position, faceted by arm.
    fpa_df = (
        df.groupby(["arm_label", "player_position"])["is_winner"]
        .mean()
        .reset_index(name="win_rate")
    )
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.barplot(
        data=fpa_df,
        x="arm_label",
        y="win_rate",
        hue="player_position",
        palette=get_colors(num_players, PALETTE),
        ax=ax,
    )
    ax.set_ylabel("Win Rate")
    ax.set_xlabel("Arm")
    ax.set_ylim(0, 1)
    ax.set_title("Win Rate by Arm × Position (FPA sanity check)")
    ax.legend(title="Position")
    sns.despine()
    plots.append(("Win Rate by Arm × Position", fig_to_base64(fig)))

    # Margin of victory
    fig, ax = plt.subplots()
    sns.kdeplot(
        data=game_scores,
        fill=True,
        alpha=0.5,
        linewidth=0,
        color=get_colors(1, PALETTE)[0],
        ax=ax,
    )
    ax.set_xlabel("Point Difference (Winner - Runner Up)")
    ax.set_xlim(0, diff_max * 1.05)
    ax.set_title("Margin of Victory Distribution")
    sns.despine()
    plots.append(("Margin of Victory", fig_to_base64(fig)))

    # Score composition by arm (stacked bar), sorted by top arm's component means
    win_by_arm = df.groupby("arm_label")["is_winner"].mean()
    top_arm = win_by_arm.idxmax()
    top_arm_df = df[df["arm_label"] == top_arm]
    component_means_top = [(c, top_arm_df[c].mean()) for c in score_components]
    component_means_top.sort(key=lambda x: x[1], reverse=True)
    score_components_sorted = [c for c, _ in component_means_top]

    composition_data = []
    for arm in arms:
        sub = df[df["arm_label"] == arm]
        for c in score_components_sorted:
            composition_data.append(
                {"Arm": arm, "Category": c, "Mean Points": sub[c].mean()}
            )
    composition_df = pd.DataFrame(composition_data)
    fig, ax = plt.subplots(figsize=(8, 5))
    composition_pivot = composition_df.pivot(
        index="Arm", columns="Category", values="Mean Points"
    )[score_components_sorted]
    component_colors = get_colors(len(score_components_sorted), PALETTE)
    composition_pivot.plot(kind="bar", stacked=True, color=component_colors, ax=ax)
    ax.set_ylabel("Mean Total Score")
    ax.set_title("Score Composition by Arm")
    ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1))
    ax.set_xticklabels(ax.get_xticklabels(), rotation=0)
    sns.despine()
    plots.append(("Score Composition", fig_to_base64(fig)))

    # Correlation heatmap (top arm)
    corr_matrix = top_arm_df[score_components_sorted].corr()
    fig, ax = plt.subplots(figsize=(8, 6))
    sns.heatmap(
        corr_matrix,
        cmap="RdBu_r",
        center=0,
        vmin=-1,
        vmax=1,
        annot=True,
        fmt=".2f",
        ax=ax,
    )
    ax.set_title(f"Score Component Correlation ({top_arm})")
    plots.append(("Correlation Heatmap", fig_to_base64(fig)))

    # === WIN RATE BOXES ===
    win_rate_boxes = ""
    for arm in arms:
        sub = df[df["arm_label"] == arm]
        wr = sub["is_winner"].mean()
        win_rate_boxes += f"""
        <div class="stat-box">
            <div class="stat-value">{wr:.1%}</div>
            <div class="stat-label">{arm} Win Rate</div>
        </div>"""

    # === ARM SUMMARY HTML ===
    arm_summary_html = ""
    if has_multi_arm:
        arm_summary_html = "<h2>Arm Performance</h2><div class='stat-grid'>"
        for _, row in arm_stats.iterrows():
            arm_summary_html += f"""
            <div class="stat-box">
                <div class="stat-value">{row['win_rate']:.1%}</div>
                <div class="stat-label">{row['arm_label']}<br>
                    <small>μ={row['mean_score']:.1f}, n={row['games']}</small>
                </div>
            </div>"""
        arm_summary_html += "</div>"

    num_games = df["game_id"].nunique()
    arm_info = f" | Arms: {', '.join(arms)}"

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Wingspan Analysis Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }}
        h1 {{ border-bottom: 2px solid #333; padding-bottom: 10px; }}
        h2 {{ color: #555; margin-top: 40px; }}
        .stat-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
        .stat-box {{ background: #f5f5f5; padding: 20px; border-radius: 8px; text-align: center; }}
        .stat-value {{ font-size: 2em; font-weight: bold; color: #333; }}
        .stat-label {{ color: #666; margin-top: 5px; }}
        .stat-label small {{ font-size: 0.8em; color: #888; }}
        img {{ max-width: 100%; height: auto; margin: 20px 0; }}
        .plot-container {{ margin: 30px 0; }}
    </style>
</head>
<body>
    <h1>Wingspan Analysis Report</h1>
    <p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | Games: {num_games} | Players: {num_players}{arm_info}</p>

    {arm_summary_html}

    <h2>Overall Score Analysis</h2>
    <div class="stat-grid">
        <div class="stat-box"><div class="stat-value">{score_mean:.1f}</div><div class="stat-label">Mean Score</div></div>
        <div class="stat-box"><div class="stat-value">{score_std:.1f}</div><div class="stat-label">Std Dev</div></div>
        <div class="stat-box"><div class="stat-value">{score_p25:.0f}</div><div class="stat-label">25th Percentile</div></div>
        <div class="stat-box"><div class="stat-value">{score_p50:.0f}</div><div class="stat-label">50th Percentile</div></div>
        <div class="stat-box"><div class="stat-value">{score_p75:.0f}</div><div class="stat-label">75th Percentile</div></div>
        <div class="stat-box"><div class="stat-value">{score_p90:.0f}</div><div class="stat-label">90th Percentile</div></div>
        <div class="stat-box"><div class="stat-value">{score_max:.0f}</div><div class="stat-label">Max Score</div></div>
    </div>

    <h2>Win Statistics</h2>
    <div class="stat-grid">{win_rate_boxes}
        <div class="stat-box">
            <div class="stat-value">{first_player_win_rate:.1%}</div>
            <div class="stat-label">First Player Wins</div>
        </div>
    </div>

    <h2>Game Closeness</h2>
    <div class="stat-grid">
        <div class="stat-box"><div class="stat-value">{diff_p25:.0f} pts</div><div class="stat-label">25th Percentile</div></div>
        <div class="stat-box"><div class="stat-value">{diff_p50:.0f} pts</div><div class="stat-label">50th Percentile</div></div>
        <div class="stat-box"><div class="stat-value">{diff_p75:.0f} pts</div><div class="stat-label">75th Percentile</div></div>
        <div class="stat-box"><div class="stat-value">{diff_p90:.0f} pts</div><div class="stat-label">90th Percentile</div></div>
        <div class="stat-box"><div class="stat-value">{diff_max:.0f} pts</div><div class="stat-label">Max Difference</div></div>
    </div>

    <h2>Distributions</h2>
"""

    for title, b64 in plots:
        html += f"""
    <div class="plot-container">
        <h3>{title}</h3>
        <img src="data:image/png;base64,{b64}" alt="{title}">
    </div>
"""

    html += "</body>\n</html>\n"

    with open(output_path, "w") as f:
        f.write(html)

    print(f"Report generated: {output_path}")


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Generate analysis report from game results"
    )
    parser.add_argument(
        "parquet_path",
        nargs="?",
        default="experiments/data/games.parquet",
        help="Path to games.parquet file",
    )
    parser.add_argument(
        "-o", "--output", help="Output HTML path (default: report.html)"
    )
    args = parser.parse_args()

    parquet_path = Path(args.parquet_path)
    output_path = args.output or "report.html"
    generate_report(str(parquet_path), output_path)
