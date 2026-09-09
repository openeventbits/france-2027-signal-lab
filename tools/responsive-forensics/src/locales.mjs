export const localeRegistry = Object.freeze({
  fr: Object.freeze({ locale: "fr", canonical: true }),
  en: Object.freeze({ locale: "en", canonical: false })
});

export const defaultAuditLocales = Object.freeze(["fr"]);

export function selectLocales(raw = "") {
  const locales = raw
    ? [...new Set(String(raw).split(",").map(value => value.trim().toLowerCase()).filter(Boolean))]
    : [...defaultAuditLocales];
  const unsupported = locales.filter(locale => !localeRegistry[locale]);
  if (unsupported.length) {
    throw new Error(`Unsupported locale(s): ${unsupported.join(", ")}. Supported locales: ${Object.keys(localeRegistry).join(", ")}`);
  }
  if (!locales.length) throw new Error("--locale requires at least one locale");
  return locales;
}

export function localeUrl(baseUrl, locale) {
  if (!localeRegistry[locale]) throw new Error(`Unsupported locale: ${locale}`);
  const url = new URL("/", baseUrl);
  if (locale === "en") url.searchParams.set("lang", "en");
  return url.toString();
}
