"use strict";
function coverAssistant(item) {
  let design = structuredClone(
    item.cover_design || {
      border: "none",
      fit: "inherit",
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
      <section class="cover-proof"><div class="proof-paper"><img id="cover-proof" alt="Cover proof. Click artwork to paint."></div>
      <span id="cover-state" role="status"></span>
      <div class="pair"><button id="cover-undo">Undo</button><button id="cover-redo">Redo</button><select aria-label="Cover zoom" id="cover-zoom"><option value="1">Fit page</option><option value="2">Zoom 2×</option><option value="3">Zoom 3×</option></select></div>
      <fieldset><legend>Paint</legend>
      <label>Tool<select id="cover-tool"><option value="bucket">Paint bucket · touching pixels</option><option value="replace">Replace color · across artwork</option></select></label>
      <div class="pair"><label>Paint color<input id="cover-brush" type="color"></label>
      <label>Tolerance (%)<input id="cover-tolerance" type="number" min="0" max="100" value="10"></label></div>
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
      <label>Artwork fit<select id="cover-fit"><option value="inherit">Use page framing</option><option value="contain">Show entire crop</option><option value="fill">Fill inside border</option></select></label></fieldset>
      <details><summary>Artwork color</summary><div id="cover-adjustments"></div></details>

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
  image.onclick = (event) => {
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
    const tol = $("cover-tolerance");
    if (!tol.reportValidity() || !Number.isFinite(tol.valueAsNumber)) return;
    edit(() =>
      design.fills.push({
        x: (l + x * (r - l)) / mapping.size[0],
        y: (t + y * (b - t)) / mapping.size[1],
        tolerance: tol.valueAsNumber,
        mode: $("cover-tool").value,
        color: brush,
      }),
    );
  };
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
          border: "none",
          fit: "inherit",
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
