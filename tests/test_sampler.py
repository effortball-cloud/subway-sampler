# -*- coding: utf-8 -*-
"""가짜 운행(배차·속도를 아는 열차)으로 수집 → 통과 시각 → A·B 출력까지 맞는지 본다.

  python -m unittest discover -s tests -v
"""
import datetime as dt
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "pipeline"))
import agg  # noqa: E402
import collect  # noqa: E402
import common as C  # noqa: E402
import export_life  # noqa: E402
import passages as P  # noqa: E402

SETTINGS = {
    "lines": ["2호선", "9호선"], "window": {"start": "07:00", "end": "09:00"},
    "snap_first": "06:58", "snap_last": "09:02", "interval_sec": 240, "daily_budget": 450,
    "holidays": [], "holiday_like_ratio": 0.8, "export_days": 20, "min_days_to_show": 1,
}
DATE = "2026-11-24"  # 화요일


def fake_line(date, sid, line, headway, run_sec=120, dwell=30, n_st=15, express_every=0, skip=(),
              drop=None, updn="1"):
    """열차가 headway초마다 출발해 역마다 run_sec초 걸리는 가짜 노선 → 스냅숏 원본 줄들.
    express_every=k 이면 k번째 열차마다 급행(skip 역은 서지 않고 지나감).
    drop=(시작, 끝) 이면 그 출발 시간대 열차를 없앤다(진짜 공백 만들기)."""
    t_first = C.hm(date, "06:20")
    trains = []
    k = 0
    t = t_first
    while t < C.hm(date, "09:00"):
        if not (drop and drop[0] <= t < drop[1]):
            exp = 1 if express_every and k % express_every == 0 else 0
            evs = []
            for i in range(n_st):
                a = t + dt.timedelta(seconds=i * run_sec)
                stid = f"{sid}000{201 + i:03d}"
                if exp and (201 + i) in skip:
                    continue  # 급행은 이 역에 사건이 안 찍힘
                evs += [(a - dt.timedelta(seconds=90), "3", stid), (a - dt.timedelta(seconds=15), "0", stid),
                        (a, "1", stid), (a + dt.timedelta(seconds=dwell), "2", stid)]
            trains.append((f"{sid[-1]}{k:03d}", exp, evs))
        k += 1
        t += dt.timedelta(seconds=headway)
    recs = []
    for T in collect.snap_times(date, SETTINGS):
        rows = []
        for no, exp, evs in trains:
            past = [e for e in evs if e[0] <= T]
            if not past or past[-1] is evs[-1] and (T - past[-1][0]).total_seconds() > 60:
                continue  # 아직 출발 전이거나 운행 끝
            et, st, stid = past[-1]
            rows.append([sid, no, updn, stid, f"역{stid[-3:]}", st, et.strftime("%Y-%m-%d %H:%M:%S"),
                         str(exp), "0", "종점"])
        recs.append({"t": T.isoformat(timespec="seconds"), "line": line, "code": "INFO-000", "rows": rows})
    return recs


