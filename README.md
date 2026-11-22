# 지하철 샘플러 — subway-sampler

평일 아침(07~09시) 서울 지하철 열차 위치를 4분마다 받아, **역·방향별로 열차가 실제로 지나간 시각**을 쌓는 수집기입니다.
쌓은 데이터는 두 서비스에 붙입니다.

| 붙는 곳 | 기능 | 출력 | 붙이는 법 |
|---|---|---|---|
| A 빌라판독기 | 출근길 실측: 건물 근처 역의 평일 아침 실제 배차 | `export/villa/commute.json` + `export/villa/commute_lookup.js` | `docs/붙이는_법_A.md` |
| B 이달의 생활숫자 | 이달의 지하철 숫자 코너(④) | `export/life_numbers/YYYY-MM.json` (facts 항목 모양) | `docs/붙이는_법_B.md` |

아이디어·결정: `claude\2026-11-23_실시간지하철_서비스_아이디어.md` · 개발 기록: `claude\2026-11-23_지하철샘플러_개발.md`

## 하루 호출 한도 (중요)

실시간 지하철 키는 **하루 1,000회**이고, 활용사례를 등록해도 이 키는 한도가 풀리지 않습니다. 같은 키를 막차 레이더(`claude\last-train`)도 씁니다.

| 쓰는 곳 | 몫 |
|---|---|
| 지하철 샘플러 | 448회: 14개 노선 × 32번(06:58~09:02, 4분 간격), 평일만 |
| 막차 레이더 | 500회 이하: 밤 시간대에만, 캐시로 묶음 |
| 시험용 여유 | 50회 정도 |

노선은 `config/settings.json`의 `lines` 순서대로 한도 안에 들어가는 만큼만 받습니다. 지금은 공항철도·경춘선이 빠집니다(`python pipeline/collect.py --plan`).

## 명령 (subway-sampler 폴더에서)

```powershell
python pipeline/collect.py --probe        # 키 넣은 뒤 처음 한 번: 노선별 형식·지원 여부(처음_확인.bat)
python pipeline/collect.py --plan         # 오늘 몇 노선 × 몇 번 부를지
python pipeline/collect.py --morning      # 평일 아침 수집(주말·공휴일은 그냥 끝남)
python pipeline/passages.py --finalize    # 하루 원본 → 통과 시각(data/daily) + 원본 .gz 묶기
python pipeline/export_villa.py           # A용 출근길 실측(최근 평일 20일)
python pipeline/export_life.py --ym 2026-12   # B용 이달의 지하철 숫자
python pipeline/stations.py               # 역 좌표 다시 받기(일반 키, 한도 걱정 없음)
python -m unittest discover -s tests      # 파이썬 테스트 14개
node --test tests/commute_lookup.test.mjs # A용 JS 모듈 테스트 3개
```

`아침수집_지금.bat`: 이 PC에서 아침 수집부터 출력까지 한 번에 돌립니다(창을 닫으면 멈춤).

## 계산 방법

- 위치 API는 열차마다 마지막 사건(진입·도착·출발·전역출발)과 그 시각(초 단위)을 줍니다. 4분마다 받아도 사건 시각은 정확합니다.
- 같은 열차의 두 사건 사이에 있는 역은 위치를 직선으로 이어 지나간 시각을 추정합니다(가짜 운행 시험에서 오차 20초 이내).
- 급행은 그날 급행이 실제로 선 역에서만 지나간 것으로 셉니다.
- 휴일처럼 열차가 적은 날(중간값의 80% 미만)과 수집이 70% 미만인 날은 통계에서 뺍니다.
- 긴 공백은 옆 역에서도 같은 시간에 비어 있었던 경우만 셉니다(수집이 빠져서 생긴 가짜 공백 걸러내기).

## 폴더

| 위치 | 내용 |
|---|---|
| `config/settings.json` | 노선·시간대·간격·한도·공휴일 |
| `config/station_master.json` | 역 좌표 784곳(서울시 역사마스터) |
| `data/raw/` | 하루 원본(수집 중 `.jsonl`, 끝나면 `.jsonl.gz`) |
| `data/daily/` | 하루 통과 시각 `.json.gz` |
| `data/state/` | 날짜별 호출 수(한도 지키기) |
| `export/` | A·B에 넘기는 파일 |
| `.github/workflows/morning.yml` | 평일 06:40 KST 자동 수집(저장소 만든 뒤 켬) |

## 원칙

- 키는 `.env`(git 제외)와 GitHub Secrets에만 둡니다. 키 넣기는 `공공데이터_서비스4종\모든_키_넣기.bat` 6번(실시간 지하철)·2번(일반 키)으로 합니다. 일반 키는 역 좌표를 다시 받을 때만 쓰고, 이 폴더에 없으면 `dongne-court\.env`에서 읽습니다. GitHub Actions에는 `SEOUL_SUBWAY_KEY` Secret 하나만 넣습니다.
- 실시간 지하철 키는 일반 인증키와 **다른 키**입니다. 일반 키를 넣으면 `ERROR-338`(실시간 서비스를 쓸 수 없음)이 납니다.
- A·B 폴더는 건드리지 않습니다. A·B가 이 폴더의 `export/`를 읽어 갑니다.
- 화면에는 "평일 07~09시 실측, 몇십 초 오차"와 출처(서울 열린데이터광장)를 함께 표시합니다.
