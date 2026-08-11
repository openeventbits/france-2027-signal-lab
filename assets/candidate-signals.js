(() => {
  "use strict";

  const STATES = Object.freeze({
    loading: "loading",
    ready: "ready",
    empty: "empty",
    unavailable: "unavailable"
  });
  const SUPPORTED_SCHEMA_VERSIONS = new Set([
    "1.0", "1.1", "1.2", "1.3"
  ]);
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
  const legacyCandidacyFields = [
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
  const candidacyFields = [
    "status",
    "display_tier",
    "upstream_presence",
    "active_field_eligible",
    "status_as_of",
    "source_date",
    "source_url",
    "source_title",
    "source_publisher",
    "status_note"
  ];
  const fieldTiers = ["main", "secondary", "hidden"];
  const legacyFieldCountKeys = [
    "main", "secondary", "hidden", "active", "total"
  ];
  const fieldCountKeys = ["main", "secondary", "hidden", "total"];
  const activeMonitoringCountKeys = ["main", "secondary", "active"];
  const schema12TopFields = [
    "schema_version",
    "candidate_universe",
    "presidential_field",
    "active_field_visibility",
    "featured_polling_package",
    "featured_poll_board",
    "visibility",
    "scrutiny_window",
    "evidence_dates",
    "candidates"
  ];
  const schema13TopFields = [
    "schema_version",
    "candidate_universe",
    "presidential_field",
    "active_monitoring_field",
    "active_field_visibility",
    "featured_polling_package",
    "featured_poll_board",
    "visibility",
    "scrutiny_window",
    "evidence_dates",
    "candidates"
  ];
  const candidateRecordFields = [
    "candidate_id",
    "candidate_name",
    "candidacy",
    "polling",
    "campaign_attention",
    "general_visibility",
    "scrutiny",
    "latest_development"
  ];
  const activePeriodFields = [
    "start_date", "end_date", "record_count", "publisher_count"
  ];
  const activeQualityFields = [
    "status", "reason", "current_record_count", "prior_record_count",
    "current_publisher_count", "prior_publisher_count",
    "common_publisher_count", "publisher_union_count",
    "publisher_overlap_ratio", "record_count_ratio", "thresholds"
  ];
  const activeThresholdFields = [
    "minimum_period_records", "minimum_period_publishers",
    "minimum_common_publishers", "minimum_publisher_overlap_ratio",
    "maximum_record_count_ratio"
  ];

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

  function normalizeCandidacy(source, isVersion13) {
    const fields = isVersion13 ? candidacyFields : legacyCandidacyFields;
    if (!hasExactKeys(source, fields)) return undefined;
    for (const field of fields) {
      if (field === "active_field_eligible") continue;
      if (!nonemptyText(source[field])) return undefined;
    }
    if (!fieldTiers.includes(source.display_tier)) return undefined;
    if (typeof source.active_field_eligible !== "boolean") return undefined;
    if (
      isVersion13 &&
      !["present", "temporarily_missing"].includes(source.upstream_presence)
    ) {
      return undefined;
    }
    if (
      !isVersion13 &&
      source.active_field_eligible !== (source.display_tier !== "hidden")
    ) {
      return undefined;
    }
    return cloneValue(source);
  }

  function normalizePresidentialField(source, candidates, isVersion13) {
    const expectedKeys = ["status_as_of", ...fieldTiers, "counts"];
    if (!hasExactKeys(source, expectedKeys) || !nonemptyText(source.status_as_of)) {
      return undefined;
    }
    const countKeys = isVersion13 ? fieldCountKeys : legacyFieldCountKeys;
    if (!hasExactKeys(source.counts, countKeys)) return undefined;
    if (!countKeys.every(key => nonnegativeInteger(source.counts[key]))) {
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
          (
            !isVersion13 &&
            candidate.candidacy.active_field_eligible !== (tier !== "hidden")
          )
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
      total: candidates.length
    };
    if (!isVersion13) {
      expectedCounts.active = normalized.main.length + normalized.secondary.length;
    }
    if (countKeys.some(key => source.counts[key] !== expectedCounts[key])) {
      return undefined;
    }
    return normalized;
  }

  function normalizeActiveMonitoringField(source, candidates) {
    if (!hasExactKeys(source, ["main", "secondary", "counts"])) {
      return undefined;
    }
    if (!hasExactKeys(source.counts, activeMonitoringCountKeys)) {
      return undefined;
    }
    if (!activeMonitoringCountKeys.every(
      key => nonnegativeInteger(source.counts[key])
    )) return undefined;

    const candidateById = new Map(
      candidates.map(candidate => [candidate.candidate_id, candidate])
    );
    const seen = new Set();
    const normalized = {
      main: [],
      secondary: [],
      counts: cloneValue(source.counts)
    };
    for (const tier of ["main", "secondary"]) {
      if (!Array.isArray(source[tier])) return undefined;
      for (const identifier of source[tier]) {
        const candidate = candidateById.get(identifier);
        if (
          !nonemptyText(identifier) || !candidate || seen.has(identifier) ||
          candidate.candidacy?.display_tier !== tier ||
          candidate.candidacy?.upstream_presence !== "present" ||
          candidate.candidacy?.active_field_eligible !== true
        ) return undefined;
        seen.add(identifier);
        normalized[tier].push(identifier);
      }
    }
    const eligible = candidates
      .filter(candidate => candidate.candidacy?.active_field_eligible === true)
      .map(candidate => candidate.candidate_id);
    if (
      eligible.length !== seen.size ||
      eligible.some(identifier => !seen.has(identifier))
    ) return undefined;
    const expectedCounts = {
      main: normalized.main.length,
      secondary: normalized.secondary.length,
      active: normalized.main.length + normalized.secondary.length
    };
    if (activeMonitoringCountKeys.some(
      key => source.counts[key] !== expectedCounts[key]
    )) return undefined;
    return normalized;
  }

  const roundActiveRatio = value =>
    Math.floor(value * 1000 + 0.5) / 1000;

  function normalizeActivePeriod(source) {
    if (!hasExactKeys(source, activePeriodFields)) return undefined;
    if (
      !/^\d{4}-\d{2}-\d{2}$/.test(source.start_date) ||
      !/^\d{4}-\d{2}-\d{2}$/.test(source.end_date) ||
      !nonnegativeInteger(source.record_count) ||
      !nonnegativeInteger(source.publisher_count) ||
      source.publisher_count > source.record_count
    ) return undefined;
    const start = Date.parse(`${source.start_date}T00:00:00Z`);
    const end = Date.parse(`${source.end_date}T00:00:00Z`);
    return Number.isFinite(start) && end - start === 6 * 86400000
      ? cloneValue(source)
      : undefined;
  }

  function normalizeActiveQuality(source, current, prior) {
    if (
      !hasExactKeys(source, activeQualityFields) ||
      !["comparable", "not_comparable"].includes(source.status) ||
      !["comparable", "insufficient_data", "publisher_panel_changed"].includes(source.reason) ||
      (source.status === "comparable") !== (source.reason === "comparable") ||
      !hasExactKeys(source.thresholds, activeThresholdFields)
    ) return undefined;
    const countFields = activeQualityFields.filter(field => field.endsWith("_count"));
    if (
      countFields.some(field => !nonnegativeInteger(source[field])) ||
      activeThresholdFields.some(field =>
        typeof source.thresholds[field] !== "number" ||
        !Number.isFinite(source.thresholds[field]) ||
        source.thresholds[field] < 0
      ) ||
      source.current_record_count !== current.record_count ||
      source.prior_record_count !== prior.record_count ||
      source.current_publisher_count !== current.publisher_count ||
      source.prior_publisher_count !== prior.publisher_count ||
      source.common_publisher_count > Math.min(
        source.current_publisher_count,
        source.prior_publisher_count
      ) ||
      source.publisher_union_count !==
        source.current_publisher_count +
        source.prior_publisher_count -
        source.common_publisher_count
    ) return undefined;
    const overlap = roundActiveRatio(
      source.publisher_union_count
        ? source.common_publisher_count / source.publisher_union_count
        : 0
    );
    const recordRatio = current.record_count && prior.record_count
      ? roundActiveRatio(
          Math.max(current.record_count, prior.record_count) /
          Math.min(current.record_count, prior.record_count)
        )
      : null;
    return source.publisher_overlap_ratio === overlap &&
      source.record_count_ratio === recordRatio
      ? cloneValue(source)
      : undefined;
  }

  function activeRowOrder(left, right) {
    for (const [shareField, countField] of [
      ["current_share", "current_record_count"],
      ["prior_share", "prior_record_count"]
    ]) {
      const leftMissing = left[shareField] === null;
      const rightMissing = right[shareField] === null;
      if (leftMissing !== rightMissing) return leftMissing ? 1 : -1;
      if (!leftMissing && left[shareField] !== right[shareField]) {
        return right[shareField] - left[shareField];
      }
      if (left[countField] !== right[countField]) {
        return right[countField] - left[countField];
      }
    }
    const leftName = left.candidate_name.toLowerCase();
    const rightName = right.candidate_name.toLowerCase();
    if (leftName !== rightName) return leftName < rightName ? -1 : 1;
    return left.candidate_id < right.candidate_id
      ? -1
      : left.candidate_id > right.candidate_id ? 1 : 0;
  }

  function normalizeActiveScope(source, field, candidatesById) {
    if (!hasExactKeys(source, [
      "current_period", "prior_period", "comparison_quality", "main", "secondary"
    ])) return undefined;
    const current = normalizeActivePeriod(source.current_period);
    const prior = normalizeActivePeriod(source.prior_period);
    if (!current || !prior) return undefined;
    if (
      Date.parse(`${current.start_date}T00:00:00Z`) -
      Date.parse(`${prior.end_date}T00:00:00Z`) !== 86400000
    ) return undefined;
    const quality = normalizeActiveQuality(source.comparison_quality, current, prior);
    if (!quality) return undefined;
    const normalized = {
      current_period: current,
      prior_period: prior,
      comparison_quality: quality,
      main: [],
      secondary: []
    };
    const rowFields = [
      "candidate_id", "candidate_name", "status", "display_tier",
      "current_record_count", "current_share", "prior_record_count",
      "prior_share", "share_change"
    ];
    const seen = new Set();
    for (const tier of ["main", "secondary"]) {
      if (!Array.isArray(source[tier])) return undefined;
      for (const row of source[tier]) {
        const candidate = candidatesById.get(row?.candidate_id);
        if (
          !hasExactKeys(row, rowFields) || !candidate || seen.has(row.candidate_id) ||
          !field[tier].includes(row.candidate_id) ||
          row.candidate_name !== candidate.candidate_name ||
          row.status !== candidate.candidacy.status || row.display_tier !== tier ||
          candidate.candidacy.display_tier !== tier ||
          candidate.candidacy.active_field_eligible !== true ||
          !nonnegativeInteger(row.current_record_count) ||
          !nonnegativeInteger(row.prior_record_count) ||
          row.current_record_count > current.record_count ||
          row.prior_record_count > prior.record_count
        ) return undefined;
        const currentShare = current.record_count
          ? roundActiveRatio(row.current_record_count / current.record_count)
          : null;
        const priorShare = prior.record_count
          ? roundActiveRatio(row.prior_record_count / prior.record_count)
          : null;
        const change = quality.status === "comparable" &&
          currentShare !== null && priorShare !== null
          ? roundActiveRatio(currentShare - priorShare)
          : null;
        if (
          row.current_share !== currentShare || row.prior_share !== priorShare ||
          row.share_change !== change
        ) return undefined;
        seen.add(row.candidate_id);
        normalized[tier].push(cloneValue(row));
      }
      const ordered = [...normalized[tier]].sort(activeRowOrder);
      if (
        normalized[tier].length !== field[tier].length ||
        normalized[tier].some((row, index) => row.candidate_id !== ordered[index].candidate_id)
      ) return undefined;
    }
    return seen.size === field.counts.active ? normalized : undefined;
  }

  function normalizeActiveFieldVisibility(
    source, field, candidates, statusAsOf, isVersion13
  ) {
    if (!hasExactKeys(source, [
      "method", "denominator_scope", "status_as_of", "primary", "general"
    ])) return undefined;
    if (
      source.method !== "share_of_active_candidate_linked_records" ||
      source.denominator_scope !==
        (isVersion13
          ? "records_linked_to_at_least_one_active_monitoring_candidate"
          : "records_linked_to_at_least_one_main_or_secondary_candidate") ||
      source.status_as_of !== statusAsOf
    ) return undefined;
    const candidatesById = new Map(
      candidates.map(candidate => [candidate.candidate_id, candidate])
    );
    const primary = normalizeActiveScope(source.primary, field, candidatesById);
    const general = normalizeActiveScope(source.general, field, candidatesById);
    if (!primary || !general) return undefined;
    if (
      primary.current_period.start_date !== general.current_period.start_date ||
      primary.current_period.end_date !== general.current_period.end_date ||
      primary.prior_period.start_date !== general.prior_period.start_date ||
      primary.prior_period.end_date !== general.prior_period.end_date
    ) return undefined;
    return {
      method: source.method,
      denominator_scope: source.denominator_scope,
      status_as_of: source.status_as_of,
      primary,
      general
    };
  }

  function normalize(payload) {
    if (!isPlainObject(payload)) return unavailable("invalid_payload");
    if (!SUPPORTED_SCHEMA_VERSIONS.has(payload.schema_version)) {
      return unavailable("unsupported_schema");
    }
    const isVersion12 = payload.schema_version === "1.2";
    const isVersion13 = payload.schema_version === "1.3";
    if (isVersion12 && !hasExactKeys(payload, schema12TopFields)) {
      return unavailable("invalid_payload");
    }
    if (isVersion13 && !hasExactKeys(payload, schema13TopFields)) {
      return unavailable("invalid_payload");
    }
    if (!Array.isArray(payload.candidates)) {
      return unavailable("invalid_payload");
    }

    const hasPresidentialField =
      payload.schema_version === "1.1" || isVersion12 || isVersion13;
    const candidateIds = new Set();
    const candidates = [];

    for (const sourceCandidate of payload.candidates) {
      if (!isPlainObject(sourceCandidate)) return unavailable("invalid_payload");
      if (
        (isVersion12 || isVersion13) &&
        !hasExactKeys(sourceCandidate, candidateRecordFields)
      ) {
        return unavailable("invalid_payload");
      }
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
      if (hasPresidentialField) {
        candidate.candidacy = normalizeCandidacy(
          sourceCandidate.candidacy,
          isVersion13
        );
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
      presidentialField: null,
      activeMonitoringField: null,
      activeFieldVisibility: null
    };
    for (const field of metadataFields) {
      metadata[field] = payload[field] === undefined ? null : cloneValue(payload[field]);
    }
    if (hasPresidentialField) {
      metadata.presidentialField = normalizePresidentialField(
        payload.presidential_field,
        candidates,
        isVersion13
      );
      if (metadata.presidentialField === undefined) {
        return unavailable("invalid_payload");
      }
    }

    if (isVersion13) {
      metadata.activeMonitoringField = normalizeActiveMonitoringField(
        payload.active_monitoring_field,
        candidates
      );
      if (metadata.activeMonitoringField === undefined) {
        return unavailable("invalid_payload");
      }
    } else if (isVersion12) {
      metadata.activeMonitoringField = {
        main: cloneValue(metadata.presidentialField.main),
        secondary: cloneValue(metadata.presidentialField.secondary),
        counts: {
          main: metadata.presidentialField.main.length,
          secondary: metadata.presidentialField.secondary.length,
          active: metadata.presidentialField.counts.active
        }
      };
    }

    if (isVersion12 || isVersion13) {
      metadata.activeFieldVisibility = normalizeActiveFieldVisibility(
        payload.active_field_visibility,
        metadata.activeMonitoringField,
        candidates,
        metadata.presidentialField.status_as_of,
        isVersion13
      );
      if (metadata.activeFieldVisibility === undefined) {
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
