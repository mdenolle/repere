"""Figure 1 for the framework paper: the cost-vs-performance plane.

Each model contributes two points per eval — without the domain skill (hollow)
and with it (filled) — joined by an arrow. The arrow IS the skill lift, and its
*direction* carries the paper's thesis: for a locally-run model the arrow is
vertical (the skill buys score at no cost), while the cloud model sits to the
right (score bought with money).

Reads the live results in site/data/skill_lift.json. Writes PNG + PDF + CSV.

    pixi run -e full python scripts/make_paper_figure.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "site" / "data" / "skill_lift.json"
OUT = REPO / "paper" / "figures"

# Suite -> human label + panel order
SUITES = {
    "codameter": "E2 · dv/v processing\n(parameter selection)",
    "synthetic_stalta": "E1 · STA/LTA detection\n(code generation)",
}
COLORS = {
    "qwen2.5:7b": "#4b2e83",
    "llama3.1:8b": "#1b7f79",
    "deepseek-r1:7b": "#c2571a",
    "olmo2:7b": "#2f6fb2",
    "claude-haiku-4-5-20251001": "#8a1f5e",
}
LABEL = {
    "claude-haiku-4-5-20251001": "claude-haiku-4.5",
    "qwen2.5:7b": "qwen2.5:7b",
    "llama3.1:8b": "llama3.1:8b",
    "deepseek-r1:7b": "deepseek-r1:7b",
    "olmo2:7b": "olmo2:7b",
}
# Illustrative quality floor. It is a property of the task and the discipline;
# we draw it to make the frugality question visible, not to assert a universal.
FLOOR = 0.75


def main() -> int:
    rows = json.loads(DATA.read_text())["rows"]
    OUT.mkdir(parents=True, exist_ok=True)

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
    })
    # Two rows, one per cost axis. The headline claim -- free local models match
    # the cloud model on parameter selection -- rests entirely on a $0 x-axis,
    # and a reviewer will ask what the $0 is hiding. The answer is wall-clock
    # time, so the figure states it rather than waiting to be asked (issue #44).
    X_AXES = (
        ("cost_none_usd", "cost_full_usd", "cost per run (USD)", True),
        ("latency_none_s", "latency_full_s", "wall-clock latency per run (s)", False),
    )
    fig, axgrid = plt.subplots(
        len(X_AXES), 2, figsize=(9.2, 7.8), sharey=True, squeeze=False
    )

    for row_i, (kx0, kx1, xlabel, is_cost) in enumerate(X_AXES):
        for col_i, (suite, title) in enumerate(SUITES.items()):
            ax = axgrid[row_i][col_i]
            sub = [r for r in rows if r["suite"] == suite]
            if not all(isinstance(r.get(kx1), (int, float)) for r in sub):
                ax.text(0.5, 0.5, f"{xlabel}\nnot measured in this run",
                        ha="center", va="center", fontsize=8.5, color="#6f6890",
                        transform=ax.transAxes)
                ax.set_xticks([])
                continue
            xmax = max((r[kx1] for r in sub), default=0.01) * 1.35 or 0.01

            ax.axhspan(FLOOR, 1.02, color="#4b2e83", alpha=0.05, zorder=0)
            ax.axhline(FLOOR, color="#6d5bd0", ls="--", lw=1, zorder=1)
            ax.text(xmax * 0.985, FLOOR + 0.015, "quality floor", ha="right",
                    va="bottom", fontsize=7.5, color="#6d5bd0")

            # Every locally-run model costs exactly $0, so their arrows would land on
            # top of one another at x=0 and hide each other. Spread them across a
            # narrow, explicitly-labelled "$0 · local" lane. The offsets are a
            # drawing device, not a cost: the lane is annotated as zero so the figure
            # cannot be misread as charging for local inference.
            lane_w = xmax * 0.085
            free = [r for r in sub if is_cost and r[kx1] == 0 and r[kx0] == 0]
            slots = {r["model_id"]: i for i, r in enumerate(sorted(free, key=lambda r: r["model_id"]))}
            step = lane_w / max(len(slots), 1)

            if is_cost:
                ax.axvspan(-lane_w * 0.35, lane_w * 1.05, color="#1b7f79", alpha=0.045, zorder=0)
                ax.text(lane_w * 0.35, 1.035, "$0 · local", ha="center", va="bottom",
                        fontsize=7.2, color="#1b7f79")

            # Bind the loop-local lane geometry explicitly: a closure over `slots`/
            # `step` would late-bind to the final panel's values (ruff B023).
            def _x(model_id: str, cost: float, *, slots=slots, step=step) -> float:
                if cost == 0 and model_id in slots:
                    return slots[model_id] * step
                return cost

            for r in sub:
                c = COLORS.get(r["model_id"], "#666")
                x0 = _x(r["model_id"], r[kx0])
                x1 = _x(r["model_id"], r[kx1])
                y0, y1 = r["score_none"], r["score_full"]
                if abs(y1 - y0) > 0.005:  # a zero-lift arrow renders as a blob
                    ax.annotate(
                        "", xy=(x1, y1), xytext=(x0, y0),
                        arrowprops=dict(arrowstyle="-|>", color=c, lw=1.5,
                                        alpha=0.75, shrinkA=4, shrinkB=5),
                        zorder=2,
                    )
                # Error bars, where repeats exist. Without them this figure
                # draws an arrow between two point estimates, and on this data
                # some of those endpoints carry a +/- 34 to 42 pp interval --
                # wide enough that the arrow's direction is the claim, not its
                # length. A run with n=1 has no interval and gets no bar.
                for xv, yv, key in ((x0, y0, "score_none_ci95"), (x1, y1, "score_full_ci95")):
                    ci = r.get(key)
                    if isinstance(ci, (int, float)) and ci > 0:
                        ax.errorbar(
                            xv, yv, yerr=ci, fmt="none", ecolor=c, elinewidth=1.1,
                            capsize=2.5, capthick=1.1, alpha=0.65, zorder=2,
                        )
                ax.scatter([x0], [y0], s=42, facecolors="white", edgecolors=c,
                           linewidths=1.6, zorder=3)
                ax.scatter([x1], [y1], s=58, color=c, edgecolors="white",
                           linewidths=1.0, zorder=4)

            ax.set_xlim(-lane_w * 0.5, xmax)
            ax.set_ylim(-0.04, 1.06)
            if row_i == 0:
                    ax.set_title(title, fontsize=9.5, pad=8)
            ax.set_xlabel(xlabel)
            ax.grid(alpha=0.15, lw=0.6)

    for row in axgrid:
        row[0].set_ylabel("performance (deterministic score)")

    handles = [
        Line2D([], [], marker="o", ls="", color=COLORS[m], label=LABEL[m], ms=6)
        for m in COLORS
    ]
    handles += [
        Line2D([], [], marker="o", ls="", mfc="white", mec="#444",
               label="no skill", ms=6),
        Line2D([], [], marker="o", ls="", color="#444", label="skill loaded", ms=6),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=7, frameon=False,
               fontsize=7.6, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle(
        "Free local models match the cloud model on parameter selection — but you pay in wall-clock time, not dollars",
        fontsize=10, y=1.0,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 0.97))

    png, pdf = OUT / "fig1_cost_vs_performance.png", OUT / "fig1_cost_vs_performance.pdf"
    fig.savefig(png, dpi=300, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")

    csv_path = OUT / "fig1_data.csv"
    cols = ["suite", "category", "model_id", "openness", "skill_name", "skill_version",
            "score_none", "score_full", "lift", "cost_none_usd", "cost_full_usd", "n_total"]
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {png}\n      {pdf}\n      {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
