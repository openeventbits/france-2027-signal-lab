const styleProperties = [
  "display", "visibility", "position", "width", "height", "min-width", "max-width",
  "min-height", "max-height", "flex-direction", "flex-wrap", "align-items",
  "justify-content", "grid-template-columns", "grid-template-rows", "gap",
  "overflow", "overflow-x", "overflow-y"
];

export const approvedLocalScrollerSelectors = [
  ".hybrid-agenda-v6-matrix-wrap",
  ".hybrid-agenda-v6-scroll",
  ".hybrid-runoff-history",
  ".runoff-body-scroll",
  ".race-scroll-shell",
  ".hybrid-events-ops-rail"
];

function rounded(value) {
  return Math.round(value * 100) / 100;
}

export async function waitForDashboard(page) {
  await page.waitForLoadState("domcontentloaded");
  await page.locator("header.masthead").waitFor({ state: "attached" });
  await Promise.all([
    page.locator(".hybrid-workspace").waitFor({ state: "attached", timeout: 20_000 }),
    page.locator(".top-media-dashboard").waitFor({ state: "attached", timeout: 20_000 }),
    page.locator(".hybrid-events-workspace").waitFor({ state: "attached", timeout: 20_000 }),
    page.locator(".candidate-signals-workspace").waitFor({ state: "attached", timeout: 20_000 })
  ]).catch(() => {});
  await page.waitForTimeout(180);
}

export async function activateComponent(page, definition) {
  if (!definition.hash) return;
  await page.evaluate(hash => {
    if (location.hash === hash) window.dispatchEvent(new HashChangeEvent("hashchange"));
    else location.hash = hash;
  }, definition.hash);
  await page.waitForTimeout(80);
}

