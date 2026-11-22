# -*- coding: utf-8 -*-
"""
역 좌표: 서울시 역사마스터 정보(subwayStationMaster, 일반 인증키 SEOUL_API_KEY, 한도 걱정 없음).

  python pipeline/stations.py         # config/station_master.json 새로 받기(1회 호출)

결과: {"기준일", "출처", "rows": [[역이름, 노선, 위도, 경도], ...]}
"""
import json
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

PATH = os.path.join(C.ROOT, "config", "station_master.json")
SOURCE = "서울시 역사마스터 정보(서울 열린데이터광장)"


def fetch():
    key = C.get_key("SEOUL_API_KEY")
    if not key:
        print(" 서울 열린데이터광장 일반 키(SEOUL_API_KEY)가 없습니다. 모든_키_넣기.bat → 2번")
        return None
    url = f"http://openapi.seoul.go.kr:8088/{urllib.parse.quote(key, safe='')}/json/subwayStationMaster/1/1000/"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "subway-sampler/0.1"}),
                                timeout=30) as r:
        d = json.loads(r.read().decode("utf-8"))
    body = d.get("subwayStationMaster") or {}
    code = (body.get("RESULT") or d.get("RESULT") or {}).get("CODE")
    if code != "INFO-000":
        print(f" 역사마스터 응답 이상: {json.dumps(d, ensure_ascii=False)[:200]}")
        return None
    rows = [[r["BLDN_NM"], r["ROUTE"], float(r["LAT"]), float(r["LOT"])] for r in body.get("row", [])
            if r.get("LAT") and r.get("LOT")]
    out = {"기준일": C.now_kst().date().isoformat(), "출처": SOURCE, "rows": rows}
    C.write_json(PATH, out)
    print(f" 역 좌표 {len(rows)}곳 저장 → config/station_master.json")
    return out


def load():
    return C.read_json(PATH, {"rows": []})


def coord_index(master=None):
    """정규화한 역 이름 → [(노선, 위도, 경도), ...]"""
    master = master or load()
    acc = {}
    for name, line, lat, lng in master.get("rows", []):
        acc.setdefault(C.norm_name(name), []).append((line, lat, lng))
    return acc


def _dist_m(a, b):
    import math
    dy = (a[0] - b[0]) * 111_000
    dx = (a[1] - b[1]) * 111_000 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dx, dy)


def _line_like(a, b):
    """'경의중앙선'↔'경의선'·'중앙선', '2호선'↔'2호선' 처럼 같은 노선으로 볼지"""
    a, b = a.replace("선", ""), b.replace("선", "")
    return a == b or a in b or b in a or (len(a) >= 2 and len(b) >= 2 and a[:2] == b[:2])


def lookup(index, name, line):
    """역 이름(+노선) → (위도, 경도) 또는 None.
    환승역은 노선마다 좌표가 조금 달라 평균을 쓰고, 이름은 같은데 서로 먼 역(5호선 양평·경의중앙 양평)은 노선으로 가린다."""
    cands = index.get(C.norm_name(name), [])
    if not cands:
        return None
    first = (cands[0][1], cands[0][2])
    if all(_dist_m(first, (lat, lng)) < 1500 for _, lat, lng in cands):
        pick = cands
    else:
        pick = [c for c in cands if _line_like(line, c[0])]
        if not pick:
            return None
    return (round(sum(c[1] for c in pick) / len(pick), 6), round(sum(c[2] for c in pick) / len(pick), 6))


if __name__ == "__main__":
    sys.exit(0 if fetch() else 1)
