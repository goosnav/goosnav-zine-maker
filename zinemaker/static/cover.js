"use strict";
function coverAssistant(item) {
  let design = structuredClone(
    item.cover_design || {
      border: "none",
      fit: "extend",
      width: 4,
      frame: "#F9C62D",
      stripe: "#222020",
      name: "Newsstand",
      palette: ["#222020", "#B54035", "#F9C62D", "#FAF1DB"],
      wash: 0,
      saturation: 100,
      contrast: 100,
      fills: [],
    },
  );
  design = {
    keyline: item.cover_design ? 0 : 1,
    zoom: 100,
    focus_x: 50,
    focus_y: 50,
    filter: "original",
    ...design,
  };
  let brush = design.palette[1],
    source = [],
    round = 0,
    timer,
    serial = 0,
    rendering = false,
    mapping = null,
    objectURL;
  const undo = [],
    redo = [];
  modal(
    "Cover assistant",
    `
    <div class="cover-desk">
      <section class="cover-proof"><div class="proof-paper"><img id="cover-proof" draggable="false" alt="Cover proof. Click artwork to paint."></div>
      <span id="cover-state" role="status"></span>
      <div class="pair"><button id="cover-undo">Undo</button><button id="cover-redo">Redo</button><select aria-label="Cover zoom" id="cover-zoom"><option value="1">Fit page</option><option value="2">Zoom 2×</option><option value="3">Zoom 3×</option></select></div>
      <fieldset><legend>Paint</legend>
      <label>Tool<select id="cover-tool"><option value="bucket">Paint bucket · touching pixels</option><option value="brush">Brush · drag to paint</option><option value="replace">Replace color · across artwork</option></select></label>
      <div class="pair"><label>Paint color<input id="cover-brush" type="color"></label>
      <label id="brush-width-label" hidden>Brush width (%)<input id="brush-width" type="number" step=".1" min=".1" max="10" value="1"></label><label id="tolerance-label">Tolerance (%)<input id="cover-tolerance" type="number" min="0" max="100" value="10"></label></div>
      <div><small>From the artwork</small><div id="sample-colors" class="color-row"></div></div>
      <div><small>Print swatches</small><div id="press-colors" class="color-row"></div></div>
      <button id="unpaint">Remove last paint edit</button>
      <p class="subtle">Pick a swatch, then click the artwork to paint.</p></fieldset>
</section>
      <section class="cover-controls">
      <fieldset><legend>Palette</legend>
      <label>Library<select id="cover-library"></select></label>
      <div id="active-colors" class="color-row"></div>
      <label>Suggest a palette<select id="cover-mood"></select></label><div id="cover-ideas"></div>
      <div class="pair"><button id="more-ideas">More suggestions</button><button id="toggle-wash"></button></div></fieldset>
      <fieldset><legend>Border</legend>
      <div class="pair"><label>Style<select id="cover-border"><option value="none">None</option><option value="solid">Solid band</option><option value="double">Two bands</option></select></label>
      <label>Width (%)<input type="number" min="1" max="15" step=".5" id="cover-width"></label></div>
      <div class="pair"><button id="set-frame">Use swatch for outer band</button><button id="set-stripe">Use swatch for inner band</button></div>
      <label>Black inner line (pt)<input type="number" id="keyline" min="0" max="6" step=".25"></label><label>Artwork fit<select id="cover-fit"><option value="inherit">Use page framing</option><option value="contain">Show entire crop</option><option value="extend">Extend edge colors · keep full artwork</option><option value="fill">Fill inside border</option></select></label>
      <label>Artwork zoom (%)<input id="art-zoom" type="range" min="100" max="300"></label>
      <div class="pair"><label>Horizontal focus<input id="focus-x" type="range" min="0" max="100"></label><label>Vertical focus<input id="focus-y" type="range" min="0" max="100"></label></div></fieldset>
      <details open><summary>Filters</summary><label>Artwork filter<select id="art-filter"><option value="original">Original color</option><option value="grayscale">Grayscale</option><option value="ink">Black ink</option><option value="palette">Match nearest palette color</option><option value="dither">Dither to palette</option></select></label><div id="cover-adjustments"></div></details>

      </section></div>`,
  );
  const dialog = $("dialog"),
    image = $("cover-proof");
  dialog.classList.add("cover-dialog");
  const controller = new AbortController();
  dialog.addEventListener(
    "close",
    () => {
      clearTimeout(timer);
      controller.abort();
      dialog.classList.remove("cover-dialog");
      if (objectURL) URL.revokeObjectURL(objectURL);
    },
    { once: true },
  );
  function remember() {
    undo.push(structuredClone(design));
    if (undo.length > 80) undo.shift();
    redo.length = 0;
  }
  function edit(change) {
    remember();
    change();
    sync();
    schedule();
  }
  function travel(from, to) {
    if (!from.length) return;
    to.push(design);
    design = from.pop();
    sync();
    schedule();
  }
  function swatch(hex, label) {
    const node = button("", () => {
      brush = hex;
      sync();
    });
    node.className = "ink-swatch";
    node.style.background = hex;
    node.title = label + " · " + hex;
    node.setAttribute("aria-label", node.title);
    node.setAttribute("aria-pressed", String(hex === brush));
    return node;
  }
  function setPalette(name, colors) {
    edit(() => {
      design.palette = colors.slice();
      design.name = name;
      design.frame = colors[2];
      design.stripe = colors[0];
      brush = colors[1];
    });
  }
  const lib = $("cover-library"),
    saved = new Option("Current palette", "");
  lib.add(saved);
  const catalog = new Map();
  for (const [group, entries] of Object.entries(coverLibrary)) {
    const opt = el("optgroup");
    opt.label = group;
    for (const [name, raw] of entries) {
      catalog.set(
        name,
        raw.split(" ").map((c) => "#" + c),
      );
      opt.append(new Option(name, name));
    }
    lib.append(opt);
  }
  lib.onchange = () => {
    if (lib.value) setPalette(lib.value, catalog.get(lib.value));
  };
  const mood = $("cover-mood");
  for (const name of Object.keys(moodRecipes)) mood.add(new Option(name, name));
  function ideas() {
    $("cover-ideas").replaceChildren(
      ...suggestCoverPalettes(source, mood.value, round).map((p) => {
        const b = button("", () => setPalette(p.name, p.colors));
        b.className = "palette-strip";
        b.title = p.name;
        b.setAttribute("aria-label", p.name);
        for (const hex of p.colors) {
          const chip = el("span");
          chip.style.backgroundColor = hex;
          b.append(chip);
        }
        return b;
      }),
    );
  }
  mood.onchange = () => {
    round = 0;
    ideas();
  };
  $("toggle-wash").onclick = () =>
    edit(() => {
      design.wash = design.wash ? 0 : 65;
    });
  $("unpaint").onclick = () => edit(() => design.fills.pop());
  $("cover-zoom").onchange = (e) => {
    const zoom = Number(e.target.value);
    image.parentElement.classList.toggle("zoomed", zoom > 1);
    image.style.width = zoom > 1 ? zoom * 100 + "%" : "";
  };
  $("more-ideas").onclick = () => {
    round++;
    ideas();
  };
  for (const [key, label, min, max] of [
    ["wash", "Palette wash", 0, 100],
    ["saturation", "Saturation", 0, 200],
    ["contrast", "Contrast", 50, 160],
  ]) {
    const wrap = el("label", label + " (%)"),
      field = el("input");
    field.type = "range";
    field.id = "color-" + key;
    field.min = min;
    field.max = max;
    const readout = el("output");
    field.oninput = () => {
      readout.value = field.value + "%";
    };
    field.onchange = () =>
      edit(() => {
        design[key] = +field.value;
      });
    wrap.append(readout, field);
    $("cover-adjustments").append(wrap);
  }
  function sync() {
    for (const [id, key] of Object.entries(geometry)) $(id).value = design[key];
    $("art-filter").value = design.filter;
    $("keyline").disabled = design.border === "none";
    saved.textContent = design.name;
    lib.value = catalog.has(design.name) ? design.name : "";
    $("cover-fit").value = design.fit || "inherit";
    $("cover-border").value = design.border;
    $("cover-width").value = design.width;
    $("cover-width").disabled = design.border === "none";
    for (const [id, key] of [
      ["set-frame", "frame"],
      ["set-stripe", "stripe"],
    ]) {
      const b = $(id);
      b.style.borderBottom = "5px solid " + design[key];
      b.disabled =
        design.border === "none" ||
        (key === "stripe" && design.border !== "double");
      b.title = "Use " + brush;
    }
    $("active-colors").replaceChildren(
      ...design.palette.map((c, i) =>
        swatch(c, ["Ink", "Accent", "Frame", "Paper"][i]),
      ),
    );
    $("press-colors").replaceChildren(
      ...Object.entries(printSwatches).map(([name, c]) => swatch(c, name)),
    );
    $("sample-colors").replaceChildren(
      ...source.map((c) => swatch(c, "Artwork")),
    );
    $("unpaint").disabled = !design.fills.length;
    $("toggle-wash").textContent = design.wash
      ? "Remove palette wash"
      : "Apply palette wash";
    $("cover-brush").value = brush;
    for (const k of ["wash", "saturation", "contrast"]) {
      const input = $("color-" + k);
      input.value = design[k];
      input.previousSibling.value = design[k] + "%";
    }
    $("cover-undo").disabled = !undo.length;
    $("cover-redo").disabled = !redo.length;
  }
  async function proof(version) {
    if (rendering || controller.signal.aborted) return;
    rendering = true;
    try {
      const response = await fetch("/api/cover-proof", {
        method: "POST",
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
          "X-Issue-Session": token,
        },
        body: JSON.stringify({
          project: issue.id,
          revision: issue.revision,
          id: item.id,
          design,
        }),
      });
      if (!response.ok) throw new Error((await response.json()).error);
      const blob = await response.blob();
      if (version !== serial || controller.signal.aborted) return;
      const url = URL.createObjectURL(blob);
      const nextMap = JSON.parse(response.headers.get("X-Art-Map"));
      if (objectURL) URL.revokeObjectURL(objectURL);
      objectURL = url;
      image.onload = () => {
        if (version === serial) {
          mapping = nextMap;
          $("cover-state").textContent = "";
        }
      };
      image.src = url;
    } catch (error) {
      if (version === serial && !controller.signal.aborted)
        $("cover-state").textContent = error.message;
    } finally {
      rendering = false;
      if (serial !== version && !controller.signal.aborted) {
        clearTimeout(timer);
        timer = setTimeout(() => proof(serial), 0);
      }
    }
  }
  function schedule() {
    const version = ++serial;
    mapping = null;
    clearTimeout(timer);
    $("cover-state").textContent = "Rendering cover…";
    timer = setTimeout(() => proof(version), 100);
  }
  function sourcePoint(event) {
    if (!mapping || design.fills.length >= 64) {
      if (mapping) message("This cover has reached 64 paint edits.");
      return;
    }
    const rect = image.getBoundingClientRect(),
      [left, top, w, h] = mapping.bounds;
    let x = ((event.clientX - rect.left) / rect.width - left) / w;
    let y = ((event.clientY - rect.top) / rect.height - top) / h;
    if (x < 0 || x >= 1 || y < 0 || y >= 1) {
      $("cover-state").textContent = "Click inside the artwork to paint.";
      return;
    }
    if (mapping.rotate === 90) [x, y] = [y, 1 - x];
    if (mapping.rotate === 180) [x, y] = [1 - x, 1 - y];
    if (mapping.rotate === 270) [x, y] = [1 - y, x];
    const [l, t, r, b] = mapping.crop;
    return [
      (l + x * (r - l)) / mapping.size[0],
      (t + y * (b - t)) / mapping.size[1],
    ];
  }
  let stroke, overlay;
  image.style.touchAction = "none";
  $("cover-tool").onchange = () => {
    const brushOn = $("cover-tool").value === "brush";
    $("brush-width-label").hidden = !brushOn;
    $("tolerance-label").hidden = brushOn;
  };
  function addPoint(event) {
    const point = sourcePoint(event);
    if (!point || !stroke || stroke.points.length >= 4096) return;
    stroke.points.push(point);
    const rect = image.getBoundingClientRect();
    const px = ((event.clientX - rect.left) / rect.width) * overlay.width;
    const py = ((event.clientY - rect.top) / rect.height) * overlay.height;
    const ctx = overlay.getContext("2d");
    ctx.lineTo(px, py);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(px, py);
  }
  image.onpointerdown = (event) => {
    if (event.button !== 0 || stroke) return;
    const point = sourcePoint(event);
    if (!point) return;
    const mode = $("cover-tool").value;
    if (mode !== "brush") {
      const tol = $("cover-tolerance");
      if (tol.reportValidity() && Number.isFinite(tol.valueAsNumber))
        edit(() =>
          design.fills.push({
            x: point[0],
            y: point[1],
            tolerance: tol.valueAsNumber,
            mode,
            color: brush,
          }),
        );
      return;
    }
    const width = $("brush-width");
    if (!width.reportValidity() || !Number.isFinite(width.valueAsNumber))
      return;
    stroke = { mode, color: brush, width: width.valueAsNumber, points: [] };
    image.setPointerCapture(event.pointerId);
    const rect = image.getBoundingClientRect();
    overlay = el("canvas");
    overlay.width = Math.max(1, Math.round(rect.width));
    overlay.height = Math.max(1, Math.round(rect.height));
    Object.assign(overlay.style, {
      position: "fixed",
      pointerEvents: "none",
      top: rect.top + "px",
      left: rect.left + "px",
    });
    dialog.append(overlay);
    const ctx = overlay.getContext("2d"),
      crop = mapping.crop;
    const sourceWidth =
      mapping.rotate % 180 ? crop[3] - crop[1] : crop[2] - crop[0];
    ctx.lineWidth = Math.max(
      1,
      (((Math.min(...mapping.size) * stroke.width) / 100) *
        rect.width *
        mapping.bounds[2]) /
        sourceWidth,
    );
    ctx.strokeStyle = brush;
    ctx.lineCap = "round";
    addPoint(event);
  };
  image.onpointermove = (event) => {
    if (stroke) addPoint(event);
  };
  function finishStroke(commit) {
    if (!stroke) return;
    const operation = stroke;
    stroke = null;
    overlay.remove();
    if (commit && operation.points.length)
      edit(() => design.fills.push(operation));
  }
  image.onpointerup = () => finishStroke(true);
  image.onpointercancel = () => finishStroke(false);
  dialog.addEventListener("close", () => finishStroke(false), { once: true });
  const geometry = {
    keyline: "keyline",
    "art-zoom": "zoom",
    "focus-x": "focus_x",
    "focus-y": "focus_y",
  };
  for (const [id, key] of Object.entries(geometry)) {
    $(id).onchange = (e) => {
      if (e.target.reportValidity() && Number.isFinite(e.target.valueAsNumber))
        edit(() => {
          design[key] = e.target.valueAsNumber;
        });
    };
  }
  $("art-filter").onchange = (e) =>
    edit(() => {
      design.filter = e.target.value;
    });
  $("cover-fit").onchange = (e) =>
    edit(() => {
      design.fit = e.target.value;
    });
  $("cover-border").onchange = (e) =>
    edit(() => {
      design.border = e.target.value;
    });
  $("cover-width").onchange = (e) => {
    if (e.target.reportValidity() && Number.isFinite(e.target.valueAsNumber))
      edit(() => {
        design.width = e.target.valueAsNumber;
      });
    else sync();
  };
  $("set-frame").onclick = () =>
    edit(() => {
      design.frame = brush;
    });
  $("set-stripe").onclick = () =>
    edit(() => {
      design.stripe = brush;
    });
  $("cover-brush").oninput = (e) => {
    brush = e.target.value.toUpperCase();
    sync();
  };
  $("cover-undo").onclick = () => travel(undo, redo);
  $("cover-redo").onclick = () => travel(redo, undo);
  const bar = el("div", undefined, "actions");
  bar.append(
    button("Reset cover", () =>
      edit(() => {
        design = {
          ...design,
          keyline: 1,
          zoom: 100,
          focus_x: 50,
          focus_y: 50,
          filter: "original",
          border: "none",
          fit: "extend",
          wash: 0,
          saturation: 100,
          contrast: 100,
          fills: [],
        };
      }),
    ),
    button("Cancel", () => dialog.close()),
    button(
      "Save cover",
      () => mutate("cover-design", { id: item.id, design }, item.id),
      true,
    ),
  );
  $("dialog-body").append(bar);
  sync();
  ideas();
  schedule();
  post("cover-swatches", { id: item.id })
    .then((data) => {
      if (!controller.signal.aborted) {
        source = data.colors;
        ideas();
        sync();
      }
    })
    .catch((err) => {
      if (!controller.signal.aborted) message(err.message);
    });
}
