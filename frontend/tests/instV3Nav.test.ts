import assert from "node:assert/strict";
import test from "node:test";
import { V3_NAV_GROUPS, visibleV3Nav, v3TitleForPath } from "../src/data/instV3Nav.ts";

const perms = {
  overview: "read",
  research: "write",
  debate: "write",
  approvals: "write",
  execution: "read",
  portfolio: "write",
  monitor: "write",
};

test("v3 nav has three groups and eight items", () => {
  assert.equal(V3_NAV_GROUPS.length, 3);
  assert.equal(V3_NAV_GROUPS.flatMap((g) => g.items).length, 8);
});

test("manager sees all flow workbenches", () => {
  const groups = visibleV3Nav("manager", perms);
  const labels = groups.flatMap((g) => g.items.map((x) => x.label));
  assert.deepEqual(labels, [
    "投资工作台", "项目流水线", "价值分析", "多空辩论", "投委会审批", "执行成交", "投资管理", "流程与权限",
  ]);
});

test("approver cannot see research/debate/execute/manage workspaces", () => {
  for (const role of ["partner", "risk", "chairman"]) {
    const labels = visibleV3Nav(role, perms).flatMap((g) => g.items.map((x) => x.label));
    assert.deepEqual(labels, ["投资工作台", "项目流水线", "投委会审批", "流程与权限"]);
  }
});

test("unknown role fails closed", () => {
  const labels = visibleV3Nav("guest", { overview: "read" }).flatMap((g) => g.items.map((x) => x.label));
  assert.deepEqual(labels, ["投资工作台", "项目流水线", "流程与权限"]);
});

test("v3 breadcrumb titles", () => {
  assert.equal(v3TitleForPath("/inst"), "投资工作台");
  assert.equal(v3TitleForPath("/inst/pipeline/result"), "项目流水线");
  assert.equal(v3TitleForPath("/inst/playbook"), "流程与权限");
  assert.equal(v3TitleForPath("/inst/approvals"), "投委会审批");
});
