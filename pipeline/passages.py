# -*- coding: utf-8 -*-
"""
하루 원본(4분 간격 열차 위치) → 역·방향별 '열차가 지나간 시각' 목록.

  python pipeline/passages.py                  # 오늘(또는 --date) 하루 만들기
  python pipeline/passages.py --date 2026-11-24
  python pipeline/passages.py --all            # 원본이 있는 날 전부 다시
  python pipeline/passages.py --finalize       # 아침 수집 직후: 만들고 원본을 .gz 로 묶기

생각:
- 위치 API는 열차마다 '마지막 사건'(진입·도착·출발·전역출발)과 그 사건 시각(recptnDt)을 준다.
  4분마다 찍어도 사건 시각은 초 단위로 정확하다.
- 같은 열차의 두 사건 사이에 있는 역은 위치를 직선으로 이어 지나간 시각을 추정한다(보간).
- 역 순서는 역 ID 끝자리로 본다(같은 구간 번호 안에서 6칸 이내만 잇는다 → 지선·순환 끝은 잇지 않음).
- 급행은 급행이 실제로 선 역(그날 급행이 도착·출발한 역)에서만 지나간 것으로 센다.

결과: data/daily/YYYY-MM-DD.json.gz
  {"date", "window": ["07:00","09:00"], "snaps": {노선: [초...]}, "lines": {subwayId: 노선},
   "stations": {statnId: [역이름, subwayId]},
   "passages": {"statnId|updn": [[초, 급행0/1, 직접1/보간0], ...]},   초 = 07:00부터 지난 초
   "terminals": {"statnId|updn": {종착역: 횟수}}, "trains_0800": {노선: 대수}, "quality": {...}}
"""
import argparse
import datetime as dt
import glob
import gzip
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

# 사건 → 역 기준 위치 보정(진행 방향 쪽이 +). 3=전역출발은 아직 앞 역 쪽, 0=진입은 거의 도착.
OFF = {"3": -0.6, "0": -0.15, "1": 0.0, "2": 0.05}
# 역에서 직접 본 사건 → 그 역을 지난(섰던) 시각 보정(초)
DIRECT_SHIFT = {"1": 0, "2": -20, "0": 25}
MAX_IDX_JUMP = 6
MAX_GAP_SEC = 12 * 60
MAX_INTERP_SEC = 10 * 60
STALE_SEC = 10 * 60


def seg_idx(statn_id):
    """'1002000222' → ('1002000', 222). 모양이 다르면 (statn_id, None)"""
    s = str(statn_id or "")
    if len(s) == 10 and s.isdigit():
        return s[:7], int(s[7:])
    return s, None


def events_of(records, date):
    """원본 줄들 → 중복 없는 사건 목록, 노선 이름, 스냅숏 시각"""
    seen, evs, lines, snaps = set(), [], {}, {}
    for rec in records:
        t_snap = C.parse_kst(rec["t"])
        if t_snap is None or t_snap.date().isoformat() != date:
            continue
        if rec.get("rows"):
            snaps.setdefault(rec["line"], set()).add(t_snap)
        for row in rec.get("rows", []):
            sid, train, updn, stid, stnm, st, rcp, direct, last, tnm = (row + [""] * 10)[:10]
            t = C.parse_kst(rcp)
            if t is None:
                continue
            lag = (t_snap - t).total_seconds()
            if lag > STALE_SEC or lag < -120:
                continue  # 오래된 위치(멈춘 정보)
            k = (sid, train, updn, stid, st, rcp)
            if k in seen:
                continue
            seen.add(k)
            lines[sid] = rec["line"]
            evs.append({"sid": sid, "train": train, "updn": updn, "stid": stid, "stnm": stnm, "st": st,
                        "t": t, "exp": 1 if direct in ("1", "7") else 0, "tnm": tnm, "snap": t_snap})
    return evs, lines, snaps


def runs_of(evs):
    """열차(노선·번호·방향)별로 시간순 → 구간이 끊기면 나눈다"""
    trips = {}
    for e in evs:
        trips.setdefault((e["sid"], e["train"], e["updn"]), []).append(e)
    out = []
    for key, es in trips.items():
        es.sort(key=lambda e: (e["t"], e["st"]))
        cur = []
        for e in es:
            seg, idx = seg_idx(e["stid"])
            if cur:
                pseg, pidx = seg_idx(cur[-1]["stid"])
                if seg != pseg or idx is None or pidx is None or abs(idx - pidx) > MAX_IDX_JUMP \
                        or (e["t"] - cur[-1]["t"]).total_seconds() > MAX_GAP_SEC:
                    out.append((key, cur))
                    cur = []
            cur.append(e)
        if cur:
            out.append((key, cur))
    return out


def express_stops(evs):
    """그날 급행이 도착·출발한 역(구간별)"""
    stops = set()
    for e in evs:
        if e["exp"] and e["st"] in ("1", "2"):
            stops.add(e["stid"])
    return stops


