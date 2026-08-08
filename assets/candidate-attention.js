(() => {
  "use strict";

  function unavailable(reason) {
    return {
      status: "unavailable",
      payload: null,
      reason
    };
  }

  function normalize(payload) {
    const period = payload?.period;
    const candidates = payload?.candidates;

    const valid =
      payload?.schema_version === "1.0" &&
      period &&
      typeof period === "object" &&
      /^\d{4}-\d{2}-\d{2}$/.test(
        String(period.data_as_of || "")
      ) &&
      Array.isArray(candidates) &&
      candidates.length > 0 &&
      candidates.every(candidate =>
        candidate &&
        typeof candidate.candidate_id === "string" &&
        Boolean(candidate.candidate_id) &&
        typeof candidate.candidate_name === "string" &&
        Boolean(candidate.candidate_name) &&
        Array.isArray(candidate.daily_series) &&
        candidate.daily_series.length >= 30
      );

    return valid
      ? {
        status: "ready",
        payload,
        reason: null
      }
      : unavailable("invalid_payload");
  }

  async function load(
    url,
    fetchImplementation =
      typeof window.fetch === "function"
        ? window.fetch.bind(window)
        : null
  ) {
    if (!fetchImplementation) {
      return unavailable("fetch_unavailable");
    }

    try {
      const response = await fetchImplementation(
        url,
        { cache: "no-store" }
      );

      if (!response.ok) {
        return unavailable("http_error");
      }

      const payload = await response.json();
      return normalize(payload);
    } catch (_error) {
      return unavailable("fetch_failed");
    }
  }

  window.France2027CandidateAttention =
    Object.freeze({
      load,
      normalize
    });
})();
