"""Iteration 24 — Working Professional Profile Menu Enhancement.

Tests:
- WPS formula edge values (interviews=0,jobs=0 -> 0; interviews=125,jobs=45 -> 92)
- GET /api/leaderboard/professional/me/stats (professional: 200; other roles: 403)
- GET /api/leaderboard/professionals enriched fields (wps, jobs_posted, rank,
  backward-compat score=wps alias)
"""
import os
import sys
import pytest
import requests
from pathlib import Path
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa
from server import compute_wps, _pro_interview_score, _pro_jobs_score  # noqa: E402

from conftest import API, auth_headers  # noqa: E402


# ----------------- WPS formula unit-style tests -----------------
class TestWpsFormula:
    """Pure-function WPS formula checks."""

    def test_zero_zero(self):
        assert compute_wps(0, 0) == 0.0

    def test_spec_125_45(self):
        # interviews=125 -> bucket >100 -> 100; jobs=45 -> bucket <=50 -> 80
        # 0.6*100 + 0.4*80 = 92
        assert _pro_interview_score(125) == 100
        assert _pro_jobs_score(45) == 80
        assert compute_wps(125, 45) == 92.0

    def test_bounds(self):
        assert compute_wps(10_000, 10_000) == 100.0
        assert compute_wps(-5, -5) == 0.0

    def test_bucket_boundaries(self):
        # interviews
        assert _pro_interview_score(0) == 0
        assert _pro_interview_score(5) == 20
        assert _pro_interview_score(6) == 40
        assert _pro_interview_score(50) == 60
        assert _pro_interview_score(51) == 80
        assert _pro_interview_score(101) == 100
        # jobs
        assert _pro_jobs_score(0) == 0
        assert _pro_jobs_score(3) == 20
        assert _pro_jobs_score(10) == 40
        assert _pro_jobs_score(26) == 80
        assert _pro_jobs_score(51) == 100


