# -*- coding: utf-8 -*-
"""
B 이달의 생활숫자용 '이달의 지하철 숫자' facts 조각 만들기.

  python pipeline/export_life.py --ym 2026-12     # 그 달 평일 아침 관측으로

결과: export/life_numbers/YYYY-MM.json — 생활숫자 facts 항목과 같은 모양(factlib.py 주석 참고)
{
 "코너": "④", "코너_이름": "이달의 지하철 숫자", "기간": "2026-12", "관측_평일수": n,
 "출처": {"④": {"이름", "이용조건"}},
 "항목": [{"키","값","단위","기간","상태","출처","기준일","코너","예시","주의"}, ...],
 "표": {"지하철_노선별_출근배차": [...], "지하철_긴공백_TOP5": [...]}
}
단위 '초'·'대'·'%'를 쓴다. 생활숫자 쪽에 '초' 단위 서식(2분 30초)과 verify 대조를 붙여야 한다(docs/붙이는_법_B.md).
긴 공백은 '옆 역에서도 같은 시간에 비어 있었던 것'만 센다(수집이 빠진 탓으로 생긴 가짜 공백 걸러내기).
"""
import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agg  # noqa: E402
import common as C  # noqa: E402
from passages import seg_idx  # noqa: E402

SOURCE = {"이름": "서울 열린데이터광장 실시간 지하철 열차 위치(서울특별시) — 평일 07~09시 4분 간격 관측",
          "이용조건": "출처 표시"}
NOTE = "평일 07~09시, 4분 간격 열차 위치 관측으로 추정한 값"
MIN_GAP = 8 * 60


def gaps_of(plist):
    secs = sorted(p[0] for p in plist)
    return [(a, b) for a, b in zip(secs, secs[1:]) if b - a >= MIN_GAP]


def snaps_ok(day, line, a, b):
    """a~b초 사이에 그 노선 스냅숏이 빠짐없이 있었는지"""
    ts = [t for t in day["snaps"].get(line, []) if a - day["interval_sec"] <= t <= b + day["interval_sec"]]
    if len(ts) < 2:
        return False
    return all(y - x <= 1.6 * day["interval_sec"] for x, y in zip(ts, ts[1:]))


def corroborated_gaps(day):
    """옆 역(같은 구간 번호 ±1, 같은 방향)에서도 70% 이상 겹치는 공백이 있으면 진짜 공백으로 본다"""
    by_seg = {}
    for key in day["passages"]:
        stid, updn = key.split("|")
        seg, idx = seg_idx(stid)
        if idx is not None:
            by_seg[(seg, idx, updn)] = key
    out = []
    for key, plist in day["passages"].items():
        stid, updn = key.split("|")
        seg, idx = seg_idx(stid)
        if idx is None:
            continue
        name, sid = day["stations"].get(stid, ["", ""])
        line = day["lines"].get(sid, sid)
        for a, b in gaps_of(plist):
            if not snaps_ok(day, line, a, b):
                continue
            best = None
            for nidx in (idx - 1, idx + 1):
                nkey = by_seg.get((seg, nidx, updn))
                if not nkey:
                    continue
                for a2, b2 in gaps_of(day["passages"][nkey]):
                    ov = min(b, b2) - max(a, a2)
                    if ov >= 0.7 * min(b - a, b2 - a2):
                        best = max(best or 0, b2 - a2)
            if best:
                # 끝 역은 열차가 사라져 공백이 길게 보일 수 있어, 옆 역과 비교해 짧은 쪽을 쓴다
                out.append({"역": C.norm_name(name), "노선": line, "updn": updn, "sid": sid,
                            "공백_초": min(b - a, best), "날짜": day["date"], "시작_초": a})
    return out


def item(key, val, unit, ym, note=NOTE):
    return {"키": key, "값": val, "단위": unit, "기간": [ym], "상태": "확정", "출처": SOURCE["이름"],
            "기준일": C.now_kst().date().isoformat(), "코너": "④", "예시": False, "주의": note}


