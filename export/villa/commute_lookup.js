// 출근길 실측 찾기 — 빌라판독기(A)에 그대로 복사해 쓰는 모듈(web/src/commute.js 로 두면 됨)
// 데이터: subway-sampler/export/villa/commute.json → A의 web/data/commute.json
// 브라우저와 node 테스트가 같은 파일을 쓴다. 화면 문구는 여기 함수로만 만든다.

const WALK_M_PER_MIN = 75; // 시속 4.5km
const DETOUR = 1.25; // 직선거리 → 실제 걷는 길

export function distM([lat1, lng1], [lat2, lng2]) {
  const r = Math.PI / 180;
  const dy = (lat1 - lat2) * 111000;
  const dx = (lng1 - lng2) * 111000 * Math.cos(((lat1 + lat2) / 2) * r);
  return Math.hypot(dx, dy);
}

export function walkMin(m) {
  return Math.max(1, Math.round((m * DETOUR) / WALK_M_PER_MIN));
}

// 건물 좌표(ll: [위도, 경도]) → 가까운 역 k곳(maxM 안). 좌표 없는 역은 건너뜀.
export function nearestStations(ll, commute, { maxM = 1000, k = 3 } = {}) {
  if (!ll || !commute || !commute.stations) return [];
  return commute.stations
    .filter((s) => s.좌표)
    .map((s) => ({ ...s, 거리m: Math.round(distM(ll, s.좌표)) }))
    .filter((s) => s.거리m <= maxM)
    .sort((a, b) => a.거리m - b.거리m)
    .slice(0, k)
    .map((s) => ({ ...s, 도보분: walkMin(s.거리m) }));
}

export function fmtSec(sec) {
  const s = Math.round(sec);
  const m = Math.floor(s / 60), r = s % 60;
  if (m === 0) return `${r}초`;
  return r ? `${m}분 ${r}초` : `${m}분`;
}

// 한 방향 → 한 줄 설명. 예: "성수행 · 평균 2분 30초마다 · 10번 중 9번은 4분 안에 옴"
export function describeDir(d) {
  const parts = [d.방면, `보통 ${fmtSec(d.배차_중간값_초)}마다`, `10번 중 9번은 ${fmtSec(d.배차_90_초)} 안에 옴`];
  if (d.급행_비율 >= 0.05) parts.push(`급행 ${Math.round(d.급행_비율 * 100)}%`);
  return parts.join(" · ");
}

// 화면 아래 작은 글씨용 기준 문구
export function basisText(meta) {
  if (!meta) return "";
  if (meta.모으는_중) return "출근길 실측 데이터를 모으는 중입니다.";
  const [a, b] = meta.기간 || [];
  return `${meta.시간대} 실측 · ${a}~${b} 평일 ${meta.평일수}일 · 출처: ${meta.출처}`;
}
