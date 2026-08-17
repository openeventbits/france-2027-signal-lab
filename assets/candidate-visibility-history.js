(() => {
  "use strict";

  const SCHEMA_VERSION = "1.0";
  const DAYS = 29;
  const CAMPAIGN_LANE = "campaign_attention";
  const GENERAL_LANE = "general_visibility";
  const LANE_NAMES = Object.freeze([
    CAMPAIGN_LANE,
    GENERAL_LANE
  ]);

  const TOP_LEVEL_KEYS = Object.freeze([
    "schema_version",
    "period",
    "methodology",
    "lanes",
    "candidates"
  ]);

  const PERIOD_KEYS = Object.freeze([
    "start_date",
    "end_date",
    "days",
    "data_as_of",
    "day_boundary",
    "current_utc_day_excluded"
  ]);

  const METHODOLOGY_KEYS = Object.freeze([
    "source",
    "primary_scopes",
    "general_scope",
    "metric",
    "candidate_linkage",
    "not_measures"
  ]);

  const DENOMINATOR_KEYS = Object.freeze([
    "date",
    "record_count",
    "publisher_count"
  ]);

  const SERIES_KEYS = Object.freeze([
    "date",
    "record_count",
    "share",
    "publisher_count"
  ]);

  const CANDIDATE_KEYS = Object.freeze([
    "candidate_id",
    "candidate_name",
    CAMPAIGN_LANE,
    GENERAL_LANE
  ]);

  function unavailable(reason) {
    return {
      status: "unavailable",
      payload: null,
      reason
    };
  }

  function exactKeys(value, expected) {
    if (
      !value ||
      typeof value !== "object" ||
      Array.isArray(value)
    ) {
      return false;
    }

    const actual = Object.keys(value).sort();
    const target = [...expected].sort();

    return (
      actual.length === target.length &&
      actual.every(
        (key, index) => key === target[index]
      )
    );
  }

  function trimmedText(value) {
    return (
      typeof value === "string" &&
      value.length > 0 &&
      value === value.trim()
    );
  }

  function nonNegativeInteger(value) {
    return (
      Number.isInteger(value) &&
      value >= 0
    );
  }

  function canonicalDate(value) {
    if (
      typeof value !== "string" ||
      !/^\d{4}-\d{2}-\d{2}$/.test(value)
    ) {
      return false;
    }

    const parsed = new Date(
      `${value}T00:00:00Z`
    );

    return (
      !Number.isNaN(parsed.getTime()) &&
      parsed.toISOString().slice(0, 10) === value
    );
  }

  function addUtcDays(value, offset) {
    const parsed = new Date(
      `${value}T00:00:00Z`
    );

    parsed.setUTCDate(
      parsed.getUTCDate() + offset
    );

    return parsed.toISOString().slice(0, 10);
  }

  function visibilityRatio(value) {
    return (
      Math.floor(value * 1000 + 0.5) /
      1000
    );
  }

  function validPeriod(period) {
    if (!exactKeys(period, PERIOD_KEYS)) {
      return false;
    }

    if (
      !canonicalDate(period.start_date) ||
      !canonicalDate(period.end_date) ||
      !canonicalDate(period.data_as_of)
    ) {
      return false;
    }

    return (
      period.days === DAYS &&
      period.end_date ===
        addUtcDays(period.start_date, DAYS - 1) &&
      period.data_as_of === period.end_date &&
      period.day_boundary === "UTC" &&
      period.current_utc_day_excluded === true
    );
  }

  function expectedDates(period) {
    return Array.from(
      { length: DAYS },
      (_unused, index) =>
        addUtcDays(period.start_date, index)
    );
  }

  function validMethodology(methodology) {
    if (
      !exactKeys(
        methodology,
        METHODOLOGY_KEYS
      )
    ) {
      return false;
    }

    return (
      methodology.source ===
        "news_wire.json:candidate_watch" &&
      Array.isArray(
        methodology.primary_scopes
      ) &&
      methodology.primary_scopes.length === 2 &&
      methodology.primary_scopes[0] ===
        "election" &&
      methodology.primary_scopes[1] ===
        "campaign" &&
      methodology.general_scope === "general" &&
      methodology.metric ===
        "candidate_share_of_lane_records" &&
      methodology.candidate_linkage ===
        "published_candidate_matches" &&
      Array.isArray(
        methodology.not_measures
      ) &&
      methodology.not_measures.length === 4 &&
      methodology.not_measures[0] ===
        "sentiment" &&
      methodology.not_measures[1] ===
        "approval" &&
      methodology.not_measures[2] ===
        "electoral support" &&
      methodology.not_measures[3] ===
        "voting intention"
    );
  }

  function normalizeExpectedCandidates(
    expectedCandidates
  ) {
    if (expectedCandidates === null) {
      return null;
    }

    if (
      !Array.isArray(expectedCandidates) ||
      expectedCandidates.length === 0
    ) {
      return null;
    }

    const identities = expectedCandidates.map(
      candidate => ({
        candidate_id:
          candidate?.candidate_id,
        candidate_name:
          candidate?.candidate_name
      })
    );

    const valid = identities.every(
      candidate =>
        trimmedText(
          candidate.candidate_id
        ) &&
        trimmedText(
          candidate.candidate_name
        )
    );

    return valid ? identities : null;
  }

  function validDenominators(
    lane,
    dates
  ) {
    if (
      !exactKeys(
        lane,
        ["daily_denominators"]
      ) ||
      !Array.isArray(
        lane.daily_denominators
      ) ||
      lane.daily_denominators.length !== DAYS
    ) {
      return null;
    }

    const indexed = new Map();

    for (
      let index = 0;
      index < lane.daily_denominators.length;
      index += 1
    ) {
      const observation =
        lane.daily_denominators[index];

      if (
        !exactKeys(
          observation,
          DENOMINATOR_KEYS
        ) ||
        observation.date !== dates[index] ||
        !nonNegativeInteger(
          observation.record_count
        ) ||
        !nonNegativeInteger(
          observation.publisher_count
        ) ||
        observation.publisher_count >
          observation.record_count
      ) {
        return null;
      }

      indexed.set(
        observation.date,
        observation
      );
    }

    return indexed;
  }

  function validSeries(
    lane,
    dates,
    denominators
  ) {
    if (
      !exactKeys(
        lane,
        ["daily_series"]
      ) ||
      !Array.isArray(
        lane.daily_series
      ) ||
      lane.daily_series.length !== DAYS
    ) {
      return false;
    }

    for (
      let index = 0;
      index < lane.daily_series.length;
      index += 1
    ) {
      const observation =
        lane.daily_series[index];

      if (
        !exactKeys(
          observation,
          SERIES_KEYS
        ) ||
        observation.date !== dates[index] ||
        !nonNegativeInteger(
          observation.record_count
        ) ||
        !nonNegativeInteger(
          observation.publisher_count
        )
      ) {
        return false;
      }

      const denominator =
        denominators.get(
          observation.date
        );

      if (!denominator) {
        return false;
      }

      if (
        observation.record_count >
          denominator.record_count ||
        observation.publisher_count >
          observation.record_count ||
        observation.publisher_count >
          denominator.publisher_count
      ) {
        return false;
      }

      if (
        denominator.record_count === 0
      ) {
        if (
          observation.record_count !== 0 ||
          observation.publisher_count !== 0 ||
          observation.share !== null
        ) {
          return false;
        }

        continue;
      }

      if (
        typeof observation.share !==
          "number" ||
        !Number.isFinite(
          observation.share
        ) ||
        observation.share < 0 ||
        observation.share > 1
      ) {
        return false;
      }

      const expectedShare =
        visibilityRatio(
          observation.record_count /
            denominator.record_count
        );

      if (
        observation.share !==
        expectedShare
      ) {
        return false;
      }
    }

    return true;
  }

  function validCandidateOrder(
    candidates
  ) {
    const identities = candidates.map(
      candidate => ({
        candidate_id:
          candidate.candidate_id,
        candidate_name:
          candidate.candidate_name
      })
    );

    const sorted = [...identities].sort(
      (left, right) => {
        const leftName =
          left.candidate_name.toLowerCase();
        const rightName =
          right.candidate_name.toLowerCase();

        if (leftName < rightName) {
          return -1;
        }

        if (leftName > rightName) {
          return 1;
        }

        if (
          left.candidate_id <
          right.candidate_id
        ) {
          return -1;
        }

        if (
          left.candidate_id >
          right.candidate_id
        ) {
          return 1;
        }

        return 0;
      }
    );

    return identities.every(
      (candidate, index) =>
        candidate.candidate_id ===
          sorted[index].candidate_id &&
        candidate.candidate_name ===
          sorted[index].candidate_name
    );
  }

  function validCandidateParity(
    candidates,
    expectedCandidates
  ) {
    if (expectedCandidates === null) {
      return true;
    }

    if (
      candidates.length !==
      expectedCandidates.length
    ) {
      return false;
    }

    return candidates.every(
      (candidate, index) =>
        candidate.candidate_id ===
          expectedCandidates[index].candidate_id &&
        candidate.candidate_name ===
          expectedCandidates[index].candidate_name
    );
  }

  function normalize(
    payload,
    expectedCandidates = null
  ) {
    if (
      !exactKeys(
        payload,
        TOP_LEVEL_KEYS
      ) ||
      payload.schema_version !==
        SCHEMA_VERSION ||
      !validPeriod(payload.period) ||
      !validMethodology(
        payload.methodology
      ) ||
      !exactKeys(
        payload.lanes,
        LANE_NAMES
      ) ||
      !Array.isArray(
        payload.candidates
      ) ||
      payload.candidates.length === 0
    ) {
      return unavailable(
        "invalid_payload"
      );
    }

    const normalizedExpected =
      normalizeExpectedCandidates(
        expectedCandidates
      );

    if (
      expectedCandidates !== null &&
      normalizedExpected === null
    ) {
      return unavailable(
        "invalid_candidate_universe"
      );
    }

    const dates = expectedDates(
      payload.period
    );

    const denominators = {};

    for (const laneName of LANE_NAMES) {
      const indexed =
        validDenominators(
          payload.lanes[
            laneName
          ],
          dates
        );

      if (!indexed) {
        return unavailable(
          "invalid_payload"
        );
      }

      denominators[laneName] =
        indexed;
    }

    const candidateIds = new Set();
    const candidateNames = new Set();

    for (
      const candidate of
        payload.candidates
    ) {
      if (
        !exactKeys(
          candidate,
          CANDIDATE_KEYS
        ) ||
        !trimmedText(
          candidate.candidate_id
        ) ||
        !trimmedText(
          candidate.candidate_name
        ) ||
        candidateIds.has(
          candidate.candidate_id
        ) ||
        candidateNames.has(
          candidate.candidate_name
        )
      ) {
        return unavailable(
          "invalid_payload"
        );
      }

      candidateIds.add(
        candidate.candidate_id
      );
      candidateNames.add(
        candidate.candidate_name
      );

      for (
        const laneName of
          LANE_NAMES
      ) {
        if (
          !validSeries(
            candidate[laneName],
            dates,
            denominators[laneName]
          )
        ) {
          return unavailable(
            "invalid_payload"
          );
        }
      }
    }

    if (
      !validCandidateOrder(
        payload.candidates
      )
    ) {
      return unavailable(
        "invalid_payload"
      );
    }

    if (
      !validCandidateParity(
        payload.candidates,
        normalizedExpected
      )
    ) {
      return unavailable(
        "candidate_mismatch"
      );
    }

    return {
      status: "ready",
      payload,
      reason: null
    };
  }

  async function load(
    url,
    expectedCandidates = null,
    fetchImplementation =
      typeof window.fetch === "function"
        ? window.fetch.bind(window)
        : null
  ) {
    if (!fetchImplementation) {
      return unavailable(
        "fetch_unavailable"
      );
    }

    try {
      const response =
        await fetchImplementation(
          url,
          { cache: "no-store" }
        );

      if (!response.ok) {
        return unavailable(
          "http_error"
        );
      }

      const payload =
        await response.json();

      return normalize(
        payload,
        expectedCandidates
      );
    } catch (_error) {
      return unavailable(
        "fetch_failed"
      );
    }
  }

  window.France2027CandidateVisibilityHistory =
    Object.freeze({
      load,
      normalize
    });
})();