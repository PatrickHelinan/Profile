"""Generate the two figures for the README from hydraulic_inventory.

Usage:  python make_figures.py [Q_m3_per_day]
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import hydraulic_inventory as hi

Q = float(sys.argv[1]) if len(sys.argv) > 1 else 1000.0
OUT = Path(__file__).resolve().parent / "figures"
OUT.mkdir(exist_ok=True)

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e2"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]  # fixed order: stage 1, 2, 3

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
})

out = hi.compare(Q)
scen = [out["candidate"]] + out["references"]

# --- Figure 1: stacked stage inventory per scenario -------------------------
fig, ax = plt.subplots(figsize=(7.2, 3.6))
labels = [s["scenario"].replace(" (design reference)", "\n(design reference)").replace(" (M20 batch sequence)", "\n(M20 batch sequence)") for s in scen]
y = range(len(scen))
for i, s in enumerate(scen):
    left = 0.0
    for j, (name, v) in enumerate(s["stage_volumes_m3"].items()):
        ax.barh(i, v, left=left, color=SERIES[j], height=0.55, edgecolor=SURFACE, linewidth=2)
        left += v
    ax.text(left + max(x["total_volume_m3"] for x in scen) * 0.01, i, f"{s['total_volume_m3']:.1f} m³", va="center", color=INK, fontsize=10)
ax.set_yticks(list(y)); ax.set_yticklabels(labels, color=INK)
ax.invert_yaxis()
ax.set_xlabel(f"Nominal hydraulic inventory, m³ per {Q:g} m³/d")
ax.xaxis.grid(True, color=GRID, linewidth=0.8); ax.set_axisbelow(True)
ax.tick_params(length=0)
# legend: stages in order (names differ by scenario, so describe position)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color=SERIES[0], label="Stage 1 (mixing / flocculation)"),
                   Patch(color=SERIES[1], label="Stage 2 (contact / clarification)"),
                   Patch(color=SERIES[2], label="Stage 3 (magnetic treatment)")],
          loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=3, frameon=False, fontsize=8)
ax.set_title("Stage-wise hydraulic inventory, V = Q·τ", loc="left", color=INK, fontsize=11)
fig.tight_layout(); fig.savefig(OUT / "fig1_inventory.png", dpi=180, bbox_inches="tight"); plt.close(fig)

# --- Figure 2: tornado on the M20 sequence ----------------------------------
rows = out["tornado"]
base = out["candidate"]["total_volume_m3"]
fig, ax = plt.subplots(figsize=(7.2, 3.0))
ax.set_xlim(-4.6, 6.2)
for i, r in enumerate(rows):
    ax.barh(i, r["low_total_m3"] - base, color=SERIES[0], height=0.55, edgecolor=SURFACE, linewidth=2)
    ax.barh(i, r["high_total_m3"] - base, color=SERIES[1], height=0.55, edgecolor=SURFACE, linewidth=2)
    ax.text(r["high_total_m3"] - base + 0.05, i, f"±{r['span_m3']/2:.2f} m³  ({r['share_of_base']:.0%} of τ)", va="center", color=INK, fontsize=9)
ax.axvline(0, color=INK2, linewidth=1)
ax.set_yticks(range(len(rows))); ax.set_yticklabels([r["stage"] for r in rows], color=INK)
ax.invert_yaxis(); ax.tick_params(length=0)
ax.set_xlabel(f"Change in total inventory from base {base:.1f} m³ when one stage moves ±50 %")
ax.xaxis.grid(True, color=GRID, linewidth=0.8); ax.set_axisbelow(True)
ax.legend(handles=[Patch(color=SERIES[0], label="−50 %"), Patch(color=SERIES[1], label="+50 %")], loc="upper center", bbox_to_anchor=(0.5, -0.35), ncol=2, frameon=False, fontsize=8.5)
ax.set_title("Sensitivity of M20 inventory to stage duration", loc="left", color=INK, fontsize=11)
fig.tight_layout(); fig.savefig(OUT / "fig2_tornado.png", dpi=180, bbox_inches="tight"); plt.close(fig)
print("wrote", OUT)
