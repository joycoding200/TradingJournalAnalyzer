"""Drift-guard tests: the get_stats/get_insight/get_whatif slow paths in
analysis.py are hand-maintained copies of compute.compute_stats /
compute_insight / compute_whatif. The get_stats copy already drifted once and
caused the 422 snapshot bug (fixed). These tests lock the behavior so any
future divergence between the API slow path and the engine is caught immediately.

Approach: force the slow path (null the snapshots), call the endpoint, then
call compute_all directly on the same analysis and assert the two agree on the
key business fields.
"""

import pytest

from app.engine.compute import compute_all
from app.models.analysis import Analysis

QMT_CSV = (
    "委托时间,证券代码,证券名称,买卖方向,成交价格,成交数量,手续费\n"
    "2024-01-05 09:30:00,000001,平安银行,买入,10.50,1000,5.00\n"
    "2024-01-10 14:00:00,000001,平安银行,卖出,11.00,1000,5.00\n"
    "2024-02-01 09:30:00,600001,包钢股份,买入,5.00,2000,3.00\n"
    "2024-02-05 14:00:00,600001,包钢股份,卖出,4.50,2000,3.00"
)

TEST_PASSWORD = "secret123"


def _register(client, email):
    resp = client.post(
        "/api/auth/register", json={"email": email, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _import(client, headers):
    r = client.post(
        "/api/upload", headers=headers, files={"file": ("t.csv", QMT_CSV, "text/csv")}
    )
    fid = r.json()["raw_file_id"]
    client.post(
        "/api/upload/confirm",
        headers=headers,
        json={"raw_file_id": fid, "source_type": "smart"},
    )
    client.post(
        "/api/upload/import", headers=headers, json={"raw_file_id": fid}
    )
    return fid


def _run(client, headers, fid):
    return client.post(
        "/api/analysis/run",
        headers=headers,
        json={
            "date_start": "2024-01-01",
            "date_end": "2024-12-31",
            "raw_file_id": fid,
        },
    ).json()["analysis_id"]


@pytest.fixture
def setup_analysis(client, db_session):
    headers = _register(client, "equiv@test.com")
    client.cookies.clear()
    fid = _import(client, headers)
    aid = _run(client, headers, fid)
    return headers, aid, fid


def _null_snapshots(db_session, aid):
    """Force the slow path on the next GET (simulate compute_all having failed
    at creation time, the exact scenario that triggered the original 422 bug)."""
    db_session.rollback()
    analysis = db_session.query(Analysis).filter_by(id=aid).first()
    assert analysis is not None
    analysis.stats_snapshot = None
    analysis.insight_snapshot = None
    analysis.whatif_snapshot = None
    db_session.commit()


def _load_analysis_and_trades(db_session, aid):
    """Reload the analysis + its trades fresh from the DB."""
    db_session.rollback()
    analysis = db_session.query(Analysis).filter_by(id=aid).first()
    from app.api.common import load_trades

    trades = load_trades(analysis, analysis.user_id, db_session)
    return analysis, trades


# Stats fields that must agree between the API slow path and compute_all.
_STATS_FIELDS = [
    "total_trades",
    "total_positions",
    "win_count",
    "loss_count",
    "win_rate",
    "total_pnl",
    "max_win",
    "max_loss",
    "consecutive_losses",
    "profit_factor",
    "max_drawdown",
    "max_drawdown_pct",
    "total_return_pct",
    "expectancy",
]


class TestStatsEquivalence:
    def test_get_stats_slow_path_equals_compute_all(self, client, db_session, setup_analysis):
        """GET /stats slow-path output must match compute_all on key fields."""
        headers, aid, fid = setup_analysis
        _null_snapshots(db_session, aid)

        resp = client.get(f"/api/analysis/{aid}/stats", headers=headers)
        assert resp.status_code == 200, resp.text
        api_stats = resp.json()

        analysis, trades = _load_analysis_and_trades(db_session, aid)
        engine_stats, _, _ = compute_all(analysis, trades, db_session)
        engine_dump = engine_stats.model_dump(mode="json")

        for field in _STATS_FIELDS:
            assert api_stats[field] == engine_dump[field], (
                f"stats drift on '{field}': API={api_stats[field]!r} "
                f"engine={engine_dump[field]!r}"
            )
        # positions count and symbol_summary count must also agree
        assert len(api_stats["positions"]) == len(engine_dump["positions"])
        assert len(api_stats["symbol_summary"]) == len(engine_dump["symbol_summary"])


class TestInsightEquivalence:
    def test_get_insight_slow_path_equals_compute_all(
        self, client, db_session, setup_analysis
    ):
        headers, aid, fid = setup_analysis
        _null_snapshots(db_session, aid)

        resp = client.get(f"/api/analysis/{aid}/insight", headers=headers)
        assert resp.status_code == 200, resp.text
        api_insight = resp.json()

        analysis, trades = _load_analysis_and_trades(db_session, aid)
        _, engine_insight, _ = compute_all(analysis, trades, db_session)
        engine_dump = engine_insight.model_dump(mode="json")

        # Best/worst pattern + baseline expectancy must agree
        assert api_insight.get("best_pattern") == engine_dump.get("best_pattern")
        assert api_insight.get("worst_pattern") == engine_dump.get("worst_pattern")
        assert api_insight.get("baseline_expectancy") == engine_dump.get(
            "baseline_expectancy"
        )
        # Same number of pattern items reported
        assert len(api_insight.get("patterns", [])) == len(
            engine_dump.get("patterns", [])
        )


class TestWhatIfEquivalence:
    def test_get_whatif_slow_path_equals_compute_all(
        self, client, db_session, setup_analysis
    ):
        headers, aid, fid = setup_analysis
        _null_snapshots(db_session, aid)

        resp = client.get(f"/api/analysis/{aid}/whatif", headers=headers)
        assert resp.status_code == 200, resp.text
        api_whatif = resp.json()

        analysis, trades = _load_analysis_and_trades(db_session, aid)
        _, _, engine_whatif = compute_all(analysis, trades, db_session)
        engine_dump = engine_whatif.model_dump(mode="json")

        # WhatIfResponse schema fields are `items` (attribution), `stop_loss`
        # (rule simulation), `shapley`. Earlier this test used wrong keys
        # ("attribution"/"rule_simulation") which silently returned [] and made
        # every assertion a no-op — the drift guard was not actually guarding.
        # Compare real values, not just lengths.
        assert len(api_whatif["items"]) == len(engine_dump["items"]), (
            f"whatif items count drift: API={len(api_whatif['items'])} "
            f"engine={len(engine_dump['items'])}"
        )
        for api_item, eng_item in zip(api_whatif["items"], engine_dump["items"]):
            assert api_item["removed_pattern"] == eng_item["removed_pattern"]
            assert api_item["delta"] == eng_item["delta"]
            assert api_item["contribution_pct"] == eng_item["contribution_pct"]

        # stop_loss is a single object (or None); compare its key fields if present
        api_sl = api_whatif["stop_loss"]
        eng_sl = engine_dump["stop_loss"]
        assert (api_sl is None) == (eng_sl is None), (
            f"stop_loss presence drift: API={'None' if api_sl is None else 'set'} "
            f"engine={'None' if eng_sl is None else 'set'}"
        )
        if api_sl is not None:
            assert api_sl["rule"] == eng_sl["rule"]
            assert api_sl["original_return"] == eng_sl["original_return"]
            assert api_sl["what_if_return"] == eng_sl["what_if_return"]
            assert api_sl["delta"] == eng_sl["delta"]
            assert api_sl["affected_positions"] == eng_sl["affected_positions"]

        # Shapley uses Monte Carlo sampling (random.shuffle, no seed), so the
        # two calls produce slightly different values for the same input — this
        # is algorithmic variance, not drift. Assert they agree on the set of
        # patterns and on each value within a sampling tolerance.
        assert len(api_whatif["shapley"]) == len(engine_dump["shapley"])
        api_sh = {s["pattern_name"]: s["shapley_value"] for s in api_whatif["shapley"]}
        eng_sh = {s["pattern_name"]: s["shapley_value"] for s in engine_dump["shapley"]}
        assert set(api_sh) == set(eng_sh), "shapley pattern set drift"
        for pat in api_sh:
            a, e = api_sh[pat], eng_sh[pat]
            # Tolerance: 5% of the larger magnitude, or 1.0 absolute (handles
            # near-zero values). Monte Carlo with 5000 samples is stable to
            # well within this.
            tol = max(abs(a), abs(e)) * 0.05 + 1.0
            assert abs(a - e) <= tol, (
                f"shapley value drift beyond sampling tolerance for '{pat}': "
                f"API={a} engine={e} tol={tol}"
            )


# ─── Large-sample fixture ────────────────────────────────────────────────────
# The default QMT_CSV fixture is only 4 trades / 2 positions, so valid_count<5
# makes `significant` empty and best_pattern/worst_pattern are both None on
# every path — the InsightEquivalence assertions degrade to None==None (trivial).
# This fixture has 5 positions (all 7-day SWING holds → one behavior tag with
# count>=5) so best_pattern is non-None and the equivalence check actually
# discriminates. 3 winners / 2 losers, and the losers breach -5% so the
# stop_loss rule (PnL-truncation fallback, no mootdx in tests) is non-None too.
LARGE_CSV = (
    "委托时间,证券代码,证券名称,买卖方向,成交价格,成交数量,手续费\n"
    "2024-01-05 09:30:00,000001,平安银行,买入,10.00,1000,5.00\n"
    "2024-01-12 14:00:00,000001,平安银行,卖出,11.20,1000,5.00\n"
    "2024-02-05 09:30:00,000002,万科A,买入,9.00,1000,5.00\n"
    "2024-02-12 14:00:00,000002,万科A,卖出,10.35,1000,5.00\n"
    "2024-03-05 09:30:00,000004,国农科技,买入,8.00,1000,5.00\n"
    "2024-03-12 14:00:00,000004,国农科技,卖出,8.70,1000,5.00\n"
    "2024-04-05 09:30:00,000005,世纪星源,买入,7.00,1000,5.00\n"
    "2024-04-12 14:00:00,000005,世纪星源,卖出,6.50,1000,5.00\n"
    "2024-05-05 09:30:00,000006,深振业A,买入,6.00,1000,5.00\n"
    "2024-05-12 14:00:00,000006,深振业A,卖出,5.40,1000,5.00"
)


@pytest.fixture
def setup_large_analysis(client, db_session):
    headers = _register(client, "equiv_large@test.com")
    client.cookies.clear()
    r = client.post(
        "/api/upload",
        headers=headers,
        files={"file": ("t_large.csv", LARGE_CSV, "text/csv")},
    )
    fid = r.json()["raw_file_id"]
    client.post(
        "/api/upload/confirm",
        headers=headers,
        json={"raw_file_id": fid, "source_type": "smart"},
    )
    client.post("/api/upload/import", headers=headers, json={"raw_file_id": fid})
    aid = _run(client, headers, fid)
    return headers, aid, fid


class TestStatsEquivalenceLargeSample:
    """Large-sample drift guard: with >=5 positions the significant-pattern
    path (best_pattern/worst_pattern) is exercised, so Insight equivalence is
    non-trivial. Also locks the V4.0 fields omitted from _STATS_FIELDS:
    equity_curve values, pnl_distribution, and the MAE/MFE/capture fields."""

    def test_best_pattern_nontrivial_and_equal(self, client, db_session, setup_large_analysis):
        headers, aid, fid = setup_large_analysis
        _null_snapshots(db_session, aid)

        resp = client.get(f"/api/analysis/{aid}/insight", headers=headers)
        assert resp.status_code == 200, resp.text
        api_insight = resp.json()

        # Sanity: the large fixture genuinely produces a significant pattern
        # (SWING count=5). If this ever becomes None, the fixture stopped
        # exercising the path and the test must be fixed, not weakened.
        assert api_insight.get("best_pattern") is not None, (
            "large fixture should yield a non-None best_pattern (count>=5); "
            "if this fails the fixture no longer discriminates"
        )

        analysis, trades = _load_analysis_and_trades(db_session, aid)
        _, engine_insight, _ = compute_all(analysis, trades, db_session)
        engine_dump = engine_insight.model_dump(mode="json")

        api_best = api_insight["best_pattern"]
        eng_best = engine_dump["best_pattern"]
        assert eng_best is not None, "compute_insight should also find best_pattern"
        assert api_best["pattern_name"] == eng_best["pattern_name"]
        assert api_best["count"] == eng_best["count"]
        assert api_best["total_pnl"] == eng_best["total_pnl"]
        assert api_best["win_rate"] == eng_best["win_rate"]
        assert api_best["expectancy"] == eng_best["expectancy"]

        # worst_pattern may or may not be set (needs >1 significant pattern);
        # only assert when both sides have it.
        api_worst = api_insight.get("worst_pattern")
        eng_worst = engine_dump.get("worst_pattern")
        assert (api_worst is None) == (eng_worst is None)
        if api_worst is not None and eng_worst is not None:
            assert api_worst["pattern_name"] == eng_worst["pattern_name"]
            assert api_worst["total_pnl"] == eng_worst["total_pnl"]

    def test_v4_fields_equal(self, client, db_session, setup_large_analysis):
        """V4.0 fields not covered by _STATS_FIELDS must not drift."""
        headers, aid, fid = setup_large_analysis
        _null_snapshots(db_session, aid)

        resp = client.get(f"/api/analysis/{aid}/stats", headers=headers)
        assert resp.status_code == 200, resp.text
        api_stats = resp.json()

        analysis, trades = _load_analysis_and_trades(db_session, aid)
        engine_stats, _, _ = compute_all(analysis, trades, db_session)
        engine_dump = engine_stats.model_dump(mode="json")

        # equity_curve: same length, same running cum_pnl at each point
        assert len(api_stats["equity_curve"]) == len(engine_dump["equity_curve"]), (
            "equity_curve length drift"
        )
        for api_pt, eng_pt in zip(api_stats["equity_curve"], engine_dump["equity_curve"]):
            assert api_pt["date"] == eng_pt["date"], (
                f"equity_curve date drift: API={api_pt['date']} eng={eng_pt['date']}"
            )
            assert api_pt["cum_pnl"] == eng_pt["cum_pnl"], (
                f"equity_curve cum_pnl drift at {api_pt['date']}: "
                f"API={api_pt['cum_pnl']} eng={eng_pt['cum_pnl']}"
            )

        # pnl_distribution: same buckets, same counts
        assert api_stats["pnl_distribution"] == engine_dump["pnl_distribution"], (
            f"pnl_distribution drift: API={api_stats['pnl_distribution']} "
            f"eng={engine_dump['pnl_distribution']}"
        )

        # MAE/MFE fields exist on both sides (no mootdx in tests → defaults)
        for field in ("avg_mae", "avg_mfe", "profit_capture_ratio"):
            assert api_stats[field] == engine_dump[field], (
                f"{field} drift: API={api_stats[field]} eng={engine_dump[field]}"
            )

    def test_whatif_stop_loss_nontrivial_and_equal(self, client, db_session, setup_large_analysis):
        """With losers breaching -5%, stop_loss is non-None and must match."""
        headers, aid, fid = setup_large_analysis
        _null_snapshots(db_session, aid)

        resp = client.get(f"/api/analysis/{aid}/whatif", headers=headers)
        assert resp.status_code == 200, resp.text
        api_whatif = resp.json()

        analysis, trades = _load_analysis_and_trades(db_session, aid)
        _, _, engine_whatif = compute_all(analysis, trades, db_session)
        engine_dump = engine_whatif.model_dump(mode="json")

        api_sl = api_whatif["stop_loss"]
        eng_sl = engine_dump["stop_loss"]
        # The large fixture has two -7%/-10% losers, so the PnL-truncation
        # fallback (no intraday market_data in tests) makes stop_loss non-None.
        # If this becomes None, the fixture stopped exercising the path.
        assert api_sl is not None, (
            "large fixture should yield a non-None stop_loss sim "
            "(losers breach -5%); fixture no longer discriminates"
        )
        assert eng_sl is not None
        assert api_sl["rule"] == eng_sl["rule"]
        assert api_sl["original_return"] == eng_sl["original_return"]
        assert api_sl["what_if_return"] == eng_sl["what_if_return"]
        assert api_sl["delta"] == eng_sl["delta"]
        assert api_sl["affected_positions"] == eng_sl["affected_positions"]
