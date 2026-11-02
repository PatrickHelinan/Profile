"""
Carbon data audit for a post-precipitation separation stage.

Compares two separation routes for the same fine-CaF2 suspension, per 1000 m3
treated:

  M  magnetic nanocoagulation  (mixing -> field-free contact -> magnetic treatment)
  C  conventional chemical clarification (flocculation -> settling)

Emission sources (GHG Protocol / ISO 14064-1:2018 categories):
  Scope 2   electricity for mixers, magnet, scrapers, pumps        (ISO cat. 2)
  Scope 3.1 purchased chemicals: nanocoagulant make-up, coagulant,
            polymer                                                 (ISO cat. 4)
  Scope 3.5 sludge transport and disposal                           (ISO cat. 4)
  Scope 1   none. A chemical separation stage has no biological
            CH4/N2O source (IPCC 2019 Vol.5 Ch.6 applies to
            biological treatment). Reported explicitly as 0 with
            the reason, never omitted.

Electricity is estimated from nameplate power x load factor x running time
(the user's chosen method). Every factor is looked up from factors.json and
carries source, year, region, boundary and status. A factor with status
'gap' is never defaulted: the line is reported as MISSING and the total is
flagged incomplete.

Boundary: separation stage only; upstream calcium precipitation (CaCl2 dosing,
reaction, ageing) is identical for both routes and excluded. The CaF2 sludge
mass itself is identical for both routes and is excluded from the
comparison; only the route-specific *additional* solids (hydroxide sludge,
lost nanocoagulant) are counted.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

FACTORS_PATH = Path(__file__).resolve().parents[1] / "shared" / "factors.json"


class InputError(ValueError):
    pass


def load_factors(path: Path = FACTORS_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- inputs

@dataclass(frozen=True)
class Equipment:
    """Nameplate-based electricity estimate for one unit."""
    name: str
    nameplate_kw: float          # installed power per 1000 m3/d capacity
    load_factor: float           # 0–1, fraction of nameplate drawn on average
    hours_per_1000m3: float      # running hours to treat 1000 m3

    def kwh(self) -> float:
        return self.nameplate_kw * self.load_factor * self.hours_per_1000m3


@dataclass(frozen=True)
class Chemical:
    name: str
    kg_per_1000m3: float
    factor_key: Optional[str]            # key in factors['chemicals'], or None if user-supplied
    user_factor: Optional[float] = None  # kg CO2e/kg, used when factor_key is None or gap
    user_factor_source: str = ""


@dataclass(frozen=True)
class Sludge:
    name: str
    t_wet_per_1000m3: float
    haul_km: Optional[float] = None


@dataclass
class Route:
    name: str
    equipment: List[Equipment]
    chemicals: List[Chemical]
    sludge: List[Sludge]
    notes: str = ""


# ---------------------------------------------------------------- validation

def _num(x, label: str) -> float:
    if x is None or (isinstance(x, float) and x != x):
        raise InputError(f"{label} is missing.")
    if not isinstance(x, (int, float)):
        raise InputError(f"{label} must be a number.")
    return float(x)


def validate_route(r: Route) -> List[str]:
    w: List[str] = []
    for e in r.equipment:
        for lbl, v in (("nameplate_kw", e.nameplate_kw), ("load_factor", e.load_factor), ("hours_per_1000m3", e.hours_per_1000m3)):
            v = _num(v, f"{r.name} / {e.name} / {lbl}")
            if v < 0:
                raise InputError(f"{r.name} / {e.name} / {lbl} cannot be negative.")
        if not 0 <= e.load_factor <= 1:
            raise InputError(f"{r.name} / {e.name}: load factor must be 0–1.")
        if e.hours_per_1000m3 > 240:
            w.append(f"{r.name} / {e.name}: {e.hours_per_1000m3} running hours per 1000 m3 — check units (hours, not minutes).")
        if e.nameplate_kw > 1000:
            w.append(f"{r.name} / {e.name}: nameplate above 1 MW per 1000 m3/d — check units (kW, not W).")
    for c in r.chemicals:
        v = _num(c.kg_per_1000m3, f"{r.name} / {c.name} / kg_per_1000m3")
        if v < 0:
            raise InputError(f"{r.name} / {c.name}: dose cannot be negative.")
        if v > 100_000:
            w.append(f"{r.name} / {c.name}: dose above 100 kg/m3 — check units (kg per 1000 m3 = g/m3).")
        if c.user_factor is not None and c.user_factor < 0:
            raise InputError(f"{r.name} / {c.name}: factor cannot be negative.")
    for s in r.sludge:
        v = _num(s.t_wet_per_1000m3, f"{r.name} / {s.name} / t_wet_per_1000m3")
        if v < 0:
            raise InputError(f"{r.name} / {s.name}: sludge mass cannot be negative.")
    return w


# ---------------------------------------------------------------- calculation

@dataclass
class Line:
    scope: str
    iso_category: str
    source: str
    activity: float
    activity_unit: str
    factor: Optional[float]
    factor_unit: str
    factor_source: str
    factor_status: str
    kg_co2e: Optional[float]

    @property
    def missing(self) -> bool:
        return self.kg_co2e is None


@dataclass
class RouteResult:
    route: str
    lines: List[Line]
    warnings: List[str] = field(default_factory=list)

    @property
    def total_kg_co2e(self) -> float:
        return sum(l.kg_co2e for l in self.lines if l.kg_co2e is not None)

    @property
    def missing_lines(self) -> List[Line]:
        return [l for l in self.lines if l.missing]

    @property
    def complete(self) -> bool:
        return not self.missing_lines

    def by_scope(self) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for l in self.lines:
            out[l.scope] = out.get(l.scope, 0.0) + (l.kg_co2e or 0.0)
        return out

    def as_dict(self) -> dict:
        return {
            "route": self.route,
            "total_kg_co2e_per_1000m3": self.total_kg_co2e,
            "kg_co2e_per_m3": self.total_kg_co2e / 1000.0,
            "complete": self.complete,
            "missing": [l.source for l in self.missing_lines],
            "by_scope": self.by_scope(),
            "lines": [asdict(l) for l in self.lines],
            "warnings": self.warnings,
        }


def _chem_factor(c: Chemical, factors: dict):
    """Return (value, unit, source, status) honouring the gap rule."""
    if c.factor_key:
        f = factors["chemicals"].get(c.factor_key)
        if f is None:
            raise InputError(f"Unknown factor key '{c.factor_key}'.")
        if f["status"] != "gap" and f["value"] is not None:
            return f["value"], f["unit"], f"{f['source']} ({f.get('year', '')}, {f.get('region', '')}, {f['boundary']})", f["status"]
        # gap: fall through to user factor
        if c.user_factor is not None:
            return c.user_factor, "kg CO2e/kg", c.user_factor_source or "user-supplied", "user"
        return None, f["unit"], f["source"], "gap"
    if c.user_factor is not None:
        return c.user_factor, "kg CO2e/kg", c.user_factor_source or "user-supplied", "user"
    return None, "kg CO2e/kg", "no factor given", "gap"


def audit(route: Route, grid_key: str, factors: Optional[dict] = None,
          sludge_disposal_factor: Optional[float] = None, sludge_disposal_source: str = "",
          transport_factor: Optional[float] = None, transport_source: str = "") -> RouteResult:
    factors = factors or load_factors()
    warnings = validate_route(route)
    g = factors["grid"].get(grid_key)
    if g is None:
        raise InputError(f"Unknown grid key '{grid_key}'.")
    lines: List[Line] = []

    # Scope 1 — explicit zero with reason
    lines.append(Line("Scope 1", "Cat. 1", "Process CH4/N2O", 0.0, "—", 0.0, "—",
                      "IPCC 2019 Vol.5 Ch.6 applies to biological treatment; chemical separation has no process gas source",
                      "n/a", 0.0))

    # Scope 2 — electricity
    for e in route.equipment:
        kwh = e.kwh()
        lines.append(Line("Scope 2", "Cat. 2", f"Electricity — {e.name}", kwh, "kWh/1000 m3", g["value"], g["unit"],
                          f"{g['source']} ({g['boundary']})", g["status"], kwh * g["value"]))

    # Scope 3.1 — chemicals
    for c in route.chemicals:
        val, unit, src, status = _chem_factor(c, factors)
        lines.append(Line("Scope 3.1", "Cat. 4", f"Chemical — {c.name}", c.kg_per_1000m3, "kg/1000 m3", val, unit, src, status,
                          None if val is None else c.kg_per_1000m3 * val))

    # Scope 3.5 — sludge
    for s in route.sludge:
        if sludge_disposal_factor is None:
            lines.append(Line("Scope 3.5", "Cat. 4", f"Sludge disposal — {s.name}", s.t_wet_per_1000m3, "t wet/1000 m3", None,
                              "kg CO2e/t", factors["sludge"]["landfill_inert"]["source"], "gap", None))
        else:
            lines.append(Line("Scope 3.5", "Cat. 4", f"Sludge disposal — {s.name}", s.t_wet_per_1000m3, "t wet/1000 m3",
                              sludge_disposal_factor, "kg CO2e/t", sludge_disposal_source or "user-supplied", "user",
                              s.t_wet_per_1000m3 * sludge_disposal_factor))
        if s.haul_km is not None:
            tkm = s.t_wet_per_1000m3 * s.haul_km
            if transport_factor is None:
                lines.append(Line("Scope 3.5", "Cat. 4", f"Sludge transport — {s.name}", tkm, "t.km/1000 m3", None,
                                  "kg CO2e/t.km", factors["sludge"]["transport_hgv"]["source"], "gap", None))
            else:
                lines.append(Line("Scope 3.5", "Cat. 4", f"Sludge transport — {s.name}", tkm, "t.km/1000 m3",
                                  transport_factor, "kg CO2e/t.km", transport_source or "user-supplied", "user",
                                  tkm * transport_factor))
    return RouteResult(route.name, lines, warnings)


# ---------------------------------------------------------------- helpers

def hydroxide_sludge_kg(fecl3_kg: float, factors: dict) -> float:
    """Dry Fe(OH)3 produced from anhydrous FeCl3 dosed, by stoichiometry."""
    return fecl3_kg * factors["stoichiometry"]["FeCl3_to_FeOH3"]["value"]


def nanocoagulant_makeup_kg(dose_g_per_m3: float, reuse_fraction: float, m3: float = 1000.0) -> float:
    if not 0 <= reuse_fraction <= 1:
        raise InputError("Reuse fraction must be 0–1.")
    return dose_g_per_m3 * m3 / 1000.0 * (1.0 - reuse_fraction)


def mixer_power_from_G(G_per_s: float, volume_m3: float, mu_pa_s: float = 1.0e-3) -> float:
    """Camp–Stein: P = G^2 * mu * V, in W (water power at the impeller)."""
    return G_per_s ** 2 * mu_pa_s * volume_m3


def pump_power_w(q_m3_per_s: float, head_m: float, eff: float = 0.5, rho: float = 1000.0) -> float:
    """Hydraulic power / wire-to-water efficiency, in W."""
    if eff <= 0 or eff > 1:
        raise InputError("Pump efficiency must be in (0, 1].")
    return rho * 9.81 * q_m3_per_s * head_m / eff


IEC_MOTORS_KW = [0.18, 0.25, 0.37, 0.55, 0.75, 1.1, 1.5, 2.2, 3.0, 4.0, 5.5, 7.5]


def nameplate_from_shaft_w(shaft_w: float, drive_eff: float = 0.85) -> dict:
    """Round a required shaft power up to the next standard IEC motor size.
    Returns nameplate kW and the implied load factor (shaft / nameplate)."""
    need_kw = shaft_w / 1000.0 / drive_eff
    for kw in IEC_MOTORS_KW:
        if kw >= need_kw:
            return {"nameplate_kw": kw, "load_factor": need_kw / kw, "required_kw": need_kw}
    return {"nameplate_kw": need_kw, "load_factor": 1.0, "required_kw": need_kw}


# ---------------------------------------------------------------- Fe3O4 bottom-up estimate

M_FE, M_FECL2, M_FECL3, M_NAOH, M_FE3O4 = 55.845, 126.751, 162.204, 39.997, 231.533


def fe3o4_bottom_up(factors: dict, grid_key: str = "SG_2024",
                    naoh_excess: float = 0.20, water_l_per_kg: float = 20.0,
                    reaction_temp_c: float = 80.0, ambient_c: float = 25.0,
                    cake_water_kg_per_kg: float = 3.0, heat_eff: float = 0.80,
                    aux_kwh_per_kg: float = 0.5) -> dict:
    """Cradle-to-gate estimate, kg CO2e per kg Fe3O4, for aqueous coprecipitation:

        FeCl2 + 2 FeCl3 + 8 NaOH -> Fe3O4 + 8 NaCl + 4 H2O

    Every term is listed in the returned breakdown with its basis. This is a
    reference estimate for screening, not a measured LCA; the assumptions are
    the function arguments and are reported alongside the result.
    """
    mol = 1000.0 / M_FE3O4                       # mol Fe3O4 per kg
    fecl3_kg = 2 * mol * M_FECL3 / 1000.0        # anhydrous
    fecl2_kg = 1 * mol * M_FECL2 / 1000.0        # anhydrous
    naoh_kg = 8 * mol * M_NAOH / 1000.0 * (1 + naoh_excess)
    # factors
    f_fecl3_prod = factors["chemicals"]["FeCl3_40pct_iron_oxide_route"]["value"]   # per kg 40 % product
    f_fecl3 = f_fecl3_prod / 0.40                                                 # per kg anhydrous FeCl3
    f_per_fe = f_fecl3_prod / 0.138                                               # per kg Fe
    f_fecl2 = f_per_fe * (M_FE / M_FECL2)                                         # proxy: same burden per kg Fe
    f_naoh = factors["chemicals"]["NaOH"]["value"]
    g = factors["grid"][grid_key]["value"]
    # energy
    heat_mj = water_l_per_kg * 4.186e-3 * (reaction_temp_c - ambient_c) / heat_eff
    dry_mj = cake_water_kg_per_kg * 2.26 / heat_eff
    kwh = (heat_mj + dry_mj) / 3.6 + aux_kwh_per_kg
    parts = {
        "FeCl3 (anhydrous, INCOPA iron-oxide route / 0.40)": fecl3_kg * f_fecl3,
        "FeCl2 (anhydrous, proxied by FeCl3 per kg Fe)": fecl2_kg * f_fecl2,
        f"NaOH (stoichiometric + {naoh_excess:.0%} excess, Euro Chlor)": naoh_kg * f_naoh,
        f"Process energy ({kwh:.2f} kWh/kg at grid {grid_key})": kwh * g,
    }
    return {
        "value": sum(parts.values()),
        "unit": "kg CO2e/kg Fe3O4",
        "breakdown": parts,
        "reagents_kg_per_kg": {"FeCl3": fecl3_kg, "FeCl2": fecl2_kg, "NaOH": naoh_kg},
        "assumptions": {"naoh_excess": naoh_excess, "water_l_per_kg": water_l_per_kg, "reaction_temp_c": reaction_temp_c,
                        "cake_water_kg_per_kg": cake_water_kg_per_kg, "heat_eff": heat_eff, "aux_kwh_per_kg": aux_kwh_per_kg, "grid": grid_key},
        "excludes": "silica coating, packaging, transport, nano-specific processing, wastewater (NaCl brine) treatment",
    }


def compare(results: List[RouteResult]) -> dict:
    base = results[0]
    return {
        "routes": [r.as_dict() for r in results],
        "difference_vs_first_kg": [r.total_kg_co2e - base.total_kg_co2e for r in results],
        "all_complete": all(r.complete for r in results),
    }


def tornado(route: Route, grid_key: str, factors: dict, swing: float = 0.3, **kw) -> List[dict]:
    """One-at-a-time ±swing on each activity quantity. Chemicals and
    electricity are linear so this is exact; it ranks contributors."""
    base = audit(route, grid_key, factors, **kw).total_kg_co2e
    rows = []
    for i, e in enumerate(route.equipment):
        for s, tag in ((1 - swing, "lo"), (1 + swing, "hi")):
            pass
        lo_e = [Equipment(x.name, x.nameplate_kw * (1 - swing) if j == i else x.nameplate_kw, x.load_factor, x.hours_per_1000m3) for j, x in enumerate(route.equipment)]
        hi_e = [Equipment(x.name, x.nameplate_kw * (1 + swing) if j == i else x.nameplate_kw, x.load_factor, x.hours_per_1000m3) for j, x in enumerate(route.equipment)]
        lo = audit(Route(route.name, lo_e, route.chemicals, route.sludge), grid_key, factors, **kw).total_kg_co2e
        hi = audit(Route(route.name, hi_e, route.chemicals, route.sludge), grid_key, factors, **kw).total_kg_co2e
        rows.append({"item": f"Electricity — {e.name}", "lo": lo, "hi": hi, "span": hi - lo})
    for i, c in enumerate(route.chemicals):
        lo_c = [Chemical(x.name, x.kg_per_1000m3 * (1 - swing) if j == i else x.kg_per_1000m3, x.factor_key, x.user_factor, x.user_factor_source) for j, x in enumerate(route.chemicals)]
        hi_c = [Chemical(x.name, x.kg_per_1000m3 * (1 + swing) if j == i else x.kg_per_1000m3, x.factor_key, x.user_factor, x.user_factor_source) for j, x in enumerate(route.chemicals)]
        lo = audit(Route(route.name, route.equipment, lo_c, route.sludge), grid_key, factors, **kw).total_kg_co2e
        hi = audit(Route(route.name, route.equipment, hi_c, route.sludge), grid_key, factors, **kw).total_kg_co2e
        rows.append({"item": f"Chemical — {c.name}", "lo": lo, "hi": hi, "span": hi - lo})
    rows.sort(key=lambda r: -abs(r["span"]))
    return [{**r, "base": base} for r in rows]


def breakeven_reuse(route_m_non_chem_kg: float, route_c_total_kg: float, dose_g_per_m3: float,
                    fe3o4_factor: float) -> dict:
    """Reuse fraction at which route M equals route C on kg CO2e per 1000 m3,
    holding everything except nanocoagulant make-up fixed.

        make-up allowed = (C_total - M_non_chemical) / f_Fe3O4   [kg/1000 m3]
        reuse_be        = 1 - make-up allowed / dose              [-]
    """
    if fe3o4_factor <= 0 or dose_g_per_m3 <= 0:
        raise InputError("Factor and dose must be positive.")
    allowed = (route_c_total_kg - route_m_non_chem_kg) / fe3o4_factor
    reuse = 1.0 - allowed / dose_g_per_m3
    return {"allowed_makeup_kg_per_1000m3": allowed, "breakeven_reuse": reuse,
            "feasible": 0.0 <= reuse <= 1.0}


# ---------------------------------------------------------------- example

def reference_equipment(q_m3_per_day: float = 1000.0) -> Dict[str, dict]:
    """Reference nameplates when plant data are unavailable. Each entry
    records its engineering basis so the number can be challenged:

    - Mixers: Camp–Stein P = G²μV with textbook design G values
      (rapid mix 600 s⁻¹, flocculation / contact 50 s⁻¹; μ = 1e-3 Pa·s),
      stage volume from V = Qτ (Case A), drive efficiency 0.85, rounded up
      to the next IEC motor size.
    - Magnetic treatment: permanent-magnet drum, so only the drum drive is
      electrical; 0.75 kW drive at 0.6 load as a reference assumption
      (vendor brochures reviewed do not publish kW; an electromagnet would
      add coil power that must be entered separately).
    - Clarifier scraper: 0.37 kW drive at 0.8 load, reference assumption
      for a small circular clarifier.
    - Pumps: P = ρgQH/η with η = 0.5; recirculation 5 % of Q at 10 m head;
      sludge withdrawal 1 % of Q at 10 m head.
    - Feed pumping is common to both routes and excluded.
    """
    q = q_m3_per_day
    v = lambda tau_min: q * tau_min / 1440.0
    rm = nameplate_from_shaft_w(mixer_power_from_G(600, v(2)))
    cm = nameplate_from_shaft_w(mixer_power_from_G(50, v(5)))
    fl = nameplate_from_shaft_w(mixer_power_from_G(50, v(20)))
    rp = nameplate_from_shaft_w(pump_power_w(0.05 * q / 86400.0, 10.0))
    sp = nameplate_from_shaft_w(pump_power_w(0.01 * q / 86400.0, 10.0))
    return {
        "rapid_mix": {**rm, "basis": "Camp–Stein G=600 s⁻¹, V=1.39 m³"},
        "contact_mix": {**cm, "basis": "Camp–Stein G=50 s⁻¹, V=3.47 m³"},
        "mag_drum": {"nameplate_kw": 0.75, "load_factor": 0.6, "basis": "Permanent-magnet drum drive, reference assumption"},
        "recirc_pump": {**rp, "basis": "ρgQH/η, 5 % Q, 10 m, η=0.5"},
        "flocculator": {**fl, "basis": "Camp–Stein G=50 s⁻¹, V=13.9 m³"},
        "scraper": {"nameplate_kw": 0.37, "load_factor": 0.8, "basis": "Clarifier scraper drive, reference assumption"},
        "sludge_pump": {**sp, "basis": "ρgQH/η, 1 % Q, 10 m, η=0.5"},
    }


def example_routes(factors: dict, fe3o4_factor: Optional[float] = None, fe3o4_source: str = "",
                   dose_g_per_m3: float = 50.0, reuse_fraction: float = 0.81,
                   fecl3_g_per_m3: float = 30.0, pam_g_per_m3: float = 1.0, ds: float = 0.2) -> List[Route]:
    """Reference inputs. Equipment from reference_equipment(). Dose 50 g/m3 is
    the manuscripts' batch dose (50 mg/L). Reuse 0.81 per cycle is derived
    from Paper B: 65.9 % of initial inventory entered Cycle 3 after two
    recoveries, so 0.659**(1/2) = 0.81 if losses were equal per cycle — a
    derivation, not a measured per-cycle recovery."""
    E = reference_equipment()
    eq = lambda name, k: Equipment(name, E[k]["nameplate_kw"], E[k]["load_factor"], 24.0)
    mk = nanocoagulant_makeup_kg(dose_g_per_m3, reuse_fraction)
    M = Route(
        "Magnetic nanocoagulation (M20)",
        equipment=[eq("Rapid mixer (2 min stage)", "rapid_mix"), eq("Contact-tank mixer (5 min stage)", "contact_mix"),
                   eq("Magnetic drum drive (10 min stage)", "mag_drum"), eq("Recovery / recirculation pump", "recirc_pump")],
        chemicals=[Chemical("Fe3O4 nanocoagulant make-up", mk, "Fe3O4_nanocoagulant", fe3o4_factor, fe3o4_source)],
        sludge=[Sludge("Lost nanocoagulant in CaF2 sludge (wet t)", mk / 1000.0 / ds, haul_km=30.0)],
        notes=f"Reference nameplates (see reference_equipment); dose {dose_g_per_m3} g/m3 and reuse {reuse_fraction} are the manuscript batch dose and a per-cycle recovery derived from Paper B reuse data.",
    )
    C = Route(
        "Conventional chemical clarification",
        equipment=[eq("Flocculator (20 min stage)", "flocculator"), eq("Clarifier scraper (240 min stage)", "scraper"),
                   eq("Sludge withdrawal pump", "sludge_pump")],
        chemicals=[Chemical("FeCl3 (40 % solution)", fecl3_g_per_m3, "FeCl3_40pct_iron_oxide_route"), Chemical("PAM polymer", pam_g_per_m3, "PAM")],
        sludge=[Sludge("Hydroxide sludge (Fe(OH)3, wet t)", hydroxide_sludge_kg(fecl3_g_per_m3 * 0.4, factors) / 1000.0 / ds, haul_km=30.0)],
        notes=f"Reference nameplates; FeCl3 {fecl3_g_per_m3} g/m3 product and PAM {pam_g_per_m3} g/m3 are screening assumptions.",
    )
    return [M, C]


if __name__ == "__main__":
    f = load_factors()
    res = [audit(r, "SG_2024", f) for r in example_routes(f)]
    print(json.dumps(compare(res), indent=1, ensure_ascii=False))
