"""
Hydraulic inventory calculator for post-precipitation separation stages.

Reference implementation of the prospective hydraulic-intensity analysis in
Paper A (He et al., magnetic nanocoagulation, Section 2.5 / 3.5). All
formulas here are deliberately simple so that every reported number can be
checked by hand:

    tau_eq      = sum of stage durations                     [min]
    V_nom       = Q * tau_eq / 1440                           [m3]   (Q in m3/d)
    V_stage_i   = Q * tau_i  / 1440                           [m3]
    ratio       = V_reference / V_candidate                   [-]

Everything beyond that block (footprint, nanocoagulant inventory, optional
cost) is a parametric *extension* with user-supplied assumptions. It is
not part of the paper and is labelled as such in the outputs.

Boundary: the calcium-precipitation and ageing steps upstream of the
separation stage are excluded, matching the paper. The continuous-flow
translation assumes equivalent treatment performance at the same nominal
HRT; it is a design-screening estimate, not a validated reactor design.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

MIN_PER_DAY = 1440.0


class InputError(ValueError):
    """Raised for inputs that cannot produce a meaningful result."""


@dataclass(frozen=True)
class Stage:
    name: str
    duration_min: float


@dataclass(frozen=True)
class Scenario:
    name: str
    stages: List[Stage]
    source: str = ""

    @property
    def tau_eq_min(self) -> float:
        return sum(s.duration_min for s in self.stages)


# --- Reference scenarios -------------------------------------------------

#: Demonstrated M20 batch sequence (Paper A, Section 2.5).
M20_BATCH = Scenario(
    "Magnetic nanocoagulation (M20 batch sequence)",
    [Stage("Mixing", 2.0), Stage("Field-free contact", 5.0), Stage("Magnetic treatment", 10.0)],
    source="Paper A experiment; 2 + 5 + 10 min",
)

#: Design-reference cases from Virginia Administrative Code 9VAC25-790-850
#: (chemical clarification), as used in Paper A for context.
REACTOR_CLARIFIER = Scenario(
    "Reactor-clarifier (design reference)",
    [Stage("Flocculation / mixing", 30.0), Stage("Clarification", 120.0)],
    source="9VAC25-790-850, reactor-clarifier: 30 + 120 min",
)
CONVENTIONAL_CLARIFICATION = Scenario(
    "Conventional clarification (design reference)",
    [Stage("Flocculation", 20.0), Stage("Settling", 240.0)],
    source="9VAC25-790-850, separate units: 20 + 240 min",
)

REFERENCE_SCENARIOS = [REACTOR_CLARIFIER, CONVENTIONAL_CLARIFICATION]


# --- Validation ----------------------------------------------------------

def validate_flow(q_m3_per_day: float) -> List[str]:
    warnings: List[str] = []
    if q_m3_per_day is None:
        raise InputError("Flow is missing.")
    if not isinstance(q_m3_per_day, (int, float)) or q_m3_per_day != q_m3_per_day:  # NaN
        raise InputError("Flow must be a number in m3/d.")
    if q_m3_per_day <= 0:
        raise InputError("Flow must be positive (m3/d).")
    if q_m3_per_day > 1_000_000:
        warnings.append("Flow above 1,000,000 m3/d — check units (m3/d, not m3/h or L/s).")
    return warnings


def validate_scenario(sc: Scenario) -> List[str]:
    warnings: List[str] = []
    if not sc.stages:
        raise InputError(f"Scenario '{sc.name}' has no stages.")
    for st in sc.stages:
        if st.duration_min is None or st.duration_min != st.duration_min:
            raise InputError(f"Stage '{st.name}' duration is missing.")
        if st.duration_min < 0:
            raise InputError(f"Stage '{st.name}' duration cannot be negative.")
        if st.duration_min == 0:
            warnings.append(f"Stage '{st.name}' has zero duration and contributes no volume.")
        if st.duration_min > MIN_PER_DAY:
            warnings.append(f"Stage '{st.name}' exceeds 24 h — check units (minutes, not seconds).")
    if sc.tau_eq_min > 12 * 60:
        warnings.append(f"Scenario '{sc.name}' total HRT exceeds 12 h; outside the screening range of this tool.")
    return warnings


# --- Core calculation ----------------------------------------------------

def stage_volume_m3(q_m3_per_day: float, duration_min: float) -> float:
    """V = Q * tau, with tau converted from minutes to days."""
    return q_m3_per_day * duration_min / MIN_PER_DAY


@dataclass
class InventoryResult:
    scenario: str
    q_m3_per_day: float
    tau_eq_min: float
    stage_volumes_m3: Dict[str, float]
    total_volume_m3: float
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def hydraulic_inventory(q_m3_per_day: float, sc: Scenario) -> InventoryResult:
    warnings = validate_flow(q_m3_per_day) + validate_scenario(sc)
    vols = {st.name: stage_volume_m3(q_m3_per_day, st.duration_min) for st in sc.stages}
    return InventoryResult(
        scenario=sc.name,
        q_m3_per_day=q_m3_per_day,
        tau_eq_min=sc.tau_eq_min,
        stage_volumes_m3=vols,
        total_volume_m3=sum(vols.values()),
        warnings=warnings,
    )


def inventory_ratio(reference: InventoryResult, candidate: InventoryResult) -> float:
    """How many times larger the reference inventory is than the candidate."""
    if candidate.total_volume_m3 <= 0:
        raise InputError("Candidate inventory is zero; ratio undefined.")
    return reference.total_volume_m3 / candidate.total_volume_m3


# --- Extensions (user-supplied assumptions; not from the paper) ----------

def footprint_m2(volume_m3: float, water_depth_m: float) -> float:
    """Plan area for a given water depth. Ignores freeboard and walls."""
    if water_depth_m <= 0:
        raise InputError("Water depth must be positive.")
    return volume_m3 / water_depth_m


@dataclass
class NanocoagulantInventory:
    """Mass of nanocoagulant in circulation and daily make-up.

    dose_g_per_m3        : dose per treated volume (user assumption)
    reuse_fraction       : fraction of inventory recovered per cycle, 0–1
    cycles_per_day       : treatment cycles per day in the batch frame
    """
    dose_g_per_m3: float
    reuse_fraction: float
    q_m3_per_day: float

    def __post_init__(self) -> None:
        if self.dose_g_per_m3 < 0:
            raise InputError("Dose cannot be negative.")
        if not 0 <= self.reuse_fraction <= 1:
            raise InputError("Reuse fraction must be between 0 and 1.")

    @property
    def gross_demand_kg_per_day(self) -> float:
        """Nanocoagulant contacted with water per day if nothing were recovered."""
        return self.dose_g_per_m3 * self.q_m3_per_day / 1000.0

    @property
    def makeup_kg_per_day(self) -> float:
        """Fresh make-up needed to replace what is not recovered."""
        return self.gross_demand_kg_per_day * (1.0 - self.reuse_fraction)


# --- Sensitivity ---------------------------------------------------------

def tornado(q_m3_per_day: float, sc: Scenario, swing: float = 0.5) -> List[dict]:
    """One-at-a-time sensitivity of total inventory to each stage duration.

    Returns rows sorted by absolute span, largest first. Because V is linear
    in each duration, the result is exact and symmetric; it is still useful
    to show which stage dominates.
    """
    base = hydraulic_inventory(q_m3_per_day, sc).total_volume_m3
    rows = []
    for st in sc.stages:
        lo = sc.tau_eq_min - st.duration_min * swing
        hi = sc.tau_eq_min + st.duration_min * swing
        v_lo = q_m3_per_day * lo / MIN_PER_DAY
        v_hi = q_m3_per_day * hi / MIN_PER_DAY
        rows.append({
            "stage": st.name,
            "base_duration_min": st.duration_min,
            "low_total_m3": v_lo,
            "high_total_m3": v_hi,
            "span_m3": v_hi - v_lo,
            "share_of_base": st.duration_min / sc.tau_eq_min if sc.tau_eq_min else 0.0,
        })
    rows.sort(key=lambda r: -abs(r["span_m3"]))
    return rows


# --- Convenience ---------------------------------------------------------

def compare(q_m3_per_day: float, candidate: Scenario = M20_BATCH,
            references: Optional[List[Scenario]] = None) -> dict:
    references = references or REFERENCE_SCENARIOS
    cand = hydraulic_inventory(q_m3_per_day, candidate)
    refs = [hydraulic_inventory(q_m3_per_day, r) for r in references]
    return {
        "candidate": cand.as_dict(),
        "references": [
            {**r.as_dict(), "ratio_to_candidate": inventory_ratio(r, cand)} for r in refs
        ],
        "tornado": tornado(q_m3_per_day, candidate),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(compare(1000.0), indent=2))