def build(ym, settings):
    days_all = [d for d in agg.load_days() if d["date"].startswith(ym)]
    days, dropped = agg.usable(days_all, settings)
    items, tables = [], {}
    items.append(item("지하철_관측_평일수", len(days), "일", ym))
    if days:
        t8 = [sum(d["trains_0800"].values()) for d in days if d.get("trains_0800")]
        if t8:
            items.append(item("지하철_8시_운행열차", round(statistics.mean(t8)), "대", ym,
                              NOTE + ". 08시 무렵 한 순간에 위치가 잡힌 열차 수(받는 노선 기준)"))
        stats = agg.station_dir_stats(days)
        meta_by = agg.station_meta(days)
        per_line = {}
        for key, s in stats.items():
            stid, _ = key.split("|")
            _, sid, line = meta_by.get(stid, ("", "", ""))
            pl = per_line.setdefault(line, {"hw": [], "exp": [], "tph": []})
            pl["hw"].extend(s["_hw"])
            if s["급행_비율"] > 0:
                pl["exp"].append(s["급행_비율"])  # 급행이 서는 역만(서지 않는 역까지 넣으면 비율이 낮게 나옴)
            pl["tph"].append(s["시간당_열차"])
        rows = []
        for line, pl in per_line.items():
            if not pl["hw"]:
                continue
            rows.append({"노선": line, "배차_중간값_초": round(statistics.median(pl["hw"])),
                         "시간당_열차": round(statistics.median(pl["tph"]), 1),
                         "급행_비율_%": round(100 * statistics.median(pl["exp"]), 1) if pl["exp"] else 0.0})
        rows.sort(key=lambda r: r["배차_중간값_초"])
        tables["지하철_노선별_출근배차"] = rows
        if rows:
            items.append(item("지하철_출근배차_가장촘촘_초", rows[0]["배차_중간값_초"], "초", ym,
                              f"{NOTE}. 노선: {rows[0]['노선']}"))
            items.append(item("지하철_출근배차_가장성김_초", rows[-1]["배차_중간값_초"], "초", ym,
                              f"{NOTE}. 노선: {rows[-1]['노선']}"))
            for r in rows:
                if r["급행_비율_%"] >= 5:
                    items.append(item(f"지하철_급행비율_{r['노선']}", r["급행_비율_%"], "%", ym))
        gaps = []
        for d in days:
            gaps.extend(corroborated_gaps(d))
        # 같은 날·같은 노선·같은 방향은 가장 긴 것 하나만(한 사건이 여러 역에 걸쳐 보이므로)
        best = {}
        for g in gaps:
            k = (g["날짜"], g["노선"], g["updn"])
            if k not in best or g["공백_초"] > best[k]["공백_초"]:
                best[k] = g
        top = sorted(best.values(), key=lambda g: -g["공백_초"])[:5]
        tables["지하철_긴공백_TOP5"] = [
            {"역": g["역"], "노선": g["노선"],
             "시각": f"{7 + g['시작_초'] // 3600:02d}:{(g['시작_초'] % 3600) // 60:02d}",
             "공백_초": g["공백_초"], "날짜": g["날짜"]} for g in top]
        if top:
            items.append(item("지하철_가장긴_공백_초", top[0]["공백_초"], "초", ym,
                              f"{NOTE}. 옆 역에서도 같은 시간에 비어 있던 경우만. {top[0]['날짜']} {top[0]['노선']} {top[0]['역']}"))
    out = {"코너": "④", "코너_이름": "이달의 지하철 숫자", "기간": ym, "관측_평일수": len(days),
           "출처": {"④": SOURCE}, "항목": items, "표": tables, "뺀_날": dropped,
           "만든시각": C.now_kst().isoformat(timespec="seconds")}
    path = os.path.join(C.EXPORT, "life_numbers", f"{ym}.json")
    C.write_json(path, out)
    print(f" 이달의 지하철 숫자 {ym}: 평일 {len(days)}일 · 항목 {len(items)}개 → export/life_numbers/{ym}.json")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ym", default=C.now_kst().strftime("%Y-%m"))
    a = ap.parse_args()
    build(a.ym, C.load_settings())
    return 0


if __name__ == "__main__":
    sys.exit(main())
