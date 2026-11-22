# -*- coding: utf-8 -*-
"""여러 날 묶기 공용: 쓸 날 고르기(휴일 같은 날·수집 덜 된 날 빼기), 역·방향별 통계, 방면 이름."""
import glob
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
from passages import headways, span_avg  # noqa: E402

CIRCLE = {"1002": {"0": "내선순환", "1": "외선순환"}}


def load_days(dates=None):
    paths = sorted(glob.glob(os.path.join(C.DAILY, "*.json.gz")))
    days = []
    for p in paths:
        d = os.path.basename(p).split(".")[0]
        if dates is None or d in dates:
            days.append(C.read_json(p))
    return days


def total_passages(day):
    return sum(len(v) for v in day["passages"].values())


def expected_snaps(date, settings):
    from collect import snap_times
    return len(snap_times(date, settings))


def usable(days, settings):
    """평일만, 수집이 70% 이상 된 날만, 통과 건수가 중간값의 80% 미만인 날(휴일 같은 날)은 뺀다.
    돌려주는 값: (쓸 날, [(뺀 날, 이유)])"""
    out, dropped = [], []
    for d in days:
        if not C.is_workday(d["date"], settings):
            dropped.append((d["date"], "주말·공휴일"))
            continue
        snaps = d.get("snaps", {})
        cover = (statistics.median(len(v) for v in snaps.values()) / expected_snaps(d["date"], settings)) if snaps else 0
        if cover < 0.7:
            dropped.append((d["date"], f"수집 {cover:.0%}만 됨"))
            continue
        out.append(d)
    if len(out) >= 3:
        med = statistics.median(total_passages(d) for d in out)
        keep = []
        for d in out:
            if total_passages(d) < settings.get("holiday_like_ratio", 0.8) * med:
                dropped.append((d["date"], "열차가 평소보다 적음(휴일형 운행)"))
            else:
                keep.append(d)
        out = keep
    return out, dropped


def pct(vals, q):
    """q 분위(0~1), 선형 보간"""
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def station_dir_stats(days, window_hours=2.0):
    """'statnId|updn' → 통계. 날마다 간격을 구해 모은다(날을 넘는 간격은 만들지 않음)."""
    acc = {}
    for d in days:
        for key, plist in d["passages"].items():
            a = acc.setdefault(key, {"hw": [], "h2": [], "counts": [], "exp": [], "days": 0, "terms": {},
                                     "maxgap": (0, None)})
            hw = headways(plist)
            a["hw"].extend(hw)
            a["h2"].extend(span_avg(plist, 2))
            a["counts"].append(len(plist))
            a["exp"].extend(p[1] for p in plist)
            a["days"] += 1
            if hw and max(hw) > a["maxgap"][0]:
                a["maxgap"] = (max(hw), d["date"])
            for t, n in d.get("terminals", {}).get(key, {}).items():
                a["terms"][t] = a["terms"].get(t, 0) + n
    out = {}
    for key, a in acc.items():
        if not a["hw"]:
            continue
        out[key] = {
            # 보통 배차 = 두 칸 평균 간격의 중간값(흔들림에 강함), 90% = 실제 간격(긴 기다림은 그대로 드러나게)
            "배차_중간값_초": round(statistics.median(a["h2"] or a["hw"])),
            "배차_90_초": round(pct(a["hw"], 0.9)),
            "시간당_열차": round(statistics.mean(a["counts"]) / window_hours, 1),
            "급행_비율": round(sum(a["exp"]) / len(a["exp"]), 3) if a["exp"] else 0,
            "관측일": a["days"],
            "가장긴_간격_초": a["maxgap"][0],
            "가장긴_간격_날": a["maxgap"][1],
            "_terms": a["terms"],
            "_hw": a["hw"],
            "_h2": a["h2"] or a["hw"],
        }
    return out


def direction_label(sid, updn, terms):
    if sid in CIRCLE:
        return CIRCLE[sid].get(updn, updn)
    top = sorted(terms.items(), key=lambda x: -x[1])
    if not top:
        return "상행" if updn == "0" else "하행"
    total = sum(n for _, n in top)
    names = [t for t, n in top[:2] if n >= 0.25 * total]
    return "·".join(C.norm_name(t) for t in names) + "행"


def station_meta(days):
    """statnId → (역이름, subwayId, 노선이름) — 가장 최근 날 기준"""
    out = {}
    for d in days:
        for stid, (name, sid) in d["stations"].items():
            out[stid] = (name, sid, d["lines"].get(sid, sid))
    return out


def fmt_min_sec(sec):
    sec = int(round(sec))
    m, s = divmod(sec, 60)
    return f"{m}분 {s}초" if s else f"{m}분"
