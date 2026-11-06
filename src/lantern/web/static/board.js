"use strict";

// The evidence board: cards pinned to cork, joined by string.
// - Mouse wheel zooms towards the pointer; dragging the cork moves around.
// - Clicking a card or a string opens plain-language case notes; a drag moves a card.
// - Dragging from a pin to another card ties the reader's own (blue) string.
// - A selected string shows end handles: drop one on another card to move the string,
//   or on bare cork to take it down. Evidence strings are never changed: moving one hides
//   it and ties a blue string marked as the reader's guess instead.
// - Positions, the reader's strings and taken-down strings are kept in this browser.
// Only SVG attributes change, so the page's Content-Security-Policy is respected.
(function startBoard() {
  const svg = document.querySelector("svg.board");
  if (!svg) return;
  const NS = "http://www.w3.org/2000/svg";
  const PIN = 26; // a pin sits this far above its card's centre
  const panel = document.getElementById("case-notes");
  const notes = document.getElementById("case-notes-body");
  const closeButton = document.getElementById("case-clear");
  const putBack = document.querySelector('[data-board="put-back"]');
  const mineLayer = svg.querySelector("g.mine");
  const handleLayer = svg.querySelector("g.handles");
  const cards = new Map([...svg.querySelectorAll(".card")].map((c) => [c.dataset.ref, c]));
  const pins = new Map([...svg.querySelectorAll(".pin")].map((p) => [p.dataset.ref, p]));
  const evidence = new Map([...svg.querySelectorAll("a.string")].map((s) => [s.dataset.ref, s]));
  const home = new Map([...cards].map(([ref, c]) => [ref, [Number(c.dataset.x), Number(c.dataset.y)]]));
  const box = svg.viewBox.baseVal;
  const start = { x: box.x, y: box.y, width: box.width, height: box.height };
  let view = { ...start };
  const storeKey = `lantern-board-${svg.dataset.investigation}`;

  // ---- what the reader changed, kept in this browser ----
  const state = { positions: {}, hidden: [], mine: [] };
  try {
    Object.assign(state, JSON.parse(window.localStorage.getItem(storeKey) || "{}"));
  } catch (_) {
    /* storage unavailable or unreadable: start fresh */
  }
  state.hidden = state.hidden.filter((ref) => evidence.has(ref));
  state.mine = state.mine.filter((own) => cards.has(own.from) && cards.has(own.to));
  const save = () => {
    try {
      window.localStorage.setItem(storeKey, JSON.stringify(state));
    } catch (_) {
      /* the board still works; changes just are not remembered */
    }
  };

  // ---- drawing ----
  const pinOf = (ref) => {
    const card = cards.get(ref);
    return [Number(card.dataset.x), Number(card.dataset.y) - PIN];
  };
  const curve = ([x1, y1], [x2, y2]) => {
    const mx = (x1 + x2) / 2;
    const my = (y1 + y2) / 2 + 0.12 * Math.hypot(x2 - x1, y2 - y1) + 8;
    return {
      d: `M${x1},${y1} Q${mx},${my} ${x2},${y2}`,
      label: [0.25 * x1 + 0.5 * mx + 0.25 * x2, 0.25 * y1 + 0.5 * my + 0.25 * y2],
    };
  };
  const shape = (element, from, to) => {
    const { d, label } = curve(pinOf(from), pinOf(to));
    element.querySelectorAll("path").forEach((path) => path.setAttribute("d", d));
    const text = element.querySelector("text");
    text.setAttribute("x", label[0]);
    text.setAttribute("y", label[1]);
  };
  const ownElements = new Map();
  const drawOwn = (own) => {
    let element = ownElements.get(own.id);
    if (!element) {
      element = document.createElementNS(NS, "a");
      element.setAttribute("class", "own string");
      element.setAttribute("href", "#");
      element.dataset.id = own.id;
      for (const kind of ["string-hit", "string-line"]) {
        const path = document.createElementNS(NS, "path");
        path.setAttribute("class", kind);
        element.appendChild(path);
      }
      const text = document.createElementNS(NS, "text");
      text.setAttribute("class", "string-label");
      element.appendChild(text);
      element.addEventListener("click", (event) => {
        event.preventDefault();
        selectOwn(own.id);
      });
      mineLayer.appendChild(element);
      ownElements.set(own.id, element);
    }
    element.querySelector("text").textContent = own.label;
    shape(element, own.from, own.to);
  };
  const drawAll = () => {
    evidence.forEach((string) => {
      shape(string, string.dataset.from, string.dataset.to);
      string.classList.toggle("down", state.hidden.includes(string.dataset.ref));
    });
    ownElements.forEach((element, id) => {
      if (!state.mine.some((own) => own.id === id)) {
        element.remove();
        ownElements.delete(id);
      }
    });
    state.mine.forEach(drawOwn);
    putBack.hidden = state.hidden.length === 0;
    putBack.textContent = `Put back ${state.hidden.length} string${state.hidden.length === 1 ? "" : "s"}`;
  };
  const placeCard = (card, x, y) => {
    card.dataset.x = x;
    card.dataset.y = y;
    card.setAttribute("transform", `translate(${x} ${y}) rotate(${card.dataset.tilt})`);
    const pin = pins.get(card.dataset.ref);
    pin.setAttribute("cx", x);
    pin.setAttribute("cy", y - PIN);
  };
  const touching = (ref) => ({
    strings: [...evidence.values()].filter(
      (s) => !s.classList.contains("down") && (s.dataset.from === ref || s.dataset.to === ref),
    ),
    mine: state.mine.filter((own) => own.from === ref || own.to === ref),
  });
  const moveCard = (card, x, y) => {
    placeCard(card, x, y);
    const { strings, mine } = touching(card.dataset.ref);
    strings.forEach((s) => shape(s, s.dataset.from, s.dataset.to));
    mine.forEach(drawOwn);
    if (selected?.from) showHandles(selected.from, selected.to);
  };
  Object.entries(state.positions).forEach(([ref, [x, y]]) => {
    if (cards.has(ref)) placeCard(cards.get(ref), x, y);
  });
  drawAll();

  // ---- view: zoom towards a point, pan, fit ----
  const showView = () => svg.setAttribute("viewBox", `${view.x} ${view.y} ${view.width} ${view.height}`);
  const toBoard = (clientX, clientY) => {
    const p = svg.createSVGPoint();
    p.x = clientX;
    p.y = clientY;
    return p.matrixTransform(svg.getScreenCTM().inverse());
  };
  const zoomAt = (factor, at) => {
    const width = Math.min(Math.max(view.width * factor, start.width / 5), start.width * 1.5);
    const scale = width / view.width;
    view = {
      x: at.x - (at.x - view.x) * scale,
      y: at.y - (at.y - view.y) * scale,
      width,
      height: view.height * scale,
    };
    showView();
  };
  const centre = () => ({ x: view.x + view.width / 2, y: view.y + view.height / 2 });
  svg.addEventListener(
    "wheel",
    (event) => {
      event.preventDefault(); // over the board, the wheel zooms instead of scrolling
      zoomAt(event.deltaY < 0 ? 0.85 : 1 / 0.85, toBoard(event.clientX, event.clientY));
    },
    { passive: false },
  );

  // ---- selection and case notes ----
  let selected = null; // { card } | { evidence } | { own }, plus from/to for strings
  const light = (refs, strings, mine) => {
    svg.querySelectorAll(".lit").forEach((item) => item.classList.remove("lit"));
    refs.forEach((ref) => {
      cards.get(ref)?.classList.add("lit");
      pins.get(ref)?.classList.add("lit");
    });
    strings.forEach((s) => s.classList.add("lit"));
    mine.forEach((own) => ownElements.get(own.id)?.classList.add("lit"));
    svg.classList.toggle("focus", refs.length > 0);
  };
  const openNotes = (content, refs) => {
    notes.replaceChildren(content);
    panel.hidden = false;
    panel.scrollTop = 0;
    // Open the notes on the side of the board away from what is selected, so they never
    // cover the selected cards or a string's end handles.
    const frame = svg.getBoundingClientRect();
    const xs = refs.map((ref) => pins.get(ref).getBoundingClientRect().x);
    const average = xs.reduce((sum, x) => sum + x, 0) / Math.max(xs.length, 1);
    panel.classList.toggle("left", average > frame.left + frame.width / 2);
    keepInView(refs);
  };
  // If the selected cards sit under the notes, move the view (zooming out only if needed)
  // so they show in the free part of the board.
  const keepInView = (refs) => {
    if (window.getComputedStyle(panel).position !== "absolute") return; // notes below the board
    const frame = svg.getBoundingClientRect();
    const side = panel.getBoundingClientRect();
    const onLeft = panel.classList.contains("left");
    const freeLeft = onLeft ? side.right + 16 : frame.left + 16;
    const freeRight = onLeft ? frame.right - 16 : side.left - 16;
    if (freeRight - freeLeft < 160) return;
    const xs = refs.map((ref) => Number(cards.get(ref).dataset.x));
    const ys = refs.map((ref) => Number(cards.get(ref).dataset.y));
    const [minX, maxX] = [Math.min(...xs) - 95, Math.max(...xs) + 95];
    const [minY, maxY] = [Math.min(...ys) - 65, Math.max(...ys) + 50];
    const perUnit = frame.width / view.width;
    const screenX = (x) => frame.left + (x - view.x) * perUnit;
    const screenY = (y) => frame.top + (y - view.y) * perUnit;
    const visible =
      screenX(minX) >= freeLeft && screenX(maxX) <= freeRight &&
      screenY(minY) >= frame.top && screenY(maxY) <= frame.bottom;
    if (visible) return;
    const fit = Math.min(perUnit, (freeRight - freeLeft) / (maxX - minX), (frame.height - 32) / (maxY - minY));
    const width = frame.width / fit;
    view = {
      x: (minX + maxX) / 2 - ((freeLeft + freeRight) / 2 - frame.left) / fit,
      y: (minY + maxY) / 2 - frame.height / 2 / fit,
      width,
      height: (width * start.height) / start.width,
    };
    showView();
  };
  const fromTemplate = (id) => document.getElementById(id).content.cloneNode(true);
  const element = (tag, text, attributes = {}) => {
    const made = document.createElement(tag);
    if (text) made.textContent = text;
    Object.entries(attributes).forEach(([key, value]) => made.setAttribute(key, value));
    return made;
  };
  const nameOf = (ref) => cards.get(ref).dataset.name;

  const selectCard = (ref) => {
    const { strings, mine } = touching(ref);
    const ends = [...strings.flatMap((s) => [s.dataset.from, s.dataset.to]), ...mine.flatMap((o) => [o.from, o.to])];
    light([ref, ...ends], strings, mine);
    cards.get(ref).parentNode.appendChild(cards.get(ref));
    clearHandles();
    selected = { card: ref };
    const content = fromTemplate(`note-${ref}`);
    const slot = content.querySelector(".note-mine");
    if (mine.length) {
      slot.appendChild(element("h5", "Your own strings"));
      const list = element("ul", "", { class: "note-own" });
      mine.forEach((own) => {
        const item = element("li");
        const button = element("button", `${nameOf(own.from)} — ${own.label} → ${nameOf(own.to)}`, { type: "button", class: "note-link", "data-own": own.id });
        item.appendChild(button);
        list.appendChild(item);
      });
      slot.appendChild(list);
    }
    const down = state.hidden.filter((r) => {
      const s = evidence.get(r);
      return s.dataset.from === ref || s.dataset.to === ref;
    });
    if (down.length) {
      const note = element("p", `${down.length} evidence string${down.length === 1 ? " is" : "s are"} taken down from this card. `, { class: "muted" });
      note.appendChild(element("button", "Put back", { type: "button", class: "note-button", "data-put-back": down.join(" ") }));
      slot.appendChild(note);
    }
    openNotes(content, [ref]);
  };
  const selectEvidence = (ref) => {
    const string = evidence.get(ref);
    if (string.classList.contains("down")) {
      state.hidden = state.hidden.filter((r) => r !== ref); // selecting from the notes puts it back
      save();
      drawAll();
    }
    light([string.dataset.from, string.dataset.to], [string], []);
    selected = { evidence: ref, from: string.dataset.from, to: string.dataset.to };
    showHandles(selected.from, selected.to);
    openNotes(fromTemplate(`note-${ref}`), [selected.from, selected.to]);
  };
  const selectOwn = (id) => {
    const own = state.mine.find((o) => o.id === id);
    if (!own) return;
    light([own.from, own.to], [], [own]);
    selected = { own: id, from: own.from, to: own.to };
    showHandles(own.from, own.to);
    const content = document.createDocumentFragment();
    content.appendChild(element("p", "Your string", { class: "note-kind" }));
    content.appendChild(element("h4", `${nameOf(own.from)} — ${own.label} → ${nameOf(own.to)}`));
    content.appendChild(element("p", "You tied this string yourself. It is your idea, not something the evidence shows yet: look for sources that confirm or rule it out.", { class: "note-caution" }));
    const label = element("label", "What links them? ");
    const labelInput = element("input", "", { type: "text", maxlength: "60", value: own.label });
    labelInput.addEventListener("input", () => {
      own.label = labelInput.value.trim() || "your link";
      drawOwn(own);
      save();
    });
    label.appendChild(labelInput);
    content.appendChild(label);
    const noteLabel = element("label", "Your notes ");
    const noteInput = element("textarea", "", { rows: "4", maxlength: "1000" });
    noteInput.value = own.note || "";
    noteInput.addEventListener("input", () => {
      own.note = noteInput.value;
      save();
    });
    noteLabel.appendChild(noteInput);
    content.appendChild(noteLabel);
    content.appendChild(element("p", "Drag the round handles at its ends to move it, or drop one on bare cork to remove it.", { class: "muted" }));
    content.appendChild(element("button", "Remove this string", { type: "button", class: "note-button", "data-remove-own": own.id }));
    openNotes(content, [own.from, own.to]);
  };
  const clearAll = () => {
    light([], [], []);
    clearHandles();
    selected = null;
    notes.replaceChildren();
    panel.hidden = true;
  };
  closeButton.addEventListener("click", clearAll);
  evidence.forEach((string, ref) =>
    string.addEventListener("click", (event) => {
      event.preventDefault();
      selectEvidence(ref);
    }),
  );
  notes.addEventListener("click", (event) => {
    const target = event.target.closest("button");
    if (!target) return;
    if (target.dataset.link) selectEvidence(target.dataset.link);
    if (target.dataset.own) selectOwn(target.dataset.own);
    if (target.dataset.stringDown) {
      state.hidden = [...new Set([...state.hidden, target.dataset.stringDown])];
      save();
      drawAll();
      clearAll();
    }
    if (target.dataset.putBack) {
      const back = target.dataset.putBack.split(" ");
      state.hidden = state.hidden.filter((r) => !back.includes(r));
      save();
      drawAll();
      if (selected?.card) selectCard(selected.card);
    }
    if (target.dataset.removeOwn) {
      state.mine = state.mine.filter((o) => o.id !== target.dataset.removeOwn);
      save();
      drawAll();
      clearAll();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (document.querySelector("dialog[open]")) return;
    const typing = ["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName);
    if (event.key === "Escape") clearAll();
    if (!typing && selected?.own && (event.key === "Delete" || event.key === "Backspace")) {
      state.mine = state.mine.filter((o) => o.id !== selected.own);
      save();
      drawAll();
      clearAll();
    }
  });
  svg.addEventListener("pointerover", (event) => {
    const card = event.target.closest(".card");
    if (card) touching(card.dataset.ref).strings.forEach((s) => s.classList.add("hover"));
  });
  svg.addEventListener("pointerout", (event) => {
    const card = event.target.closest(".card");
    if (card) touching(card.dataset.ref).strings.forEach((s) => s.classList.remove("hover"));
  });

  // ---- handles on a selected string, and the string being drawn ----
  const circle = (x, y, end) => {
    const c = document.createElementNS(NS, "circle");
    c.setAttribute("class", "handle");
    c.setAttribute("cx", x);
    c.setAttribute("cy", y);
    c.setAttribute("r", "9");
    c.dataset.end = end;
    return c;
  };
  function clearHandles() {
    handleLayer.replaceChildren();
  }
  function showHandles(from, to) {
    clearHandles();
    const [x1, y1] = pinOf(from);
    const [x2, y2] = pinOf(to);
    handleLayer.appendChild(circle(x1, y1, "from"));
    handleLayer.appendChild(circle(x2, y2, "to"));
  }
  const draft = document.createElementNS(NS, "path");
  draft.setAttribute("class", "draft");
  const cardAt = (event) => {
    const found = document.elementFromPoint(event.clientX, event.clientY);
    if (found?.classList.contains("pin")) return cards.get(found.dataset.ref); // its card's pin
    return found?.closest(".card");
  };
  const newId = () => `own-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e6).toString(36)}`;

  // ---- one pointer at a time: drag a card, pan, move a handle or draw from a pin ----
  let held = null;
  svg.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    const handle = event.target.closest(".handle");
    const pin = event.target.closest(".pin");
    const card = event.target.closest(".card");
    if (event.target.closest("a.string") && !handle) return; // a click on a string selects it
    const at = toBoard(event.clientX, event.clientY);
    if (handle) held = { type: "handle", end: handle.dataset.end, keep: handle.dataset.end === "from" ? selected.to : selected.from };
    else if (pin) held = { type: "pin", from: pin.dataset.ref };
    else if (card) held = { type: "card", card, dx: at.x - Number(card.dataset.x), dy: at.y - Number(card.dataset.y) };
    else held = { type: "pan", x: event.clientX, y: event.clientY, view: { ...view } };
    held.startX = event.clientX;
    held.startY = event.clientY;
    held.moved = false;
    svg.setPointerCapture(event.pointerId);
  });
  svg.addEventListener("pointermove", (event) => {
    if (!held) return;
    if (!held.moved && Math.hypot(event.clientX - held.startX, event.clientY - held.startY) < 5) return;
    held.moved = true;
    const at = toBoard(event.clientX, event.clientY);
    if (held.type === "pan") {
      const scale = view.width / svg.getBoundingClientRect().width;
      view.x = held.view.x - (event.clientX - held.x) * scale;
      view.y = held.view.y - (event.clientY - held.y) * scale;
      showView();
      svg.classList.add("panning");
    } else if (held.type === "card") {
      held.card.classList.add("lifted");
      const x = Math.min(Math.max(at.x - held.dx, 90), start.width - 90);
      const y = Math.min(Math.max(at.y - held.dy, 50), start.height - 40);
      moveCard(held.card, x, y);
    } else {
      // a handle or a pin: draw a loose string from the end that stays to the pointer
      const anchor = pinOf(held.type === "pin" ? held.from : held.keep);
      draft.setAttribute("d", curve(anchor, [at.x, at.y]).d);
      if (!draft.isConnected) handleLayer.appendChild(draft);
      svg.classList.add("tying");
    }
  });
  const drop = (event) => {
    if (!held) return;
    const was = held;
    held = null;
    svg.classList.remove("panning", "tying");
    draft.remove();
    if (was.type === "card") {
      was.card.classList.remove("lifted");
      if (!was.moved) selectCard(was.card.dataset.ref);
      else {
        state.positions[was.card.dataset.ref] = [Number(was.card.dataset.x), Number(was.card.dataset.y)];
        save();
      }
      return;
    }
    if (was.type === "pan") {
      if (!was.moved) clearAll(); // a click on bare cork closes the notes
      return;
    }
    if (!was.moved || event.type === "pointercancel") {
      if (was.type === "pin") selectCard(was.from);
      return;
    }
    const target = cardAt(event)?.dataset.ref;
    if (was.type === "pin") {
      if (target && target !== was.from) {
        const own = { id: newId(), from: was.from, to: target, label: "your link", note: "" };
        state.mine.push(own);
        save();
        drawAll();
        selectOwn(own.id);
      }
      return;
    }
    // a handle was dropped: move the string's end, or take the string down
    const keep = was.keep;
    if (selected?.evidence) {
      const string = evidence.get(selected.evidence);
      state.hidden = [...new Set([...state.hidden, selected.evidence])];
      if (target && target !== keep) {
        const relation = string.querySelector("text").textContent;
        const [from, to] = was.end === "to" ? [keep, target] : [target, keep];
        const own = { id: newId(), from, to, label: `${relation} (your guess)`, note: "" };
        state.mine.push(own);
        save();
        drawAll();
        selectOwn(own.id);
      } else {
        save();
        drawAll();
        clearAll();
      }
    } else if (selected?.own) {
      const own = state.mine.find((o) => o.id === selected.own);
      if (target && target !== keep) {
        if (was.end === "to") own.to = target;
        else own.from = target;
        save();
        drawAll();
        selectOwn(own.id);
      } else {
        state.mine = state.mine.filter((o) => o.id !== own.id);
        save();
        drawAll();
        clearAll();
      }
    }
  };
  svg.addEventListener("pointerup", drop);
  svg.addEventListener("pointercancel", drop);

  // ---- toolbar ----
  document.querySelectorAll("[data-board]").forEach((button) =>
    button.addEventListener("click", () => {
      const action = button.dataset.board;
      if (action === "zoom-in") zoomAt(0.75, centre());
      if (action === "zoom-out") zoomAt(1 / 0.75, centre());
      if (action === "fit") {
        view = { ...start };
        showView();
      }
      if (action === "tidy") {
        home.forEach(([x, y], ref) => moveCard(cards.get(ref), x, y));
        state.positions = {};
        save();
      }
      if (action === "put-back") {
        state.hidden = [];
        save();
        drawAll();
      }
      if (action === "reset" && window.confirm("Undo all your changes to this board: card positions, your own strings and taken-down strings?")) {
        state.positions = {};
        state.hidden = [];
        state.mine = [];
        save();
        home.forEach(([x, y], ref) => placeCard(cards.get(ref), x, y));
        drawAll();
        clearAll();
        view = { ...start };
        showView();
      }
    }),
  );
})();
