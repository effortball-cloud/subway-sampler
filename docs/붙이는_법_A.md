# A 빌라판독기에 '출근길 실측' 붙이는 법

작성 2026-11-23 · 만든 곳: `claude\subway-sampler` · 이 문서 사본: `villa-check\docs\지하철_출근길실측_붙이기.md`

## 무엇을 보여 주나

건물 카드에 가까운 역 1~2곳의 **평일 아침(07~09시) 실제 배차**를 보여 줍니다. 시간표가 아니라 실측이라는 점이 차별점입니다.

```
🚇 출근길 실측
교대역 · 도보 6분
  2호선 내선순환 · 보통 2분 30초마다 · 10번 중 9번은 4분 안에 옴
  3호선 오금행 · 보통 4분마다 · 10번 중 9번은 6분 안에 옴
평일 07:00~09:00 실측 · 2026-11-23~2026-12-24 평일 24일 · 출처: 서울 열린데이터광장
```

## 붙이는 순서 (A 세션에서)

1. **데이터**: `subway-sampler\export\villa\commute.json`을 `villa-check\web\data\commute.json`으로 복사합니다.
   - 로컬: `build_index.py` 끝에 복사 한 줄을 넣거나 따로 복사합니다.
   - 배포(GitHub Actions): A 워크플로에서 샘플러 저장소의 파일을 내려받고, 실패하면 이전 파일을 그대로 둡니다(공통 원칙: 원천이 멈추면 마지막 데이터 유지).
     `curl -sfL https://raw.githubusercontent.com/<계정>/subway-sampler/main/export/villa/commute.json -o web/data/commute.json.new && mv web/data/commute.json.new web/data/commute.json`
2. **모듈**: `subway-sampler\export\villa\commute_lookup.js`를 `villa-check\web\src\commute.js`로 복사합니다(테스트 있음: `subway-sampler\tests\commute_lookup.test.mjs`).
3. **화면**: 건물 카드에서 아래처럼 부릅니다. 건물 좌표는 `web/data/gu/*.json`의 `ll`([위도, 경도])입니다.
   ```js
   import { nearestStations, describeDir, basisText } from "./commute.js";
   const near = nearestStations(b.ll, commute, { maxM: 1000, k: 2 });   // 1km 안 2곳
   // near[i].역, near[i].도보분, near[i].노선[j].노선, near[i].노선[j].방향[k] → describeDir()
   // 맨 아래 작은 글씨: basisText(commute.meta)
   ```
   - 1km 안에 역이 없으면 칸을 숨기지 말고 "1km 안에 지하철역 없음"으로 보여 줍니다(빌라 고를 때 중요한 정보).
   - `commute.meta.모으는_중`이 true면 "출근길 실측 데이터를 모으는 중입니다."만 보여 줍니다.
4. **폰 375px 확인**: 노선이 3개인 환승역(예: 종로3가)에서 줄이 넘치지 않는지 봅니다.

## 파일 모양 (`commute.json`)

```json
{"meta": {"기간": ["2026-11-23","2026-12-24"], "평일수": 24, "시간대": "평일 07:00~09:00", "관측간격_초": 240,
          "출처": "...", "역좌표_출처": "...", "만든시각": "...", "주의": "...", "뺀_날": [], "모으는_중": false},
 "stations": [{"역": "교대", "좌표": [37.4935, 127.0142], "노선": [
   {"노선": "2호선", "방향": [{"방면": "내선순환", "배차_중간값_초": 150, "배차_90_초": 240,
                               "시간당_열차": 24.5, "급행_비율": 0.0, "관측일": 24}]}]}]}
```

## 일정

- 12-27 공개 때 평일 20일 이상을 보여 주려면 **이번 주부터 수집**해야 합니다. 11-23(월)에 시작하면 12-24까지 평일 24일, 11-30(월)에 시작하면 19일입니다.
- 관측일이 5일 미만인 역·방향은 파일에 넣지 않습니다(`settings.min_days_to_show`).

## 주의

- 문구는 "실측", "보통 ○분마다", "10번 중 9번은 ○분 안에"로 씁니다. "정시율", "지연" 같은 말은 시간표와 비교하지 않으므로 쓰지 않습니다.
- 출처 표시는 서울 열린데이터광장 실시간 지하철(서울특별시)과 역 좌표(서울시 역사마스터 정보)입니다.
