(function (global) {
  "use strict";

  const documentElement =
    global.document && global.document.documentElement;
  const catalogs = global.FR27_LOCALES || Object.create(null);
  const fallbackLocale = "en";

  const normalizeLocale = value =>
    String(value || "")
      .trim()
      .toLowerCase() === "en"
      ? "en"
      : "fr";

  const requestedLocale =
    global.location &&
    new URLSearchParams(global.location.search).get("lang");
  const documentLocale =
    documentElement && documentElement.lang;
  let locale = requestedLocale
    ? normalizeLocale(requestedLocale)
    : normalizeLocale(documentLocale);
  let localeTag = locale === "fr" ? "fr-FR" : "en-GB";

  if (documentElement) {
    documentElement.lang = locale;
  }

  const isDevelopment = Boolean(
    global.location &&
      (global.location.protocol === "file:" ||
        /^(localhost|127\.0\.0\.1)$/.test(
          global.location.hostname
        ))
  );

  let activeCatalog =
    catalogs[locale] || catalogs[fallbackLocale];
  const fallbackCatalog =
    catalogs[fallbackLocale] || Object.create(null);

  const messageFor = (key, callerFallback) => {
    const normalizedKey = String(key || "");

    if (
      activeCatalog &&
      Object.prototype.hasOwnProperty.call(
        activeCatalog,
        normalizedKey
      )
    ) {
      return activeCatalog[normalizedKey];
    }

    if (
      fallbackCatalog &&
      Object.prototype.hasOwnProperty.call(
        fallbackCatalog,
        normalizedKey
      )
    ) {
      return fallbackCatalog[normalizedKey];
    }

    if (isDevelopment && global.console) {
      global.console.warn(
        "[fr27-i18n] Missing localization key:",
        normalizedKey
      );
    }

    if (
      typeof callerFallback === "string" &&
      callerFallback.trim()
    ) {
      return callerFallback;
    }

    return normalizedKey;
  };

  const pluralPattern =
    /\{([A-Za-z0-9_]+),\s*plural,\s*one\s*\{([^{}]*)\}\s*other\s*\{([^{}]*)\}\s*\}/g;

  const applyPluralRules = (message, parameters) =>
    message.replace(
      pluralPattern,
      (match, parameterName, oneValue, otherValue) => {
        const numericValue = Number(parameters[parameterName]);
        const category =
          new Intl.PluralRules(localeTag).select(numericValue);

        return category === "one" ? oneValue : otherValue;
      }
    );

  const interpolate = (message, parameters) =>
    message.replace(
      /\{([A-Za-z0-9_]+)\}/g,
      (match, parameterName) =>
        Object.prototype.hasOwnProperty.call(
          parameters,
          parameterName
        )
          ? String(parameters[parameterName])
          : match
    );

  const t = (key, parameters, callerFallback) => {
    const safeParameters =
      parameters || Object.create(null);
    const pluralized = applyPluralRules(
      String(messageFor(key, callerFallback)),
      safeParameters
    );

    return interpolate(pluralized, safeParameters);
  };

  const formatDate = (value, options) =>
    new Intl.DateTimeFormat(localeTag, options).format(
      value instanceof Date ? value : new Date(value)
    );

  const formatNumber = (value, options) =>
    new Intl.NumberFormat(localeTag, options).format(value);

  const formatPercent = (value, options) =>
    new Intl.NumberFormat(
      localeTag,
      Object.assign(
        { style: "percent" },
        options || Object.create(null)
      )
    ).format(value);

  const pluralCategory = value =>
    new Intl.PluralRules(localeTag).select(Number(value));

  const siteRoot =
    (documentElement && documentElement.dataset.siteRoot) ||
    "./";

  const initialBaseURI = global.document?.baseURI;
  const siteRootUrl = () =>
    new URL(siteRoot, initialBaseURI);

  const siteUrl = path =>
    new URL(String(path || ""), siteRootUrl()).toString();

  const buildLocaleUrl = targetLocale => {
    const target = normalizeLocale(targetLocale);
    const current = new URL(global.location.href);
    const next = new URL(
      target === "en" ? "en/" : "",
      siteRootUrl()
    );

    current.searchParams.delete("lang");
    next.search = current.searchParams.toString();
    next.hash = current.hash;

    return next.toString();
  };

  const migrateLegacyLocaleUrl = () => {
    if (
      !requestedLocale ||
      normalizeLocale(requestedLocale) !== "en" ||
      !global.location ||
      !global.document ||
      !documentElement
    ) {
      return false;
    }

    const current = new URL(global.location.href);
    const target = buildLocaleUrl("en");

    if (current.toString() === target) {
      return false;
    }

    if (typeof global.location.replace === "function") {
      global.location.replace(target);
      return true;
    }

    if (
      global.history &&
      typeof global.history.replaceState === "function"
    ) {
      global.history.replaceState(null, "", target);
      return true;
    }

    return false;
  };

  migrateLegacyLocaleUrl();

  const applyDocumentTitle = () => {
    if (!documentElement || !global.document) {
      return;
    }

    const titleKey =
      documentElement.dataset.i18nDocumentTitle;

    if (titleKey) {
      global.document.title = t(titleKey);
    }
  };

  const applyTextTranslations = () => {
    if (!global.document || !global.document.querySelectorAll) {
      return;
    }

    const elements = global.document.querySelectorAll(
      "[data-i18n]"
    );

    elements.forEach(element => {
      const key = element.getAttribute("data-i18n");
      const current = String(element.textContent || "");

      element.textContent = t(key, null, current);
    });
  };

  const applyAttributeTranslations = () => {
    if (!global.document || !global.document.querySelectorAll) {
      return;
    }

    const elements = global.document.querySelectorAll(
      "[data-i18n-aria-label]"
    );

    elements.forEach(element => {
      const key = element.getAttribute(
        "data-i18n-aria-label"
      );
      const current = element.getAttribute("aria-label");

      element.setAttribute(
        "aria-label",
        t(key, null, current)
      );
    });
  };

  const applyTooltipTranslations = () => {
    if (!global.document || !global.document.querySelectorAll) {
      return;
    }

    const elements = global.document.querySelectorAll(
      "[data-i18n-fr27-tooltip]"
    );

    elements.forEach(element => {
      const key = element.getAttribute(
        "data-i18n-fr27-tooltip"
      );
      const current = element.getAttribute("data-fr27-tooltip");

      element.setAttribute(
        "data-fr27-tooltip",
        t(key, null, current)
      );
    });
  };

  const applyStaticTranslations = () => {
    applyTextTranslations();
    applyAttributeTranslations();
    applyTooltipTranslations();
  };

  const applyLanguageLinks = () => {
    if (!global.document || !global.document.querySelectorAll) {
      return;
    }

    const links = global.document.querySelectorAll(
      "[data-fr27-language]"
    );

    links.forEach(link => {
      const target = normalizeLocale(
        link.getAttribute("data-fr27-language")
      );

      link.setAttribute("href", buildLocaleUrl(target));

      if (target === locale) {
        link.setAttribute("aria-current", "page");
      } else {
        link.removeAttribute("aria-current");
      }
    });
  };

  // Only the dashboard owns a retained, language-independent evidence state.
  // Family pages keep their ordinary bilingual document navigation.
  const isDashboard = () => Boolean(global.document.getElementById?.("hybrid-signal-board"));
  const setDashboardLocale = (target, updateHistory = true) => {
    if (!isDashboard()) return;
    const next = buildLocaleUrl(target);
    locale = normalizeLocale(target);
    localeTag = locale === "fr" ? "fr-FR" : "en-GB";
    activeCatalog = catalogs[locale] || fallbackCatalog;
    documentElement.lang = locale;
    // Keep pending relative requests on the same site root after pushState.
    if (!global.document.querySelector("base")) {
      const base = global.document.createElement("base");
      base.href = siteRootUrl().toString();
      global.document.head.prepend(base);
    }
    if (updateHistory) global.history.pushState(null, "", next);
    applyDocumentTitle();
    applyStaticTranslations();
    applyLanguageLinks();
    const alternate = global.document.querySelector(`link[rel="alternate"][hreflang="${locale}"]`);
    if (alternate) {
      global.document.querySelector('link[rel="canonical"]')?.setAttribute("href", alternate.href);
      global.document.querySelector('meta[property="og:url"]')?.setAttribute("content", alternate.href);
    }
    const navigation = global.FR27DashboardNavigation;
    global.document.querySelectorAll("[data-section-family]").forEach(link => {
      const family = link.dataset.sectionFamily;
      const href = navigation?.hub(family);
      if (href) link.href = href;
      const label = link.querySelector(".fr27-section-label");
      if (label) label.textContent = t(`navigation.hub_${family}`).replace(/\s*\u2192$/, "");
    });
    const trigger = global.document.querySelector(
      '[data-fr27-section-launcher] [aria-controls="fr27-section-menu"]'
    );
    trigger?.setAttribute("aria-label", locale === "fr" ? "Explorer les sections" : "Explore sections");
    // Synchronous presentation update: pending loaders read the current locale
    // at commit time and never carry an obsolete FR/EN document with them.
    global.document.dispatchEvent(new CustomEvent("fr27:locale", {detail: {locale}}));
  };

  const applyBootLocalization = () => {
    applyStaticTranslations();
    applyLanguageLinks();
    if (isDashboard()) {
      global.document.addEventListener("click", event => {
        const link = event.target.closest?.("[data-fr27-language]");
        if (!link || event.defaultPrevented || event.button !== 0 ||
            event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        const target = normalizeLocale(link.getAttribute("data-fr27-language"));
        if (target !== locale) setDashboardLocale(target);
      });
      global.addEventListener("popstate", () => {
        const target = /\/en\/?$/.test(global.location.pathname) ? "en" : "fr";
        if (target !== locale) setDashboardLocale(target, false);
      });
    }

    global.addEventListener("hashchange", () => {
      global.setTimeout(applyLanguageLinks, 0);
    });
  };

  const api = Object.freeze({
    get locale() { return locale; },
    get localeTag() { return localeTag; },
    fallbackLocale,
    t,
    formatDate,
    formatNumber,
    formatPercent,
    pluralCategory,
    siteUrl,
    buildLocaleUrl,
    applyDocumentTitle,
    applyStaticTranslations
  });

  global.FR27I18N = api;
  applyDocumentTitle();

  if (global.document) {
    if (global.document.readyState === "loading") {
      global.document.addEventListener(
        "DOMContentLoaded",
        applyBootLocalization,
        { once: true }
      );
    } else {
      applyBootLocalization();
    }
  }
})(window);
