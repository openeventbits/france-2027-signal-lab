import { pathToFileURL } from "node:url";

export const REPORTS = ["pageviews", "daily", "pages", "referrers", "countries", "devices", "locales", "last7"];

export function buildQuery(report, days = report === "pageviews" ? 1 : 7, now = new Date()) {
  if (!REPORTS.includes(report)) throw new Error("Unknown report. Use --help.");
  if (!Number.isInteger(days) || days < 1 || days > 31 || (report === "last7" && days !== 7)) {
    throw new Error("Days must be an integer from 1 to 31; last7 requires 7.");
  }
  // Explicit UTC bounds avoid machine/server timezone differences. Today is partial.
  const end = now.toISOString().slice(0, 19).replace("T", " ");
  const start = new Date(now);
  start.setUTCHours(0, 0, 0, 0);
  start.setUTCDate(start.getUTCDate() - days + 1);
  const lower = start.toISOString().slice(0, 19).replace("T", " ");
  const where = `FROM fr27_traffic\nWHERE timestamp >= toDateTime('${lower}', 'Etc/UTC')\n  AND timestamp <= toDateTime('${end}', 'Etc/UTC')\n  AND blob1 != '/__synthetic_test__'`;
  const totals = "SUM(_sample_interval * double1) AS pageviews, MAX(_sample_interval) AS max_sample_interval";
  if (report === "pageviews") return `SELECT ${totals}\n${where}\nFORMAT JSON`;
  if (["daily", "last7"].includes(report)) {
    return `SELECT formatDateTime(timestamp, '%Y-%m-%d', 'Etc/UTC') AS day,\n  ${totals}, COUNT(DISTINCT index1) AS observed_daily_visitor_ids\n${where}\nGROUP BY day\nORDER BY day ASC\nFORMAT JSON`;
  }
  const dimension = { pages: "blob1", referrers: "blob2", countries: "blob3", devices: "blob4", locales: "blob5" }[report];
  return `SELECT ${dimension} AS dimension, ${totals}\n${where}\nGROUP BY dimension\nORDER BY pageviews DESC\nLIMIT 50\nFORMAT JSON`;
}

export async function executeQuery(sql, env = process.env, fetchImpl = fetch) {
  const account = env.FR27_REPORT_ACCOUNT_ID;
  const token = env.FR27_REPORT_API_TOKEN;
  if (!/^[a-f0-9]{32}$/i.test(account || "") || !token?.trim()) {
    throw new Error("Set FR27_REPORT_ACCOUNT_ID (32 hex characters) and FR27_REPORT_API_TOKEN in your local environment.");
  }
  let response;
  try {
    response = await fetchImpl(`https://api.cloudflare.com/client/v4/accounts/${account}/analytics_engine/sql`, {
      method: "POST", redirect: "error", signal: AbortSignal.timeout(30_000),
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "text/plain" }, body: sql
    });
  } catch {
    throw new Error("Analytics SQL request failed; no retry was attempted.");
  }
  // Do not echo server bodies/errors: those can contain request details or data.
  if (!response.ok) throw new Error(`Analytics SQL returned HTTP ${response.status}.`);
  let result;
  try { result = await response.json(); } catch { throw new Error("Analytics SQL returned invalid JSON."); }
  if (!Array.isArray(result.data)) throw new Error("Analytics SQL returned an unexpected result.");
  return result;
}

export async function main(args = process.argv.slice(2)) {
  if (!args.length || args[0] === "--help") {
    console.log("Usage: npm run report -- <pageviews|daily|pages|referrers|countries|devices|locales|last7> [--days 1..31] [--execute]\nDefault: print SQL only. pageviews defaults to today UTC; others to 7 UTC dates including today. --execute prints private aggregate JSON to this terminal.");
    return;
  }
  const [report, ...options] = args;
  let days, execute = false;
  for (let i = 0; i < options.length; i++) {
    if (options[i] === "--execute" && !execute) execute = true;
    else if (options[i] === "--days" && days === undefined && /^\d+$/.test(options[i + 1] || "")) days = Number(options[++i]);
    else throw new Error("Invalid options. Use --help.");
  }
  const sql = buildQuery(report, days);
  if (!execute) { console.log(sql); return; }
  console.error("Private aggregate output. Pageviews are sampling-weighted; observed daily IDs may undercount with sampling. Missing days have no returned rows. Recent writes may be delayed.");
  console.log(JSON.stringify(await executeQuery(sql), null, 2));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
