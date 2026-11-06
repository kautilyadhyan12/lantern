"use strict";

// Interactive before/after viewer over NASA GIBS daily imagery (Leaflet, served by Lantern).
// Drag the slider to swipe between the two dates; change dates, view and labels freely.
(function startEarthView() {
  const box = document.getElementById("eo");
  if (!box || !window.L) return;
  const base = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/";
  // Each option is one NASA layer. VIIRS covers a wider strip on each pass, so it rarely
  // has the black gaps between passes that MODIS leaves near the tropics.
  const views = {
    viirs: ["VIIRS_NOAA20_CorrectedReflectance_TrueColor", 9],
    viirs21: ["VIIRS_NOAA21_CorrectedReflectance_TrueColor", 9],
    modis: ["MODIS_Terra_CorrectedReflectance_TrueColor", 9],
    aqua: ["MODIS_Aqua_CorrectedReflectance_TrueColor", 9],
    // The next line is a NASA layer name that the secret scanner mistakes for a key.
    viirsFalse: ["VIIRS_NOAA20_CorrectedReflectance_BandsM11-I2-I1", 9], // pragma: allowlist secret
    bands721: ["MODIS_Terra_CorrectedReflectance_Bands721", 9],
  };
  const credit = 'Imagery <a href="https://www.earthdata.nasa.gov/eosdis/science-system-description/eosdis-components/gibs">NASA EOSDIS GIBS</a>';
  const data = box.dataset;
  const beforeInput = document.getElementById("eo-before");
  const afterInput = document.getElementById("eo-after");
  const choice = document.getElementById("eo-view");
  const outlineBox = document.getElementById("eo-outline");
  const swipe = document.getElementById("eo-swipe");
  const divider = document.getElementById("eo-divider");

  const map = L.map("eo-map", { minZoom: 2, maxZoom: 12, worldCopyJump: true });
  map.zoomControl.setPosition("bottomleft"); // keeps the Before tag readable
  map.fitBounds([
    [Number(data.south), Number(data.west)],
    [Number(data.north), Number(data.east)],
  ]);
  // Imagery panes sit under Leaflet's overlay pane, so the area outline stays on top.
  ["before", "after"].forEach((name) => {
    map.createPane(name);
    map.getPane(name).style.zIndex = 250;
  });

  const imagery = (key, day, pane) => {
    const [name, level] = views[key];
    const url = `${base}${name}/default/${day}/GoogleMapsCompatible_Level${level}/{z}/{y}/{x}.jpg`;
    return L.tileLayer(url, { pane, maxNativeZoom: level, maxZoom: 12, attribution: credit });
  };
  // NASA's own label and border tiles have opaque backgrounds in this projection, so
  // Lantern draws the investigated area and its name itself instead.
  const outline = L.rectangle(
    [
      [Number(data.south), Number(data.west)],
      [Number(data.north), Number(data.east)],
    ],
    { color: "#ffd24d", weight: 2, fill: false, dashArray: "6 4", interactive: false },
  ).bindTooltip(data.name, { permanent: true, direction: "center", className: "eo-name" });

  let before = null;
  let after = null;
  const clip = () => {
    const size = map.getSize();
    const x = (size.x * Number(swipe.value)) / 100;
    const nw = map.containerPointToLayerPoint([0, 0]);
    const se = map.containerPointToLayerPoint(size);
    const cut = map.containerPointToLayerPoint([x, 0]).x;
    map.getPane("before").style.clip = `rect(${nw.y}px, ${cut}px, ${se.y}px, ${nw.x}px)`;
    map.getPane("after").style.clip = `rect(${nw.y}px, ${se.x}px, ${se.y}px, ${cut}px)`;
    divider.style.left = `${x}px`;
  };
  const redraw = () => {
    if (before) map.removeLayer(before);
    if (after) map.removeLayer(after);
    before = imagery(choice.value, beforeInput.value, "before").addTo(map);
    after = imagery(choice.value, afterInput.value, "after").addTo(map);
    clip();
  };
  const toggleOutline = () => {
    if (outlineBox.checked) outline.addTo(map);
    else map.removeLayer(outline);
  };

  [beforeInput, afterInput, choice].forEach((input) => input.addEventListener("change", redraw));
  outlineBox.addEventListener("change", toggleOutline);
  swipe.addEventListener("input", clip);
  // Whole-map flips: compare the same place on both dates without dragging the line.
  document.querySelectorAll("[data-eo-show]").forEach((button) =>
    button.addEventListener("click", () => {
      swipe.value = { before: "100", swipe: "50", after: "0" }[button.dataset.eoShow];
      document
        .querySelectorAll("[data-eo-show]")
        .forEach((other) => other.setAttribute("aria-pressed", String(other === button)));
      clip();
    }),
  );
  map.on("move zoom resize", clip);
  redraw();
  toggleOutline();
})();
