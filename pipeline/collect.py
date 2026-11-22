# -*- coding: utf-8 -*-
"""
서울 실시간 열차 위치(realtimePosition)를 노선별로 받아 하루 원본에 쌓는다.

  python pipeline/collect.py --probe          # 키 넣은 뒤 첫 실행: 노선마다 1회씩 불러 형식·지원 노선 확인(18회 안팎)
  python pipeline/collect.py --once           # 지금 스냅숏 1번(받는 노선 전부)
  python pipeline/collect.py --morning        # 평일 아침 수집(06:58~09:02, 4분 간격). 주말·공휴일은 그냥 끝남
  python pipeline/collect.py --morning --force   # 주말에도 시험 삼아 돌리기
  python pipeline/collect.py --plan           # 오늘 몇 노선 × 몇 번 부를지(한도 계산)만 보기

원본: data/raw/YYYY-MM-DD.jsonl  한 줄 = 스냅숏 한 번의 한 노선
  {"t": 스냅숏 시각, "line": "2호선", "code": "INFO-000", "rows": [[subwayId, trainNo, updnLine, statnId, statnNm,
   trainSttus, recptnDt, directAt, lstcarAt, statnTnm], ...]}
하루 한도: 실시간 지하철 키는 하루 1,000회. 샘플러 몫은 settings.daily_budget(450)이고 넘으면 멈춘다.
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

FIELDS = ["subwayId", "trainNo", "updnLine", "statnId", "statnNm", "trainSttus", "recptnDt",
          "directAt", "lstcarAt", "statnTnm"]


class StopAll(Exception):
    """키 문제·한도 초과처럼 더 불러도 소용없는 상황"""


def snap_times(date, settings):
    t = C.hm(date, settings["snap_first"])
    end = C.hm(date, settings["snap_last"])
    out = []
    while t <= end:
        out.append(t)
        t += dt.timedelta(seconds=settings["interval_sec"])
    return out


def plan_lines(settings, n_snaps):
    """하루 한도 안에 들어가는 노선(우선순위 앞에서부터)"""
    per_line = max(1, n_snaps)
    k = max(0, settings["daily_budget"] // per_line)
    return settings["lines"][:k]


def fetch(line, key, settings):
    url = (f"{settings['base_url']}/{urllib.parse.quote(key, safe='')}/json/realtimePosition/0/300/"
           f"{urllib.parse.quote(line)}")
    req = urllib.request.Request(url, headers={"User-Agent": "subway-sampler/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return {"_http": e.code}
    except Exception as e:  # 네트워크
        return {"_net": str(e)[:200]}
    try:
        return json.loads(body)
    except ValueError:
        return {"_text": body[:300]}


def parse(resp):
    """응답 → (code, message, rows). 오류 모양이 두 가지라 둘 다 본다."""
    if "_http" in resp or "_net" in resp or "_text" in resp:
        return "NET", json.dumps(resp, ensure_ascii=False), []
    em = resp.get("errorMessage") or resp  # 정상일 때 errorMessage 안에 code가 있고, 오류면 맨 위에 있다
    code = str(em.get("code", "") or "")
    msg = str(em.get("message", "") or "")
    rows = []
    for r in resp.get("realtimePositionList") or []:
        rows.append([str(r.get(f, "") or "") for f in FIELDS])
    return code, msg, rows


def is_fatal(code, msg):
    """키가 틀렸거나 한도를 넘었으면 오늘은 그만"""
    if code in ("INFO-100", "ERROR-337", "ERROR-338"):
        return True
    return any(w in msg for w in ("인증키", "초과", "제한"))


def take_snapshot(t_snap, lines, key, settings, budget, out_path, verbose=True):
    got = 0
    for line in lines:
        budget.take(1)
        code, msg, rows = parse(fetch(line, key, settings))
        if code == "NET":  # 네트워크 한 번만 다시
            time.sleep(3)
            budget.take(1)
            code, msg, rows = parse(fetch(line, key, settings))
        rec = {"t": t_snap.isoformat(timespec="seconds"), "line": line, "code": code, "rows": rows}
        if code not in ("INFO-000", ""):
            rec["msg"] = msg[:200]
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
        got += len(rows)
        if is_fatal(code, msg):
            raise StopAll(f"{line}: {code} {msg}")
    if verbose:
        print(f" {t_snap:%H:%M} 열차 {got}대 기록 (오늘 {budget.used}/{budget.limit}회)", flush=True)
    return got


def cmd_probe(key, settings):
    budget = C.Budget(1000)  # 시험은 샘플러 몫과 별도로 세되, 키 전체 한도는 넘지 않게
    fx = os.path.join(C.ROOT, "tests", "fixtures")
    os.makedirs(fx, exist_ok=True)
    print(f" 키 {C.mask(key)} 로 노선별 1회씩 확인")
    ok = []
    for line in settings["probe_lines"]:
        budget.take(1)
        resp = fetch(line, key, settings)
        code, msg, rows = parse(resp)
        print(f"  {line:<8} {code:<10} 열차 {len(rows):>3}대  {msg[:40]}")
        if rows:
            ok.append(line)
            with open(os.path.join(fx, f"real_position_{line}.json"), "w", encoding="utf-8") as f:
                json.dump(resp, f, ensure_ascii=False, indent=1)
        if code == "ERROR-338":
            print("  → 이 키는 일반 인증키입니다. 서울 열린데이터광장 '인증키 신청'에서 '실시간 지하철 인증키'를 따로 받아 6번에 넣어 주세요.")
            return 1
        if is_fatal(code, msg):
            print("  → 키가 아직 안 됐거나 한도에 걸림. 키를 다시 넣거나(모든_키_넣기.bat 6번) 1~2시간 뒤 다시.")
            return 1
    print(f" 데이터가 오는 노선 {len(ok)}개: {', '.join(ok)}")
    print(" 원본 응답은 tests/fixtures/real_position_*.json 에 저장(공개 데이터만 들어 있음)")
    return 0


def cmd_morning(key, settings, force=False, today=None):
    now = C.now_kst()
    today = today or now.date()
    if not force and not C.is_workday(today, settings):
        print(f" {today} 은 평일이 아니라 수집하지 않음")
        return 0
    snaps = snap_times(today, settings)
    lines = plan_lines(settings, len(snaps))
    skipped = settings["lines"][len(lines):]
    print(f" {today} 아침 수집: 노선 {len(lines)}개 × 최대 {len(snaps)}번 (한도 {settings['daily_budget']}회)")
    if skipped:
        print(f"  한도 때문에 뺀 노선: {', '.join(skipped)}")
    budget = C.Budget(settings["daily_budget"], today)
    out = C.raw_path(today.isoformat())
    done = {r["t"] for r in C.read_raw(today.isoformat())}
    for t in snaps:
        if t.isoformat(timespec="seconds") in done:
            continue
        wait = (t - C.now_kst()).total_seconds()
        if wait < -settings["interval_sec"] / 2:
            continue  # 이미 지나간 칸(늦게 시작함)
        if wait > 0:
            time.sleep(wait)
        if budget.left() < len(lines):
            print(" 오늘 몫을 다 써서 멈춤")
            break
        try:
            take_snapshot(t, lines, key, settings, budget, out)
        except StopAll as e:
            print(f" 멈춤: {e}")
            return 2
        except C.BudgetExceeded as e:
            print(f" 멈춤: {e}")
            break
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--morning", action="store_true")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    settings = C.load_settings()
    if a.plan:
        today = C.now_kst().date()
        snaps = snap_times(today, settings)
        lines = plan_lines(settings, len(snaps))
        print(f" 스냅숏 {len(snaps)}번 × 노선 {len(lines)}개 = {len(snaps) * len(lines)}회 / 한도 {settings['daily_budget']}회")
        print(f" 받는 노선: {', '.join(lines)}")
        print(f" 뺀 노선: {', '.join(settings['lines'][len(lines):]) or '없음'}")
        return 0
    key = C.get_key("SEOUL_SUBWAY_KEY")
    if not key:
        if os.environ.get("GITHUB_ACTIONS"):
            print("::warning::SEOUL_SUBWAY_KEY Secret이 아직 없어 수집을 건너뜀")
            return 0  # 키를 넣기 전까지 매일 실패 메일이 가지 않게
        print(" 실시간 지하철 키가 없습니다. 공공데이터_서비스4종\\모든_키_넣기.bat → 6번에서 넣어 주세요.")
        return 1
    if a.probe:
        return cmd_probe(key, settings)
    if a.once:
        now = C.now_kst().replace(microsecond=0)
        snaps = snap_times(now.date(), settings)
        lines = plan_lines(settings, len(snaps))
        budget = C.Budget(settings["daily_budget"], now.date())
        take_snapshot(now, lines, key, settings, budget, C.raw_path(now.date().isoformat()))
        return 0
    if a.morning:
        return cmd_morning(key, settings, a.force)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