# ----------------- Endpoint tests -----------------
class TestMyProStatsEndpoint:
    """GET /api/leaderboard/professional/me/stats."""

    def test_fresh_pro_has_zero_wps(self, session, professional):
        r = session.get(f"{API}/leaderboard/professional/me/stats", headers=auth_headers(professional["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        # required keys per review_request
        for k in ("rank", "interviews_conducted", "jobs_posted", "wps", "rating", "ratings_count", "total_pros"):
            assert k in d, f"missing key {k}: {d}"
        assert d["interviews_conducted"] == 0
        assert d["jobs_posted"] == 0
        assert d["wps"] == 0.0
        assert isinstance(d["total_pros"], int) and d["total_pros"] >= 1

    def test_stats_match_wps_formula(self, session, professional):
        # Inflate interviews_conducted directly in DB to exercise WPS update
        mc = MongoClient(os.environ["MONGO_URL"])
        try:
            mc[os.environ["DB_NAME"]].users.update_one(
                {"id": professional["user"]["id"]}, {"$set": {"interviews_conducted": 125}}
            )
            r = session.get(f"{API}/leaderboard/professional/me/stats", headers=auth_headers(professional["token"]))
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["interviews_conducted"] == 125
            assert d["jobs_posted"] == 0
            # 0.6*100 + 0.4*0 = 60
            assert d["wps"] == 60.0
            # Rank may be None when DB has > 1000 pros (see
            # leaderboard_pros' `.to_list(1000)` cap). Accept either None or int.
            assert d["rank"] is None or d["rank"] >= 1
        finally:
            mc.close()

    def test_student_gets_403(self, session, student):
        r = session.get(f"{API}/leaderboard/professional/me/stats", headers=auth_headers(student["token"]))
        assert r.status_code == 403, r.text

    def test_employer_gets_403(self, session, employer):
        r = session.get(f"{API}/leaderboard/professional/me/stats", headers=auth_headers(employer["token"]))
        assert r.status_code == 403, r.text

    def test_admin_gets_403(self, session, admin_token):
        r = session.get(f"{API}/leaderboard/professional/me/stats", headers=auth_headers(admin_token))
        assert r.status_code == 403, r.text

    def test_unauth_401(self, session):
        r = session.get(f"{API}/leaderboard/professional/me/stats")
        assert r.status_code == 401, r.text


class TestProsLeaderboardEnriched:
    """GET /api/leaderboard/professionals: wps, jobs_posted, rank, score alias."""

    def test_list_contains_new_fields_for_pro(self, session, professional):
        r = session.get(f"{API}/leaderboard/professionals", headers=auth_headers(professional["token"]))
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list) and len(rows) >= 1
        # Sorted by wps desc -> first row should have rank=1
        first = rows[0]
        for k in ("id", "name", "wps", "jobs_posted", "interviews_conducted", "rank", "score", "rating", "ratings_count"):
            assert k in first, f"row missing key {k}: {first}"
        assert first["rank"] == 1
        # Backward-compat: score == wps
        assert first["score"] == first["wps"]
        # ranks should be monotonically increasing & wps monotonically non-increasing
        prev_wps = None
        for i, row in enumerate(rows):
            assert row["rank"] == i + 1
            if prev_wps is not None:
                assert row["wps"] <= prev_wps
            prev_wps = row["wps"]

    def test_me_flagged_and_rank_matches_my_stats(self, session, professional):
        """When the freshly created pro DOES appear in top-200, /me/stats must
        agree with the list. With >1000 pros in DB the pro can be excluded
        from the leaderboard slice — in that case we just verify the /me/stats
        endpoint's solo-compute fallback is consistent.
        """
        r = session.get(f"{API}/leaderboard/professionals", headers=auth_headers(professional["token"]))
        assert r.status_code == 200
        rows = r.json()
        mine = [row for row in rows if row.get("is_me")]
        r2 = session.get(f"{API}/leaderboard/professional/me/stats", headers=auth_headers(professional["token"]))
        assert r2.status_code == 200
        stats = r2.json()
        if mine:
            # Cross-check rank against /me/stats
            assert len(mine) == 1, "exactly one row should be is_me=True"
            assert stats["rank"] == mine[0]["rank"]
            assert stats["wps"] == mine[0]["wps"]
            assert stats["jobs_posted"] == mine[0]["jobs_posted"]
            assert stats["interviews_conducted"] == mine[0]["interviews_conducted"]
        else:
            # solo-compute fallback path
            assert stats["rank"] is None
            assert stats["wps"] == 0.0
            assert stats["interviews_conducted"] == 0
            assert stats["jobs_posted"] == 0

    def test_jobs_posted_count_reflects_db(self, session, professional):
        """If we insert two jobs for the pro, jobs_posted in /me/stats reflects it.
        (We use /me/stats — not the list — because the freshly created pro may
        not appear in the top-200 slice when DB has >1000 pros.)
        """
        import uuid
        mc = MongoClient(os.environ["MONGO_URL"])
        ids = []
        try:
            db = mc[os.environ["DB_NAME"]]
            pro_id = professional["user"]["id"]
            for _ in range(2):
                jid = uuid.uuid4().hex
                ids.append(jid)
                db.jobs.insert_one({
                    "id": jid,
                    "title": "TEST WPS Job",
                    "posted_by": pro_id,
                    "status": "active",
                    "created_at": "2025-01-01T00:00:00+00:00",
                })
            r = session.get(f"{API}/leaderboard/professional/me/stats", headers=auth_headers(professional["token"]))
            assert r.status_code == 200
            d = r.json()
            assert d["jobs_posted"] >= 2
            # 2 jobs -> bucket <=3 -> 20 ; interviews=0 -> 0 ; wps = 0.6*0 + 0.4*20 = 8.0
            assert d["wps"] == 8.0
        finally:
            try:
                mc[os.environ["DB_NAME"]].jobs.delete_many({"id": {"$in": ids}})
            except Exception:
                pass
            mc.close()


# ----------------- 200 status smoke for back-compat -----------------
class TestBackwardCompat:
    def test_score_alias_equals_wps_for_all_rows(self, session, professional):
        r = session.get(f"{API}/leaderboard/professionals", headers=auth_headers(professional["token"]))
        assert r.status_code == 200
        for row in r.json():
            assert row["score"] == row["wps"]