def passages_of_run(run, stations_by_seg, exp_stops):
    """한 열차 구간 → [(statnId, 시각, 직접여부)]"""
    out = {}
    exp = run[0]["exp"]
    # 1) 역에서 직접 본 사건
    for e in run:
        if e["st"] in DIRECT_SHIFT:
            t = e["t"] + dt.timedelta(seconds=DIRECT_SHIFT[e["st"]])
            prev = out.get(e["stid"])
            # 도착(1)을 가장 믿고, 없으면 진입·출발
            rank = {"1": 0, "0": 1, "2": 2}[e["st"]]
            if prev is None or rank < prev[2]:
                out[e["stid"]] = (t, 1, rank)
    # 2) 사이 역 보간
    seg, i0 = seg_idx(run[0]["stid"])
    _, i1 = seg_idx(run[-1]["stid"])
    if i0 is not None and i1 is not None and i0 != i1 and len(run) >= 2:
        s = 1 if i1 > i0 else -1
        pts = []
        for e in run:
            _, idx = seg_idx(e["stid"])
            p = idx + s * OFF.get(e["st"], 0.0)
            if pts and s * p < s * pts[-1][0] - 0.01:
                continue  # 뒤로 간 위치(정보 흔들림)는 버림
            pts.append((p, e["t"]))
        for (pa, ta), (pb, tb) in zip(pts, pts[1:]):
            span = (tb - ta).total_seconds()
            if span <= 0 or span > MAX_INTERP_SEC or pa == pb:
                continue
            lo, hi = sorted((pa, pb))
            for stid, idx in stations_by_seg.get(seg, []):
                if not (lo <= idx <= hi) or stid in out:
                    continue
                if exp and stid not in exp_stops:
                    continue  # 급행이 서지 않는 역
                t = ta + dt.timedelta(seconds=span * (idx - pa) / (pb - pa))
                out[stid] = (t, 0, 9)
    return [(stid, t, d) for stid, (t, d, _) in out.items()]


def build_day(records, date, settings):
    w0 = C.hm(date, settings["window"]["start"])
    w1 = C.hm(date, settings["window"]["end"])
    evs, lines, snaps = events_of(records, date)
    stations, by_seg = {}, {}
    for e in evs:
        if e["stid"] not in stations:
            stations[e["stid"]] = [e["stnm"], e["sid"]]
            seg, idx = seg_idx(e["stid"])
            if idx is not None:
                by_seg.setdefault(seg, []).append((e["stid"], idx))
    exp_stops = express_stops(evs)
    passages, terminals, nd, ni = {}, {}, 0, 0
    for (sid, train, updn), run in runs_of(evs):
        tnm = max((e["tnm"] for e in run), key=lambda x: sum(1 for e in run if e["tnm"] == x)) if run else ""
        for stid, t, direct in passages_of_run(run, by_seg, exp_stops):
            if not (w0 <= t < w1):
                continue
            key = f"{stid}|{updn}"
            sec = int(round((t - w0).total_seconds()))
            lst = passages.setdefault(key, {})
            if train in lst:
                continue
            lst[train] = [sec, run[0]["exp"], direct]
            if tnm:
                terminals.setdefault(key, {})
                terminals[key][tnm] = terminals[key].get(tnm, 0) + 1
            nd += direct
            ni += 1 - direct
    # 08:00에 가장 가까운 스냅숏의 노선별 열차 수
    t8 = C.hm(date, "08:00")
    trains_0800 = {}
    for line, ts in snaps.items():
        near = min(ts, key=lambda t: abs((t - t8).total_seconds()))
        if abs((near - t8).total_seconds()) <= settings["interval_sec"]:
            trains_0800[line] = len({(e["train"], e["updn"]) for e in evs
                                     if lines.get(e["sid"]) == line and e["snap"] == near})
    return {
        "date": date,
        "window": [settings["window"]["start"], settings["window"]["end"]],
        "interval_sec": settings["interval_sec"],
        "lines": lines,
        "snaps": {line: sorted(int((t - w0).total_seconds()) for t in ts) for line, ts in snaps.items()},
        "stations": stations,
        "passages": {k: sorted(v.values()) for k, v in passages.items()},
        "terminals": terminals,
        "trains_0800": trains_0800,
        "quality": {"events": len(evs), "direct": nd, "interp": ni},
    }


def headways(pass_list, min_gap=20):
    """[[초, ...], ...] → 연속 열차 사이 간격(초). 20초 미만은 같은 열차 중복으로 보고 버림"""
    secs = sorted(p[0] for p in pass_list)
    return [b - a for a, b in zip(secs, secs[1:]) if b - a >= min_gap]


def finalize_raw(date):
    """하루가 끝난 원본 .jsonl → .jsonl.gz (저장소 크기 줄이기)"""
    src, dst = C.raw_path(date), C.raw_path(date, gz=True)
    if os.path.exists(src):
        mode = "ab" if os.path.exists(dst) else "wb"
        with open(src, "rb") as f, gzip.open(dst, mode) as g:
            shutil.copyfileobj(f, g)
        os.remove(src)


def build(date, settings, finalize=False):
    records = C.read_raw(date)
    if not records:
        print(f" {date}: 원본 없음")
        return None
    day = build_day(records, date, settings)
    C.write_json(C.daily_path(date), day, compact=True)
    q = day["quality"]
    n = sum(len(v) for v in day["passages"].values())
    print(f" {date}: 노선 {len(day['snaps'])}개 · 역방향 {len(day['passages'])}곳 · 통과 {n:,}건 "
          f"(직접 {q['direct']:,} / 보간 {q['interp']:,})")
    end = C.hm(date, settings["snap_last"]) + dt.timedelta(minutes=1)
    if finalize or C.now_kst() > end + dt.timedelta(hours=1):
        finalize_raw(date)  # 하루 끝난 원본은 .gz 로(저장소에 올리는 것은 .gz 뿐)
    return day


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--finalize", action="store_true", help="수집이 끝났으니 원본을 .gz 로 묶기")
    a = ap.parse_args()
    settings = C.load_settings()
    if a.all:
        dates = sorted({os.path.basename(p).split(".")[0] for p in glob.glob(os.path.join(C.RAW, "*.jsonl*"))})
    else:
        dates = [a.date or C.now_kst().date().isoformat()]
    for d in dates:
        build(d, settings, finalize=a.finalize)
    return 0


if __name__ == "__main__":
    sys.exit(main())
