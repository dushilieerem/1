import assert from "node:assert/strict";
import test from "node:test";
import {
  accessBadge,
  sortWorkspaces,
  visibleWorkspaces,
  workspaceForPath,
} from "../src/data/instNav";
import type { InstAccess, InstWorkspace } from "../src/lib/instAuth";

function ws(
  key: string,
  access: InstAccess,
  visible = access !== "none",
): InstWorkspace {
  return {
    key,
    label_cn: key,
    label_en: key,
    path: `/inst/${key}`,
    access,
    visible,
  };
}

test("visibleWorkspaces 隐藏 none 与 visible=false，并按固定顺序排序", () => {
  const list = [
    ws("monitor", "write"),
    ws("ideas", "none"),
    ws("overview", "read"),
    ws("approvals", "write"),
    ws("about", "read", false),
  ];
  const out = visibleWorkspaces(list).map((x) => x.key);
  assert.deepEqual(out, ["overview", "approvals"]);
});

test("投后管理合并进投资管理后 monitor 不再作为独立菜单", () => {
  const out = visibleWorkspaces([ws("monitor", "write"), ws("portfolio", "write")]).map(
    (x) => x.key,
  );
  assert.deepEqual(out, ["portfolio"]);
});

test("visibleWorkspaces 对空值返回空数组并去重", () => {
  assert.deepEqual(visibleWorkspaces(null), []);
  assert.deepEqual(visibleWorkspaces(undefined), []);
  const dup = [ws("research", "read"), ws("research", "write")];
  assert.deepEqual(
    visibleWorkspaces(dup).map((x) => x.key),
    ["research"],
  );
});

test("sortWorkspaces 未知工作区排在最后且保持相对顺序", () => {
  const out = sortWorkspaces([ws("zeta", "read"), ws("ideas", "read"), ws("alpha", "read")]);
  assert.deepEqual(
    out.map((x) => x.key),
    ["ideas", "zeta", "alpha"],
  );
});

test("accessBadge 只给只读与摘要加标识", () => {
  assert.equal(accessBadge("read"), "只读");
  assert.equal(accessBadge("digest"), "仅摘要");
  assert.equal(accessBadge("write"), null);
  assert.equal(accessBadge("none"), null);
});

test("workspaceForPath 匹配最长前缀", () => {
  const list = [ws("research", "read"), ws("research/archive", "read")];
  assert.equal(workspaceForPath(list, "/inst/research")?.key, "research");
  assert.equal(workspaceForPath(list, "/inst/research/archive/42")?.key, "research/archive");
  assert.equal(workspaceForPath(list, "/inst/unknown"), null);
});
