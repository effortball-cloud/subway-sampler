// node --test tests/commute_lookup.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { nearestStations, describeDir, fmtSec, basisText, walkMin } from "../export/villa/commute_lookup.js";

const commute = {
  meta: { 기간: ["2026-12-01", "2026-12-26"], 평일수: 18, 시간대: "평일 07:00~09:00", 출처: "서울 열린데이터광장", 모으는_중: false },
  stations: [
    { 역: "교대", 좌표: [37.4934, 127.0142], 노선: [{ 노선: "2호선", 방향: [{ 방면: "내선순환", 배차_중간값_초: 150, 배차_90_초: 240, 시간당_열차: 24, 급행_비율: 0, 관측일: 18 }] }] },
    { 역: "서초", 좌표: [37.4918, 127.0076], 노선: [] },
    { 역: "강남", 좌표: [37.4979, 127.0276], 노선: [] },
    { 역: "좌표없음", 좌표: null, 노선: [] },
  ],
};

test("가까운 역 순서·거리·도보", () => {
  const r = nearestStations([37.4930, 127.0130], commute, { maxM: 1000, k: 3 });
  assert.deepEqual(r.map((s) => s.역), ["교대", "서초"]);
  assert.ok(r[0].거리m < 150);
  assert.equal(r[0].도보분, walkMin(r[0].거리m));
});

test("문구", () => {
  assert.equal(fmtSec(150), "2분 30초");
  assert.equal(fmtSec(240), "4분");
  assert.equal(fmtSec(45), "45초");
  assert.equal(describeDir(commute.stations[0].노선[0].방향[0]), "내선순환 · 보통 2분 30초마다 · 10번 중 9번은 4분 안에 옴");
  assert.equal(describeDir({ 방면: "중앙보훈병원행", 배차_중간값_초: 200, 배차_90_초: 300, 급행_비율: 0.33 }),
    "중앙보훈병원행 · 보통 3분 20초마다 · 10번 중 9번은 5분 안에 옴 · 급행 33%");
  assert.match(basisText(commute.meta), /평일 18일/);
  assert.equal(basisText({ 모으는_중: true }), "출근길 실측 데이터를 모으는 중입니다.");
});

test("데이터 없을 때", () => {
  assert.deepEqual(nearestStations(null, commute), []);
  assert.deepEqual(nearestStations([37.5, 127], null), []);
});
