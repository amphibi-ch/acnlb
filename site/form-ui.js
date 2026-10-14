/* The item builder: a table of draft items, an editor for one of them, and an
 * export that produces the files `acnlb new --intake` would have written.
 *
 * All the parsing, validating and packaging lives in item-form.js, which is
 * DOM-free and checked against the Python it mirrors. This file only moves
 * strings between that module and the page.
 *
 * Two other things arrive over the wire and are used as data, never re-typed:
 * `schema.json` (the vocabulary the CLI owns) and `items.json` (the values the
 * published set already uses — `vocab`). The second one is what makes the fields
 * concrete: a drafter picking 任务类型 from the ten the set already has cannot
 * invent an eleventh spelling that no report can group by. Every list still has
 * a free-text escape, because none of these fields is a constraint.
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
  var VOCAB = null;          // items.json.vocab — what the published set already uses
  var ROWS = [];
  var LANG = "en";
  var editing = null;
  var DRAFT_KEY = "acnlb-draft-v1";

  // The rubric editor's view of `editing.rubric`. "rows" is the table; the raw
  // textarea stays available because a rubric the row model cannot carry line for
  // line must not be silently shortened.
  var RUBRIC_MODE = "rows";
  var RUBRIC_ROWS = [];
  var RUBRIC_BLOCKED = [];

  // Sentinel values for the escape-hatch options. Neither can collide with a real
  // value in practice (`__` is not something a task type or a document path is
  // called), and both are stripped before anything is written.
  var CUSTOM = "__custom__";
  var CLEAR = "__clear__";

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
      jurisdiction: "管辖 jurisdiction",
      noId: "（未填 id）",
      idNext: "用下一个可用编号",
      idHint: "文件名，只能用字母数字与 . _ -",
      unset: "（未选）",
      custom: "自定义…",
      noVocab: "题集词汇未加载（items.json）：下拉是空的，直接手填即可。",
      ctxLine: function (n) {
        return "有附件 has_context: " + (n > 0 ? "true" : "false") + "（由附件数量推出，" + n + " 个路径）";
      },
      documents: "附件路径 documents",
      docsHint: "每行一个，相对 items 目录；新附件要随 PR 一起提交",
      docPick: "从已提交的附件里选…",
      authority: "法源依据 authority_basis",
      authorityHint: "逗号或顿号分隔；能从已有写法里选就选，能落到条号更好",
      notes: "备注 notes", prompt: "Prompt（模型收到的原话）",
      gold: "参考答案 gold answer",
      goldHint: "先写它，再写 rubric（设计稿 §3.6）；留空则写入 TODO 占位",
      rubric: "Rubric",
      startFrom: "起始模板",
      tplClear: "清空 rubric",
      modeRows: "表格",
      modeRaw: "原文",
      blockedRows: "这份 rubric 无法用表格完整表示，已切到原文模式：",
      sum: function (n) { return "得分上限 " + n; },
      kindAff: "得分点",
      kindNeg: "扣分点",
      colSection: "段",
      colSub: "小节",
      colPts: "分",
      colText: "内容",
      colCode: "代码",
      colOps: "",
      addPoint: "＋ 加得分点",
      addNeg: "＋ 加扣分点",
      rowsEmpty: "还没有得分点。先在上面套用轨道模板，或直接加一行。",
      retTitle: "检索基准（仅 retrieval 轨道）",
      retClass: "检索类别 class",
      retHead: ["层级", "依据", "说明", ""],
      retEmpty: "还没有检索基准。检索题至少要有一行。",
      retHint: "层级只能是",
      addGoldRow: "＋ 加一行",
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
      noRubricLayout: "schema.json 里没有 rubric 版式，表格模式不可用。",
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
      jurisdiction: "jurisdiction",
      noId: "(no id)",
      idNext: "Use the next free id",
      idHint: "a file name — letters, digits and . _ - only",
      unset: "(none)",
      custom: "Other…",
      noVocab: "Item-set vocabulary not loaded (items.json): the lists are empty, just type.",
      ctxLine: function (n) {
        return "has_context: " + (n > 0 ? "true" : "false") + " — derived from the document list (" + n + " path(s))";
      },
      documents: "Document paths",
      docsHint: "one per line, relative to the items dir; new files must be committed too",
      docPick: "Pick a document the set already ships…",
      authority: "authority_basis",
      authorityHint: "comma separated; prefer a spelling the set already uses, with an article number if you have one",
      notes: "notes", prompt: "Prompt (the exact text the model receives)",
      gold: "Gold answer",
      goldHint: "write it before the rubric (design doc §3.6); left blank, a TODO placeholder is written",
      rubric: "Rubric",
      startFrom: "Start from",
      tplClear: "Clear the rubric",
      modeRows: "Table",
      modeRaw: "Markdown",
      blockedRows: "This rubric cannot be shown as a table without losing a line; using the markdown editor:",
      sum: function (n) { return "ceiling " + n; },
      kindAff: "Affirmative",
      kindNeg: "Negative",
      colSection: "Part",
      colSub: "Sub",
      colPts: "Pts",
      colText: "Text",
      colCode: "Code",
      colOps: "",
      addPoint: "+ Add point",
      addNeg: "+ Add deduction",
      rowsEmpty: "No points yet. Apply a track template above, or add a row.",
      retTitle: "Retrieval gold (retrieval track only)",
      retClass: "Retrieval class",
      retHead: ["Tier", "Ref", "Note", ""],
      retEmpty: "No retrieval gold yet. A retrieval item needs at least one row.",
      retHint: "tier must be one of",
      addGoldRow: "+ Add row",
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
      noRubricLayout: "schema.json carries no rubric layout, so the table editor is unavailable.",
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

  /* ---------- field widgets ---------- */

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

  function layout() { return (SCHEMA && SCHEMA.rubric_layout) || null; }

  function vocabList(key) {
    return (VOCAB && Array.isArray(VOCAB[key])) ? VOCAB[key] : [];
  }

  function select(blankText, pairs) {
    var sel = document.createElement("select");
    if (blankText != null) {
      var blank = document.createElement("option");
      blank.value = "";
      blank.textContent = blankText;
      sel.appendChild(blank);
    }
    (pairs || []).forEach(function (p) {
      var o = document.createElement("option");
      o.value = p.value;
      o.textContent = p.label == null ? p.value : p.label;
      sel.appendChild(o);
    });
    return sel;
  }

  function labelled(list) {
    return (list || []).map(function (v) { return { value: v, label: v }; });
  }

  /* A closed list plus an escape hatch.
   *
   * The list is "what the published set already uses", not a constraint: the
   * schema keeps these fields free strings on purpose, because the set may grow
   * a category nobody anticipated. So the last option hands the field to a text
   * input. Without the escape the form is a cage; without the list every drafter
   * picks their own spelling and no report can group by 任务类型 afterwards. */
  function combo(value, list, onChange) {
    var wrap = el("div", "stack");
    var known = list.slice();
    if (value && known.indexOf(value) < 0) known = [value].concat(known);

    var sel = select(tx("unset"), labelled(known).concat([{ value: CUSTOM, label: tx("custom") }]));
    var free = document.createElement("input");
    free.type = "text";
    free.className = "text-in";
    free.value = value || "";

    function emit() {
      var v = sel.value === CUSTOM ? free.value.trim() : sel.value;
      value = v;
      sync();
      onChange(v);
    }

    function sync() {
      var v = (value || "").trim();
      sel.value = (v && known.indexOf(v) >= 0) ? v : (v ? CUSTOM : "");
      free.hidden = sel.value !== CUSTOM;
      if (free.hidden) free.value = v;
    }

    sel.addEventListener("change", function () {
      if (sel.value === CUSTOM) { free.hidden = false; free.focus(); emit(); }
      else emit();
    });
    free.addEventListener("input", emit);

    wrap.appendChild(sel);
    wrap.appendChild(free);
    sync();
    return wrap;
  }

  /* A list of known-good values that does not close the field: the browser's own
   * suggestions, so an existing spelling is one keystroke away without making a
   * new one impossible. */
  function datalistField(field_, value, list) {
    var n = input(field_, "text");
    n.value = value || "";
    if (!list.length) return n;
    var dl = el("datalist");
    dl.id = "dl-" + field_;
    list.forEach(function (v) {
      var o = document.createElement("option");
      o.value = v;
      dl.appendChild(o);
    });
    n.setAttribute("list", dl.id);
    var wrap = el("div", "stack");
    wrap.appendChild(n);
    wrap.appendChild(dl);
    return wrap;
  }

  /* ---------- editor ---------- */

  function openEditor(row) {
    editing = row;
    var host = document.getElementById("row-editor");
    if (!host) return;
    host.hidden = false;
    host.textContent = "";
    RUBRIC_MODE = "rows";
    RUBRIC_ROWS = [];
    RUBRIC_BLOCKED = [];

    // Seed the rubric from the track's template so the table, the exported
    // markdown and what `acnlb new` would have written are the same text. Left
    // empty, the CLI falls back to the generic skeleton and the page would be
    // showing something else.
    if (SCHEMA && !row.rubric) {
      row.rubric = F.rubricTemplate(SCHEMA, row.track, row.id || "", row.task || "");
      saveDraft();
    }

    var bar = el("div", "editor-bar");
    bar.appendChild(el("h3", null, row.id || tx("noId")));
    var close = el("button", "link-btn", tx("close"));
    close.type = "button";
    close.addEventListener("click", closeEditor);
    bar.appendChild(close);
    host.appendChild(bar);

    var grid = el("div", "grid");

    var idNode = input("id", "text");
    idNode.value = row.id || "";
    var idWrap = el("div", "stack");
    idWrap.appendChild(idNode);
    var idBtn = el("button", "link-btn", tx("idNext"));
    idBtn.type = "button";
    idBtn.addEventListener("click", function () {
      var next = F.nextId(VOCAB, { track: row.track, category: row.category });
      if (!next) return log([tx("noVocab")], true);
      row.id = next;
      idNode.value = next;
      saveDraft();
      // The rubric's title line carries the id, so it has to be rewritten too.
      resyncRubricTitle();
      openEditor(row);
    });
    idWrap.appendChild(idBtn);
    grid.appendChild(field(tx("id"), idWrap, tx("idHint")));

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

    var taskNode = input("task", "text");
    taskNode.value = row.task || "";
    grid.appendChild(field(tx("task"), taskNode));

    // Everything below is a closed list with an escape hatch, fed by items.json.
    [["category", tx("category"), "categories"],
     ["task_type", tx("taskType"), "task_types"],
     ["jurisdiction", tx("jurisdiction"), "jurisdictions"]
    ].forEach(function (triple) {
      var key = triple[0];
      grid.appendChild(field(triple[1], combo(row[key] || "", vocabList(triple[2]), function (v) {
        row[key] = v;
        saveDraft();
        refresh();
      })));
    });
    host.appendChild(grid);

    var docsWrap = el("div", "stack");
    var docs = input("documents", "area");
    docs.rows = 3;
    docs.value = (row.documents || []).join("\n");
    docsWrap.appendChild(docs);
    if (vocabList("documents").length) {
      var docPick = select(tx("docPick"), labelled(vocabList("documents")));
      docPick.className = "picker";
      docPick.addEventListener("change", function () {
        var v = docPick.value;
        docPick.value = "";
        if (!v) return;
        var cur = (docs.value || "").split("\n").map(function (s) { return s.trim(); })
          .filter(function (s) { return s.length > 0; });
        if (cur.indexOf(v) < 0) cur.push(v);
        docs.value = cur.join("\n");
        row.documents = cur;
        saveDraft();
        refresh();
      });
      docsWrap.appendChild(docPick);
    }
    host.appendChild(field(tx("documents"), docsWrap, tx("docsHint")));

    // has_context is derived, so it is shown rather than asked. A checkbox next
    // to the document list is a second source of truth that can only disagree.
    var ctx = el("div", "ctx-line");
    host.appendChild(ctx);

    host.appendChild(field(tx("authority"),
      datalistField("authority_basis_text", row.authority_basis_text || "", vocabList("authority_basis")),
      tx("authorityHint")));

    var promptArea = input("prompt", "area");
    promptArea.value = row.prompt || "";
    host.appendChild(field(tx("prompt"), promptArea));

    host.appendChild(field(tx("gold"), goldArea(row), tx("goldHint")));

    var notesArea = input("notes", "area");
    notesArea.rows = 3;
    notesArea.value = row.notes || "";
    host.appendChild(field(tx("notes"), notesArea));

    /* ---- rubric ---- */

    var rubricWrap = el("div", "field");
    var rubricHead = el("div", "field-k");
    rubricHead.appendChild(document.createTextNode(tx("rubric")));
    rubricHead.appendChild(document.createTextNode("  "));
    var tplSel = select(tx("startFrom"),
      ((SCHEMA && SCHEMA.valid_tracks) || []).map(function (t) {
        return { value: t, label: t + (SCHEMA.track_labels[t] ? " · " + SCHEMA.track_labels[t] : "") };
      }).concat([{ value: CLEAR, label: tx("tplClear") }]));
    tplSel.className = "picker";
    tplSel.addEventListener("change", function () {
      var v = tplSel.value;
      tplSel.value = "";
      if (!v) return;
      applyTemplate(v);
    });
    rubricHead.appendChild(tplSel);

    var modeBtn = el("button", "link-btn", tx("modeRaw"));
    modeBtn.type = "button";
    modeBtn.addEventListener("click", function () {
      if (RUBRIC_MODE === "raw" && RUBRIC_BLOCKED.length) return;
      RUBRIC_MODE = RUBRIC_MODE === "raw" ? "rows" : "raw";
      if (RUBRIC_MODE === "rows") row.rubric = rubricArea.value;
      saveDraft();
      renderRubric();
    });
    rubricHead.appendChild(document.createTextNode(" "));
    rubricHead.appendChild(modeBtn);
    var sumSpan = el("span", "field-h", "");
    rubricHead.appendChild(document.createTextNode("  "));
    rubricHead.appendChild(sumSpan);
    rubricWrap.appendChild(rubricHead);

    var blockNote = el("p", "check-warn");
    blockNote.hidden = true;
    rubricWrap.appendChild(blockNote);

    var rubricBody = el("div", "rubric-body");
    rubricWrap.appendChild(rubricBody);

    var rubricArea = input("rubric", "area");
    rubricArea.className = "mono-area";
    rubricArea.rows = 16;
    rubricArea.value = row.rubric || "";
    rubricWrap.appendChild(rubricArea);

    rubricWrap.appendChild(el("span", "field-h",
      (SCHEMA ? SCHEMA.negatives.map(function (n) { return "[" + n.code + "]"; }).join(" ") : "")));
    host.appendChild(rubricWrap);

    /* ---- retrieval gold ---- */

    var retWrap = el("div", "field ret-field");
    retWrap.hidden = row.track !== "retrieval";
    var retBody = el("div", "ret-body");
    if (row.track === "retrieval") {
      retWrap.appendChild(el("div", "field-k", tx("retTitle")));
      var classSel = document.createElement("select");
      classSel.setAttribute("data-field", "retrieval_class");
      ((SCHEMA && SCHEMA.retrieval_classes) || []).forEach(function (c) {
        var o = document.createElement("option");
        o.value = c;
        o.textContent = c;
        classSel.appendChild(o);
      });
      classSel.value = row.retrieval_class || ((SCHEMA && SCHEMA.retrieval_classes) || ["statute"])[0];
      retWrap.appendChild(field(tx("retClass"), classSel));
      retWrap.appendChild(retBody);
    }
    host.appendChild(retWrap);

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

    /* ---- rubric editor ---- */

    function ceiling() {
      return F.fmtPoints(F.parseRubric(row.rubric || "").maxPositivePoints);
    }

    function applyTemplate(track) {
      if (track === CLEAR) {
        row.rubric = "";
        RUBRIC_MODE = "rows";
      } else {
        row.rubric = F.rubricTemplate(SCHEMA, track, row.id || "", row.task || "");
        RUBRIC_MODE = "rows";
      }
      saveDraft();
      renderRubric();
      refresh();
    }

    /* Rows are the editor and `row.rubric` is what gets exported, so every edit
     * writes the markdown back out. If the layout is missing this refuses rather
     * than inventing headings — a page that writes a format the CLI cannot read
     * is worse than a page that says it is broken. */
    function syncRubric() {
      try {
        row.rubric = F.rubricFromRows(RUBRIC_ROWS, {
          layout: layout(), id: row.id || "", task: row.task || ""
        });
      } catch (e) {
        return log([tx("noRubricLayout")], true);
      }
      saveDraft();
      refresh();
    }

    /* Rewrite only the title line, keeping the rest byte for byte. Used when the
     * id changes, because the title carries it. */
    function resyncRubricTitle() {
      if (!row.rubric || !layout()) return;
      RUBRIC_MODE = "rows";
      RUBRIC_ROWS = F.rubricRows(row.rubric, layout(), SCHEMA).rows;
      if (!RUBRIC_ROWS.length) return;
      row.rubric = F.rubricFromRows(RUBRIC_ROWS, {
        layout: layout(), id: row.id || "", task: row.task || ""
      });
    }

    function textCell(value, onChange) {
      var td = el("td");
      var n = document.createElement("textarea");
      n.rows = 2;
      n.value = value;
      n.addEventListener("input", function () { onChange(n.value); });
      td.appendChild(n);
      return td;
    }

    function pointsCell(r) {
      var td = el("td");
      var n = document.createElement("input");
      n.type = "number";
      n.step = "0.5";
      n.min = "0";
      n.className = "num-input";
      n.value = F.fmtPoints(r.points);
      n.addEventListener("input", function () {
        var v = parseFloat(n.value);
        r.points = isNaN(v) ? 0 : Math.abs(v);
        syncRubric();
      });
      td.appendChild(n);
      return td;
    }

    function rowOps(r, rerender) {
      var td = el("td", "row-ops");
      var del = el("button", "link-btn", tx("del"));
      del.type = "button";
      del.addEventListener("click", function () {
        RUBRIC_ROWS.splice(RUBRIC_ROWS.indexOf(r), 1);
        syncRubric();
        rerender();
      });
      td.appendChild(del);
      return td;
    }

    function tableOf(headers, rows) {
      var table = el("table", "rubric-table");
      var thead = document.createElement("thead");
      var htr = document.createElement("tr");
      headers.forEach(function (h) { htr.appendChild(el("th", null, h)); });
      thead.appendChild(htr);
      table.appendChild(thead);
      var tb = el("tbody");
      rows.forEach(function (tr) { tb.appendChild(tr); });
      table.appendChild(tb);
      var wrap = el("div", "table-wrap");
      wrap.appendChild(table);
      return wrap;
    }

    function affirmativeBlock() {
      var block = el("div", "rubric-block");
      var head = el("div", "rubric-head");
      head.appendChild(el("span", null, tx("kindAff")));
      var add = el("button", "link-btn", tx("addPoint"));
      add.type = "button";
      add.addEventListener("click", function () {
        RUBRIC_ROWS.push(F.blankRubricRow("affirmative", SCHEMA, layout()));
        syncRubric();
        renderRubric();
      });
      head.appendChild(add);
      block.appendChild(head);

      var mine = RUBRIC_ROWS.filter(function (r) { return r.kind === "affirmative"; });
      if (!mine.length) {
        block.appendChild(el("p", "muted", tx("rowsEmpty")));
        return block;
      }

      var rows = mine.map(function (r) {
        var tr = document.createElement("tr");

        var secTd = el("td");
        var secSel = select(null, ((layout() || {}).sections || []).map(function (s) {
          return { value: s.key, label: s.title };
        }));
        secSel.value = r.section;
        secSel.addEventListener("change", function () {
          r.section = secSel.value;
          syncRubric();
          renderRubric();
        });
        secTd.appendChild(secSel);
        tr.appendChild(secTd);

        tr.appendChild(textCell(r.subsection || "", function (v) { r.subsection = v; syncRubric(); }));
        tr.appendChild(pointsCell(r));
        tr.appendChild(textCell(r.text || "", function (v) { r.text = v; syncRubric(); }));
        tr.appendChild(rowOps(r, renderRubric));
        return tr;
      });
      block.appendChild(tableOf(
        [tx("colSection"), tx("colSub"), tx("colPts"), tx("colText"), tx("colOps")], rows));
      return block;
    }

    function negativeBlock() {
      var block = el("div", "rubric-block");
      var head = el("div", "rubric-head");
      head.appendChild(el("span", null, tx("kindNeg")));
      var add = el("button", "link-btn", tx("addNeg"));
      add.type = "button";
      add.addEventListener("click", function () {
        RUBRIC_ROWS.push(F.blankRubricRow("negative", SCHEMA, layout()));
        syncRubric();
        renderRubric();
      });
      head.appendChild(add);
      block.appendChild(head);

      var mine = RUBRIC_ROWS.filter(function (r) { return r.kind === "negative"; });
      if (!mine.length) return block;

      var codes = ((SCHEMA && SCHEMA.negatives) || []);
      var rows = mine.map(function (r) {
        var tr = document.createElement("tr");

        var codeTd = el("td");
        var codeSel = select(null, codes.map(function (n) {
          return { value: n.code, label: n.code };
        }));
        codeSel.value = r.code;
        codeSel.addEventListener("change", function () {
          r.code = codeSel.value;
          syncRubric();
        });
        codeTd.appendChild(codeSel);
        tr.appendChild(codeTd);

        tr.appendChild(pointsCell(r));
        tr.appendChild(textCell(r.text || "", function (v) { r.text = v; syncRubric(); }));
        tr.appendChild(rowOps(r, renderRubric));
        return tr;
      });
      block.appendChild(tableOf([tx("colCode"), tx("colPts"), tx("colText"), tx("colOps")], rows));
      return block;
    }

    function rawArea() {
      rubricArea.value = row.rubric || "";
      return rubricArea;
    }

    function renderRubric() {
      var lay = layout();
      var parsed = lay
        ? F.rubricRows(row.rubric || "", lay, SCHEMA)
        : { rows: [], blocked: [tx("noRubricLayout")] };
      RUBRIC_BLOCKED = parsed.blocked;
      RUBRIC_ROWS = parsed.rows;
      // A shape the table cannot carry goes to the raw editor, and stays there:
      // approximating it is how a rubric quietly loses a line.
      if (RUBRIC_BLOCKED.length) RUBRIC_MODE = "raw";

      var raw = RUBRIC_MODE === "raw";
      modeBtn.textContent = raw ? tx("modeRows") : tx("modeRaw");
      blockNote.hidden = !RUBRIC_BLOCKED.length;
      blockNote.textContent = RUBRIC_BLOCKED.length ? tx("blockedRows") + RUBRIC_BLOCKED.join("；") : "";
      sumSpan.textContent = tx("sum", ceiling());

      rubricBody.textContent = "";
      if (raw) {
        rubricBody.appendChild(rawArea());
      } else {
        rubricBody.appendChild(affirmativeBlock());
        rubricBody.appendChild(negativeBlock());
      }
    }

    /* ---- retrieval gold editor ---- */

    function renderRetrieval() {
      if (row.track !== "retrieval") return;
      retBody.textContent = "";
      var items = row.retrieval_items || [];
      var tiers = (SCHEMA && SCHEMA.valid_tiers) || [];

      if (items.length) {
        var rows = items.map(function (g) {
          var tr = document.createElement("tr");

          var tierTd = el("td");
          var tierSel = select(null, labelled(tiers));
          tierSel.value = g.tier;
          tierSel.addEventListener("change", function () {
            g.tier = tierSel.value;
            saveDraft();
            refresh();
          });
          tierTd.appendChild(tierSel);
          tr.appendChild(tierTd);

          tr.appendChild(textCell(g.ref || "", function (v) { g.ref = v; saveDraft(); refresh(); }));
          tr.appendChild(textCell(g.note || "", function (v) { g.note = v; saveDraft(); refresh(); }));

          var ops = el("td", "row-ops");
          var del = el("button", "link-btn", tx("del"));
          del.type = "button";
          del.addEventListener("click", function () {
            row.retrieval_items.splice(row.retrieval_items.indexOf(g), 1);
            saveDraft();
            renderRetrieval();
            refresh();
          });
          ops.appendChild(del);
          tr.appendChild(ops);
          return tr;
        });
        retBody.appendChild(tableOf(tx("retHead"), rows));
      } else {
        retBody.appendChild(el("p", "muted", tx("retEmpty")));
      }

      var add = el("button", "link-btn", tx("addGoldRow"));
      add.type = "button";
      add.addEventListener("click", function () {
        row.retrieval_items = (row.retrieval_items || []).concat([{ tier: tiers[0] || "", ref: "", note: "" }]);
        saveDraft();
        renderRetrieval();
        refresh();
      });
      retBody.appendChild(add);
      retBody.appendChild(el("span", "field-h", tx("retHint") + " " + tiers.join(" / ")));
    }

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
      if (title) title.textContent = row.id || tx("noId");
      ctx.textContent = tx("ctxLine", (row.documents || []).length);
      sumSpan.textContent = tx("sum", ceiling());
    }

    function bind(node) {
      var key = node.getAttribute("data-field");
      var handler = function () {
        if (key === "documents") {
          row.documents = node.value.split("\n").map(function (s) { return s.trim(); })
            .filter(function (s) { return s.length > 0; });
        } else if (key === "track") {
          row.track = node.value;
          saveDraft();
          openEditor(row);
          return;
        } else if (key === "rubric") {
          row.rubric = node.value;
        } else {
          row[key] = node.value;
        }
        saveDraft();
        refresh();
      };
      node.addEventListener("input", handler);
      node.addEventListener("change", handler);
    }

    host.querySelectorAll("[data-field]").forEach(bind);

    // The retrieval table is only built when the row is on that track; a row
    // switched to `retrieval` goes back through openEditor and lands here again.
    if (row.track === "retrieval") renderRetrieval();
    renderRubric();
    refresh();
  }

  function goldArea(row) {
    var a = input("gold", "area");
    a.value = row.gold || "";
    return a;
  }

  function closeEditor() {
    editing = null;
    RUBRIC_ROWS = [];
    RUBRIC_BLOCKED = [];
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
        skipped.push((row.id || tx("noId")) + "：" + b.intake.errors.join("；"));
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
      if (!res.ok) { rejected.push((row.id || tx("noId")) + "：" + res.errors.join("；")); return; }
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

    function json(name) {
      return fetch(name, { cache: "no-store" }).then(function (r) {
        if (!r.ok) throw new Error(name + ": " + r.status);
        return r.json();
      });
    }

    // items.json is the second source, and it is allowed to be absent: the lists
    // go empty and every field is still typeable. schema.json is not optional —
    // without it the form cannot tell what the CLI accepts.
    Promise.all([json("schema.json"), json("items.json").catch(function () { return null; })])
      .then(function (pair) {
        SCHEMA = pair[0];
        VOCAB = (pair[1] && pair[1].vocab) || null;
        if (!VOCAB && status) status.textContent = tx("noVocab");
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
