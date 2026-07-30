(() => {
  "use strict";

  const STATES = Object.freeze({
    loading: "loading",
    ready: "ready",
    empty: "empty",
    unavailable: "unavailable"
  });
  const SUPPORTED_SCHEMA_VERSION = "1.0";
  const metadataFields = [
    "candidate_universe",
    "featured_polling_package",
    "visibility",
    "scrutiny_window",
    "evidence_dates"
  ];
  const candidateEvidenceFields = Object.freeze({
    polling: [
      "evidence_state",
      "hypothesis_count",
      "range_min",
      "range_max",
      "selected_hypothesis_score",
      "selected_hypothesis_rank"
    ],
    campaign_attention: [
      "evidence_state",
      "record_count",
      "share",
      "publisher_count",
      "active_day_count",
      "headline_match_count",
      "summary_only_match_count",
      "scope_counts",
      "scope_shares",
      "story_cluster_count",
      "concentration"
    ],
    general_visibility: [
      "evidence_state",
      "record_count",
      "share",
      "publisher_count",
      "active_day_count",
      "headline_match_count",
      "summary_only_match_count",
      "story_cluster_count",
      "concentration"
    ],
    scrutiny: [
      "latest_14_days",
      "archive"
    ],
    latest_development: [
      "evidence_state",
      "id",
      "published_at",
      "publisher",
      "headline",
      "url",
      "coverage_scope"
    ]
  });

  function isPlainObject(value) {
    if (value === null || typeof value !== "object") return false;
    const prototype = Object.getPrototypeOf(value);
    return prototype === Object.prototype || prototype === null;
  }

  function cloneValue(value) {
    if (Array.isArray(value)) return value.map(cloneValue);
    if (!isPlainObject(value)) return value;
    return Object.fromEntries(
      Object.entries(value).map(([key, entry]) => [key, cloneValue(entry)])
    );
  }

  function copyFields(source, fields) {
    if (source === undefined || source === null) return null;
    if (!isPlainObject(source)) return undefined;
    return Object.fromEntries(
      fields.map(field => [
        field,
        source[field] === undefined ? null : cloneValue(source[field])
      ])
    );
  }

  function stateObject(status, candidates = [], metadata = {}, reason = null) {
    return { status, candidates, metadata, reason };
  }

  function unavailable(reason) {
    return stateObject(STATES.unavailable, [], {}, reason);
  }

  function normalize(payload) {
    if (!isPlainObject(payload)) return unavailable("invalid_payload");
    if (payload.schema_version !== SUPPORTED_SCHEMA_VERSION) {
      return unavailable("unsupported_schema");
    }
    if (!Array.isArray(payload.candidates)) {
      return unavailable("invalid_payload");
    }

    const candidateIds = new Set();
    const candidates = [];

    for (const sourceCandidate of payload.candidates) {
      if (!isPlainObject(sourceCandidate)) {
        return unavailable("invalid_payload");
      }

      const candidateId = sourceCandidate.candidate_id;
      const candidateName = sourceCandidate.candidate_name;
      if (
        typeof candidateId !== "string" ||
        !candidateId.trim() ||
        typeof candidateName !== "string" ||
        !candidateName.trim() ||
        candidateIds.has(candidateId)
      ) {
        return unavailable("invalid_payload");
      }

      const candidate = {
        candidate_id: candidateId,
        candidate_name: candidateName
      };

      for (const [field, fields] of Object.entries(candidateEvidenceFields)) {
        const evidence = copyFields(sourceCandidate[field], fields);
        if (evidence === undefined) return unavailable("invalid_payload");
        candidate[field] = evidence;
      }

      candidateIds.add(candidateId);
      candidates.push(candidate);
    }

    const metadata = { schema_version: payload.schema_version };
    for (const field of metadataFields) {
      metadata[field] =
        payload[field] === undefined ? null : cloneValue(payload[field]);
    }

    return stateObject(
      candidates.length ? STATES.ready : STATES.empty,
      candidates,
      metadata
    );
  }

  async function load(url) {
    let response;
    try {
      response = await window.fetch(url, { cache: "no-store" });
    } catch (_error) {
      return unavailable("fetch_failed");
    }

    if (!response.ok) return unavailable("http_error");

    let payload;
    try {
      payload = await response.json();
    } catch (_error) {
      return unavailable("invalid_payload");
    }

    return normalize(payload);
  }

  window.France2027CandidateSignals = Object.freeze({
    load,
    normalize,
    STATES
  });
})();
