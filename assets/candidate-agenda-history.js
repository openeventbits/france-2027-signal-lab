(() => {
  "use strict";

  const SCHEMA_VERSION = "1.0";
  const PROFILE_MODES = new Set(["policy", "campaign"]);

  function unavailable(reason) {
    return {
      status: "unavailable",
      payload: null,
      reason
    };
  }

  function canonicalDate(value) {
    if (
      typeof value !== "string" ||
      !/^\d{4}-\d{2}-\d{2}$/.test(value)
    ) {
      return false;
    }

    const parsed = new Date(`${value}T00:00:00Z`);
    return (
      Number.isFinite(parsed.getTime()) &&
      parsed.toISOString().slice(0, 10) === value
    );
  }

  function nonNegativeInteger(value) {
    return Number.isInteger(value) && value >= 0;
  }

  function validTopic(topic, topicIds) {
    if (
      !topic ||
      typeof topic !== "object" ||
      Array.isArray(topic) ||
      typeof topic.id !== "string" ||
      !topic.id ||
      topicIds.has(topic.id) ||
      typeof topic.label !== "string" ||
      !topic.label ||
      !nonNegativeInteger(topic.count) ||
      typeof topic.share !== "number" ||
      !Number.isFinite(topic.share) ||
      topic.share < 0 ||
      topic.share > 1
    ) {
      return false;
    }

    topicIds.add(topic.id);
    return true;
  }

  function validProfile(profile, trackingStart, dataAsOf) {
    if (
      !profile ||
      typeof profile !== "object" ||
      Array.isArray(profile) ||
      !PROFILE_MODES.has(profile.profile_mode) ||
      !canonicalDate(profile.period_start) ||
      !canonicalDate(profile.period_end) ||
      profile.period_start !== trackingStart ||
      profile.period_end !== dataAsOf ||
      !nonNegativeInteger(profile.association_count) ||
      !Array.isArray(profile.topics)
    ) {
      return false;
    }

    const topicIds = new Set();
    return profile.topics.every(topic => validTopic(topic, topicIds));
  }

  function normalize(payload) {
    const tracking = payload?.tracking;
    const candidates = payload?.candidates;

    if (
      payload?.schema_version !== SCHEMA_VERSION ||
      !tracking ||
      typeof tracking !== "object" ||
      Array.isArray(tracking) ||
      !canonicalDate(tracking.start_date) ||
      !canonicalDate(tracking.data_as_of) ||
      tracking.day_boundary !== "UTC" ||
      tracking.current_utc_day_excluded !== false ||
      !Array.isArray(candidates)
    ) {
      return unavailable("invalid_payload");
    }

    const candidateIds = new Set();
    for (const candidate of candidates) {
      if (
        !candidate ||
        typeof candidate !== "object" ||
        Array.isArray(candidate) ||
        typeof candidate.candidate_id !== "string" ||
        !candidate.candidate_id ||
        candidateIds.has(candidate.candidate_id) ||
        !canonicalDate(candidate.tracking_start) ||
        !validProfile(
          candidate.cumulative_profile,
          candidate.tracking_start,
          tracking.data_as_of
        )
      ) {
        return unavailable("invalid_payload");
      }

      candidateIds.add(candidate.candidate_id);
    }

    return {
      status: "ready",
      payload,
      reason: null
    };
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
      if (!response.ok) return unavailable("http_error");
      return normalize(await response.json());
    } catch (_error) {
      return unavailable("fetch_failed");
    }
  }

  window.France2027CandidateAgendaHistory = Object.freeze({
    load,
    normalize
  });
})();
