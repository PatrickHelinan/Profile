import json
import math
from pathlib import Path

import pytest

import hydraulic_inventory as hi

VECTORS = json.loads((Path(__file__).resolve().parents[1] / "shared" / "test_vectors.json").read_text())


def _scenario(stages: dict) -> hi.Scenario:
    return hi.Scenario("test", [hi.Stage(k, v) for k, v in stages.items()])


@pytest.mark.parametrize("case", VECTORS["cases"], ids=[c["id"] for c in VECTORS["cases"]])
def test_cases(case):
    res = hi.hydraulic_inventory(case["q_m3_per_day"], _scenario(case["stages"]))
    tol = case["tolerance"]
    exp = case["expect"]
    assert math.isclose(res.tau_eq_min, exp["tau_eq_min"], abs_tol=tol)
    assert math.isclose(res.total_volume_m3, exp["total_volume_m3"], abs_tol=tol)
    for k, v in exp.get("stage_volumes_m3", {}).items():
        assert math.isclose(res.stage_volumes_m3[k], v, abs_tol=tol)
    if "warning_contains" in exp:
        assert any(exp["warning_contains"] in w for w in res.warnings)


def test_paper_reference_ratios():
    case = next(c for c in VECTORS["cases"] if c["id"] == "paper_1000")
    out = hi.compare(case["q_m3_per_day"])
    exp = case["expect"]
    for r in out["references"]:
        assert math.isclose(r["total_volume_m3"], exp["reference_totals_m3"][r["scenario"]], abs_tol=1e-9)
        assert math.isclose(r["ratio_to_candidate"], exp["reference_ratios"][r["scenario"]], abs_tol=1e-9)
    # Rounded figures as reported in the manuscript text
    assert round(out["candidate"]["total_volume_m3"], 1) == exp["reported_rounded"]["total_volume_m3"]
    assert [round(r["ratio_to_candidate"], 1) for r in out["references"]] == exp["reported_rounded"]["ratios"]
    assert [round(r["total_volume_m3"], 1) for r in out["references"]] == exp["reported_rounded"]["reference_totals_m3"]


@pytest.mark.parametrize("case", VECTORS["errors"], ids=[c["id"] for c in VECTORS["errors"]])
def test_errors(case):
    with pytest.raises(hi.InputError) as e:
        hi.hydraulic_inventory(case["q_m3_per_day"], _scenario(case["stages"]))
    assert case["error_contains"] in str(e.value).lower()


@pytest.mark.parametrize("case", VECTORS["warnings"], ids=[c["id"] for c in VECTORS["warnings"]])
def test_warnings(case):
    res = hi.hydraulic_inventory(case["q_m3_per_day"], _scenario(case["stages"]))
    assert any(case["warning_contains"] in w for w in res.warnings)


def test_tornado_is_linear_and_ordered():
    rows = hi.tornado(1000, hi.M20_BATCH, swing=0.5)
    assert [r["stage"] for r in rows] == ["Magnetic treatment", "Field-free contact", "Mixing"]
    base = hi.hydraulic_inventory(1000, hi.M20_BATCH).total_volume_m3
    for r in rows:
        assert math.isclose(r["high_total_m3"] - base, base - r["low_total_m3"], abs_tol=1e-9)
    assert math.isclose(sum(r["share_of_base"] for r in rows), 1.0, abs_tol=1e-12)


def test_extensions():
    assert math.isclose(hi.footprint_m2(11.805555555555555, 3.0), 3.935185185185185)
    with pytest.raises(hi.InputError):
        hi.footprint_m2(10, 0)
    n = hi.NanocoagulantInventory(dose_g_per_m3=100, reuse_fraction=0.659, q_m3_per_day=1000)
    assert math.isclose(n.gross_demand_kg_per_day, 100.0)
    assert math.isclose(n.makeup_kg_per_day, 34.1)
    with pytest.raises(hi.InputError):
        hi.NanocoagulantInventory(100, 1.2, 1000)
