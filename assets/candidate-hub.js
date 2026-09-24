(() => {
  "use strict";

  const search = document.querySelector("[data-candidate-search]");
  const status = document.querySelector("[data-candidate-status]");
  const count = document.querySelector("[data-candidate-visible-count]");
  const cards = Array.from(document.querySelectorAll("[data-candidate-card]"));

  if (!search || !status || !count || !cards.length) return;

  const normalize = (value) => value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase();

  const update = () => {
    const query = normalize(search.value.trim());
    const selectedStatus = status.value;
    let visible = 0;

    cards.forEach((card) => {
      const matchesName = !query || normalize(card.dataset.candidateName || "").includes(query);
      const matchesStatus = !selectedStatus || card.dataset.candidateStatus === selectedStatus;
      const show = matchesName && matchesStatus;
      card.hidden = !show;
      if (show) visible += 1;
    });

    count.textContent = String(visible);
  };

  search.addEventListener("input", update);
  status.addEventListener("change", update);
})();
