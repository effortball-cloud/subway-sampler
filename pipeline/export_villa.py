# -*- coding: utf-8 -*-
"""
A 빌라판독기용 '출근길 실측' 파일 만들기.

  python pipeline/export_villa.py                 # 최근 평일 20일(settings.export_days)
  python pipeline/export_villa.py --days 10

결과: export/villa/commute.json  (A는 이 파일을 web/data/commute.json 으로 복사해 쓰고,
      export/villa/commute_lookup.js 로 건물 좌표 → 가까운 역 실측을 찾는다)
{
 "meta": {"기간": [첫날, 끝날], "평일수", "시간대": "평일 07:00~09:00", "관측간격_초": 240, "출처", "만든시각", "주의",
          "뺀_날": [[날짜, 이유], ...], "모으는_중": bool},
 "stations": [{"역": "교대", "좌표": [위도, 경도] | null, "노선": [
     {"노선": "2호선", "방향": [{"방면": "내선순환", "배차_중간값_초": 150, "배차_90_초": 240,
                                  "시간당_열차": 24.5, "급행_비율": 0.0, "관측일": 18}]}]}]
}
관측일이 settings.min_days_to_show(5)보다 적은 역·방향은 빼고, 모두 모자라면 meta.모으는_중 = true.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agg  # noqa: E402
import common as C  # noqa: E402
import stations as ST  # noqa: E402

SOURCE = "서울 열린데이터광장 실시간 지하철 열차 위치(서울특별시)"
NOTE = ("평일 아침 4분마다 열차 위치를 받아, 열차가 각 역을 지난 시각을 추정해 낸 값입니다. "
        "시간표가 아니라 실제 운행 기준이며, 몇십 초 오차가 있을 수 있습니다.")


def build(settings, n_days=None):
    n_days = n_days or settings["export_days"]
    days, dropped = agg.usable(agg.load_days(), settings)
    days = days[-n_days:]
    meta_by = agg.station_meta(days)
    stats = agg.station_dir_stats(days)
    index = ST.coord_index()
    min_days = settings["min_days_to_show"]
    by_name = {}
    for key, s in stats.items():
        if s["관측일"] < min_days:
            continue
        stid, updn = key.split("|")
        name, sid, line = meta_by.get(stid, (stid, "", ""))
        st = by_name.setdefault(C.norm_name(name), {"역": C.norm_name(name), "좌표": None, "노선": {}})
        if st["좌표"] is None:
            xy = ST.lookup(index, name, line)
            st["좌표"] = list(xy) if xy else None
        st["노선"].setdefault(line, []).append({
            "방면": agg.direction_label(sid, updn, s["_terms"]),
            "배차_중간값_초": s["배차_중간값_초"],
            "배차_90_초": s["배차_90_초"],
            "시간당_열차": s["시간당_열차"],
            "급행_비율": s["급행_비율"],
            "관측일": s["관측일"],
        })
    out_st = []
    for name in sorted(by_name):
        st = by_name[name]
        st["노선"] = [{"노선": ln, "방향": sorted(v, key=lambda x: x["방면"])} for ln, v in sorted(st["노선"].items())]
        out_st.append(st)
    out = {
        "meta": {
            "기간": [days[0]["date"], days[-1]["date"]] if days else None,
            "평일수": len(days),
            "시간대": f"평일 {settings['window']['start']}~{settings['window']['end']}",
            "관측간격_초": settings["interval_sec"],
            "출처": SOURCE,
            "역좌표_출처": ST.load().get("출처"),
            "만든시각": C.now_kst().isoformat(timespec="seconds"),
            "주의": NOTE,
            "뺀_날": dropped[-10:],
            "모으는_중": len(days) < min_days,
        },
        "stations": out_st,
    }
    path = os.path.join(C.EXPORT, "villa", "commute.json")
    C.write_json(path, out, compact=True)
    no_xy = sum(1 for s in out_st if not s["좌표"])
    print(f" 출근길 실측: 평일 {len(days)}일 · 역 {len(out_st)}곳(좌표 없음 {no_xy}) → export/villa/commute.json")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int)
    a = ap.parse_args()
    build(C.load_settings(), a.days)
    return 0


if __name__ == "__main__":
    sys.exit(main())
