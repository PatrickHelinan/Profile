import math
import pytest

import carbon_audit as ca

F = ca.load_factors()


def test_factor_register_integrity():
    for group in ("grid", "chemicals", "sludge"):
        for k, f in F[group].items():
            assert "status" in f and "source" in f and "unit" in f, k
            if f["status"] == "gap":
                assert f["value"] is None, k
            else:
                assert isinstance(f["value"], (int, float)), k
    assert math.isclose(F["stoichiometry"]["FeCl3_to_FeOH3"]["value"], 106.87 / 162.20, rel_tol=2e-3)
    assert math.isclose(F["stoichiometry"]["Fe_fraction_in_Fe3O4"]["value"], 3 * 55.845 / 231.533, rel_tol=1e-3)
    lb = F["chemicals"]["Fe3O4_nanocoagulant"]["lower_bound"]["value"]
    assert math.isclose(lb, 0.395 / 0.138 * (3 * 55.845 / 231.533), rel_tol=5e-3)


def test_equipment_kwh():
    e = ca.Equipment("x", nameplate_kw=1.5, load_factor=0.6, hours_per_1000m3=24)
    assert math.isclose(e.kwh(), 21.6)


def test_scope2_uses_grid_factor():
    r = ca.Route("t", [ca.Equipment("m", 1.0, 1.0, 10.0)], [], [])
    res = ca.audit(r, "SG_2024", F)
    s2 = [l for l in res.lines if l.scope == "Scope 2"][0]
    assert math.isclose(s2.activity, 10.0) and math.isclose(s2.kg_co2e, 10.0 * 0.401)
    res_cn = ca.audit(r, "CN_2022_national", F)
    assert math.isclose(res_cn.total_kg_co2e, 10.0 * 0.5366)


def test_scope1_explicit_zero_present():
    res = ca.audit(ca.Route("t", [], [], []), "SG_2024", F)
    s1 = [l for l in res.lines if l.scope == "Scope 1"]
    assert len(s1) == 1 and s1[0].kg_co2e == 0.0 and "biological" in s1[0].factor_source


def test_gap_factor_marks_incomplete_not_zero():
    r = ca.Route("t", [], [ca.Chemical("Fe3O4", 10.0, "Fe3O4_nanocoagulant")], [])
    res = ca.audit(r, "SG_2024", F)
    assert not res.complete
    assert res.missing_lines[0].kg_co2e is None
    assert res.total_kg_co2e == 0.0  # nothing silently added


def test_gap_factor_overridden_by_user_value():
    r = ca.Route("t", [], [ca.Chemical("Fe3O4", 10.0, "Fe3O4_nanocoagulant", 2.07, "lower bound")], [])
    res = ca.audit(r, "SG_2024", F)
    assert res.complete and math.isclose(res.total_kg_co2e, 20.7)
    assert res.lines[1].factor_status == "user"


def test_verified_factor_not_overridden_by_user():
    r = ca.Route("t", [], [ca.Chemical("FeCl3", 10.0, "FeCl3_40pct_iron_oxide_route", 99.0)], [])
    res = ca.audit(r, "SG_2024", F)
    assert math.isclose(res.total_kg_co2e, 3.95)


def test_sludge_gap_and_user_factor():
    r = ca.Route("t", [], [], [ca.Sludge("s", 0.5, haul_km=20)])
    res = ca.audit(r, "SG_2024", F)
    assert len(res.missing_lines) == 2
    res2 = ca.audit(r, "SG_2024", F, sludge_disposal_factor=10.0, transport_factor=0.1)
    assert res2.complete and math.isclose(res2.total_kg_co2e, 0.5 * 10 + 0.5 * 20 * 0.1)


@pytest.mark.parametrize("bad", [
    ca.Route("t", [ca.Equipment("m", -1, 0.5, 1)], [], []),
    ca.Route("t", [ca.Equipment("m", 1, 1.5, 1)], [], []),
    ca.Route("t", [], [ca.Chemical("c", -5, "PAC")], []),
    ca.Route("t", [], [], [ca.Sludge("s", -0.1)]),
])
def test_validation_errors(bad):
    with pytest.raises(ca.InputError):
        ca.audit(bad, "SG_2024", F)


