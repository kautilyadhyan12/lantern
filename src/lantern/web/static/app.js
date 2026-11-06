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

function startBoard() {
  // Drag cards on the evidence board; their strings and pins follow.
  const svg = document.querySelector("svg.board");
  if (!svg) return;
  const cards = new Map([...svg.querySelectorAll(".card")].map((card) => [card.dataset.ref, card]));
  const pins = new Map([...svg.querySelectorAll(".pin")].map((pin) => [pin.dataset.ref, pin]));
  const strings = [...svg.querySelectorAll("a.string")];
  const box = svg.viewBox.baseVal;
  const pinOf = (card) => [Number(card.dataset.x), Number(card.dataset.y) - 26];
  const restring = (string) => {
    const [x1, y1] = pinOf(cards.get(string.dataset.from));
    const [x2, y2] = pinOf(cards.get(string.dataset.to));
    const mx = (x1 + x2) / 2;
    const my = (y1 + y2) / 2 + 0.12 * Math.hypot(x2 - x1, y2 - y1) + 8;
    string.querySelector("path").setAttribute("d", `M${x1},${y1} Q${mx},${my} ${x2},${y2}`);
    const label = string.querySelector("text");
    label.setAttribute("x", 0.25 * x1 + 0.5 * mx + 0.25 * x2);
    label.setAttribute("y", 0.25 * y1 + 0.5 * my + 0.25 * y2);
  };
  const point = (event) => {
    const p = svg.createSVGPoint();
    p.x = event.clientX;
    p.y = event.clientY;
    return p.matrixTransform(svg.getScreenCTM().inverse());
  };
  let held = null;
  svg.addEventListener("pointerdown", (event) => {
    const card = event.target.closest(".card");
    if (!card) return;
    const p = point(event);
    held = { card, dx: p.x - Number(card.dataset.x), dy: p.y - Number(card.dataset.y) };
    card.parentNode.appendChild(card); // the card being moved goes on top
    card.classList.add("lifted");
    svg.setPointerCapture(event.pointerId);
  });
  svg.addEventListener("pointermove", (event) => {
    if (!held) return;
    const p = point(event);
    const { card } = held;
    const x = Math.min(Math.max(p.x - held.dx, 90), box.width - 90);
    const y = Math.min(Math.max(p.y - held.dy, 50), box.height - 40);
    card.dataset.x = x;
    card.dataset.y = y;
    card.setAttribute("transform", `translate(${x} ${y}) rotate(${card.dataset.tilt})`);
    const pin = pins.get(card.dataset.ref);
    pin.setAttribute("cx", x);
    pin.setAttribute("cy", y - 26);
    strings
      .filter((s) => s.dataset.from === card.dataset.ref || s.dataset.to === card.dataset.ref)
      .forEach(restring);
  });
  const drop = () => {
    if (held) held.card.classList.remove("lifted");
    held = null;
  };
  svg.addEventListener("pointerup", drop);
  svg.addEventListener("pointercancel", drop);
}

startForm();
startContinue();
startMapFilters();
startBoard();
startPolling();
startCitations();
