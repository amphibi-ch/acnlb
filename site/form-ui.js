/* The item builder: a table of draft items, an editor for one of them, and an
 * export that produces the files `acnlb new --intake` would have written.
 *
 * All the parsing, validating and packaging lives in item-form.js, which is
 * DOM-free and checked against the Python it mirrors. This file only moves
 * strings between that module and the page.
 *
 * Read-only guests of the page are unaffected: nothing here runs until the
 * section is present, and nothing is sent anywhere. Drafts live in
 * localStorage; the export is a download.
 */
(function () {
  "use strict";

  var F = window.ACNLBForm;
  if (!F) return;

  var SCHEMA = null;
  var ROWS = [];
  var LANG = "en";
  var editing = null;
  var DRAFT_KEY = "acnlb-draft-v1";
  var DEFAULT_RUBRIC_TEXT = "";

  /* ---------- copy ---------- */

  var T = {
    zh: {
      addRow: "新增一条",
      addBlank: "追加空行",
      importOpen: "粘贴 / 导入",
      exportZip: "导出全部（.zip）",
      clear: "清空草稿",
      name: "题集名",
      rowsHead: ["编号", "轨道", "任务类型", "任务", "得分点", "状态", ""],
      empty: "还没有草稿条目。点「新增一条」，或把已有的 intake 表单粘进「粘贴 / 导入」。",
      ok: "通过",
      errN: function (n) { return n + " 处错误"; },
      edit: "编辑",
      dup: "复制",
      del: "删除",
      close: "收起",
      id: "编号 id", track: "轨道", category: "类别 category",
      taskType: "任务类型 task_type", task: "任务 task",
      jurisdiction: "管辖 jurisdiction", hasContext: "有附件 has_context",
      documents: "附件路径（每行一个，相对 items 目录）",
      authority: "法源依据 authority_basis（逗号／顿号分隔）",
      notes: "备注 notes", prompt: "Prompt（模型收到的原话）",
      gold: "参考答案 gold answer", rubric: "Rubric",
      fillSkeleton: "填入骨架",
      retrievalClass: "检索类别 class", retrievalItems: "检索基准（每行：层级 | 依据 | 说明）",
      tierHint: "层级只能取 ",
      intake: "导出 INTAKE.md", files: "下载三件套", copyJson: "复制 JSON",
      checkOk: "校验通过，等同于 acnlb new 会写出的文件。",
      checkLint: "可作为草稿导出；注意：",
      importTitle: "批量导入",
      importHint: "把一份或多份 intake 表单粘进来。多条时每条以 `id:` 开头，或用单独一行 `%%%` 分隔。也可以选择本地 .md / .json 文件。",
      importGo: "导入",
      pickFiles: "选择文件…",
      imported: function (n) { return "导入 " + n + " 条。"; },
      nothingImported: "没解析出任何条目。",
      skipped: function (n) { return "跳过 " + n + " 条无法解析的表单："; },
      exportedZip: function (n, f) { return "已导出 " + n + " 条（" + f + " 个文件）。"; },
      allBad: "没有可导出的条目——先修掉校验错误。",
      rejected: "以下条目校验未过，未导出：",
      copied: "已复制到剪贴板。",
      copyFail: "复制失败，请手动选中。",
      unavailable: "录入器未加载：取不到 schema.json。部署后的站点上可用；本地预览请先跑 python tools/build_site_schema.py。",
      confirmClear: "清空全部草稿？此操作不可撤销。",
      draftSaved: function (n) { return "草稿 " + n + " 条，已存在本机浏览器。"; },
      noSchema: "schema 未加载",
      docsWarn: "记得把附件一起放进 items 目录。"
    },
    en: {
      addRow: "Add item",
      addBlank: "Add blank rows",
      importOpen: "Paste / import",
      exportZip: "Export all (.zip)",
      clear: "Clear draft",
      name: "Set name",
      rowsHead: ["ID", "Track", "Task type", "Task", "Points", "State", ""],
      empty: "No draft items yet. Use “Add item”, or paste existing intake forms under “Paste / import”.",
      ok: "ok",
      errN: function (n) { return n + " error(s)"; },
      edit: "Edit",
      dup: "Duplicate",
      del: "Delete",
      close: "Collapse",
      id: "id", track: "track", category: "category",
      taskType: "task_type", task: "task",
      jurisdiction: "jurisdiction", hasContext: "has_context",
      documents: "Document paths (one per line, relative to the items dir)",
      authority: "authority_basis (comma separated)",
      notes: "notes", prompt: "Prompt (the exact text the model receives)",
      gold: "Gold answer", rubric: "Rubric",
      fillSkeleton: "Fill with skeleton",
      retrievalClass: "Retrieval class", retrievalItems: "Retrieval gold (one per line: tier | ref | note)",
      tierHint: "tiers: ",
      intake: "Export INTAKE.md", files: "Download 3 files", copyJson: "Copy JSON",
      checkOk: "Valid — identical to what `acnlb new` writes.",
      checkLint: "Exportable as a draft; note: ",
      importTitle: "Bulk import",
      importHint: "Paste one or more intake forms. Each extra form starts at an `id:` line, or after a lone `%%%` line. Local .md / .json files work too.",
      importGo: "Import",
      pickFiles: "Choose files…",
      imported: function (n) { return "Imported " + n + " item(s)."; },
      nothingImported: "No items parsed.",
      skipped: function (n) { return "Skipped " + n + " unparseable form(s): "; },
      exportedZip: function (n, f) { return "Exported " + n + " item(s), " + f + " file(s)."; },
      allBad: "Nothing to export — fix the validation errors first.",
      rejected: "Not exported (validation failed):",
      copied: "Copied.",
      copyFail: "Copy failed; select the text manually.",
      unavailable: "Builder unavailable: schema.json not found. Present on the deployed site; for local preview run python tools/build_site_schema.py.",
      confirmClear: "Clear the whole draft? This cannot be undone.",
      draftSaved: function (n) { return n + " draft item(s), stored in this browser."; },
      noSchema: "schema not loaded",
      docsWarn: "Remember to put the attachments in the items dir too."
    }
  };

  function tx(k) { var v = T[LANG][k]; return typeof v === "function" ? v.apply(null, [].slice.call(arguments, 1)) : v; }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  /* ---------- row model ---------- */

  function blankRow(over) {
    var row = {
      id: "", track: "core", category: "", task_type: "", task: "",
      jurisdiction: "CN-mainland", has_context: false,
      authority_basis_text: "", notes: "",
      prompt: "", documents: [], gold: "", rubric: "",
      retrieval_class: "statute", retrieval_items: []
    };
    Object.keys(over || {}).forEach(function (k) { row[k] = over[k]; });
    return row;
  }

  function rowIntake(row) { return F.parseIntake(F.rowToIntake(row), SCHEMA); }

  function checkRow(row) {
    if (!SCHEMA) return { ok: false, errors: [tx("noSchema")], lint: [], built: null };
    var built = F.buildItem(rowIntake(row), { schema: SCHEMA });
    if (!built.ok) return { ok: false, errors: built.errors, lint: [], built: null };
    return { ok: true, errors: [], lint: F.lintItem(built, SCHEMA), built: built };
  }

  /* ---------- persistence ---------- */

  function saveDraft() {
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify(ROWS)); } catch (e) {}
    var note = document.getElementById("draft-state");
    if (note) note.textContent = tx("draftSaved", ROWS.length);
  }

  function loadDraft() {
    try {
      var raw = localStorage.getItem(DRAFT_KEY);
      if (raw) {
        var parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) ROWS = parsed.map(function (r) { return blankRow(r); });
      }
    } catch (e) { ROWS = []; }
  }

  /* ---------- file plumbing ---------- */

  function download(name, data, mime) {
    var blob = data instanceof Uint8Array
      ? new Blob([data], { type: mime || "application/zip" })
      : new Blob([data], { type: mime || "text/plain;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = el("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
  }

  function log(lines, isError) {
    var box = document.getElementById("builder-log");
    if (!box) return;
    box.textContent = "";
    box.hidden = lines.length === 0;
    box.className = "log" + (isError ? " log-bad" : " log-ok");
    lines.forEach(function (l) { box.appendChild(el("div", null, l)); });
  }

  /* ---------- rows table ---------- */

  function renderRows() {
    var body = document.getElementById("rows-body");
    if (!body) return;
    body.textContent = "";
    if (!ROWS.length) {
      body.appendChild(el("p", "muted", tx("empty")));
      return;
    }
    var table = el("table", "items-table draft-table");
    var head = el("thead");
    var htr = document.createElement("tr");
    tx("rowsHead").forEach(function (label) {
      htr.appendChild(el("th", null, label));
    });
    head.appendChild(htr);
    table.appendChild(head);

    var tb = el("tbody");
    ROWS.forEach(function (row) {
      var res = checkRow(row);
      var tr = document.createElement("tr");
      tr.appendChild(el("td", "mono", row.id || "—"));
      tr.appendChild(el("td", null, (SCHEMA && SCHEMA.track_labels[row.track]) || row.track));
      tr.appendChild(el("td", null, row.task_type || "—"));
      var task = el("td");
      task.appendChild(el("div", "cell-main", row.task || "—"));
      tr.appendChild(task);
      tr.appendChild(el("td", "num", res.ok ? String(res.built.item.max_positive_points) : "—"));

      var state = el("td");
      state.appendChild(el("span", "pill " + (res.ok ? (res.lint.length ? "pill-warn" : "pill-ok") : "pill-bad"),
        res.ok ? (res.lint.length ? res.lint.length + " ⚠" : tx("ok")) : tx("errN", res.errors.length)));
      tr.appendChild(state);

      var ops = el("td", "row-ops");
      [["edit", function () { openEditor(row); }],
       ["dup", function () { ROWS.push(blankRow(JSON.parse(JSON.stringify(row)))); renderRows(); saveDraft(); }],
       ["del", function () { ROWS.splice(ROWS.indexOf(row), 1); if (editing === row) closeEditor(); renderRows(); saveDraft(); }]
      ].forEach(function (pair) {
        var b = el("button", "link-btn", tx(pair[0]));
        b.type = "button";
        b.addEventListener("click", pair[1]);
        ops.appendChild(b);
      });
      tr.appendChild(ops);
      tb.appendChild(tr);
    });
    table.appendChild(tb);

    var wrap = el("div", "table-wrap");
    wrap.appendChild(table);
    body.appendChild(wrap);
  }

  /* ---------- editor ---------- */

  function field(label, node, hint) {
    var f = el("label", "field");
    f.appendChild(el("span", "field-k", label));
    f.appendChild(node);
    if (hint) f.appendChild(el("span", "field-h", hint));
    return f;
  }

  function input(field_, type) {
    var n = document.createElement(type === "area" ? "textarea" : "input");
    if (type !== "area") n.type = type || "text";
    else n.rows = 8;
    n.setAttribute("data-field", field_);
    return n;
  }

  function openEditor(row) {
    editing = row;
    var host = document.getElementById("row-editor");
    if (!host) return;
    host.hidden = false;
    host.textContent = "";

    var res = checkRow(row);

    var bar = el("div", "editor-bar");
    bar.appendChild(el("h3", null, row.id || "（未填 id）"));
    var close = el("button", "link-btn", tx("close"));
    close.type = "button";
    close.addEventListener("click", closeEditor);
    bar.appendChild(close);
    host.appendChild(bar);

    var grid = el("div", "grid");
    var text = ["id", "category", "task_type", "task", "jurisdiction", "authority_basis_text", "notes"];
    text.forEach(function (key) {
      var n = input(key, key === "notes" ? "area" : "text");
      n.value = row[key] || "";
      if (key === "notes") n.rows = 3;
      grid.appendChild(field(tx(key === "authority_basis_text" ? "authority" : key), n));
    });

    var trackSel = document.createElement("select");
    trackSel.setAttribute("data-field", "track");
    (SCHEMA ? SCHEMA.valid_tracks : ["core", "workflows", "retrieval"]).forEach(function (t) {
      var o = document.createElement("option");
      o.value = t;
      o.textContent = t + (SCHEMA && SCHEMA.track_labels[t] ? "  ·  " + SCHEMA.track_labels[t] : "");
      trackSel.appendChild(o);
    });
    trackSel.value = row.track;
    grid.appendChild(field(tx("track"), trackSel));

    var ctx = document.createElement("input");
    ctx.type = "checkbox";
    ctx.setAttribute("data-field", "has_context");
    ctx.checked = !!row.has_context;
    grid.appendChild(field(tx("hasContext"), ctx));
    host.appendChild(grid);

    var docs = input("documents", "area");
    docs.rows = 3;
    docs.value = (row.documents || []).join("\n");
    host.appendChild(field(tx("documents"), docs));

    var promptArea = input("prompt", "area");
    promptArea.value = row.prompt || "";
    host.appendChild(field(tx("prompt"), promptArea));

    var goldArea = input("gold", "area");
    goldArea.value = row.gold || "";
    host.appendChild(field(tx("gold"), goldArea));

    var rubricHead = el("div", "field-k");
    rubricHead.appendChild(document.createTextNode(tx("rubric")));
    var skeletonBtn = el("button", "link-btn", tx("fillSkeleton"));
    skeletonBtn.type = "button";
    skeletonBtn.addEventListener("click", function () {
      var tpl = (SCHEMA && SCHEMA.default_rubric) || DEFAULT_RUBRIC_TEXT;
      row.rubric = F.defaultRubric(SCHEMA, row.id || "<id>", row.task || "<task>");
      rubricArea.value = row.rubric;
      refresh();
    });
    rubricHead.appendChild(document.createTextNode("  "));
    rubricHead.appendChild(skeletonBtn);
    var rubricWrap = el("div", "field");
    rubricWrap.appendChild(rubricHead);
    var rubricArea = input("rubric", "area");
    rubricArea.className = "mono-area";
    rubricArea.rows = 14;
    rubricArea.value = row.rubric || "";
    rubricWrap.appendChild(rubricArea);
    rubricWrap.appendChild(el("span", "field-h",
      (SCHEMA ? SCHEMA.negatives.map(function (n) { return "[" + n.code + "]"; }).join(" ") : "")));
    host.appendChild(rubricWrap);

    var retrievalWrap = el("div", "field retrieval-fields");
    if (row.track !== "retrieval") retrievalWrap.hidden = true;
    if (row.track === "retrieval") {
      var classSel = document.createElement("select");
      classSel.setAttribute("data-field", "retrieval_class");
      ((SCHEMA && SCHEMA.retrieval_classes) || ["statute", "similar_case", "document"]).forEach(function (c) {
        var o = document.createElement("option");
        o.value = c;
        o.textContent = c;
        classSel.appendChild(o);
      });
      classSel.value = row.retrieval_class || "statute";
      retrievalWrap.appendChild(field(tx("retrievalClass"), classSel));

      var itemsArea = input("retrieval_items", "area");
      itemsArea.rows = 4;
      itemsArea.value = (row.retrieval_items || []).map(function (g) {
        return g.tier + " | " + g.ref + " | " + (g.note || "");
      }).join("\n");
      retrievalWrap.appendChild(field(tx("retrievalItems"), itemsArea,
        tx("tierHint") + ((SCHEMA && SCHEMA.valid_tiers) || []).join(" / ")));
    }
    host.appendChild(retrievalWrap);

    var check = el("div", "editor-check");
    host.appendChild(check);

    var tools = el("div", "editor-tools");
    [["intake", function () {
        download((row.id || "item") + ".intake.md", F.rowToIntake(row));
      }],
     ["files", function () {
        var r = checkRow(row);
        if (!r.ok) return log(r.errors, true);
        F.assembleFiles(r.built).forEach(function (f) {
          download(f.name.split("/").pop(), f.data);
        });
        log([tx("checkOk")], false);
      }],
     ["copyJson", function () {
        var r = checkRow(row);
        if (!r.ok) return log(r.errors, true);
        var text = JSON.stringify(r.built.item, null, 2) + "\n";
        if (navigator.clipboard) {
          navigator.clipboard.writeText(text).then(function () { log([tx("copied")], false); },
            function () { log([tx("copyFail")], true); });
        } else {
          log([tx("copyFail")], true);
        }
      }]
    ].forEach(function (pair) {
      var b = el("button", "btn btn-line btn-sm", tx(pair[0]));
      b.type = "button";
      b.addEventListener("click", pair[1]);
      tools.appendChild(b);
    });
    host.appendChild(tools);

    var logBox = document.getElementById("builder-log");
    if (logBox) logBox.hidden = true;

    function refresh() {
      var r = checkRow(row);
      check.textContent = "";
      if (r.ok) {
        check.className = "editor-check check-ok";
        check.appendChild(el("div", null, tx("checkOk")));
        r.lint.forEach(function (l) { check.appendChild(el("div", "check-warn", tx("checkLint") + l)); });
      } else {
        check.className = "editor-check check-bad";
        r.errors.forEach(function (e) { check.appendChild(el("div", null, e)); });
      }
      var title = host.querySelector("h3");
      if (title) title.textContent = row.id || "（未填 id）";
    }

    function bind(node) {
      var key = node.getAttribute("data-field");
      var handler = function () {
        if (key === "has_context") row[key] = node.checked;
        else if (key === "documents") row.documents = node.value.split("\n").map(function (s) { return s.trim(); })
          .filter(function (s) { return s.length > 0; });
        else if (key === "retrieval_items") row.retrieval_items = parseGoldLines(node.value);
        else if (key === "track") { row.track = node.value; saveDraft(); openEditor(row); return; }
        else row[key] = node.value;
        saveDraft();
        refresh();
      };
      node.addEventListener("input", handler);
      node.addEventListener("change", handler);
    }

    host.querySelectorAll("[data-field]").forEach(bind);
    refresh();
  }

  function parseGoldLines(text) {
    var out = [];
    text.split("\n").forEach(function (line) {
      var s = line.trim();
      if (!s) return;
      var parts = s.split("|").map(function (p) { return p.trim(); });
      if (parts.length < 2) return;
      out.push({ tier: parts[0], ref: parts[1], note: parts.length > 2 ? parts[2] : "" });
    });
    return out;
  }

  function closeEditor() {
    editing = null;
    var host = document.getElementById("row-editor");
    if (host) { host.hidden = true; host.textContent = ""; }
    renderRows();
    saveDraft();
  }

  /* ---------- import ---------- */

  function importFromText(text) {
    if (!SCHEMA) return log([tx("unavailable")], true);
    var blocks = F.parseIntakeBlocks(text, SCHEMA);
    var added = 0;
    var skipped = [];
    blocks.forEach(function (b) {
      var row = F.intakeToRow(b.intake);
      if (!row.id && !row.task && !row.prompt) { skipped.push("（空白表单）"); return; }
      var res = checkRow(row);
      if (!res.ok && b.intake.errors.length) {
        skipped.push((row.id || "（未填 id）") + "：" + b.intake.errors.join("；"));
        return;
      }
      ROWS.push(row);
      added++;
    });
    renderRows();
    saveDraft();
    var lines = [tx("imported", added)];
    if (skipped.length) {
      lines.push(tx("skipped", skipped.length));
      skipped.slice(0, 8).forEach(function (s) { lines.push("  · " + s); });
    }
    log(lines, skipped.length > 0);
    return added;
  }

  function importFiles(files) {
    var pending = files.length;
    if (!pending) return;
    var mode = document.querySelector('input[name="import-mode"]:checked');
    var replace = mode && mode.value === "replace";
    if (replace) { ROWS = []; closeEditor(); }
    Array.prototype.forEach.call(files, function (file) {
      var reader = new FileReader();
      reader.onload = function () {
        var text = String(reader.result || "");
        if (/\.json$/i.test(file.name)) {
          try {
            var parsed = JSON.parse(text);
            var docs = parsed.items || (Array.isArray(parsed) ? parsed : [parsed]);
            docs.forEach(function (item) {
              ROWS.push(blankRow({
                id: item.id || "", track: item.track || "core", category: item.category || "",
                task_type: item.task_type || "", task: item.task || "",
                jurisdiction: item.jurisdiction || "CN-mainland",
                has_context: !!item.has_context,
                authority_basis_text: (item.authority_basis || []).join(", "),
                notes: item.notes || "", prompt: item.prompt || "",
                documents: (item.documents || []).map(function (d) { return typeof d === "string" ? d : d.path; }),
                gold: item._gold_text || "", rubric: item._rubric_text || "",
                retrieval_class: (item.retrieval_gold || {})["class"] || "statute",
                retrieval_items: ((item.retrieval_gold || {}).gold_items || []).map(function (g) {
                  return { tier: g.tier, ref: g.ref, note: g.note || "" };
                })
              }));
            });
          } catch (e) {
            log(["无法解析 " + file.name + "：" + e.message], true);
          }
        } else {
          importFromText(text);
        }
        if (--pending === 0) { renderRows(); saveDraft(); }
      };
      reader.readAsText(file, "utf-8");
    });
  }

  /* ---------- export ---------- */

  function exportAll() {
    if (!SCHEMA) return log([tx("unavailable")], true);
    var nameInput = document.getElementById("export-name");
    var name = (nameInput && nameInput.value.trim()) || "draft";
    var entries = [];
    var rejected = [];
    var good = 0;
    ROWS.forEach(function (row) {
      var res = checkRow(row);
      if (!res.ok) { rejected.push((row.id || "（未填 id）") + "：" + res.errors.join("；")); return; }
      F.assembleFiles(res.built).forEach(function (f) { entries.push(f); });
      good++;
    });
    if (!entries.length) return log([tx("allBad")].concat(rejected), true);

    entries.push({
      name: "EXPORT.txt",
      data: [
        "acnlb item draft export",
        "",
        "Exported items: " + good,
        "Files: " + entries.length,
        "",
        "Drop this folder into items/<your-set>/ and run:",
        "  python -m acnlb validate --items items/" + name,
        ""
      ].join("\n")
    });
    if (rejected.length) {
      entries.push({ name: "EXPORT.rejected.txt", data: tx("rejected") + "\n\n" + rejected.join("\n") + "\n" });
    }
    download("acnlb-" + name + ".zip", F.makeZip(entries));

    var lines = [tx("exportedZip", good, entries.length)];
    if (rejected.length) {
      lines.push(tx("rejected"));
      rejected.forEach(function (r) { lines.push("  · " + r); });
    }
    log(lines, rejected.length > 0);
  }

  /* ---------- wiring ---------- */

  function bind() {
    var add = document.getElementById("row-add");
    if (add) add.addEventListener("click", function () {
      var row = blankRow();
      ROWS.push(row);
      renderRows();
      saveDraft();
      openEditor(row);
    });

    var bulk = document.getElementById("row-add-n");
    if (bulk) bulk.addEventListener("click", function () {
      var n = parseInt((document.getElementById("row-count") || {}).value, 10);
      if (!n || n < 1) n = 1;
      n = Math.min(n, 50);
      var tpl = document.getElementById("row-template");
      for (var i = 0; i < n; i++) {
        var row = blankRow();
        if (tpl && tpl.value.trim()) {
          var parsed = F.parseIntake(tpl.value, SCHEMA);
          row = F.intakeToRow(parsed);
          row.id = "";
        }
        ROWS.push(row);
      }
      renderRows();
      saveDraft();
    });

    var go = document.getElementById("import-go");
    if (go) go.addEventListener("click", function () {
      var area = document.getElementById("import-text");
      importFromText((area && area.value) || "");
    });

    var pick = document.getElementById("import-files");
    if (pick) pick.addEventListener("change", function () { importFiles(pick.files); });

    var exp = document.getElementById("row-export");
    if (exp) exp.addEventListener("click", exportAll);

    var clear = document.getElementById("row-clear");
    if (clear) clear.addEventListener("click", function () {
      if (!ROWS.length || window.confirm(tx("confirmClear"))) {
        ROWS = [];
        closeEditor();
        renderRows();
        saveDraft();
        log([], false);
      }
    });

    var toggle = document.getElementById("import-toggle");
    if (toggle) toggle.addEventListener("click", function () {
      var panel = document.getElementById("import-panel");
      if (panel) panel.hidden = !panel.hidden;
    });
  }

  function init() {
    var section = document.getElementById("contribute");
    if (!section) return;
    var status = document.getElementById("builder-status");
    fetch("schema.json", { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (s) {
        SCHEMA = s;
        DEFAULT_RUBRIC_TEXT = s.default_rubric || "";
        loadDraft();
        renderRows();
        bind();
        saveDraft();
      })
      .catch(function () {
        if (status) status.textContent = tx("unavailable");
        var bar = document.querySelector(".builder-bar");
        if (bar) bar.hidden = true;
      });
  }

  window.ACNLBFormUI = {
    init: init,
    setLang: function (lang) {
      LANG = lang === "zh" ? "zh" : "en";
      if (!SCHEMA) return;
      renderRows();
      if (editing) openEditor(editing);
      saveDraft();
    }
  };
})();
