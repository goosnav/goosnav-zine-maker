"use strict";
const $ = (id) => document.getElementById(id);
const roles = {
  alignment: "Blank before facing spread",
  generated: "Automatic cover",
  comic: "Comic",
  essay: "Essay",
  ad: "Advertisement",
  cover: "Front cover",
  back: "Back cover",
};
const fits = {
  contain: "Trim paper & center",
  original: "Keep full image",
  fill: "Fill frame",
};
const styles = {
  ornamental: "Goosnav ornaments",
  ruled: "Ruled border",
  plain: "Plain",
};
let issue,
  selected = 0,
  token,
  busy = false,
  latestExport;
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function button(text, fn, primary = false) {
  const node = el("button", text, primary ? "primary" : "");
  node.type = "button";
  node.onclick = fn;
  return node;
}
function note(text) {
  $("alert").textContent = text;
  $("alert").hidden = !text;
}
function message(text) {
  if ($("dialog").open && $("dialog-error"))
    $("dialog-error").textContent = text;
  else note(text);
}
async function request(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok)
    throw new Error(data.error || "Could not complete the operation.");
  return data;
}
function post(action, values = {}) {
  return request("/api/" + action, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Issue-Session": token },
    body: JSON.stringify({
      project: issue?.id,
      revision: issue?.revision,
      ...values,
    }),
  });
}
async function working(label, fn) {
  if (busy) return;
  busy = true;
  let status;
  note("");
  $("status").textContent = label;
  if ($("dialog-error")) $("dialog-error").textContent = "";
  document.querySelector("main").inert = true;
  document.querySelector(".toolbar").inert = true;
  $("dialog-body").inert = true;
  $("close").disabled = true;
  try {
    await fn();
  } catch (err) {
    status = "Action incomplete";
    message(err.message);
  } finally {
    busy = false;
    document.querySelector("main").inert = false;
    document.querySelector(".toolbar").inert = false;
    $("dialog-body").inert = false;
    $("close").disabled = false;
    $("status").textContent = status || (issue ? "Saved locally" : "Ready");
  }
}
function adopt(data) {
  if (data.token) token = data.token;
  issue = data.id ? data : null;
  if (!issue) return;
  if (issue.warnings.length) note(issue.warnings.join("\n"));
  selected = Math.min(selected, Math.max(0, issue.pages.length - 1));
}
function current() {
  return issue?.pages[selected];
}
function itemFor(page) {
  return page && issue.items.find((i) => i.id === page.id);
}
function pageName(page) {
  if (page.kind === "alignment") return "Spread alignment";
  return page.kind === "generated" ? issue.title : itemFor(page).title;
}
function pickIndex(index) {
  const listFocused = $("pages").contains(document.activeElement);
  selected = index;
  render();
  const list = $("pages"),
    row = list.children[index];
  if (row) {
    if (listFocused) row.firstElementChild.focus({ preventScroll: true });
    const top =
      row.getBoundingClientRect().top - list.getBoundingClientRect().top;
    if (top < 0) list.scrollTop += top;
    if (top + row.offsetHeight > list.clientHeight)
      list.scrollTop += top + row.offsetHeight - list.clientHeight;
  }
}
function focusItem(id) {
  const pos = issue.pages.findIndex(
    (p) => p.kind !== "generated" && p.kind !== "alignment" && p.id === id,
  );
  if (pos >= 0) selected = pos;
}
async function mutate(action, payload, focus) {
  await working("Saving…", async () => {
    if (!(await ensureIssue())) return;
    adopt(await post(action, payload));
    $("dialog").close();
    if (focus) focusItem(focus);
    latestExport = null;
    render();
  });
}
function property(label, value) {
  const div = el("div", undefined, "property");
  div.append(el("small", label), document.createTextNode(value));
  return div;
}
function render() {
  const page = current(),
    item = itemFor(page);
  const proofIds = Object.keys(issue?.essay_proofs || {});
  $("review-proof").hidden = !proofIds.length;
  $("review-proof").onclick = () => {
    const index = issue.pages.findIndex(
      (p) => p.kind === "comic" && p.id === proofIds[0],
    );
    if (index >= 0) pickIndex(index);
  };
  $("empty-open").hidden = !!issue;
  $("empty-add").hidden = !issue;
  $("empty-hint").textContent = issue
    ? "Drop comic images here or add an essay."
    : "Open a comics folder or start with an essay.";
  $("save-project").disabled = !issue;
  $("rescan").disabled = !issue;
  if (!issue) {
    $("empty").hidden = false;
    for (const id of ["prev", "next", "up", "down", "export"])
      $(id).disabled = true;
    return;
  }
  $("issue-title").textContent = issue.title;
  $("trim").textContent = issue.width + " × " + issue.height + " in";
  $("count").textContent = String(issue.pages.length);
  $("location").textContent = issue.folder;
  $("location").title = issue.folder;
  $("pages").replaceChildren(
    ...issue.pages.map((p, index) => {
      const row = button("", () => pickIndex(index));
      row.className = "page-row";
      row.title = pageName(p);
      if (index === selected) row.setAttribute("aria-current", "page");
      const words = el("span");
      words.append(
        el("strong", pageName(p)),
        el("small", roles[p.kind] + (p.part > 1 ? " · continued" : "")),
      );
      row.append(el("span", String(index + 1), "mini"), words);
      const li = el("li");
      li.append(row);
      return li;
    }),
  );
  $("no-pages").hidden = !!page;
  $("empty").hidden = !!page;
  $("prev").disabled = !page || !selected;
  $("next").disabled = !page || selected === issue.pages.length - 1;
  $("export").disabled = !page;
  const order =
    item && !["generated", "alignment"].includes(page.kind)
      ? issue.items.indexOf(item)
      : -1;
  $("up").disabled = order < 1;
  $("down").disabled = order < 0 || order === issue.items.length - 1;
  $("position").textContent = page
    ? "Page " + (selected + 1) + " of " + issue.pages.length
    : "No pages";
  const preview = $("preview");
  if (page) {
    const url =
      "/api/page?project=" +
      issue.id +
      "&revision=" +
      issue.revision +
      "&index=" +
      selected;
    if (preview.getAttribute("src") !== url) {
      preview.hidden = true;
      $("preview-status").textContent = "Rendering page…";
      preview.onload = () => {
        preview.hidden = false;
        $("preview-status").textContent = "";
      };
      preview.onerror = () => {
        preview.hidden = true;
        $("preview-status").textContent =
          "Preview unavailable. Check the issue assets and reload.";
      };
      preview.src = url;
    }
  } else {
    preview.removeAttribute("src");
    preview.hidden = true;
    $("preview-status").textContent = "";
  }
  const pane = $("properties");
  pane.replaceChildren();
  if (!page) {
    pane.append(
      el("p", "Select a page to edit its artwork or text.", "subtle"),
    );
    return;
  }
  pane.append(el("h3", roles[page.kind]));
  if (page.kind === "alignment") {
    pane.append(
      el(
        "p",
        "This blank places the next comic on facing left and right pages.",
      ),
      button("Panel layout…", () => panelDialog(item)),
    );
    return;
  }
  if (page.kind === "generated") {
    pane.append(
      property("Title", issue.title),
      el("p", "The cover uses the issue title and the first comic.", "subtle"),
      button("Edit issue setup…", setupDialog),
    );
  } else {
    pane.append(
      property(
        item.role === "essay" ? "Title" : "Source",
        item.name || item.title,
      ),
    );
    if (["cover", "back"].includes(item.role))
      pane.append(button("Cover assistant…", () => coverAssistant(item), true));
    if (issue.essay_proofs?.[item.id])
      pane.append(
        el(
          "p",
          "This image appears to repeat the essay “" +
            issue.essay_proofs[item.id] +
            "”. Review the page, then use Remove from issue to keep just the editable essay.",
        ),
      );
    if (item.role === "comic")
      pane.append(button("Panel layout…", () => panelDialog(item)));
    if (item.size)
      pane.append(
        property("Original size", item.size.join(" × ") + " px"),
        property(
          "Framing",
          item.crop
            ? "Custom crop"
            : ["cover", "back", "ad"].includes(item.role) &&
                item.fit === "contain"
              ? "Center full image"
              : fits[item.fit],
        ),
      );
    pane.append(
      button(
        item.role === "essay" ? "Edit essay…" : "Edit artwork…",
        () => (item.role === "essay" ? essayDialog(item) : artworkDialog(item)),
        !["cover", "back"].includes(item.role),
      ),
      button("Remove from issue…", () => removeDialog(item)),
    );
  }
}
function modal(title, html) {
  $("dialog-title").textContent = title;
  $("dialog-body").innerHTML =
    html + '<div role="alert" id="dialog-error"></div>';
  if (!$("dialog").open) $("dialog").showModal();
}
function actions(label, fn) {
  const bar = el("div", undefined, "actions");
  bar.append(
    button("Cancel", () => $("dialog").close()),
    button(label, fn, true),
  );
  $("dialog-body").append(bar);
}
function options(select, entries, value) {
  select.replaceChildren(
    ...Object.entries(entries).map(([key, text]) => new Option(text, key)),
  );
  select.value = value;
}
function setupDialog() {
  modal(
    "Issue setup",
    '<label>Issue title<input id="title" maxlength="160"></label><label>Trim size<select id="preset"></select></label><div class="pair"><label>Width (in)<input id="width" type="number" min="3" max="24" step=".01"></label><label>Height (in)<input id="height" type="number" min="3" max="24" step=".01"></label></div><label>Comic page style<select id="style"></select></label><label class="check"><input type="checkbox" id="cover">Generate a cover when none is supplied</label><label class="check"><input type="checkbox" id="numbers">Print page numbers on comics and essays</label>',
  );
  const presetKey = issue.width + "x" + issue.height;
  const presets = {
    "8.5x5.5": "Goosnav landscape · 8.5 × 5.5 in",
    "9x6": "Landscape · 9 × 6 in",
    "6x9": "Digest · 6 × 9 in",
    "8.5x11": "US Letter · 8.5 × 11 in",
    custom: "Custom",
  };
  options($("preset"), presets, presetKey in presets ? presetKey : "custom");
  $("title").value = issue.title;
  $("width").value = issue.width;
  $("height").value = issue.height;
  $("preset").onchange = () => {
    if ($("preset").value !== "custom") {
      [$("width").value, $("height").value] = $("preset").value.split("x");
    }
  };
  $("width").oninput = $("height").oninput = () =>
    ($("preset").value = "custom");
  options($("style"), styles, issue.style);
  $("cover").checked = issue.cover;
  $("numbers").checked = issue.numbers;
  actions("Save setup", () =>
    mutate("settings", {
      title: $("title").value,
      width: $("width").valueAsNumber,
      height: $("height").valueAsNumber,
      style: $("style").value,
      cover: $("cover").checked,
      numbers: $("numbers").checked,
    }),
  );
}
function essayDialog(item) {
  modal(
    item ? "Edit essay" : "Add essay",
    `
    <label>Essay title<input id="title" maxlength="160"></label>
    <label>Essay text<textarea id="body" rows="7" maxlength="150000"></textarea></label>
    <div class="pair"><label>Text size (pt)<input id="essay-size" type="number" min="7" max="24" step=".5" placeholder="Automatic"></label>
    <label class="check"><input id="drop-cap" type="checkbox">Blackletter initial</label></div>
    <fieldset><legend>Illustration</legend>
    <input type="file" id="essay-image" aria-label="Choose illustration" accept=".jpg,.jpeg,.png,.tif,.tiff,.webp,.bmp,.gif">
    <div id="essay-image-tools">
    <div class="pair"><label>Position<select id="image-side"><option value="right">Bottom right</option><option value="left">Bottom left</option></select></label>
    <label>Framing<select id="image-fit"><option value="contain">Show whole drawing</option><option value="fill">Crop to fill</option></select></label></div>
    <div class="pair"><label>Column width (%)<input id="image-width" type="number" min="10" max="100"></label>
    <label>Column height (%)<input id="image-height" type="number" min="10" max="70"></label></div>
    <div class="pair"><label>Zoom (%)<input id="image-zoom" type="number" min="100" max="250"></label>
    <label>Horizontal focus<input id="image-x" type="range" min="0" max="100"></label>
    <label>Vertical focus<input id="image-y" type="range" min="0" max="100"></label></div>
    <button id="remove-illustration">Remove illustration</button></div></fieldset>`,
  );
  $("title").value = item?.title || "";
  $("body").value = item?.body || "";
  $("essay-size").value = item?.font_size || "";
  $("drop-cap").checked = item?.drop_cap ?? true;
  let illustration = item?.illustration || null;
  const file = $("essay-image");
  function syncImage() {
    $("essay-image-tools").hidden = !illustration && !file.files.length;
  }
  file.onchange = syncImage;
  $("remove-illustration").onclick = () => {
    illustration = null;
    file.value = "";
    syncImage();
  };
  syncImage();
  for (const [key, fallback] of Object.entries({
    side: "right",
    fit: "contain",
    width: 100,
    height: 38,
    zoom: 100,
    x: 50,
    y: 50,
  })) {
    $("image-" + key).value = item?.["image_" + key] ?? fallback;
  }
  const saveLabel = item
    ? "Save essay"
    : issue
      ? "Add essay"
      : "Choose folder & save essay…";
  actions(saveLabel, () =>
    working("Saving essay…", async () => {
      for (const input of $("dialog-body").querySelectorAll("input"))
        if (!input.reportValidity()) return;
      if (!(await ensureIssue())) return;
      if (file.files.length) {
        const image = file.files[0];
        const q = new URLSearchParams({ name: image.name, project: issue.id });
        illustration = (
          await request("/api/illustration?" + q, {
            method: "POST",
            headers: { "X-Issue-Session": token },
            body: image,
          })
        ).asset;
      }
      const payload = {
        id: item?.id,
        title: $("title").value,
        body: $("body").value,
        illustration,
        font_size: $("essay-size").valueAsNumber || null,
        drop_cap: $("drop-cap").checked,
        image_side: $("image-side").value,
        image_fit: $("image-fit").value,
      };
      for (const key of ["width", "height", "zoom", "x", "y"])
        payload["image_" + key] = +$("image-" + key).value;
      const ids = new Set(issue.items.map((i) => i.id));
      adopt(await post(item ? "item" : "essay", payload));
      focusItem(item?.id || issue.items.find((i) => !ids.has(i.id)).id);
      latestExport = null;
      $("dialog").close();
      render();
    }),
  );
}
function artworkDialog(item) {
  modal(
    "Edit artwork",
    '<label>Page title<input id="title" maxlength="160"></label><div class="pair"><label>Page type<select id="role"></select></label><label>Rotation<select id="rotation"></select></label></div><label>Framing<select id="fit"></select></label><p class="subtle">Drag a rectangle on the original to set a custom crop.</p><div id="crop-surface"><img id="crop-image" draggable="false" alt="Original artwork for cropping"><span id="crop-box"></span></div><div class="crop-fields"></div><button id="reset-crop">Reset automatic crop</button>',
  );
  $("title").value = item.title;
  options(
    $("role"),
    {
      comic: "Comic",
      ad: "Advertisement",
      cover: "Front cover",
      back: "Back cover",
    },
    item.role,
  );
  options($("fit"), fits, item.fit);
  options(
    $("rotation"),
    { 0: "0°", 90: "90°", 180: "180°", 270: "270°" },
    String(item.rotate),
  );
  const surface = $("crop-surface"),
    box = $("crop-box");
  $("crop-image").src = "/api/art?project=" + issue.id + "&id=" + item.id;
  let crop = item.crop?.slice() || null,
    start;
  const fields = ["Left", "Top", "Right", "Bottom"].map((name, index) => {
    const label = el("label", name + " %"),
      input = el("input");
    input.type = "number";
    input.min = "0";
    input.max = "100";
    input.step = ".1";
    input.oninput = () => {
      const arr = effective().slice();
      arr[index] = input.valueAsNumber / 100;
      crop = arr;
      drawBox(false);
    };
    label.append(input);
    document.querySelector(".crop-fields").append(label);
    return input;
  });
  function effective() {
    if (crop) return crop;
    return $("fit").value !== "original" && $("role").value === "comic"
      ? item.auto
      : [0, 0, 1, 1];
  }
  function drawBox(sync = true) {
    const [l, t, r, b] = effective();
    Object.assign(box.style, {
      left: l * 100 + "%",
      top: t * 100 + "%",
      width: (r - l) * 100 + "%",
      height: (b - t) * 100 + "%",
    });
    if (sync)
      fields.forEach(
        (field, i) => (field.value = +(effective()[i] * 100).toFixed(2)),
      );
  }
  function point(event) {
    const rect = surface.getBoundingClientRect();
    return [
      (event.clientX - rect.left) / rect.width,
      (event.clientY - rect.top) / rect.height,
    ].map((v) => Math.max(0, Math.min(1, v)));
  }
  surface.onpointerdown = (event) => {
    if (event.button !== 0) return;
    start = point(event);
    surface.setPointerCapture(event.pointerId);
  };
  surface.onpointermove = (event) => {
    if (!start) return;
    const [x, y] = point(event);
    crop = [
      Math.min(x, start[0]),
      Math.min(y, start[1]),
      Math.max(x, start[0]),
      Math.max(y, start[1]),
    ];
    drawBox();
  };
  surface.onpointerup = surface.onpointercancel = () => (start = null);
  $("reset-crop").onclick = () => {
    crop = null;
    drawBox();
  };
  $("fit").onchange = $("role").onchange = () => drawBox();
  drawBox();
  actions("Apply edits", () =>
    mutate(
      "item",
      {
        id: item.id,
        title: $("title").value,
        role: $("role").value,
        fit: $("fit").value,
        rotate: Number($("rotation").value),
        crop,
      },
      item.id,
    ),
  );
}
function removeDialog(item) {
  modal("Remove from issue", '<p id="remove-text"></p>');
  $("remove-text").textContent =
    "Remove “" +
    item.title +
    "” from this issue? The original file stays in your folder.";
  actions("Remove item", () => mutate("remove", { id: item.id }));
}
// Called from an editor action only. Cancelling keeps the draft dialog open.
async function ensureIssue() {
  if (issue) return true;
  const folder = await post("pick");
  if (!folder.key) return false;
  adopt(await post("open", { source: folder.key }));
  render();
  return true;
}
$("save-project").onclick = () =>
  working("Saving project file…", async () => {
    const result = await post("save-project");
    modal(
      "Project file saved",
      '<p>Your editable issue and its original artwork are saved together.</p><p class="path" id="saved-project-path"></p>',
    );
    $("saved-project-path").textContent = result.path;
    $("dialog-body").append(button("Done", () => $("dialog").close(), true));
  });
