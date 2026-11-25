"use strict";
function panelDialog(item) {
  modal(
    "Panel layout",
    `
    <label>Pages for this comic<select id="panel-mode"></select></label>
    <p class="subtle">Rectangles follow reading order. Select a number and drag on the scan to redraw it. Multi-page layouts use these rectangles on plain pages.</p>
    <div id="panel-canvas"><img id="panel-image" alt="Original comic with numbered panel boundaries" draggable="false"><div id="panel-overlay"></div></div>
    <div class="pair"><button id="find-border">Find drawn borders</button><button id="find-gutter">Find gaps between panels</button></div>
    <div class="panel-tools"><label>Panel<select id="active-panel"></select></label>
    <button id="panel-add">Add panel</button><button id="panel-remove">Remove</button>
    <button id="panel-earlier">Earlier</button><button id="panel-later">Later</button></div>`,
  );
  const boxes = structuredClone(item.panels || []);
  const select = $("active-panel"),
    surface = $("panel-canvas");
  options(
    $("panel-mode"),
    {
      auto: "Automatic",
      single: "Keep one page",
      2: "Two pages",
      4: "Four pages",
      10: "One page per panel",
      spread: "Facing spread · continuous artwork",
    },
    item.layout || "auto",
  );
  $("panel-image").src = "/api/art?project=" + issue.id + "&id=" + item.id;
  let active = 0,
    start = null,
    adding = false;
  function overlay() {
    $("panel-overlay").replaceChildren(
      ...boxes.map(([l, t, r, b], i) => {
        const box = el("span", String(i + 1), i === active ? "active" : "");
        Object.assign(box.style, {
          left: l * 100 + "%",
          top: t * 100 + "%",
          width: (r - l) * 100 + "%",
          height: (b - t) * 100 + "%",
        });
        return box;
      }),
    );
  }
  function sync() {
    select.replaceChildren(
      ...boxes.map((_, i) => new Option("Panel " + (i + 1), i)),
    );
    select.value = active;
    $("panel-add").disabled = boxes.length >= 10;
    $("panel-remove").disabled = !boxes.length;
    $("panel-earlier").disabled = active <= 0;
    $("panel-later").disabled = active >= boxes.length - 1;
    overlay();
  }
  for (const method of ["border", "gutter"]) {
    $("find-" + method).onclick = () =>
      working("Finding panels…", async () => {
        const result = await post("find-panels", { id: item.id, method });
        if (!result.boxes.length) {
          message(
            "No clear panel boundaries found. Add a panel and draw its rectangle.",
          );
          return;
        }
        boxes.splice(0, boxes.length, ...result.boxes);
        active = 0;
        adding = false;
        sync();
      });
  }
  select.onchange = () => {
    active = +select.value;
    adding = false;
    sync();
  };
  $("panel-add").onclick = () => {
    adding = true;
    $("dialog-error").textContent = "Drag a rectangle around the next panel.";
  };
  $("panel-remove").onclick = () => {
    boxes.splice(active, 1);
    active = Math.max(0, Math.min(active, boxes.length - 1));
    sync();
  };
  function move(delta) {
    const other = active + delta;
    [boxes[other], boxes[active]] = [boxes[active], boxes[other]];
    active = other;
    sync();
  }
  $("panel-earlier").onclick = () => move(-1);
  $("panel-later").onclick = () => move(1);
  const point = (e) => {
    const rect = surface.getBoundingClientRect();
    return [
      (e.clientX - rect.left) / rect.width,
      (e.clientY - rect.top) / rect.height,
    ].map((n) => Math.min(1, Math.max(0, n)));
  };
  let previous;
  surface.onpointerdown = (e) => {
    if (e.button !== 0) return;
    start = point(e);
    if (adding || !boxes.length) {
      active = boxes.length;
      previous = null;
      adding = false;
    } else previous = boxes[active];
    surface.setPointerCapture(e.pointerId);
  };
  surface.onpointermove = (e) => {
    if (!start) return;
    const [x, y] = point(e);
    boxes[active] = [
      Math.min(start[0], x),
      Math.min(start[1], y),
      Math.max(start[0], x),
      Math.max(start[1], y),
    ];
    overlay();
  };
  function end(cancel) {
    if (!start) return;
    const b = boxes[active];
    if (cancel || !b || b[2] - b[0] < 0.005 || b[3] - b[1] < 0.005) {
      if (previous) boxes[active] = previous;
      else boxes.splice(active, 1);
    }
    active = Math.max(0, Math.min(active, boxes.length - 1));
    start = null;
    $("dialog-error").textContent = "";
    sync();
  }
  surface.onpointerup = () => end(false);
  surface.onpointercancel = () => end(true);
  sync();
  actions("Apply panel layout", () =>
    mutate(
      "item",
      {
        id: item.id,
        title: item.title,
        role: "comic",
        panels: boxes,
        layout: $("panel-mode").value,
        crop: $("panel-mode").value === "spread" ? item.crop : null,
        rotate: $("panel-mode").value === "spread" ? item.rotate : 0,
        fit: "contain",
      },
      item.id,
    ),
  );
}
