# -*- coding: utf-8 -*-
"""지하철 샘플러 공용: 경로·설정·키·시간(KST)·하루 호출 한도·JSON 읽고 쓰기."""
import datetime as dt
import gzip
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.dirname(ROOT)  # ...\Desktop\claude
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(DATA, "raw")
DAILY = os.path.join(DATA, "daily")
STATE = os.path.join(DATA, "state")
EXPORT = os.path.join(ROOT, "export")
KST = dt.timezone(dt.timedelta(hours=9))

# 키가 이 폴더 .env 에 없을 때 읽어 볼 다른 프로젝트(같은 사람의 같은 키)
KEY_FALLBACK = {
    "SEOUL_API_KEY": ["dongne-court", "seoul-guide"],
    "SEOUL_SUBWAY_KEY": ["last-train"],
}


def now_kst():
    return dt.datetime.now(KST)


def parse_kst(s):
    """'2026-11-23 08:01:23' → aware datetime(KST). 형식이 다르면 None."""
    if not s:
        return None
    s = s.strip().replace("T", " ")[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M%S"):
        try:
            return dt.datetime.strptime(s, fmt).replace(tzinfo=KST)
        except ValueError:
            pass
    return None


def hm(date, text):
    """date(YYYY-MM-DD 문자열 또는 date) + 'HH:MM' → KST datetime"""
    if isinstance(date, str):
        date = dt.date.fromisoformat(date)
    h, m = (int(x) for x in text.split(":"))
    return dt.datetime(date.year, date.month, date.day, h, m, tzinfo=KST)


def load_settings():
    return read_json(os.path.join(ROOT, "config", "settings.json"))


def is_workday(date, settings=None):
    settings = settings or load_settings()
    if isinstance(date, str):
        date = dt.date.fromisoformat(date)
    return date.weekday() < 5 and date.isoformat() not in set(settings.get("holidays", []))


# ---------------------------------------------------------------- 키
def read_env(path):
    out = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def get_key(name):
    """환경변수(GitHub Secrets) → 이 폴더 .env → 같은 키를 가진 다른 프로젝트 .env"""
    if os.environ.get(name):
        return os.environ[name].strip()
    v = read_env(os.path.join(ROOT, ".env")).get(name)
    if v:
        return v
    for p in KEY_FALLBACK.get(name, []):
        v = read_env(os.path.join(BASE, p, ".env")).get(name)
        if v:
            return v
    return ""


def mask(k):
    return k[:4] + "****" + k[-4:] if len(k) > 8 else "****"


# ---------------------------------------------------------------- 하루 호출 한도
class BudgetExceeded(Exception):
    pass


class Budget:
    """샘플러가 오늘 쓴 호출 수(KST 날짜 기준)를 파일에 적어 두고 한도를 넘지 않게 막는다."""

    def __init__(self, limit, today=None, state_dir=STATE):
        self.limit = limit
        self.today = (today or now_kst().date()).isoformat()
        self.path = os.path.join(state_dir, f"calls_{self.today}.json")
        self.used = read_json(self.path, {}).get("n", 0)

    def left(self):
        return max(0, self.limit - self.used)

    def take(self, n=1):
        if self.used + n > self.limit:
            raise BudgetExceeded(f"오늘 샘플러 몫 {self.limit}회를 다 씀({self.used}회)")
        self.used += n
        write_json(self.path, {"n": self.used, "limit": self.limit})


# ---------------------------------------------------------------- JSON
def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj, compact=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    opener = gzip.open if path.endswith(".gz") else open
    tmp = path + ".tmp"
    with opener(tmp, "wt", encoding="utf-8", newline="\n") as f:
        if compact:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def daily_path(date):
    return os.path.join(DAILY, f"{date}.json.gz")


def raw_path(date, gz=False):
    return os.path.join(RAW, f"{date}.jsonl" + (".gz" if gz else ""))


def read_raw(date):
    """하루 원본 스냅숏 줄들. 진행 중(.jsonl)과 끝난 것(.jsonl.gz)을 모두 읽는다."""
    out = []
    for p, opener in ((raw_path(date, True), gzip.open), (raw_path(date), open)):
        if os.path.exists(p):
            with opener(p, "rt", encoding="utf-8") as f:
                out.extend(json.loads(l) for l in f if l.strip())
    return out


def norm_name(name):
    """역 이름 맞추기: '서울역'·'서울' / '총신대입구(이수)' → '총신대입구'"""
    n = (name or "").strip()
    if "(" in n:
        n = n.split("(")[0].strip()
    if n.endswith("역") and len(n) > 2:
        n = n[:-1]
    return n
