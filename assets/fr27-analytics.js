(function () {
  "use strict";

  const PRODUCTION_HOST = "france2027.app";
  const PROJECT_TOKEN =
    "phc_pMNSSA2jsB9dXsYcFy8ewngmRtasgG7Wa4szeSojfzkh";
  const API_HOST = "https://eu.i.posthog.com";
  const CONSENT_KEY = "fr27_analytics_consent";

  const ALLOWED_EVENTS = Object.freeze({
    workspace_open: [
      "workspace",
      "source"
    ],
    candidate_dossier_open: [
      "candidate_id"
    ],
    poll_detail_open: [
      "candidate_id",
      "pollster",
      "evidence_type"
    ],
    evidence_open: [
      "workspace",
      "candidate_id",
      "evidence_type"
    ],
    campaign_event_open: [
      "event_id",
      "event_type"
    ],
    outbound_source_click: [
      "workspace",
      "context",
      "destination_domain"
    ],
    share_action: [
      "method",
      "context"
    ],
    professional_conversion: [
      "action"
    ]
  });

  const CAMPAIGN_KEYS = Object.freeze([
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term"
  ]);

  const pendingEvents = [];

  let ready = false;

  function isProduction() {
    return window.location.hostname === PRODUCTION_HOST;
  }

  function locale() {
    const value = String(
      document.documentElement.lang || "fr"
    )
      .trim()
      .toLowerCase();

    return value.startsWith("en") ? "en" : "fr";
  }

  function currentPath() {
    return locale() === "en" ? "/en/" : "/";
  }

  function safeString(value, maxLength = 160) {
    if (value === null || value === undefined) return "";

    return String(value)
      .trim()
      .slice(0, maxLength);
  }

  function safeDomain(value) {
    const raw = safeString(value, 2048);
    if (!raw) return "";

    try {
      return new URL(raw, window.location.href)
        .hostname
        .toLowerCase()
        .replace(/^www\./, "");
    } catch (_) {
      return "";
    }
  }

  function readConsent() {
    try {
      const value = window.localStorage.getItem(
        CONSENT_KEY
      );

      return value === "granted"
        ? "granted"
        : value === "denied"
          ? "denied"
          : "unknown";
    } catch (_) {
      return "unknown";
    }
  }

  function writeConsent(value) {
    try {
      window.localStorage.setItem(
        CONSENT_KEY,
        value
      );
    } catch (_) {
      // Analytics must never interfere with FR27.
    }
  }

  function normalizedCampaign() {
    const params = new URLSearchParams(
      window.location.search
    );
    const campaign = {};

    CAMPAIGN_KEYS.forEach(key => {
      const value = safeString(
        params.get(key),
        120
      );

      if (value) {
        campaign[key] = value;
      }
    });

    return campaign;
  }

  function captureCampaign() {
    const campaign = normalizedCampaign();

    if (
      ready &&
      Object.keys(campaign).length &&
      window.posthog &&
      typeof window.posthog.register_for_session ===
        "function"
    ) {
      window.posthog.register_for_session(
        campaign
      );
    }

    return campaign;
  }

  function sanitizeProperties(eventName, properties) {
    const allowed =
      ALLOWED_EVENTS[eventName] || [];
    const source =
      properties &&
      typeof properties === "object"
        ? properties
        : {};
    const clean = {
      locale: locale(),
      path: currentPath()
    };

    allowed.forEach(key => {
      let value = source[key];

      if (key === "destination_domain") {
        value = safeDomain(value);
      } else {
        value = safeString(value);
      }

      if (value) {
        clean[key] = value;
      }
    });

    return clean;
  }

  function flushPendingEvents() {
    if (
      !ready ||
      !window.posthog ||
      typeof window.posthog.capture !== "function"
    ) {
      return;
    }

    while (pendingEvents.length) {
      const entry = pendingEvents.shift();

      window.posthog.capture(
        entry.eventName,
        entry.properties
      );
    }
  }

  function bootstrapPostHog() {
    !function(t,e){var o,n,p,r;e.__SV||(window.posthog&&window.posthog.__loaded)||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}p||((p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",p.onerror=function(){p=null},(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r));var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],Object.defineProperty(u,"toString",{configurable:!0,enumerable:!0,writable:!0,value:function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e}}),Object.defineProperty(u.people,"toString",{configurable:!0,enumerable:!0,writable:!0,value:function(){return u.toString(1)+".people (stub)"}}),o="su ru ou lu hu init Au Fu Eu Pu Nu zl Ru ju Tu Uu Wu Vu capture getExtension Ou iu Qu calculateEventProperties Zu register register_once register_for_session unregister unregister_for_session Xu Mu Ju getFeatureFlag getFeatureFlagPayload getFeatureFlagResult getAllFeatureFlags isFeatureEnabled reloadFeatureFlags updateFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSurveysLoaded onSessionId getSurveys getActiveMatchingSurveys renderSurvey displaySurvey cancelPendingSurvey canRenderSurvey canRenderSurveyAsync th identify setPersonProperties unsetPersonProperties group resetGroups setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags reset eh shutdown setIdentity clearIdentity get_distinct_id getGroups get_session_id get_session_replay_url alias set_config startSessionRecording stopSessionRecording sessionRecordingStarted captureException addExceptionStep captureLog startExceptionAutocapture stopExceptionAutocapture loadToolbar get_property getSessionProperty Ku zu createPersonProfile setInternalOrTestUser Yu cu du opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing get_explicit_consent_status is_capturing clear_opt_in_out_capturing Bu debug Ul $s getPageViewId captureTraceFeedback captureTraceMetric Su".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);
  }

  function initializePostHog() {
    if (!isProduction()) {
      return Promise.resolve(false);
    }

    if (readConsent() !== "granted") {
      return Promise.resolve(false);
    }

    if (ready) {
      return Promise.resolve(true);
    }

    bootstrapPostHog();

    if (
      !window.posthog ||
      typeof window.posthog.init !== "function"
    ) {
      return Promise.resolve(false);
    }

    window.posthog.init(
      PROJECT_TOKEN,
      {
        api_host: API_HOST,
        defaults: "2026-05-30",
        person_profiles: "identified_only",
        persistence: "localStorage+cookie",
        autocapture: false,
        disable_session_recording: true,
        capture_pageview: true,
        capture_pageleave: true
      }
    );

    /*
     * The official PostHog bootstrap queues calls made before the
     * network-loaded SDK is ready, so the FR27 adapter can safely
     * begin emitting after init without depending on SDK load timing.
     */
    ready = true;
    captureCampaign();
    flushPendingEvents();

    return Promise.resolve(true);
  }
  function track(eventName, properties = {}) {
    if (!isProduction()) return false;

    if (
      !Object.prototype.hasOwnProperty.call(
        ALLOWED_EVENTS,
        eventName
      )
    ) {
      return false;
    }

    if (readConsent() !== "granted") {
      return false;
    }

    const clean = sanitizeProperties(
      eventName,
      properties
    );

    if (
      ready &&
      window.posthog &&
      typeof window.posthog.capture ===
        "function"
    ) {
      window.posthog.capture(
        eventName,
        clean
      );
      return true;
    }

    pendingEvents.push({
      eventName,
      properties: clean
    });

    initializePostHog();
    return true;
  }

  function pageview() {
    if (!isProduction()) return false;
    if (readConsent() !== "granted") {
      return false;
    }

    if (
      ready &&
      window.posthog &&
      typeof window.posthog.capture ===
        "function"
    ) {
      window.posthog.capture(
        "$pageview",
        {
          locale: locale(),
          path: currentPath()
        }
      );
      return true;
    }

    initializePostHog();
    return true;
  }

  function notifyAnalyticsReady() {
    window.dispatchEvent(
      new Event(
        "fr27:analytics-ready"
      )
    );
  }
  function setConsent(granted) {
    const value = granted
      ? "granted"
      : "denied";

    writeConsent(value);

    if (granted) {
      if (
        ready &&
        window.posthog &&
        typeof window.posthog.opt_in_capturing ===
          "function"
      ) {
        window.posthog.opt_in_capturing();
        captureCampaign();
        notifyAnalyticsReady();
        return;
      }

      initializePostHog().then(
        function (initialized) {
          if (initialized) {
            notifyAnalyticsReady();
          }
        }
      );
      return;
    }

    pendingEvents.length = 0;

    if (
      window.posthog &&
      typeof window.posthog.opt_out_capturing ===
        "function"
    ) {
      window.posthog.opt_out_capturing();
    }
  }

  function consentStatus() {
    return readConsent();
  }

  function consentCopy() {
    if (locale() === "en") {
      return {
        title: "OPTIONAL ANALYTICS",
        body:
          "PostHog analytics, hosted in the EU, use a first-party browser identifier to measure visits, feature use and return visits. No advertising tracking.",
        allow: "ALLOW ANALYTICS",
        decline: "DECLINE",
        settings: "ANALYTICS SETTINGS"
      };
    }

    return {
      title: "STATISTIQUES FACULTATIVES",
      body:
        "Les statistiques PostHog, hébergées dans l’UE, utilisent un identifiant analytique dans votre navigateur pour mesurer les visites, l’usage des fonctions et les retours. Aucun traçage publicitaire.",
      allow: "AUTORISER",
      decline: "REFUSER",
      settings: "PARAMÈTRES ANALYTIQUES"
    };
  }

  function ensureConsentStyles() {
    if (
      document.getElementById(
        "fr27-analytics-consent-style"
      )
    ) {
      return;
    }

    const style = document.createElement("style");
    style.id = "fr27-analytics-consent-style";
    style.textContent = `
      .fr27-analytics-consent {
        position: fixed;
        right: 14px;
        bottom: 14px;
        z-index: 10000;
        width: min(390px, calc(100vw - 28px));
        padding: 14px;
        border: 1px solid rgba(99, 179, 237, .34);
        background: rgba(5, 12, 20, .97);
        box-shadow: 0 14px 44px rgba(0, 0, 0, .42);
        color: #d7e4ef;
        font: 11px/1.5 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      }

      .fr27-analytics-consent strong {
        display: block;
        margin-bottom: 7px;
        color: #76d7ff;
        font-size: 11px;
        letter-spacing: .08em;
      }

      .fr27-analytics-consent p {
        margin: 0 0 12px;
        color: #aabac8;
      }

      .fr27-analytics-consent-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 7px;
      }

      .fr27-analytics-consent button,
      .fr27-analytics-settings {
        border: 1px solid rgba(99, 179, 237, .36);
        background: rgba(13, 27, 40, .9);
        color: #d7e4ef;
        font: inherit;
        letter-spacing: .04em;
        cursor: pointer;
      }

      .fr27-analytics-consent button {
        padding: 7px 10px;
      }

      .fr27-analytics-consent button:hover,
      .fr27-analytics-consent button:focus-visible,
      .fr27-analytics-settings:hover,
      .fr27-analytics-settings:focus-visible {
        border-color: rgba(118, 215, 255, .8);
        color: #ffffff;
        outline: none;
      }

      .fr27-analytics-consent .is-primary {
        color: #76d7ff;
      }

      .fr27-analytics-settings {
        display: block;
        width: 100%;
        margin-top: 8px;
        padding: 6px 8px;
        text-align: left;
      }
    `;

    document.head.appendChild(style);
  }

  function closeConsentPrompt() {
    document
      .getElementById(
        "fr27-analytics-consent"
      )
      ?.remove();
  }

  function showConsentPrompt() {
    if (!isProduction()) return;
    if (!document.body) return;

    closeConsentPrompt();
    ensureConsentStyles();

    const copy = consentCopy();
    const panel = document.createElement("section");

    panel.id = "fr27-analytics-consent";
    panel.className =
      "fr27-analytics-consent";
    panel.setAttribute(
      "aria-label",
      copy.title
    );

    const title =
      document.createElement("strong");
    title.textContent = copy.title;

    const body =
      document.createElement("p");
    body.textContent = copy.body;

    const actions =
      document.createElement("div");
    actions.className =
      "fr27-analytics-consent-actions";

    const allow =
      document.createElement("button");
    allow.type = "button";
    allow.className = "is-primary";
    allow.textContent = copy.allow;

    const decline =
      document.createElement("button");
    decline.type = "button";
    decline.textContent = copy.decline;

    allow.addEventListener(
      "click",
      function () {
        setConsent(true);
        closeConsentPrompt();
      }
    );

    decline.addEventListener(
      "click",
      function () {
        setConsent(false);
        closeConsentPrompt();
      }
    );

    actions.append(
      allow,
      decline
    );

    panel.append(
      title,
      body,
      actions
    );

    document.body.appendChild(panel);
  }

  const SOURCE_LINK_SELECTOR = [
    "a.candidate-signals-source-link[href]",
    "a.candidate-signals-scrutiny-source[href]",
    "a.hybrid-events-dossier-source[href]",
    "a.hybrid-runoff-source[href]",
    "a.pe-source-link[href]",
    "a.freshness-source[href]",
    ".top-media-source-link a[href]",
    "a#race-source[href]"
  ].join(", ");

  let delegatedSourceTrackingMounted = false;

  function sourceWorkspace(link) {
    if (link.closest("#signal-candidates-panel")) {
      return "candidates";
    }

    if (link.closest("#signal-runoff-panel")) {
      return "runoff";
    }

    if (link.closest("#signal-events-panel")) {
      return "events";
    }

    if (link.closest("#signal-agenda-panel")) {
      return "agenda";
    }

    if (link.closest("#signal-issues-panel")) {
      return "issues";
    }

    return "overview";
  }

  function sourceContext(link) {
    if (
      link.matches(
        ".candidate-signals-source-link"
      )
    ) {
      return "candidate_source";
    }

    if (
      link.matches(
        ".candidate-signals-scrutiny-source"
      )
    ) {
      return "scrutiny_review";
    }

    if (
      link.matches(
        ".hybrid-events-dossier-source"
      )
    ) {
      return "campaign_event_source";
    }

    if (
      link.matches(
        ".hybrid-runoff-source"
      )
    ) {
      return "runoff_evidence";
    }

    if (link.matches(".pe-source-link")) {
      return "polling_evidence";
    }

    if (link.matches(".freshness-source")) {
      return "freshness_watch";
    }

    if (
      link.closest(".top-media-source-link")
    ) {
      return "media_pulse";
    }

    if (link.id === "race-source") {
      return "race_at_a_glance";
    }

    return "source";
  }

  function mountDelegatedSourceTracking() {
    if (delegatedSourceTrackingMounted) {
      return;
    }

    delegatedSourceTrackingMounted = true;

    document.addEventListener(
      "click",
      function (event) {
        const target =
          event.target instanceof Element
            ? event.target.closest(
                SOURCE_LINK_SELECTOR
              )
            : null;

        if (!target) return;

        const href =
          target.getAttribute("href") || "";

        if (!href) return;

        const domain = safeDomain(href);

        if (
          !domain ||
          domain === PRODUCTION_HOST
        ) {
          return;
        }

        track(
          "outbound_source_click",
          {
            workspace:
              sourceWorkspace(target),
            context:
              sourceContext(target),
            destination_domain: href
          }
        );
      }
    );
  }
  function mountAnalyticsSettings() {
    if (!isProduction()) return;

    mountDelegatedSourceTracking();
    ensureConsentStyles();

    const contact =
      document.getElementById(
        "fr27-hud-contact-popover"
      );

    if (
      contact &&
      !document.getElementById(
        "fr27-analytics-settings"
      )
    ) {
      const button =
        document.createElement("button");

      button.type = "button";
      button.id =
        "fr27-analytics-settings";
      button.className =
        "fr27-analytics-settings";
      button.textContent =
        consentCopy().settings;

      button.addEventListener(
        "click",
        function (event) {
          event.stopPropagation();
          showConsentPrompt();
        }
      );

      contact.appendChild(button);
    }

    if (readConsent() === "unknown") {
      showConsentPrompt();
    }
  }
  window.FR27Analytics = Object.freeze({
    track,
    pageview,
    setConsent,
    captureCampaign,
    consentStatus,
    isProduction
  });

  if (
    isProduction() &&
    readConsent() === "granted"
  ) {
    initializePostHog();
  }

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      mountAnalyticsSettings,
      { once: true }
    );
  } else {
    mountAnalyticsSettings();
  }
})();
