import assert from "node:assert/strict";
import { test } from "node:test";
import { buildQuery, executeQuery, REPORTS } from "../scripts/report.mjs";

const now = new Date("2026-10-17T15:00:00Z");
test("all reports have UTC bounds, synthetic exclusion and weighted pageviews", () => {
  for (const report of REPORTS) {
    const sql = buildQuery(report, undefined, now);
    assert.match(sql, /FROM fr27_traffic/);
    assert.match(sql, /AND blob1 != '\/__synthetic_test__'/);
    assert.match(sql, /SUM\(_sample_interval \* double1\)/);
    assert.match(sql, /MAX\(_sample_interval\)/);
    assert.match(sql, /timestamp <= toDateTime\('2026-10-17 15:00:00', 'Etc\/UTC'\)/);
    assert.match(sql, /FORMAT JSON$/);
    assert.doesNotMatch(sql, /SELECT \*/);
  }
  assert.match(buildQuery("pageviews", undefined, now), /2026-10-17 00:00:00/);
  assert.match(buildQuery("last7", undefined, now), /2026-10-11 00:00:00/);
  assert.match(buildQuery("daily", undefined, now), /COUNT\(DISTINCT index1\) AS observed_daily_visitor_ids/);
  assert.match(buildQuery("daily", undefined, now), /GROUP BY day/);
  for (const [report, column] of Object.entries({ pages: 1, referrers: 2, countries: 3, devices: 4, locales: 5 })) {
    assert.match(buildQuery(report), new RegExp(`blob${column} AS dimension`));
  }
});

test("query arguments cannot inject SQL or unbounded date ranges", () => {
  assert.throws(() => buildQuery("fr27_traffic; DROP TABLE"));
  for (const days of [0, -1, 32, 1.5, NaN, "7", "7; DROP TABLE"]) assert.throws(() => buildQuery("daily", days));
  assert.throws(() => buildQuery("last7", 8));
  assert.match(buildQuery("daily", 7, new Date("2026-01-02T01:00:00Z")), /2025-12-27 00:00:00/);
});

test("execution requires explicit credentials and posts to fixed read-only SQL API", async () => {
  let calls = 0;
  await assert.rejects(executeQuery("SELECT 1", {}, () => { calls++; }));
  assert.equal(calls, 0);
  const env = { FR27_REPORT_ACCOUNT_ID: "a".repeat(32), FR27_REPORT_API_TOKEN: "test-report-token" };
  const sql = buildQuery("pageviews", undefined, now);
  const result = await executeQuery(sql, env, async (url, options) => {
    assert.equal(url, `https://api.cloudflare.com/client/v4/accounts/${"a".repeat(32)}/analytics_engine/sql`);
    assert.equal(options.method, "POST");
    assert.equal(options.redirect, "error");
    assert.equal(options.body, sql);
    assert.equal(options.headers.Authorization, "Bearer test-report-token");
    return Response.json({ data: [{ pageviews: 42 }] });
  });
  assert.deepEqual(result.data, [{ pageviews: 42 }]);
  await assert.rejects(executeQuery(sql, env, async () => new Response("secret server detail", { status: 403 })), { message: "Analytics SQL returned HTTP 403." });
  await assert.rejects(executeQuery(sql, env, async () => { throw new Error("secret request detail"); }), { message: "Analytics SQL request failed; no retry was attempted." });
  await assert.rejects(executeQuery(sql, env, async () => Response.json({ success: false })), { message: "Analytics SQL returned an unexpected result." });
});