class TestPassages(unittest.TestCase):
    def test_headway_recovered(self):
        day = P.build_day(fake_line(DATE, "1002", "2호선", 150), DATE, SETTINGS)
        key = "1002000208|1"
        hw = P.headways(day["passages"][key])
        self.assertAlmostEqual(sorted(hw)[len(hw) // 2], 150, delta=5)
        self.assertGreaterEqual(len(day["passages"][key]), 46)  # 2시간 / 150초 = 48
        q = day["quality"]
        self.assertGreater(q["interp"], 0)  # 4분 간격이라 보간이 꼭 생김

    def test_interpolated_close_to_truth(self):
        day = P.build_day(fake_line(DATE, "1002", "2호선", 150), DATE, SETTINGS)
        # 열차 k는 06:20 + 150k 초에 201역, 208역은 +7*120초 → 07:00 기준 초
        truth = {(-40 * 60 + 150 * k + 7 * 120) for k in range(200)}
        for sec, _exp, _d in day["passages"]["1002000208|1"]:
            self.assertLessEqual(min(abs(sec - t) for t in truth), 20)

    def test_batch_time_robust(self):
        """응답 시각이 묶음 갱신 시각(=스냅숏 시각)이어도 보통 배차가 참값 근처"""
        for hw in (150, 210):
            recs = fake_line(DATE, "1002", "2호선", hw)
            for r in recs:
                for row in r["rows"]:
                    row[6] = r["t"][:19].replace("T", " ")
            day = P.build_day(recs, DATE, SETTINGS)
            s = agg.station_dir_stats([day])["1002000208|1"]
            self.assertAlmostEqual(s["배차_중간값_초"], hw, delta=10)
            self.assertGreaterEqual(s["배차_90_초"], hw)  # 90%는 줄여 말하지 않음

    def test_express_skips(self):
        recs = fake_line(DATE, "1009", "9호선", 180, express_every=3, skip=(204, 205, 206))
        day = P.build_day(recs, DATE, SETTINGS)
        skipped = day["passages"]["1009000205|1"]
        normal = day["passages"]["1009000209|1"]
        self.assertTrue(all(p[1] == 0 for p in skipped))  # 급행은 205역에 안 섬
        self.assertTrue(any(p[1] == 1 for p in normal))  # 209역엔 급행도 섬
        self.assertGreater(len(normal), len(skipped))

    def test_stale_rows_ignored(self):
        recs = fake_line(DATE, "1002", "2호선", 150)
        recs[10]["rows"].append(["1002", "X999", "1", "1002000210", "역210", "1", f"{DATE} 05:00:00", "0", "0", ""])
        day = P.build_day(recs, DATE, SETTINGS)
        self.assertFalse(any("X999" in str(v) for v in day["passages"].values()))


class TestCollect(unittest.TestCase):
    def test_parse_shapes(self):
        ok = {"errorMessage": {"status": 200, "code": "INFO-000", "message": "정상"},
              "realtimePositionList": [{"subwayId": "1002", "trainNo": "2234", "updnLine": "0", "statnId": "1002000222",
                                        "statnNm": "강남", "trainSttus": "1", "recptnDt": "2026-11-24 08:00:00",
                                        "directAt": "0", "lstcarAt": "0", "statnTnm": "성수"}]}
        code, _, rows = collect.parse(ok)
        self.assertEqual(code, "INFO-000")
        self.assertEqual(rows[0][4], "강남")
        code, msg, rows = collect.parse({"status": 500, "code": "INFO-100", "message": "인증키가 유효하지 않습니다."})
        self.assertEqual((code, rows), ("INFO-100", []))
        self.assertTrue(collect.is_fatal(code, msg))
        self.assertFalse(collect.is_fatal("INFO-200", "해당하는 데이터가 없습니다."))
        self.assertTrue(collect.is_fatal("ERROR-338", "해당 인증키로는 실시간 서비스를 사용할 수 없습니다."))

    def test_plan_fits_budget(self):
        s = dict(SETTINGS, lines=[f"{i}호선" for i in range(1, 17)])
        n = len(collect.snap_times(DATE, s))
        self.assertEqual(n, 32)
        lines = collect.plan_lines(s, n)
        self.assertLessEqual(len(lines) * n, s["daily_budget"])
        self.assertEqual(len(lines), 14)

    def test_budget_guard(self):
        tmp = tempfile.mkdtemp()
        try:
            b = C.Budget(3, dt.date(2026, 11, 24), state_dir=tmp)
            b.take(); b.take(); b.take()
            with self.assertRaises(C.BudgetExceeded):
                b.take()
            self.assertEqual(C.Budget(3, dt.date(2026, 11, 24), state_dir=tmp).used, 3)  # 파일에 남음
        finally:
            shutil.rmtree(tmp)


class TestAggregate(unittest.TestCase):
    def day(self, date, headway, **kw):
        return P.build_day(fake_line(date, "1002", "2호선", headway, **kw), date, SETTINGS)

    def test_holiday_like_dropped(self):
        days = [self.day(f"2026-11-{d}", 150) for d in (23, 24, 25, 26)] + [self.day("2026-11-27", 300)]
        keep, dropped = agg.usable(days, SETTINGS)
        self.assertEqual([d["date"] for d in keep], ["2026-11-23", "2026-11-24", "2026-11-25", "2026-11-26"])
        self.assertIn("2026-11-27", [d for d, _ in dropped])

    def test_weekend_dropped(self):
        keep, dropped = agg.usable([self.day("2026-11-28", 150)], SETTINGS)  # 토요일
        self.assertEqual(keep, [])

    def test_station_stats(self):
        days = [self.day(f"2026-11-{d}", 150) for d in (23, 24, 25)]
        s = agg.station_dir_stats(days)["1002000208|1"]
        self.assertAlmostEqual(s["배차_중간값_초"], 150, delta=5)
        self.assertLessEqual(s["배차_90_초"], 175)
        self.assertEqual(s["관측일"], 3)
        self.assertEqual(agg.direction_label("1002", "1", s["_terms"]), "외선순환")

    def test_real_gap_corroborated(self):
        d = self.day(DATE, 150, drop=(C.hm(DATE, "07:10"), C.hm(DATE, "07:25")))
        gaps = export_life.corroborated_gaps(d)
        self.assertTrue(gaps)
        self.assertGreaterEqual(max(g["공백_초"] for g in gaps), 15 * 60)

    def test_missing_snapshots_not_a_gap(self):
        recs = fake_line(DATE, "1002", "2호선", 150)
        recs = [r for r in recs if not ("07:30" <= r["t"][11:16] <= "07:50")]  # 수집이 20분 빠짐
        d = P.build_day(recs, DATE, SETTINGS)
        self.assertEqual(export_life.corroborated_gaps(d), [])


class TestNames(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(C.norm_name("서울역"), "서울")
        self.assertEqual(C.norm_name("총신대입구(이수)"), "총신대입구")
        self.assertEqual(C.norm_name("역삼"), "역삼")
        # 11-23 저녁 실제 응답에서 나온 이름
        self.assertEqual(C.norm_name("성수종착"), "성수")
        self.assertEqual(C.norm_name("4.19 민주묘지"), "4.19민주묘지")
        self.assertEqual(C.norm_name("응암(하선-종착)"), "응암")
        self.assertEqual(C.norm_name("성수지선"), "성수")
        self.assertEqual(agg.direction_label("1002", "0", {"성수지선": 3}, "1002002112"), "성수행")
        self.assertEqual(agg.direction_label("1002", "0", {"성수": 3}, "1002000222"), "내선순환")

    def test_lookup_same_name_far_apart(self):
        import stations as ST
        idx = {"양평": [("5호선", 37.5258, 126.8866), ("경의중앙선", 37.4927, 127.4918)],
               "교대": [("2호선", 37.4934, 127.0142), ("3호선", 37.4938, 127.0139)]}
        self.assertEqual(ST.lookup(idx, "양평", "5호선"), (37.5258, 126.8866))
        self.assertEqual(ST.lookup(idx, "양평", "경의중앙선"), (37.4927, 127.4918))
        self.assertAlmostEqual(ST.lookup(idx, "교대", "2호선")[0], 37.4936, places=3)


class TestRealEvening(unittest.TestCase):
    """11-23 22:57~23:21 실제 응답(14개 노선 x 7번). 역 번호 순서·이름·보간 오차를 실데이터로 지킨다."""

    @classmethod
    def setUpClass(cls):
        import gzip
        import json
        path = os.path.join(os.path.dirname(__file__), "fixtures", "real_evening_2026-11-23.jsonl.gz")
        with gzip.open(path, "rt", encoding="utf-8") as f:
            cls.recs = [json.loads(line) for line in f]
        cls.evs, cls.lines, _ = P.events_of(cls.recs, "2026-11-23")

    def test_station_ids_run_along_the_line(self):
        moves = {}
        for (sid, _tr, updn), run in P.runs_of(self.evs):
            for a, b in zip(run, run[1:]):
                d = P.seg_idx(b["stid"])[1] - P.seg_idx(a["stid"])[1]
                if d:
                    m = moves.setdefault((self.lines[sid], updn), [0, 0])
                    m[0 if d > 0 else 1] += 1
        for (line, updn), (up, down) in moves.items():
            if line == "경의중앙선" or up + down < 5:
                continue  # 경의중앙선은 경의·중앙 구간 번호가 반대로 매겨져 방향이 섞인다(열차마다 따로 보간하니 괜찮음)
            self.assertGreaterEqual(max(up, down) / (up + down), 0.9, (line, updn, up, down))

    def test_every_station_has_coords(self):
        import stations as ST
        idx = ST.coord_index()
        miss = {(e["stnm"], self.lines[e["sid"]]) for e in self.evs
                if ST.lookup(idx, e["stnm"], self.lines[e["sid"]]) is None}
        self.assertEqual(miss, set())

    def test_interpolation_error_leave_one_out(self):
        by_seg = {}
        for e in self.evs:
            seg, i = P.seg_idx(e["stid"])
            if i is not None and (e["stid"], i) not in by_seg.setdefault(seg, []):
                by_seg[seg].append((e["stid"], i))
        errs = []
        for _k, run in P.runs_of(self.evs):
            for j in range(1, len(run) - 1):
                m = run[j]
                if m["st"] != "1" or m["stid"] in (run[j - 1]["stid"], run[j + 1]["stid"]):
                    continue
                got = {a: t for a, t, d in P.passages_of_run([run[j - 1], run[j + 1]], by_seg, set()) if d == 0}
                if m["stid"] in got:
                    errs.append(abs((got[m["stid"]] - m["t"]).total_seconds()))
        errs.sort()
        self.assertGreater(len(errs), 300)
        self.assertLessEqual(errs[len(errs) // 2], 30)  # 11-23 실측: 중간값 21초
        self.assertLessEqual(errs[int(len(errs) * 0.9)], 90)  # 11-23 실측: 62초


if __name__ == "__main__":
    unittest.main()