export async function collectComponent(page, name, definition, viewport, requestedLocale, consoleErrors = []) {
  return page.evaluate(({ name, definition, viewport, requestedLocale, styleProperties, approvedLocalScrollerSelectors, consoleErrors }) => {
    const root = document.querySelector(definition.selector);
    const visible = element => {
      if (!element || element.hidden) return false;
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity) !== 0 && rect.width > 0 && rect.height > 0;
    };
    const geometryState = element => {
      const rect = element.getBoundingClientRect();
      const viewportIntersection = rect.right > 0 && rect.bottom > 0 && rect.left < innerWidth && rect.top < innerHeight;
      const insideViewport = rect.left >= -1 && rect.right <= innerWidth + 1 && rect.top >= -1 && rect.bottom <= innerHeight + 1;
      let clippedByAncestor = false;
      for (let ancestor = element.parentElement; ancestor && ancestor !== document.body; ancestor = ancestor.parentElement) {
        const style = getComputedStyle(ancestor);
        if (!/(hidden|clip)/.test(`${style.overflow} ${style.overflowX} ${style.overflowY}`)) continue;
        const bounds = ancestor.getBoundingClientRect();
        if (rect.left < bounds.left - 1 || rect.right > bounds.right + 1 || rect.top < bounds.top - 1 || rect.bottom > bounds.bottom + 1) {
          clippedByAncestor = true;
          break;
        }
      }
      return { viewportIntersection, insideViewport, clippedByAncestor };
    };
    const lineCount = element => {
      if (!element || !element.textContent.trim()) return 0;
      const range = document.createRange();
      range.selectNodeContents(element);
      const tops = [...range.getClientRects()].filter(rect => rect.width > 0 && rect.height > 0).map(rect => Math.round(rect.top));
      return new Set(tops).size;
    };
    const snapshot = (element, selector) => {
      if (!element) return { selector, present: false };
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      const styles = Object.fromEntries(styleProperties.map(property => [property, style.getPropertyValue(property)]));
      const localOverflow = element.scrollWidth > element.clientWidth + 1 || element.scrollHeight > element.clientHeight + 1;
      return {
        selector,
        present: true,
        visible: visible(element),
        rect: { x: Math.round(rect.x * 100) / 100, y: Math.round(rect.y * 100) / 100, width: Math.round(rect.width * 100) / 100, height: Math.round(rect.height * 100) / 100, top: Math.round(rect.top * 100) / 100, right: Math.round(rect.right * 100) / 100, bottom: Math.round(rect.bottom * 100) / 100, left: Math.round(rect.left * 100) / 100 },
        styles,
        textLines: lineCount(element),
        geometry: geometryState(element),
        state: { ariaCurrent: element.getAttribute("aria-current"), ariaSelected: element.getAttribute("aria-selected") },
        scroll: { scrollWidth: element.scrollWidth, clientWidth: element.clientWidth, scrollHeight: element.scrollHeight, clientHeight: element.clientHeight },
        localOverflow: localOverflow ? (approvedLocalScrollerSelectors.some(candidate => element.matches(candidate)) ? "approved-local" : "observed") : "none"
      };
    };
    const requiredControlDefinitions = (definition.requiredControls || []).filter(control =>
      (control.minWidth == null || viewport.width >= control.minWidth) &&
      (control.maxWidth == null || viewport.width <= control.maxWidth)
    );
    const requiredControls = requiredControlDefinitions.map(control => {
      const element = document.querySelector(control.selector);
      return {
        selector: control.selector, label: control.label, present: Boolean(element), visible: visible(element),
        disabled: Boolean(element?.disabled), replacement: control.replacement || null,
        requireViewport: Boolean(control.requireViewport), geometry: element ? geometryState(element) : null,
        rect: element ? snapshot(element, control.selector).rect : null,
        ariaCurrent: element?.getAttribute("aria-current") || null
      };
    });
    const selected = [];
    const stateValue = element => element ? (element.id || element.getAttribute("data-top-media-tab") || element.getAttribute("data-candidate-signals-candidate") || element.getAttribute("data-agenda-topic") || element.getAttribute("data-issue-topic") || element.getAttribute("data-hybrid-event-id") || element.textContent.trim().slice(0, 80)) : null;
    if (definition.state?.tabs) {
      selected.push({ selector: definition.state.tabs, value: stateValue(document.querySelector(`${definition.state.tabs}[aria-selected='true']`)) });
    }
    for (const selector of definition.state?.selects || []) {
      const element = document.querySelector(selector);
      selected.push({ selector, value: element ? element.value : null });
    }
    if (definition.state?.pressed) {
      selected.push({ selector: definition.state.pressed, value: stateValue(document.querySelector(`${definition.state.pressed}[aria-pressed='true'], ${definition.state.pressed}.is-selected, ${definition.state.pressed}.active`)) });
    }
    const documentElement = document.documentElement;
    const body = document.body;
    const documentOverflow = Math.max(documentElement.scrollWidth, body?.scrollWidth || 0) > documentElement.clientWidth + 1;
    const rootShot = snapshot(root, definition.selector);
    const probes = (definition.probes || []).map(selector => snapshot(root?.querySelector(selector) || document.querySelector(selector), selector));
    const hardFailures = [];
    const activeLanguageLinks = [...document.querySelectorAll("[data-fr27-language][aria-current='page']")].map(element => element.getAttribute("data-fr27-language"));
    const runtimeLocale = globalThis.FR27I18N?.locale || null;
    const expectedLocalePath = requestedLocale === "en" ? "/en/" : "/";
    const localeVerification = {
      requested: requestedLocale,
      resolved: {
        documentLanguage: documentElement.lang || null,
        runtimeLocale,
        runtimeLocaleTag: globalThis.FR27I18N?.localeTag || null,
        activeLanguageLinks,
        url: location.href,
        pathname: location.pathname,
        search: location.search,
        searchParameters: Object.fromEntries(new URL(location.href).searchParams)
      },
      matchesRequested: documentElement.lang === requestedLocale && runtimeLocale === requestedLocale &&
        activeLanguageLinks.length === 1 && activeLanguageLinks[0] === requestedLocale &&
        location.pathname === expectedLocalePath
    };
    if (!localeVerification.matchesRequested) hardFailures.push({ type: "requested-locale-not-resolved", localeVerification });
    if (documentOverflow) hardFailures.push({ type: "document-horizontal-overflow", scrollWidth: Math.max(documentElement.scrollWidth, body?.scrollWidth || 0), clientWidth: documentElement.clientWidth });
    const activeResponsiveTiers = ["fr27-tier2-active", "fr27-tier3-active"].filter(className => documentElement.classList.contains(className));
    if (activeResponsiveTiers.length > 1) hardFailures.push({ type: "tier-controller-overlap", activeResponsiveTiers });
    for (const control of requiredControls) {
      if (!control.present || !control.visible || control.disabled) hardFailures.push({ type: "required-control-unavailable", ...control });
      if (control.present && control.visible && control.requireViewport && (!control.geometry.viewportIntersection || !control.geometry.insideViewport)) {
        hardFailures.push({ type: "required-control-outside-viewport", ...control });
      }
      if (control.present && control.visible && control.requireViewport && control.geometry.clippedByAncestor) {
        hardFailures.push({ type: "required-control-clipped", ...control });
      }
    }
    const footer = document.querySelector("#method-disclosure");
    const footerRect = footer?.getBoundingClientRect();
    if (footer && getComputedStyle(footer).position === "fixed" && visible(footer)) {
      for (const control of requiredControlDefinitions) {
        const element = document.querySelector(control.selector);
        if (!element || !visible(element) || footer.contains(element)) continue;
        const rect = element.getBoundingClientRect();
        const inViewport = rect.bottom > 0 && rect.top < innerHeight;
        const overlapsFooter = footerRect && rect.bottom > footerRect.top && rect.top < footerRect.bottom;
        if (inViewport && overlapsFooter && footer.contains(document.elementFromPoint(Math.max(0, Math.min(innerWidth - 1, rect.left + rect.width / 2)), Math.max(0, Math.min(innerHeight - 1, rect.top + rect.height / 2))))) {
          hardFailures.push({ type: "fixed-footer-occlusion", selector: control.selector, label: control.label });
        }
      }
    }
    if (consoleErrors.length) hardFailures.push({ type: "console-errors", messages: consoleErrors });
    const signatureSource = [rootShot, ...probes].map(item => ({ selector: item.selector, present: item.present, visible: item.visible, rect: item.rect ? { width: item.rect.width, height: item.rect.height } : null, styles: item.styles || null }));
    return {
      component: name,
      locale: requestedLocale,
      localeVerification,
      viewport,
      tier: viewport.width >= 1399 ? "tier-1" : viewport.width >= 1024 ? "tier-2" : "tier-3",
      tierClasses: [...documentElement.classList].filter(value => /tier[123]/i.test(value)),
      root: rootShot,
      probes,
      requiredControls,
      selectedState: selected,
      document: { scrollWidth: Math.max(documentElement.scrollWidth, body?.scrollWidth || 0), clientWidth: documentElement.clientWidth, scrollHeight: Math.max(documentElement.scrollHeight, body?.scrollHeight || 0), clientHeight: documentElement.clientHeight, horizontalOverflow: documentOverflow },
      consoleErrors,
      hardFailures,
      signature: JSON.stringify(signatureSource)
    };
  }, { name, definition, viewport, requestedLocale, styleProperties, approvedLocalScrollerSelectors, consoleErrors });
}

