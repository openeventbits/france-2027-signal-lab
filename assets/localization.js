(function (global) {
  "use strict";

  const documentElement =
    global.document && global.document.documentElement;
  const catalogs = global.FR27_LOCALES || Object.create(null);
  const fallbackLocale = "en";

  const normalizeLocale = value => {
    const normalized = String(value || fallbackLocale)
      .trim()
      .toLowerCase();

    return normalized.indexOf("fr") === 0 ? "fr" : "en";
  };

  const locale = normalizeLocale(
    documentElement &&
      (documentElement.dataset.locale || documentElement.lang)
  );

  const localeTag = locale === "fr" ? "fr-FR" : "en-GB";

  const isDevelopment = Boolean(
    global.location &&
      (global.location.protocol === "file:" ||
        /^(localhost|127\.0\.0\.1)$/.test(
          global.location.hostname
        ))
  );

  const activeCatalog =
    catalogs[locale] || catalogs[fallbackLocale];
  const fallbackCatalog =
    catalogs[fallbackLocale] || Object.create(null);

  const messageFor = key => {
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

  const t = (key, parameters) => {
    const safeParameters =
      parameters || Object.create(null);
    const pluralized = applyPluralRules(
      String(messageFor(key)),
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

  const siteRootUrl = () =>
    new URL(siteRoot, global.document.baseURI);

  const siteUrl = path =>
    new URL(String(path || ""), siteRootUrl()).toString();

  const buildLocaleUrl = targetLocale => {
    const target = normalizeLocale(targetLocale);
    const next = new URL(global.location.href);
    const root = siteRootUrl();
    const rootPath = root.pathname.replace(/\/?$/, "/");
    let relativePath = next.pathname;

    if (relativePath.indexOf(rootPath) === 0) {
      relativePath = relativePath.slice(rootPath.length);
    }

    relativePath = relativePath
      .replace(/^\/+/, "")
      .replace(/^fr\//, "");

    next.pathname =
      target === "fr"
        ? rootPath + "fr/" + relativePath
        : rootPath + relativePath;

    return next.toString();
  };

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

  const fallbackMessageFor = key => {
    const normalizedKey = String(key || "");

    return Object.prototype.hasOwnProperty.call(
      fallbackCatalog,
      normalizedKey
    )
      ? String(fallbackCatalog[normalizedKey])
      : null;
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
      const fallback = fallbackMessageFor(key);
      const current = String(element.textContent || "").trim();

      if (fallback !== null && current === fallback.trim()) {
        element.textContent = t(key);
      }
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
      const fallback = fallbackMessageFor(key);
      const current = element.getAttribute("aria-label");

      if (fallback !== null && current === fallback) {
        element.setAttribute("aria-label", t(key));
      }
    });
  };

  const applyStaticTranslations = () => {
    applyTextTranslations();
    applyAttributeTranslations();
  };

  const api = Object.freeze({
    locale,
    localeTag,
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
        applyStaticTranslations,
        { once: true }
      );
    } else {
      applyStaticTranslations();
    }
  }
})(window);
