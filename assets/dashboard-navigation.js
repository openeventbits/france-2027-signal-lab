(() => {
  "use strict";
  const element = document.getElementById("published-dashboard-navigation");
  if (!element) return;
  const routes = JSON.parse(element.textContent);
  const language = () => (globalThis.FR27I18N?.localeTag ||
    document.documentElement.lang).toLowerCase().startsWith("en") ? "en" : "fr";
  const hub = family => routes.hubs[family]?.[language()] || "";
  const detail = (family, id) => routes[family]?.[id]?.[language()] || "";
  const poll = eventId => {
    const association = Object.hasOwn(routes.events, eventId) ? routes.events[eventId] : null;
    return association
      ? `${routes.waves[association[0]][language()]}#scenario-${association[1]}`
      : hub("polls");
  };
  window.FR27DashboardNavigation = Object.freeze({hub, detail, poll});
})();
