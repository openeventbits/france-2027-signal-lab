import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { test } from "node:test";
import worker, {
  shouldTrack, referrerDomain, normalizePath, localeClass, deviceClass,
  dailyVisitorId
} from "../src/index.js";

const request = (headers = {}, options = {}) => new Request(
  "https://france2027.app/en/agenda/?private=query", { headers, ...options }
);
const html = (status = 200, type = "text/html; charset=utf-8") =>
  new Response("origin body", { status, headers: { "content-type": type } });

for (const [name, headers, options, status, type, expected] of [
  ["GET HTML", {}, {}, 200, "text/html", true],
  ["POST", {}, { method: "POST" }, 200, "text/html", false],
  ["HEAD", {}, { method: "HEAD" }, 200, "text/html", false],
  ["404", {}, {}, 404, "text/html", false],
  ["500", {}, {}, 500, "text/html", false],
  ["JSON", {}, {}, 200, "application/json", false],
  ["missing HTML type", {}, {}, 200, "", false],
  ["HTML lookalike", {}, {}, 200, "text/html-extra", false],
  ["case-insensitive MIME", {}, {}, 200, "Text/HTML; charset=UTF-8", true],
  ["Googlebot", { "user-agent": "Mozilla/5.0 (compatible; Googlebot/2.1)" }, {}, 200, "text/html", false],
  ["GPTBot", { "user-agent": "GPTBot/1.0" }, {}, 200, "text/html", false],
  ["headless", { "user-agent": "HeadlessChrome/130" }, {}, 200, "text/html", false],
  ["prefetch", { purpose: "prefetch" }, {}, 200, "text/html", false],
  ["sec-purpose prerender", { "sec-purpose": "prefetch;prerender" }, {}, 200, "text/html", false],
  ["prerender", { purpose: "prerender" }, {}, 200, "text/html", false],
  ["script destination", { "sec-fetch-dest": "script" }, {}, 200, "text/html", false],
  ["image destination", { "sec-fetch-dest": "image" }, {}, 200, "text/html", false],
  ["empty token destination", { "sec-fetch-dest": "empty" }, {}, 200, "text/html", false],
  ["document destination", { "sec-fetch-dest": "document" }, {}, 200, "text/html", true],
  ["iframe destination (existing policy)", { "sec-fetch-dest": "iframe" }, {}, 200, "text/html", true],
  ["unknown destination", { "sec-fetch-dest": "object" }, {}, 200, "text/html", false]
]) {
  test(`eligibility: ${name}`, () => {
    assert.equal(shouldTrack(request(headers, options), html(status, type)), expected);
  });
}

test("referrers contain only normalized hostnames or category markers", () => {
  for (const [input, expected] of [
    [null, "(direct)"], ["", "(direct)"],
    ["https://WWW.Example.COM:8443/private?token=secret#fragment", "example.com"],
    ["https://user:password@example.com/path", "example.com"],
    ["https://www.france2027.app/other?x=1", "(internal)"],
    ["https://france2027.app./", "(internal)"],
    ["https://france2027.app.evil.example/", "france2027.app.evil.example"],
    ["invalid", "(unknown)"], ["/relative", "(unknown)"],
    ["javascript:alert(1)", "(unknown)"],
    ["file:///private/file", "(unknown)"], ["ftp://example.com/", "(unknown)"]
  ]) assert.equal(referrerDomain(input, "FRANCE2027.APP"), expected);
});

test("paths use URL pathname, preserve route spelling and are bounded", () => {
  assert.equal(normalizePath(""), "/");
  assert.equal(normalizePath(new URL("https://france2027.app/en/?token=private#hash").pathname), "/en/");
  assert.equal(normalizePath("/En/%C3%A9/index.html"), "/En/%C3%A9/index.html");
  assert.equal(normalizePath("/" + "a".repeat(400)).length, 300);
});

test("locale is classified by the English path segment", () => {
  for (const path of ["/en", "/en/", "/en/candidates/"]) assert.equal(localeClass(path), "en");
  for (const path of ["/", "/agenda/", "/english/", "/enjeux/", "/EN/"]) assert.equal(localeClass(path), "fr");
});

test("device classes remain coarse", () => {
  for (const [ua, expected] of [
    ["Mozilla Windows Chrome", "desktop"], ["", "desktop"],
    ["iPhone Mobile Safari", "mobile"], ["Android Mobile", "mobile"],
    ["iPad Safari", "tablet"], ["Tablet", "tablet"], ["Android Chrome", "tablet"]
  ]) assert.equal(deviceClass(ua), expected);
});

