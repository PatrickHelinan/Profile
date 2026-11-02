"""Figures for the README. Reference inputs, Fe3O4 at the bottom-up
estimate, sludge factors set to 0 (gap shown separately)."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

import carbon_audit as ca

OUT = Path(__file__).resolve().parent / "figures"; OUT.mkdir(exist_ok=True)
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e2"
S = {"Scope 2": "#2a78d6", "Scope 3.1": "#eb6834", "Scope 3.5": "#1baf7a"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.spines.left": False, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE})

F = ca.load_factors()
EST = ca.fe3o4_bottom_up(F)["value"]
routes = ca.example_routes(F, fe3o4_factor=EST, fe3o4_source="bottom-up reference estimate")
res = [ca.audit(r, "SG_2024", F, sludge_disposal_factor=0.0, sludge_disposal_source="set to 0 — gap", transport_factor=0.0, transport_source="set to 0 — gap") for r in routes]

# Fig 1: stacked by scope
fig, ax = plt.subplots(figsize=(7.2, 3.0))
for i, r in enumerate(res):
    left = 0.0
    for sc, col in S.items():
        v = r.by_scope().get(sc, 0.0)
        ax.barh(i, v, left=left, color=col, height=0.55, edgecolor=SURFACE, linewidth=2); left += v
    ax.text(left + 1.5, i, f"{r.total_kg_co2e:.0f} kg CO₂e", va="center", color=INK)
ax.set_yticks(range(len(res))); ax.set_yticklabels([r.route.replace(" (M20)", "\n(M20)").replace(" chemical ", "\nchemical ") for r in res], color=INK)
ax.invert_yaxis(); ax.tick_params(length=0)
ax.set_xlabel(f"kg CO₂e per 1000 m³ · SG grid 2024 (0.401) · Fe₃O₄ {EST:.1f} kg CO₂e/kg (bottom-up) · dose 50 g/m³, reuse 0.81 · sludge = gap (0)", fontsize=8.5)
ax.xaxis.grid(True, color=GRID, linewidth=0.8); ax.set_axisbelow(True)
ax.legend(handles=[Patch(color=c, label=f"{k} ({'electricity' if k=='Scope 2' else 'chemicals' if k=='Scope 3.1' else 'sludge'})") for k, c in S.items()],
          loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=3, frameon=False, fontsize=8.5)
ax.set_title("Separation-stage emissions by scope (illustrative inputs)", loc="left", color=INK, fontsize=11)
fig.savefig(OUT / "fig1_by_scope.png", dpi=180, bbox_inches="tight"); plt.close(fig)

# Fig 2: tornado on route M
rows = ca.tornado(routes[0], "SG_2024", F, swing=0.3, sludge_disposal_factor=0.0, transport_factor=0.0)
base = rows[0]["base"]
fig, ax = plt.subplots(figsize=(7.2, 3.2))
for i, r in enumerate(rows):
    ax.barh(i, r["lo"] - base, color="#2a78d6", height=0.55, edgecolor=SURFACE, linewidth=2)
    ax.barh(i, r["hi"] - base, color="#eb6834", height=0.55, edgecolor=SURFACE, linewidth=2)
    ax.text(r["hi"] - base + 0.4, i, f"±{r['span']/2:.1f}", va="center", color=INK, fontsize=9)
ax.axvline(0, color=INK2, linewidth=1)
ax.set_yticks(range(len(rows))); ax.set_yticklabels([r["item"].replace("Electricity — ", "E: ").replace("Chemical — ", "C: ")[:38] for r in rows], color=INK, fontsize=9)
ax.invert_yaxis(); ax.tick_params(length=0)
ax.set_xlabel(f"Change in route-M total (base {base:.0f} kg CO₂e/1000 m³) when one activity moves ±30 %")
ax.xaxis.grid(True, color=GRID, linewidth=0.8); ax.set_axisbelow(True)
ax.legend(handles=[Patch(color="#2a78d6", label="−30 %"), Patch(color="#eb6834", label="+30 %")], loc="upper center", bbox_to_anchor=(0.5, -0.3), ncol=2, frameon=False, fontsize=8.5)
ax.set_title("What drives the magnetic route: nanocoagulant make-up", loc="left", color=INK, fontsize=11)
fig.savefig(OUT / "fig2_tornado.png", dpi=180, bbox_inches="tight"); plt.close(fig)

# Fig 3: route M total vs reuse fraction, with route C line and breakeven
import numpy as np
m_nonchem = res[0].total_kg_co2e - res[0].by_scope()["Scope 3.1"]
c_total = res[1].total_kg_co2e
reuse = np.linspace(0.5, 1.0, 101)
fig, ax = plt.subplots(figsize=(7.2, 3.2))
for dose, col, lab in [(50, "#2a78d6", "dose 50 g/m³ (manuscript)"), (25, "#1baf7a", "dose 25 g/m³"), (100, "#eb6834", "dose 100 g/m³")]:
    tot = m_nonchem + dose * (1 - reuse) * EST
    ax.plot(reuse * 100, tot, color=col, linewidth=2, label=lab)
ax.axhline(c_total, color=INK2, linewidth=1.2, linestyle="--")
ax.text(50.5, c_total + 2, f"route C = {c_total:.0f} kg CO₂e", color=INK2, fontsize=9)
be = ca.breakeven_reuse(m_nonchem, c_total, 50, EST)["breakeven_reuse"] * 100
ax.plot([be], [c_total], "o", color="#2a78d6", markersize=7, markeredgecolor=SURFACE)
ax.annotate(f"break-even {be:.1f} % at 50 g/m³", (be, c_total), xytext=(be - 36, c_total + 95), color=INK, fontsize=9, arrowprops=dict(arrowstyle="-", color=INK2))
ax.set_xlabel("Per-cycle reuse fraction of nanocoagulant, %"); ax.set_ylabel("Route M total, kg CO₂e / 1000 m³")
ax.set_ylim(0, None); ax.xaxis.grid(True, color=GRID, linewidth=0.8); ax.yaxis.grid(True, color=GRID, linewidth=0.8); ax.set_axisbelow(True); ax.tick_params(length=0)
ax.legend(loc="upper right", frameon=False, fontsize=8.5)
ax.set_title("Where the magnetic route beats conventional clarification on carbon", loc="left", color=INK, fontsize=11)
fig.savefig(OUT / "fig3_breakeven.png", dpi=180, bbox_inches="tight"); plt.close(fig)
print("wrote", OUT, [round(r.total_kg_co2e, 1) for r in res], "EST", round(EST, 2), "breakeven", round(be, 1))
