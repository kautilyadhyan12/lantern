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
  // The evidence board: select cards and strings to read their evidence in the case
  // notes, drag cards, zoom and pan, and tidy up. Only SVG attributes change (CSP-safe).
  const svg = document.querySelector("svg.board");
  if (!svg) return;
  const panel = document.getElementById("case-notes");
  const notes = document.getElementById("case-notes-body");
  const clearButton = document.getElementById("case-clear");
  const cards = new Map([...svg.querySelectorAll(".card")].map((card) => [card.dataset.ref, card]));
  const pins = new Map([...svg.querySelectorAll(".pin")].map((pin) => [pin.dataset.ref, pin]));
  const strings = [...svg.querySelectorAll("a.string")];
  const home = new Map([...cards].map(([ref, card]) => [ref, [card.dataset.x, card.dataset.y]]));
  const full = svg.viewBox.baseVal;
  const start = { x: full.x, y: full.y, width: full.width, height: full.height };
  let view = { ...start };
  const showView = () =>
    svg.setAttribute("viewBox", `${view.x} ${view.y} ${view.width} ${view.height}`);

  const pinOf = (card) => [Number(card.dataset.x), Number(card.dataset.y) - 26];
  const restring = (string) => {
    const [x1, y1] = pinOf(cards.get(string.dataset.from));
    const [x2, y2] = pinOf(cards.get(string.dataset.to));
    const mx = (x1 + x2) / 2;
    const my = (y1 + y2) / 2 + 0.12 * Math.hypot(x2 - x1, y2 - y1) + 8;
    string.querySelectorAll("path").forEach((path) =>
      path.setAttribute("d", `M${x1},${y1} Q${mx},${my} ${x2},${y2}`),
    );
    const label = string.querySelector("text");
    label.setAttribute("x", 0.25 * x1 + 0.5 * mx + 0.25 * x2);
    label.setAttribute("y", 0.25 * y1 + 0.5 * my + 0.25 * y2);
  };
  const moveCard = (card, x, y) => {
    card.dataset.x = x;
    card.dataset.y = y;
    card.setAttribute("transform", `translate(${x} ${y}) rotate(${card.dataset.tilt})`);
    const pin = pins.get(card.dataset.ref);
    pin.setAttribute("cx", x);
    pin.setAttribute("cy", y - 26);
    strings.filter((s) => s.dataset.from === card.dataset.ref || s.dataset.to === card.dataset.ref).forEach(restring);
  };
  const attached = (ref) => strings.filter((s) => s.dataset.from === ref || s.dataset.to === ref);

  // ---- selection and the case notes ----
  const light = (refs, links) => {
    svg.querySelectorAll(".lit").forEach((item) => item.classList.remove("lit"));
    refs.forEach((ref) => {
      cards.get(ref)?.classList.add("lit");
      pins.get(ref)?.classList.add("lit");
    });
    links.forEach((string) => string.classList.add("lit"));
    svg.classList.toggle("focus", refs.length > 0);
  };
  const show = (ref) => {
    const template = document.getElementById(`note-${ref}`);
    if (!template) return;
    notes.replaceChildren(template.content.cloneNode(true));
    panel.hidden = false;
    panel.scrollTop = 0;
  };
  const selectCard = (ref) => {
    const links = attached(ref);
    const ends = links.flatMap((s) => [s.dataset.from, s.dataset.to]);
    light([ref, ...ends], links);
    cards.get(ref).parentNode.appendChild(cards.get(ref));
    show(ref);
  };
  const selectString = (string) => {
    light([string.dataset.from, string.dataset.to], [string]);
    show(string.dataset.ref);
  };
  const clear = () => {
    light([], []);
    notes.replaceChildren();
    panel.hidden = true;
  };
  clearButton.addEventListener("click", clear);
  notes.addEventListener("click", (event) => {
    const button = event.target.closest(".note-link");
    if (!button) return;
    const string = strings.find((s) => s.dataset.ref === button.dataset.link);
    if (string) selectString(string);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !document.querySelector("dialog[open]")) clear();
  });

  // ---- hover: a card's strings stand out ----
  svg.addEventListener("pointerover", (event) => {
    const card = event.target.closest(".card");
    if (card) attached(card.dataset.ref).forEach((s) => s.classList.add("hover"));
  });
  svg.addEventListener("pointerout", (event) => {
    const card = event.target.closest(".card");
    if (card) attached(card.dataset.ref).forEach((s) => s.classList.remove("hover"));
  });

  // ---- strings: select instead of jumping down the page ----
  strings.forEach((string) =>
    string.addEventListener("click", (event) => {
      event.preventDefault();
      selectString(string);
    }),
  );

  // ---- dragging cards, panning the cork; a short press is a click ----
  const point = (event) => {
    const p = svg.createSVGPoint();
    p.x = event.clientX;
    p.y = event.clientY;
    return p.matrixTransform(svg.getScreenCTM().inverse());
  };
  let held = null;
  svg.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || event.target.closest("a.string")) return;
    const card = event.target.closest(".card");
    const p = point(event);
    held = card
      ? { card, dx: p.x - Number(card.dataset.x), dy: p.y - Number(card.dataset.y) }
      : { pan: true, x: event.clientX, y: event.clientY, view: { ...view } };
    held.startX = event.clientX;
    held.startY = event.clientY;
    held.moved = false;
    svg.setPointerCapture(event.pointerId);
  });
  svg.addEventListener("pointermove", (event) => {
    if (!held) return;
    if (Math.hypot(event.clientX - held.startX, event.clientY - held.startY) > 4) held.moved = true;
    if (!held.moved) return;
    if (held.pan) {
      const scale = view.width / svg.getBoundingClientRect().width;
      view.x = held.view.x - (event.clientX - held.x) * scale;
      view.y = held.view.y - (event.clientY - held.y) * scale;
      showView();
      svg.classList.add("panning");
      return;
    }
    held.card.classList.add("lifted");
    const p = point(event);
    const x = Math.min(Math.max(p.x - held.dx, 90), start.width - 90);
    const y = Math.min(Math.max(p.y - held.dy, 50), start.height - 40);
    moveCard(held.card, x, y);
  });
  const drop = () => {
    if (!held) return;
    if (held.card && !held.moved) selectCard(held.card.dataset.ref);
    else if (held.pan && !held.moved) clear(); // a click on bare cork clears the selection
    held.card?.classList.remove("lifted");
    svg.classList.remove("panning");
    held = null;
  };
  svg.addEventListener("pointerup", drop);
  svg.addEventListener("pointercancel", drop);

  // ---- zoom, fit and tidy up ----
  const zoom = (factor) => {
    const width = Math.min(Math.max(view.width * factor, start.width / 4), start.width);
    const height = (width * start.height) / start.width;
    view = {
      x: view.x + (view.width - width) / 2,
      y: view.y + (view.height - height) / 2,
      width,
      height,
    };
    showView();
  };
  document.querySelectorAll("[data-board]").forEach((button) =>
    button.addEventListener("click", () => {
      const action = button.dataset.board;
      if (action === "zoom-in") zoom(0.75);
      if (action === "zoom-out") zoom(1 / 0.75);
      if (action === "fit") {
        view = { ...start };
        showView();
      }
      if (action === "tidy") {
        home.forEach(([x, y], ref) => moveCard(cards.get(ref), Number(x), Number(y)));
        view = { ...start };
        showView();
      }
    }),
  );
  svg.addEventListener(
    "wheel",
    (event) => {
      if (!event.ctrlKey) return; // plain scrolling still scrolls the page
      event.preventDefault();
      zoom(event.deltaY < 0 ? 0.85 : 1 / 0.85);
    },
    { passive: false },
  );
}

startForm();
startContinue();
startMapFilters();
startBoard();
startPolling();
startCitations();
