"""Run: python test_stats.py   (all asserts must pass before you hand your code to the team)"""
import numpy as np, pandas as pd
import stats_engine as S


def synthetic(slope=0.05, y0=2000, y1=2023, seed=0, base=17.0, spike=None, missing=()):
    rng = np.random.default_rng(seed)
    payload = {}
    for y in range(y0, y1 + 1):
        for m in range(1, 13):
            payload[f"{y}{m:02d}"] = base + slope * (y - y0) + 8 * np.sin(2 * np.pi * (m - 4) / 12) + rng.normal(0, .7)
        payload[f"{y}13"] = 17.0  # annual value, must be ignored
    for k in missing: payload[k] = -999
    if spike: payload[spike[0]] += spike[1]
    return {"properties": {"parameter": {"T2M": payload}}}


def test_parse():
    df = S.parse_power(synthetic(missing=("200503",)), "T2M")
    assert len(df) == 24 * 12 and df.value.isna().sum() == 1, "parse: annual key or -999 handled wrongly"


def test_trend():
    df = S.parse_power(synthetic(slope=0.05), "T2M"); ym = S.yearly_means(df)
    mk, sen = S.mann_kendall(ym.value), S.sen_slope(ym.year, ym.value)
    assert mk["trend"] == "increasing" and mk["p"] < 0.001
    assert abs(sen["slope"] - 0.05) < 0.01, sen
    flat = S.mann_kendall(S.yearly_means(S.parse_power(synthetic(slope=0.0, seed=3), "T2M")).value)
    assert flat["p"] > 0.05, flat


def test_mk_against_library():
    try: import pymannkendall as pmk
    except ImportError: print("  (pymannkendall not installed: skipped cross-check)"); return
    y = S.yearly_means(S.parse_power(synthetic(seed=5), "T2M")).value.values
    assert abs(S.mann_kendall(y)["p"] - pmk.original_test(y).p) < 1e-6


def test_anomaly():
    df = S.parse_power(synthetic(spike=("201507", 6.0)), "T2M")
    an = S.detect_anomalies(df); hit = an[an.anomaly]
    assert ((hit.year == 2015) & (hit.month == 7)).any(), "injected heat spike not detected"


def test_seasonality():
    prof = S.seasonal_profile(S.parse_power(synthetic(), "T2M"))
    assert prof["warmest_month"] in (6, 7, 8) and prof["amplitude"] > 12


def test_compare():
    a = S.parse_power(synthetic(slope=0.08, seed=1), "T2M"); b = S.parse_power(synthetic(slope=0.01, seed=2), "T2M")
    c = S.compare_regions(a, b); assert c["slope_diff"] > 0.05 and c["significant"], c
    pc = S.compare_periods(a); assert pc["diff"] > 0 and pc["significant"], pc


def test_analyze_dict():
    import json
    r = S.analyze_region(S.parse_power(synthetic(), "T2M"), "Test", "temperature", "C")
    json.dumps(r)  # must be JSON-serializable
    for k in ("slope_sen", "mk_p", "n_anomalies", "top_anomalies", "yearly", "seasonal"): assert k in r


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name)
    print("ALL TESTS PASSED")
