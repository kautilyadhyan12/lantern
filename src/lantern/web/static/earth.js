"use strict";

// Interactive before/after viewer over NASA GIBS daily imagery (Leaflet, served by Lantern).
// Drag the slider to swipe between the two dates; change dates, view and labels freely.
(function startEarthView() {
  const box = document.getElementById("eo");
  if (!box || !window.L) return;
  const base = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/";
  const views = {
    modis: ["MODIS_Terra_CorrectedReflectance_TrueColor", 9],
    viirs: ["VIIRS_NOAA20_CorrectedReflectance_TrueColor", 9],
    bands721: ["MODIS_Terra_CorrectedReflectance_Bands721", 9],
  };
  const credit = 'Imagery <a href="https://www.earthdata.nasa.gov/eosdis/science-system-description/eosdis-components/gibs">NASA EOSDIS GIBS</a>';
  const data = box.dataset;
  const beforeInput = document.getElementById("eo-before");
  const afterInput = document.getElementById("eo-after");
  const choice = document.getElementById("eo-view");
  const labelsBox = document.getElementById("eo-labels");
  const swipe = document.getElementById("eo-swipe");
  const divider = document.getElementById("eo-divider");

  const map = L.map("eo-map", { minZoom: 2, maxZoom: 12, worldCopyJump: true });
  map.fitBounds([
    [Number(data.south), Number(data.west)],
    [Number(data.north), Number(data.east)],
  ]);
  ["before", "after", "labels"].forEach((name) => map.createPane(name));
  map.getPane("labels").style.zIndex = 650;
  map.getPane("labels").style.pointerEvents = "none";

  const imagery = (key, day, pane) => {
    const [name, level] = views[key];
    const url = `${base}${name}/default/${day}/GoogleMapsCompatible_Level${level}/{z}/{y}/{x}.jpg`;
    return L.tileLayer(url, { pane, maxNativeZoom: level, maxZoom: 12, attribution: credit });
  };
  const reference = (name) =>
    L.tileLayer(`${base}${name}/default/GoogleMapsCompatible_Level13/{z}/{y}/{x}.png`, {
      pane: "labels",
      maxNativeZoom: 13,
      maxZoom: 12,
    });
  const labels = L.layerGroup([reference("Reference_Features_15m"), reference("Reference_Labels_15m")]);

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
  const toggleLabels = () => {
    if (labelsBox.checked) labels.addTo(map);
    else map.removeLayer(labels);
  };

  [beforeInput, afterInput, choice].forEach((input) => input.addEventListener("change", redraw));
  labelsBox.addEventListener("change", toggleLabels);
  swipe.addEventListener("input", clip);
  map.on("move zoom resize", clip);
  redraw();
  toggleLabels();
})();