def test_unit_warnings():
    r = ca.Route("t", [ca.Equipment("m", 2000, 0.5, 1440)], [ca.Chemical("c", 1e6, "PAC")], [])
    res = ca.audit(r, "SG_2024", F)
    assert sum("check units" in w for w in res.warnings) == 3


def test_unknown_keys():
    with pytest.raises(ca.InputError):
        ca.audit(ca.Route("t", [], [], []), "NOPE", F)
    with pytest.raises(ca.InputError):
        ca.audit(ca.Route("t", [], [ca.Chemical("c", 1, "NOPE")], []), "SG_2024", F)


def test_helpers():
    assert math.isclose(ca.nanocoagulant_makeup_kg(100, 0.66), 34.0)
    assert math.isclose(ca.hydroxide_sludge_kg(12.0, F), 12.0 * 0.659)
    assert math.isclose(ca.mixer_power_from_G(300, 1.389), 125.0, rel_tol=1e-3)
    with pytest.raises(ca.InputError):
        ca.nanocoagulant_makeup_kg(100, 1.5)


def test_fe3o4_bottom_up_is_reproducible_and_bounded():
    r = ca.fe3o4_bottom_up(F)
    mol = 1000 / 231.533
    assert math.isclose(r["reagents_kg_per_kg"]["FeCl3"], 2 * mol * 162.204 / 1000, rel_tol=1e-6)
    assert math.isclose(r["reagents_kg_per_kg"]["NaOH"], 8 * mol * 39.997 / 1000 * 1.2, rel_tol=1e-6)
    assert math.isclose(r["value"], sum(r["breakdown"].values()))
    assert 4.0 < r["value"] < 6.0
    lo = ca.fe3o4_bottom_up(F, naoh_excess=0, water_l_per_kg=10, cake_water_kg_per_kg=2, aux_kwh_per_kg=0.3)["value"]
    hi = ca.fe3o4_bottom_up(F, naoh_excess=0.5, water_l_per_kg=30, cake_water_kg_per_kg=4, aux_kwh_per_kg=1.0)["value"]
    assert lo < r["value"] < hi
    assert r["value"] > F["chemicals"]["Fe3O4_nanocoagulant"]["lower_bound"]["value"]


def test_reference_equipment_bases():
    E = ca.reference_equipment()
    assert E["rapid_mix"]["nameplate_kw"] in ca.IEC_MOTORS_KW and 0 < E["rapid_mix"]["load_factor"] <= 1
    assert math.isclose(ca.mixer_power_from_G(600, 1000 * 2 / 1440), 600 ** 2 * 1e-3 * 1000 * 2 / 1440)
    assert math.isclose(ca.pump_power_w(0.01, 10, 0.5), 1000 * 9.81 * 0.01 * 10 / 0.5)
    assert ca.nameplate_from_shaft_w(500)["nameplate_kw"] == 0.75


def test_breakeven_reuse():
    b = ca.breakeven_reuse(route_m_non_chem_kg=11.0, route_c_total_kg=20.0, dose_g_per_m3=50, fe3o4_factor=5.0)
    assert math.isclose(b["allowed_makeup_kg_per_1000m3"], 1.8) and math.isclose(b["breakeven_reuse"], 1 - 1.8 / 50)
    assert not ca.breakeven_reuse(30.0, 20.0, 50, 5.0)["feasible"]


def test_example_routes_run_and_tornado_orders():
    routes = ca.example_routes(F, fe3o4_factor=2.07, fe3o4_source="lower bound")
    res = [ca.audit(r, "SG_2024", F, sludge_disposal_factor=0.0, transport_factor=0.0) for r in routes]
    assert all(r.complete for r in res)
    rows = ca.tornado(routes[1], "SG_2024", F, sludge_disposal_factor=0.0, transport_factor=0.0)
    assert rows[0]["item"].startswith("Chemical — FeCl3")
    for r in rows:
        assert math.isclose(r["hi"] - r["base"], r["base"] - r["lo"], abs_tol=1e-9)