test("daily HMAC has a fixed vector, rotates in UTC and bounds the UA", async () => {
  const req = request({ "cf-connecting-ip": "192.0.2.10", "user-agent": "Test Browser" });
  const day = new Date("2026-10-17T23:59:59Z");
  const id = await dailyVisitorId(req, "test-only-salt", day);
  assert.equal(id, "8459d29c820fb1e555d44dbfebc45ef7");
  assert.match(id, /^[a-f0-9]{32}$/);
  assert.equal(await dailyVisitorId(req, "test-only-salt", new Date("2026-10-18T01:00:00+02:00")), id);
  assert.notEqual(await dailyVisitorId(req, "test-only-salt", new Date("2026-10-18T00:00:00Z")), id);
  assert.notEqual(await dailyVisitorId(req, "different-test-salt", day), id);
  for (const headers of [
    { "cf-connecting-ip": "192.0.2.11", "user-agent": "Test Browser" },
    { "cf-connecting-ip": "192.0.2.10", "user-agent": "Other Browser" }
  ]) assert.notEqual(await dailyVisitorId(request(headers), "test-only-salt", day), id);
  const longUA = "x".repeat(300);
  assert.equal(
    await dailyVisitorId(request({ "user-agent": longUA + "ignored" }), "test-only-salt", day),
    createHmac("sha256", "test-only-salt").update(`2026-10-17\nunknown\n${longUA}`).digest("hex").slice(0, 32)
  );
});

test("workers.dev validation never fetches the origin or schedules analytics", async (t) => {
  t.mock.method(globalThis, "fetch", () => { throw new Error("unexpected origin fetch"); });
  const env = { get TRAFFIC() { throw new Error("unexpected analytics"); } };
  const ctx = { waitUntil() { throw new Error("unexpected scheduling"); } };
  const response = await worker.fetch(new Request("https://fr27-traffic.driftsignals.workers.dev/__health"), env, ctx);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    ok: true, service: "fr27-traffic", mode: "validation", analytics: "disabled-on-workers-dev"
  });
  for (const path of ["/", "/en/", "/__synthetic_test__", "/__health/", "/report"]) {
    assert.equal((await worker.fetch(new Request(`https://fr27-traffic.driftsignals.workers.dev${path}`), env, ctx)).status, 404);
  }
});

test("origin request and streamed response are preserved; schema contains no raw inputs", async (t) => {
  const req = request({ "cf-connecting-ip": "192.0.2.10", "user-agent": "Test Browser", referer: "https://www.example.com/private?secret=1" });
  Object.defineProperty(req, "cf", { value: { country: "FR" } });
  const response = html();
  response.headers.set("x-origin", "preserved");
  t.mock.method(globalThis, "fetch", async (forwarded) => {
    assert.equal(forwarded, req);
    return response;
  });
  const writes = [], pending = [];
  const result = await worker.fetch(req, {
    FR27_ANALYTICS_SALT: "test-only-salt", TRAFFIC: { writeDataPoint: point => writes.push(point) }
  }, { waitUntil: promise => pending.push(promise) });
  assert.equal(result, response);
  assert.equal(result.bodyUsed, false);
  assert.equal(result.headers.get("x-origin"), "preserved");
  assert.equal(pending.length, 1);
  await Promise.all(pending);
  assert.equal(writes.length, 1);
  assert.deepEqual(writes[0].blobs, ["/en/agenda/", "example.com", "FR", "desktop", "en", "200"]);
  assert.deepEqual(writes[0].doubles, [1]);
  assert.match(writes[0].indexes[0], /^[a-f0-9]{32}$/);
  assert.doesNotMatch(JSON.stringify(writes), /192\.0\.2\.10|Test Browser|private|secret|query/);
  assert.equal(await result.text(), "origin body");
});

test("analytics failures and missing bindings/secret preserve the origin response", async (t) => {
  const response = html();
  t.mock.method(globalThis, "fetch", async () => response);
  const pending = [];
  const ctx = { waitUntil: p => pending.push(p) };
  for (const env of [
    {}, { FR27_ANALYTICS_SALT: "test-only-salt" },
    { FR27_ANALYTICS_SALT: "test-only-salt", TRAFFIC: { writeDataPoint() { throw new Error("write failed"); } } },
    { get FR27_ANALYTICS_SALT() { throw new Error("binding failed"); } }
  ]) assert.equal(await worker.fetch(request(), env, ctx), response);
  assert.equal(await worker.fetch(request(), { FR27_ANALYTICS_SALT: "test-only-salt" }, {
    waitUntil(p) { pending.push(p); throw new Error("schedule failed"); }
  }), response);
  await Promise.all(pending);
});

test("ineligible origin responses schedule no writes", async (t) => {
  const response = html(404);
  t.mock.method(globalThis, "fetch", async () => response);
  assert.equal(await worker.fetch(request(), { FR27_ANALYTICS_SALT: "test-only-salt" }, {
    waitUntil() { assert.fail("404 scheduled analytics"); }
  }), response);
});
