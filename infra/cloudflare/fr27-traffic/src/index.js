const BOT_RE =
  /bot\b|crawler|spider|slurp|facebookexternalhit|whatsapp|headlesschrome|lighthouse/i;

const encoder = new TextEncoder();

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    /*
     * workers.dev exists only for safe validation.
     * It never proxies traffic and never records analytics.
     */
    if (url.hostname.endsWith(".workers.dev")) {
      if (url.pathname === "/__health") {
        return Response.json({
          ok: true,
          service: "fr27-traffic",
          mode: "validation",
          analytics: "disabled-on-workers-dev"
        });
      }

      return new Response("Not found", {
        status: 404
      });
    }

    /*
     * When a production route is eventually enabled,
     * this forwards the request unchanged to FR27's
     * existing GitHub Pages origin.
     */
    const response = await fetch(request);

    /*
     * Skip analytics unless eligible. Analytics errors must not affect FR27.
     *
     * - only qualifying HTML page requests
     * - only if the analytics secret exists
     * - never allow analytics failure to affect FR27
     */
    try {
      if (shouldTrack(request, response) && env.FR27_ANALYTICS_SALT) {
        ctx.waitUntil(recordPageview(request, response, env).catch(() => {}));
      }
    } catch {
      // Also isolate synchronous filtering/scheduling failures. Never log inputs.
    }

    return response;
  }
};

export function shouldTrack(request, response) {
  if (request.method !== "GET") {
    return false;
  }

  if (response.status >= 400) {
    return false;
  }

  const contentType =
    response.headers.get("content-type") || "";

  if (contentType.split(";", 1)[0].trim().toLowerCase() !== "text/html") {
    return false;
  }

  const userAgent =
    request.headers.get("user-agent") || "";

  if (BOT_RE.test(userAgent)) {
    return false;
  }

  const purpose = [
    request.headers.get("purpose"),
    request.headers.get("sec-purpose")
  ]
    .filter(Boolean)
    .join(" ");

  if (/prefetch|prerender/i.test(purpose)) {
    return false;
  }

  const destination =
    request.headers.get("sec-fetch-dest");

  if (
    destination &&
    destination !== "document" &&
    destination !== "iframe"
  ) {
    return false;
  }

  return true;
}

async function recordPageview(
  request,
  response,
  env
) {
  const url = new URL(request.url);

  const visitorId =
    await dailyVisitorId(
      request,
      env.FR27_ANALYTICS_SALT
    );

  const referrer =
    referrerDomain(
      request.headers.get("referer"),
      url.hostname
    );

  const country =
    request.cf?.country || "XX";

  const device =
    deviceClass(
      request.headers.get("user-agent") || ""
    );

  const locale = localeClass(url.pathname);

  /*
   * Analytics Engine schema:
   *
   * blob1  path
   * blob2  referrer domain
   * blob3  country
   * blob4  device class
   * blob5  locale
   * blob6  HTTP status
   *
   * double1 pageview count (= 1)
   *
   * index1 daily pseudonymous visitor ID
   */
  env.TRAFFIC.writeDataPoint({
    blobs: [
      normalizePath(url.pathname),
      referrer,
      country,
      device,
      locale,
      String(response.status)
    ],

    doubles: [1],

    indexes: [visitorId]
  });
}

export async function dailyVisitorId(
  request,
  secret,
  now = new Date()
) {
  const ip =
    request.headers.get("cf-connecting-ip") ||
    "unknown";

  const userAgent =
    (
      request.headers.get("user-agent") || ""
    ).slice(0, 300);

  /*
   * UTC date deliberately rotates identity daily.
   */
  const day =
    now.toISOString().slice(0, 10);

  const key =
    await crypto.subtle.importKey(
      "raw",
      encoder.encode(secret),
      {
        name: "HMAC",
        hash: "SHA-256"
      },
      false,
      ["sign"]
    );

  const signature =
    await crypto.subtle.sign(
      "HMAC",
      key,
      encoder.encode(
        `${day}\n${ip}\n${userAgent}`
      )
    );

  /*
   * Keep only 128 bits.
   *
   * The resulting 32-character identifier
   * contains no raw IP or User-Agent.
   */
  return Array.from(
    new Uint8Array(signature).slice(0, 16)
  )
    .map(byte =>
      byte.toString(16).padStart(2, "0")
    )
    .join("");
}

export function normalizePath(pathname) {
  if (!pathname) {
    return "/";
  }

  /*
   * Query strings are deliberately excluded.
   */
  return pathname.slice(0, 300);
}

export function referrerDomain(
  referrer,
  currentHostname
) {
  if (!referrer) {
    return "(direct)";
  }

  try {
    const url = new URL(referrer);
    if (!["http:", "https:"].includes(url.protocol) || !url.hostname) {
      return "(unknown)";
    }
    const hostname =
      url.hostname
        .toLowerCase()
        .replace(/\.$/, "")
        .replace(/^www\./, "");

    const current =
      currentHostname
        .toLowerCase()
        .replace(/\.$/, "")
        .replace(/^www\./, "");

    if (hostname === current) {
      return "(internal)";
    }

    /*
     * Store domain only, never full referring URL.
     */
    return hostname.slice(0, 200);
  } catch {
    return "(unknown)";
  }
}

export function localeClass(pathname) {
  return pathname === "/en" || pathname.startsWith("/en/") ? "en" : "fr";
}

export function deviceClass(userAgent) {
  if (
    /iPad|Tablet|Android(?!.*Mobile)/i
      .test(userAgent)
  ) {
    return "tablet";
  }

  if (
    /Mobi|iPhone|Android/i
      .test(userAgent)
  ) {
    return "mobile";
  }

  return "desktop";
}



