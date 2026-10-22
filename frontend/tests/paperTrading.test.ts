import "./domSetup.mjs";
import assert from "node:assert/strict";
import test from "node:test";
import {
  createPaperAccount,
  listPaperAccounts,
  settlePaperAccount,
} from "../src/lib/paperTradingApi";

const originalFetch = globalThis.fetch;

function mockFetch(status: number, body: unknown) {
  globalThis.fetch = (async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    })) as typeof fetch;
}

test("listPaperAccounts returns accounts array", async () => {
  mockFetch(200, { ok: true, accounts: [{ id: 1, name: "测试账户" }] });
  const accounts = await listPaperAccounts();
  assert.equal(accounts.length, 1);
  assert.equal(accounts[0].name, "测试账户");
  globalThis.fetch = originalFetch;
});

test("createPaperAccount posts snapshot input", async () => {
  let captured: RequestInit | undefined;
  globalThis.fetch = (async (_url: string, init?: RequestInit) => {
    captured = init;
    return new Response(JSON.stringify({ account: { id: 2 } }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }) as typeof fetch;
  const account = await createPaperAccount({
    name: "账户 A",
    strategy_project_id: "p1",
    initial_cash: 500000,
    first_settlement_date: "2026-10-21",
  });
  assert.equal(account.id, 2);
  const body = JSON.parse(String(captured?.body));
  assert.equal(body.strategy_project_id, "p1");
  assert.equal(body.initial_cash, 500000);
  globalThis.fetch = originalFetch;
});

test("settlePaperAccount surfaces machine error code", async () => {
  mockFetch(409, { error: "行情数据尚未就绪", code: "DATA_NOT_READY" });
  await assert.rejects(
    () => settlePaperAccount(1),
    (error: Error) =>
      error.message.includes("DATA_NOT_READY") &&
      error.message.includes("行情数据尚未就绪"),
  );
  globalThis.fetch = originalFetch;
});
