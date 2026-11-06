"use strict";

function startForm() {
  const form = document.getElementById("ask");
  if (!form) return;
  const error = document.getElementById("ask-error");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button");
    const brief = document.getElementById("brief").value.trim();
    const choice = form.querySelector('input[name="depth"]:checked');
    const depth = choice ? choice.value : "deep";
    error.hidden = true;
    button.disabled = true;
    try {
      const response = await fetch("/api/investigations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ brief, depth }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not start the investigation.");
      window.location.href = `/investigations/${data.id}`;
    } catch (problem) {
      error.textContent = problem.message;
      error.hidden = false;
      button.disabled = false;
    }
  });
}

function startPolling() {
  const id = document.body.dataset.id;
  const status = document.body.dataset.status;
  if (!id || !["queued", "running"].includes(status)) return;
  const steps = document.getElementById("steps");
  const counts = document.getElementById("counts");
  const tick = async () => {
    try {
      const response = await fetch(`/api/investigations/${id}`, { cache: "no-store" });
      const data = await response.json();
      if (!["queued", "running"].includes(data.status)) {
        window.location.reload();
        return;
      }
      steps.replaceChildren(
        ...data.steps.map((text) => {
          const item = document.createElement("li");
          item.textContent = text;
          return item;
        }),
      );
      const c = data.counts;
      counts.textContent =
        `${c.questions} key questions · ${c.sources} pages saved · ${c.claims} claims`;
    } catch (_) {
      /* The next tick retries. */
    }
    window.setTimeout(tick, 2000);
  };
  window.setTimeout(tick, 1500);
}

function startCitations() {
  const dialog = document.getElementById("card");
  if (!dialog) return;
  const body = document.getElementById("card-body");
  document.addEventListener("click", (event) => {
    const button = event.target.closest(".cite");
    if (!button) return;
    const template = document.getElementById(`card-${button.dataset.ref}`);
    if (!template) return;
    body.replaceChildren(template.content.cloneNode(true));
    dialog.showModal();
  });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
}

function startContinue() {
  const button = document.getElementById("continue");
  if (!button) return;
  const error = document.getElementById("continue-error");
  button.addEventListener("click", async () => {
    button.disabled = true;
    error.hidden = true;
    try {
      const response = await fetch(`/api/investigations/${button.dataset.id}/continue`, {
        method: "POST",
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not continue the investigation.");
      window.location.reload();
    } catch (problem) {
      error.textContent = problem.message;
      error.hidden = false;
      button.disabled = false;
    }
  });
}

function startMapFilters() {
  const filters = document.getElementById("map-filters");
  if (!filters) return;
  const apply = () => {
    const off = (attribute) =>
      new Set(
        [...filters.querySelectorAll(`input[${attribute}]`)]
          .filter((box) => !box.checked)
          .map((box) => box.getAttribute(attribute)),
      );
    const kinds = off("data-kind");
    const statuses = off("data-status");
    document.querySelectorAll(".linkmap .node").forEach((node) => {
      node.classList.toggle("off", kinds.has(node.dataset.kind));
    });
    document.querySelectorAll(".linkmap [data-kinds]").forEach((item) => {
      const hidden =
        statuses.has(item.dataset.status) ||
        item.dataset.kinds.split(" ").some((kind) => kinds.has(kind));
      item.classList.toggle("off", hidden);
    });
  };
  filters.addEventListener("change", apply);
}

startForm();
startContinue();
startMapFilters();
startPolling();
startCitations();