const structuralProperties = new Set(["display", "visibility", "position", "flex-direction", "flex-wrap", "align-items", "justify-content", "grid-template-columns", "grid-template-rows", "overflow", "overflow-x", "overflow-y", "min-height", "max-height"]);

function structuralValue(property, value) {
  if (property === "grid-template-columns" || property === "grid-template-rows") {
    return value.replace(/-?\d+(?:\.\d+)?px/g, "<px>").replace(/\s+/g, " ").trim();
  }
  return value;
}

export function compareSnapshots(previous, current) {
  const changes = [];
  const before = new Map([previous.root, ...previous.probes].map(item => [item.selector, item]));
  for (const after of [current.root, ...current.probes]) {
    const prior = before.get(after.selector);
    if (!prior) continue;
    if (prior.present !== after.present || prior.visible !== after.visible) {
      changes.push({ selector: after.selector, property: "visibility/presence", previous: `${prior.present}/${prior.visible}`, current: `${after.present}/${after.visible}`, abrupt: true });
      continue;
    }
    if (!prior.present || !after.present) continue;
    for (const property of structuralProperties) {
      if (structuralValue(property, prior.styles[property]) !== structuralValue(property, after.styles[property])) changes.push({ selector: after.selector, property, previous: prior.styles[property], current: after.styles[property], abrupt: true });
    }
    for (const dimension of ["height"]) {
      const oldValue = prior.rect[dimension];
      const newValue = after.rect[dimension];
      const delta = Math.abs(newValue - oldValue);
      const ratio = Math.max(oldValue, newValue) / Math.max(1, Math.min(oldValue, newValue));
      if (delta >= 120 || (delta >= 40 && ratio >= 1.5)) changes.push({ selector: after.selector, property: dimension, previous: oldValue, current: newValue, delta: rounded(delta), ratio: rounded(ratio), abrupt: true });
    }
  }
  const previousControls = new Map(previous.requiredControls.map(item => [item.selector, item]));
  for (const control of current.requiredControls) {
    const prior = previousControls.get(control.selector);
    if (prior && prior.visible !== control.visible) changes.push({ selector: control.selector, property: "required-control-visibility", previous: prior.visible, current: control.visible, abrupt: true });
  }
  const previousState = new Map(previous.selectedState.map(item => [item.selector, item.value]));
  for (const state of current.selectedState) {
    if (previousState.has(state.selector) && previousState.get(state.selector) !== state.value) {
      changes.push({ selector: state.selector, property: "selected-state", previous: previousState.get(state.selector), current: state.value, abrupt: true });
    }
  }
  return changes;
}

