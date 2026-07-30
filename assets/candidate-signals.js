(() => {
  "use strict";

  const STATES = Object.freeze({
    loading: "loading",
    ready: "ready",
    empty: "empty",
    unavailable: "unavailable"
  });
  const SUPPORTED_SCHEMA_VERSIONS = new Set(["1.0", "1.1"]);
  const metadataFields = [
    "candidate_universe",
    "featured_polling_package",
    "featured_poll_board",
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
  const candidacyFields = [
    "status",
    "display_tier",
    "active_field_eligible",
    "status_as_of",
    "source_date",
    "source_url",
    "source_title",
    "source_publisher",
    "status_note"
  ];
  const fieldTiers = ["main", "secondary", "hidden"];
  const fieldCountKeys = ["main", "secondary", "hidden", "active", "total"];

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

  function hasExactKeys(source, keys) {
    if (!isPlainObject(source)) return false;
    const actual = Object.keys(source);
    if (actual.length !== keys.length) return false;
    return keys.every(key => Object.prototype.hasOwnProperty.call(source, key));
  }

  function nonemptyText(value) {
    return typeof value === "string" && !!value.trim() && value === value.trim();
  }

  function nonnegativeInteger(value) {
    return Number.isInteger(value) && value >= 0;
  }

  function stateObject(status, candidates = [], metadata = {}, reason = null) {
    return { status, candidates, metadata, reason };
  }

  function unavailable(reason) {
    return stateObject(STATES.unavailable, [], {}, reason);
  }

  function normalizeCandidacy(source) {
    if (!hasExactKeys(source, candidacyFields)) return undefined;
    for (const field of candidacyFields) {
      if (field === "active_field_eligible") continue;
      if (!nonemptyText(source[field])) return undefined;
    }
    if (!fieldTiers.includes(source.display_tier)) return undefined;
    if (typeof source.active_field_eligible !== "boolean") return undefined;
    if (source.active_field_eligible !== (source.display_tier !== "hidden")) {
      return undefined;
    }
    return cloneValue(source);
  }

  function normalizePresidentialField(source, candidates) {
    const expectedKeys = ["status_as_of", ...fieldTiers, "counts"];
    if (!hasExactKeys(source, expectedKeys) || !nonemptyText(source.status_as_of)) {
      return undefined;
    }
    if (!hasExactKeys(source.counts, fieldCountKeys)) return undefined;
    if (!fieldCountKeys.every(key => nonnegativeInteger(source.counts[key]))) {
      return undefined;
    }

    const candidateById = new Map(candidates.map(candidate => [candidate.candidate_id, candidate]));
    const membership = new Map();
    const normalized = {
      status_as_of: source.status_as_of,
      main: [],
      secondary: [],
      hidden: [],
      counts: cloneValue(source.counts)
    };

    for (const tier of fieldTiers) {
      if (!Array.isArray(source[tier])) return undefined;
      for (const identifier of source[tier]) {
        if (!nonemptyText(identifier) || !candidateById.has(identifier)) return undefined;
        if (membership.has(identifier)) return undefined;
        const candidate = candidateById.get(identifier);
        if (
          !candidate.candidacy ||
          candidate.candidacy.display_tier !== tier ||
          candidate.candidacy.active_field_eligible !== (tier !== "hidden")
        ) {
          return undefined;
        }
        membership.set(identifier, tier);
        normalized[tier].push(identifier);
      }
    }

    if (membership.size !== candidates.length) return undefined;
    const expectedCounts = {
      main: normalized.main.length,
      secondary: normalized.secondary.length,
      hidden: normalized.hidden.length,
      active: normalized.main.length + normalized.secondary.length,
      total: candidates.length
    };
    if (fieldCountKeys.some(key => source.counts[key] !== expectedCounts[key])) {
      return undefined;
    }
    return normalized;
  }

  function normalize(payload) {
    if (!isPlainObject(payload)) return unavailable("invalid_payload");
    if (!SUPPORTED_SCHEMA_VERSIONS.has(payload.schema_version)) {
      return unavailable("unsupported_schema");
    }
    if (!Array.isArray(payload.candidates)) {
      return unavailable("invalid_payload");
    }

    const isVersion11 = payload.schema_version === "1.1";
    const candidateIds = new Set();
    const candidates = [];

    for (const sourceCandidate of payload.candidates) {
      if (!isPlainObject(sourceCandidate)) return unavailable("invalid_payload");
      const candidateId = sourceCandidate.candidate_id;
      const candidateName = sourceCandidate.candidate_name;
      if (
        !nonemptyText(candidateId) ||
        !nonemptyText(candidateName) ||
        candidateIds.has(candidateId)
      ) {
        return unavailable("invalid_payload");
      }

      const candidate = {
        candidate_id: candidateId,
        candidate_name: candidateName,
        candidacy: null
      };
      if (isVersion11) {
        candidate.candidacy = normalizeCandidacy(sourceCandidate.candidacy);
        if (candidate.candidacy === undefined) return unavailable("invalid_payload");
      }

      for (const [field, fields] of Object.entries(candidateEvidenceFields)) {
        const evidence = copyFields(sourceCandidate[field], fields);
        if (evidence === undefined) return unavailable("invalid_payload");
        candidate[field] = evidence;
      }
      candidateIds.add(candidateId);
      candidates.push(candidate);
    }

    const metadata = {
      schema_version: payload.schema_version,
      presidentialField: null
    };
    for (const field of metadataFields) {
      metadata[field] = payload[field] === undefined ? null : cloneValue(payload[field]);
    }
    if (isVersion11) {
      metadata.presidentialField = normalizePresidentialField(
        payload.presidential_field,
        candidates
      );
      if (metadata.presidentialField === undefined) {
        return unavailable("invalid_payload");
      }
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