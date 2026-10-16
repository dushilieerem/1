import assert from "node:assert/strict";
import test from "node:test";
import { icMetrics, sampleStandardDeviation } from "../src/lib/factorIcMetrics";

const series = [-0.2, 0.1, 0.4].map((value, i) => ({ date: `2025-01-0${i + 2}`, value }));
const near = (actual: number | null, expected: number) => {
  assert.notEqual(actual, null);
  assert.ok(Math.abs(actual! - expected) < 1e-12, `${actual} != ${expected}`);
};

test("旧报告缺少ic_std：按N−1补算，[-0.2,0.1,0.4]的标准差为0.3", () => {
  for (const fa of [undefined, { ic_std: null }, { ic_std: NaN }]) {
    const metrics = icMetrics(series, fa);
    near(metrics.mean, 0.1);
    near(metrics.std, 0.3);
    near(metrics.ir, 1 / 3);
    near(metrics.posPct, 200 / 3);
  }
});

test("优先使用后端有效标准差，包括合法的0", () => {
  near(icMetrics(series, { ic_std: 0.5 }).std, 0.5);
  near(icMetrics(series, { ic_std: 0 }).std, 0);
  near(icMetrics(series, { ic_std: 0 }).ir, 0);
});

test("样本标准差忽略非有限值，且不以可能被舍入的展示均值为中心", () => {
  near(sampleStandardDeviation([-0.2, 0.1, 0.4, NaN, Infinity]), 0.3);
  near(icMetrics(series, { ic_mean: 0.09 }).std, 0.3);
});

test("无数据或仅一个有效样本时，标准差和IR不可计算", () => {
  for (const input of [[], series.slice(0, 1)]) {
    const metrics = icMetrics(input, { ic_std: null });
    assert.equal(metrics.std, null);
    assert.equal(metrics.ir, null);
  }
  near(sampleStandardDeviation([0.2, 0.2]), 0);
});