$("open-project").onclick = () =>
  working("Opening project file…", async () => {
    const data = await post("open-project");
    if (data.cancelled) return;
    adopt(data);
    selected = 0;
    latestExport = null;
    render();
  });
function openDialog() {
  modal(
    "Open comics folder",
    '<label>Comics folder<button id="pick-source">Choose folder…</button></label><span class="path" id="source-path"></span><label>Save issue and exports in<button id="pick-output">Choose another location…</button></label><span class="path" id="output-path">Inside the comics folder</span>',
  );
  let source, destination;
  async function pick(isSource) {
    await working("Choosing folder…", async () => {
      const picked = await post("pick");
      if (!picked.key) return;
      if (isSource) {
        source = picked.key;
        $("source-path").textContent = picked.path;
      } else {
        destination = picked.key;
        $("output-path").textContent = picked.path;
      }
    });
  }
  $("pick-source").onclick = () => pick(true);
  $("pick-output").onclick = () => pick(false);
  actions("Open issue", () => {
    if (!source) {
      message("Choose the comics folder first.");
      return;
    }
    working("Opening comics…", async () => {
      adopt(await post("open", { source, destination }));
      selected = 0;
      latestExport = null;
      render();
      $("dialog").close();
    });
  });
}
function exportDialog() {
  modal(
    "Export issue",
    '<div id="export-summary"></div><p class="subtle">Creates a print PDF, a smaller digital PDF, and a website folder you can upload to a static host.</p><div class="path" id="export-path"></div><div id="export-results"></div>',
  );
  $("export-summary").textContent =
    issue.title +
    " · " +
    issue.pages.length +
    " pages · " +
    issue.width +
    " × " +
    issue.height +
    " in";
  $("export-path").textContent = issue.folder + "/exports";
  function showResult(result) {
    const list = el("ul");
    for (const [filename, label] of [
      ["print.pdf", "Open print PDF"],
      ["digital.pdf", "Open digital PDF"],
      ["website/index.html", "Open web edition"],
    ]) {
      const a = el("a", label);
      a.href = result.url + "/" + filename;
      a.target = "_blank";
      a.rel = "noopener";
      const li = el("li");
      li.append(a);
      list.append(li);
    }
    const reveal = button("Show export folder", () =>
      working("Opening export folder…", () =>
        post("reveal", { run: result.url.split("/").pop() }),
      ),
    );
    $("export-results").replaceChildren(list, reveal);
    $("export-path").textContent = result.path;
  }
  if (latestExport) showResult(latestExport);
  const bar = el("div", undefined, "actions");
  const make = button(
    "Generate editions",
    () =>
      working("Generating editions…", async () => {
        make.textContent = "Generating editions…";
        const job = crypto.randomUUID(),
          stop = $("stop-export");
        $("export-monitor").hidden = false;
        $("export-progress").textContent = "Preparing pages…";
        stop.disabled = false;
        stop.onclick = async () => {
          stop.disabled = true;
          try {
            await post("cancel-export", { job });
          } catch (err) {
            message(err.message);
            stop.disabled = false;
          }
        };
        const timer = setInterval(async () => {
          try {
            const data = await request("/api/export-progress?job=" + job);
            if (data.status) $("export-progress").textContent = data.status;
          } catch {
            /* The export request reports any connection failure. */
          }
        }, 700);
        try {
          latestExport = await post("export", { job });
          showResult(latestExport);
        } finally {
          clearInterval(timer);
          $("export-monitor").hidden = true;
          make.textContent = "Generate editions";
        }
      }),
    true,
  );
  bar.append(
    button("Close", () => $("dialog").close()),
    make,
  );
  $("dialog-body").append(bar);
}
async function upload(fileList, asCover = false) {
  const files = Array.from(fileList).sort((a, b) =>
    a.name.localeCompare(b.name, undefined, { numeric: true }),
  );
  if (!files.length) return;
  await working("Importing files…", async () => {
    const errors = [];
    if (!(await ensureIssue())) return;
    const wasEmpty = !issue.pages.length;
    let coverId;
    for (const [index, file] of files.entries()) {
      $("status").textContent =
        "Importing " + (index + 1) + " of " + files.length + "…";
      const params = new URLSearchParams({
        name: file.name,
        revision: String(issue.revision),
        project: issue.id,
      });
      if (asCover) params.set("role", "cover");
      try {
        const data = await request("/api/upload?" + params, {
          method: "POST",
          headers: { "X-Issue-Session": token },
          body: file,
        });
        adopt(data);
        if (asCover) coverId = data.imported_id;
      } catch (err) {
        errors.push(file.name + " — " + err.message);
      }
    }
    if (wasEmpty) selected = 0;
    if (coverId) focusItem(coverId);
    latestExport = null;
    render();
    note(errors.join("\n"));
    if (coverId) coverAssistant(itemFor(current()));
    $("files").value = "";
  });
}
$("add").onclick = $("empty-add").onclick = () => $("files").click();
$("add-cover").onclick = () => {
  $("cover-file").value = "";
  $("cover-file").click();
};
$("cover-file").onchange = () => upload($("cover-file").files, true);
$("files").onchange = () => upload($("files").files);
$("drop").ondragover = (e) => {
  e.preventDefault();
  $("drop").classList.add("dragging");
};
$("drop").ondragleave = () => $("drop").classList.remove("dragging");
$("drop").ondrop = (e) => {
  e.preventDefault();
  $("drop").classList.remove("dragging");
  upload(e.dataTransfer.files);
};
$("up").onclick = () => move(-1);
$("down").onclick = () => move(1);
function move(delta) {
  const item = itemFor(current());
  return mutate(
    "move",
    { id: item.id, index: issue.items.indexOf(item) + delta },
    item.id,
  );
}
$("prev").onclick = () => pickIndex(selected - 1);
$("next").onclick = () => pickIndex(selected + 1);
$("setup").onclick = () => {
  if (issue) setupDialog();
  else
    working("Opening issue…", async () => {
      if (await ensureIssue()) setupDialog();
    });
};
$("essay").onclick = () => essayDialog();
$("export").onclick = exportDialog;
$("empty-open").onclick = $("open").onclick = openDialog;
$("rescan").onclick = () =>
  working("Scanning folder…", async () => {
    const before = issue.items.length;
    adopt(await post("scan"));
    render();
    latestExport = null;
    note(
      [
        issue.items.length - before + " new items imported.",
        ...issue.warnings,
      ].join("\n"),
    );
  });