export function compareLocaleSnapshots(frSample, enSample) {
  const differences = [];
  const frItems = new Map([frSample.root, ...frSample.probes].map(item => [item.selector, item]));
  for (const enItem of [enSample.root, ...enSample.probes]) {
    const frItem = frItems.get(enItem.selector);
    if (!frItem) continue;
    if (frItem.present !== enItem.present || frItem.visible !== enItem.visible) {
      differences.push({ selector: enItem.selector, property: "visibility/presence", fr: `${frItem.present}/${frItem.visible}`, en: `${enItem.present}/${enItem.visible}` });
      continue;
    }
    if (!frItem.present || !enItem.present) continue;
    for (const dimension of ["width", "height"]) {
      const delta = rounded(frItem.rect[dimension] - enItem.rect[dimension]);
      if (Math.abs(delta) >= 1) differences.push({ selector: enItem.selector, property: dimension, fr: frItem.rect[dimension], en: enItem.rect[dimension], delta });
    }
    if (frItem.textLines !== enItem.textLines) differences.push({ selector: enItem.selector, property: "text-lines", fr: frItem.textLines, en: enItem.textLines, delta: frItem.textLines - enItem.textLines });
    for (const metric of ["scrollWidth", "clientWidth", "scrollHeight", "clientHeight"]) {
      if (frItem.scroll[metric] !== enItem.scroll[metric]) differences.push({ selector: enItem.selector, property: metric, fr: frItem.scroll[metric], en: enItem.scroll[metric], delta: frItem.scroll[metric] - enItem.scroll[metric] });
    }
    for (const property of structuralProperties) {
      if (structuralValue(property, frItem.styles[property]) !== structuralValue(property, enItem.styles[property])) {
        differences.push({ selector: enItem.selector, property, fr: frItem.styles[property], en: enItem.styles[property] });
      }
    }
  }
  const frControls = new Map(frSample.requiredControls.map(control => [control.selector, control]));
  for (const enControl of enSample.requiredControls) {
    const frControl = frControls.get(enControl.selector);
    if (frControl && (frControl.visible !== enControl.visible || frControl.present !== enControl.present)) {
      differences.push({ selector: enControl.selector, property: "required-control-availability", fr: `${frControl.present}/${frControl.visible}`, en: `${enControl.present}/${enControl.visible}` });
    }
  }
  return differences;
}

export async function cdpMatchedRules(session, selector, properties, stylesheets) {
  if (!properties.length) return [];
  try {
    const { root } = await session.send("DOM.getDocument", { depth: 0 });
    const { nodeId } = await session.send("DOM.querySelector", { nodeId: root.nodeId, selector });
    if (!nodeId) return [];
    const matched = await session.send("CSS.getMatchedStylesForNode", { nodeId });
    const results = [];
    for (const entry of matched.matchedCSSRules || []) {
      const declarations = (entry.rule?.style?.cssProperties || []).filter(item => properties.includes(item.name) && item.value);
      if (!declarations.length) continue;
      const styleSheetId = entry.rule.styleSheetId;
      results.push({
        selector: entry.rule.selectorList?.text || "",
        source: stylesheets.get(styleSheetId)?.sourceURL || null,
        line: entry.rule.style?.range ? entry.rule.style.range.startLine + 1 : null,
        media: (entry.rule.media || []).map(item => item.text).filter(Boolean),
        declarations: declarations.map(item => ({ property: item.name, value: item.value, important: Boolean(item.important) }))
      });
    }
    return results.slice(-12);
  } catch {
    return [];
  }
}