$("close").onclick = () => $("dialog").close();
$("dialog").oncancel = (e) => {
  if (busy) e.preventDefault();
};
$("help").onclick = () =>
  modal(
    "Using Zine Maker",
    "<p>Open a folder of comics or drop files onto the page preview. Numbered filenames determine the initial comic order.</p><p>Use <b>Issue setup</b> to change trim size, borders, page numbers, and the cover. Choose a page and use <b>Edit artwork</b> to correct its crop.</p><p>Put optional ads in an <b>ads</b> folder, essays in <b>essays</b>, and name cover images <b>cover</b> or <b>back-cover</b>. Plain text essays paginate automatically.</p><p><b>Export issue</b> creates both PDFs and a static web edition. The status bar shows where the editable issue is saved.</p>",
  );
document.addEventListener("keydown", (e) => {
  if (
    !issue ||
    $("dialog").open ||
    busy ||
    !issue.pages.length ||
    e.altKey ||
    e.metaKey ||
    e.ctrlKey
  )
    return;
  if (e.target.closest?.("input,textarea,select,[contenteditable=true]"))
    return;
  if (["ArrowUp", "ArrowLeft"].includes(e.key) && selected > 0) {
    e.preventDefault();
    pickIndex(selected - 1);
  }
  if (
    ["ArrowDown", "ArrowRight"].includes(e.key) &&
    selected < issue.pages.length - 1
  ) {
    e.preventDefault();
    pickIndex(selected + 1);
  }
});
working("Opening issue…", async () => {
  adopt(await request("/api/state"));
  render();
});
