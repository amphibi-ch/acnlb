/* Item authoring logic for the web form. Pure — no DOM, no fetch.
 *
 * This is a second implementation of `acnlb/scaffold.py` + `acnlb/rubric.py` +
 * `Item.from_dict`, and a second implementation is only worth having if it can
 * be shown to agree. So it is deliberately DOM-free: `tests/test_form_parity.py`
 * loads this file in node, feeds it the same intake forms the Python side gets,
 * and compares the results field by field. Drift fails CI.
 *
 * The vocabulary (tracks, tiers, negative codes, the rubric skeleton) is NOT
 * defined here — it arrives in `schema.json`, exported from the package that
 * owns it. Re-typing those lists is exactly how a form ends up accepting what
 * the CLI rejects.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ACNLBForm = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  /* ---------- intake parsing (mirror of scaffold.parse_intake) ---------- */

  var SECTION_RE = /^##\s+(.+?)\s*$/;
  var HEADER_RE = /^([A-Za-z_][A-Za-z0-9_ ]*?)\s*[:：]\s*(.*)$/;
  var ID_HEAD_RE = /^\s*%%%\s*$|^id\s*[:：]/;

  function knownSections(schema) {
    var s = schema || {};
    var set = {};
    (s.intake_sections || ["prompt", "documents", "rubric", "notes", "gold answer", "gold", "参考答案"]).forEach(function (k) {
      set[k.toLowerCase()] = true;
    });
    return set;
  }

  function goldSections(schema) {
    var s = schema || {};
    return (s.gold_sections || ["gold answer", "gold", "参考答案"]).map(function (k) { return k.toLowerCase(); });
  }

  function retrievalSections(schema) {
    var s = schema || {};
    return (s.retrieval_sections || ["retrieval gold", "retrieval_gold"]).map(function (k) { return k.toLowerCase(); });
  }

  function parseListBlock(block) {
    var out = [];
    block.split("\n").forEach(function (line) {
      var s = line.trim().replace(/^[-*]+/, "").trim();
      if (s && s.charAt(0) !== "#") out.push(s);
    });
    return out;
  }

  function parseGoldBlock(block, schema) {
    var valid = {};
    (schema && schema.valid_tiers || ["高", "中", "低"]).forEach(function (t) { valid[t] = true; });
    var klass = "";
    var items = [];
    var errors = [];
    block.split("\n").forEach(function (raw) {
      var line = raw.trim();
      if (!line) return;
      var hm = HEADER_RE.exec(line);
      if (hm && hm[1].trim().toLowerCase().replace(/ /g, "_") === "class") {
        klass = hm[2].trim();
        return;
      }
      if (line.charAt(0) !== "-" && line.charAt(0) !== "*") return;
      var parts = line.replace(/^[-*]+/, "").split("|").map(function (p) { return p.trim(); });
      if (parts.length < 2) {
        errors.push("retrieval gold 行需要 '<tier> | <ref> | <note>'：" + line);
        return;
      }
      if (!valid[parts[0]]) {
        errors.push("无效 tier " + JSON.stringify(parts[0]) + "；只能是 " + Object.keys(valid).join(" / "));
        return;
      }
      if (!parts[1]) {
        errors.push("retrieval gold 行缺少 ref：" + line);
        return;
      }
      items.push({ tier: parts[0], ref: parts[1], note: parts.length > 2 ? parts[2] : "" });
    });
    if (!klass) errors.push("retrieval gold 段缺少 'class:'");
    return { klass: klass, items: items, errors: errors };
  }

  /* One intake form → the 3.3 fields. Never throws; problems land in `errors`. */
  function parseIntake(text, schema) {
    var known = knownSections(schema);
    var gold = goldSections(schema);
    var retrieval = retrievalSections(schema);
    var out = {
      meta: {}, prompt: "", documents: [], gold: "", rubric: "", notes: "",
      retrieval_gold: null, errors: []
    };
    var section = null;
    var buf = [];

    function flush() {
      if (section !== null) {
        var block = buf.join("\n").replace(/^\n+|\n+$/g, "");
        if (section === "prompt") out.prompt = block.trim();
        else if (section === "documents") out.documents = parseListBlock(block);
        else if (gold.indexOf(section) >= 0) out.gold = block.trim();
        else if (section === "rubric") out.rubric = block.trim();
        else if (section === "notes") out.notes = block.trim();
        else if (retrieval.indexOf(section) >= 0) {
          var parsed = parseGoldBlock(block, schema);
          out.errors = out.errors.concat(parsed.errors);
          out.retrieval_gold = { klass: parsed.klass, items: parsed.items };
        }
      }
      buf = [];
    }

    text.split(/\r?\n/).forEach(function (raw) {
      var line = raw.replace(/\s+$/, "");
      var m = SECTION_RE.exec(line);
      if (m && known[m[1].trim().toLowerCase()]) {
        flush();
        section = m[1].trim().toLowerCase();
        return;
      }
      if (section === null) {
        if (!line.trim() || line.replace(/^\s+/, "").charAt(0) === "#") return;
        var hm = HEADER_RE.exec(line.trim());
        if (hm) out.meta[hm[1].trim().toLowerCase().replace(/ /g, "_")] = hm[2].trim();
        return;
      }
      buf.push(line);
    });
    flush();
    return out;
  }

  /* Split a paste of several forms into blocks. A new form starts at a top-level
   * `id:` line, or wherever an explicit `%%%` line says so. */
  function splitIntakes(text) {
    var blocks = [];
    var cur = [];
    text.split(/\r?\n/).forEach(function (line) {
      var hard = /^\s*%%%\s*$/.test(line);
      var soft = /^id\s*[:：]/.test(line) && cur.length > 0;
      if (hard || soft) {
        if (cur.length) blocks.push(cur.join("\n"));
        cur = [];
        if (hard) return;
      }
      cur.push(line);
    });
    if (cur.length) blocks.push(cur.join("\n"));
    return blocks.filter(function (b) { return b.trim().length > 0; });
  }

  /* ---------- rubric parsing (mirror of rubric.parse_rubric_text) ---------- */

  var RUBRIC_ID_RE = /^#\s+(\S+)\s+rubric/m;
  var SUB_RE = /^###+\s+(.+?)\s*$/;
  var AFFIRM_RE = /^[-*]?\s*\+?(\d+(?:\.\d+)?)\s*(?:pt|pts|point|points)\b\s*(.*)$/i;
  var NEG_RE = /^[-*]?\s*-(\d+(?:\.\d+)?)\s*(?:pt|pts|point|points)\b\s*(.*)$/i;
  var CODE_RE = /\[([A-Z_]+)\]/;
  var NA_RE = /^\s*[-*]?\s*(?:N\/?A|无|—|-)\s*$/i;

  function round6(n) { return Math.round(n * 1e6) / 1e6; }

  function sectionKind(name) {
    var low = name.toLowerCase();
    if (low.indexOf("negative") >= 0 || name.indexOf("扣分") >= 0 || name.indexOf("负面") >= 0) return "negative";
    if (low.indexOf("structure") >= 0 || name.indexOf("结构") >= 0 || name.indexOf("格式") >= 0) return "structure";
    if (low.indexOf("style") >= 0 || name.indexOf("风格") >= 0 || name.indexOf("语体") >= 0) return "style";
    if (low.indexOf("substance") >= 0 || name.indexOf("实质") >= 0) return "substance";
    if (low.indexOf("affirmative") >= 0 || name.indexOf("得分") >= 0 || name.indexOf("正面") >= 0) return "affirmative";
    return null;
  }

  function parseRubric(text) {
    var lines = String(text || "").split(/\r?\n/);
    var idm = RUBRIC_ID_RE.exec(text || "");
    var rubric = {
      itemId: idm ? idm[1] : "",
      title: lines.length && lines[0].indexOf("# ") === 0 ? lines[0].slice(2).trim() : "",
      affirmative: [],
      negative: [],
      warnings: []
    };
    var section = null, subsection = null, subKind = null;

    function currentSectionName() {
      var s = subKind || section || "substance";
      return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
    }

    lines.forEach(function (raw) {
      var line = raw.replace(/\s+$/, "");
      if (!line.trim()) return;

      var sec = SECTION_RE.exec(line);
      if (sec) {
        section = sectionKind(sec[1]);
        subsection = null;
        subKind = null;
        return;
      }
      var sub = SUB_RE.exec(line);
      if (sub) {
        var label = sub[1];
        var kind = sectionKind(label);
        if (kind === "structure" || kind === "style" || kind === "substance") {
          subKind = kind;
          subsection = null;
        } else {
          subsection = label;
        }
        return;
      }
      if (section === "negative") {
        var neg = parseNegative(line);
        if (neg) rubric.negative.push(neg);
        else if (!NA_RE.test(line)) rubric.warnings.push("未解析的负分行：" + line.trim());
        return;
      }
      if (section === "affirmative" || section === "structure" || section === "style" ||
          section === "substance" || section === null) {
        var aff = parseAffirmative(line, currentSectionName(), subsection || "");
        if (aff) rubric.affirmative.push(aff);
        else if (!NA_RE.test(line) && line.replace(/^\s+/, "").charAt(0) !== "#") {
          rubric.warnings.push("未解析的得分行：" + line.trim());
        }
      }
    });

    rubric.maxPositivePoints = round6(
      rubric.affirmative.reduce(function (s, p) { return s + p.points; }, 0)
    );
    return rubric;
  }

  function parseAffirmative(line, section, subsection) {
    var m = AFFIRM_RE.exec(line.trim());
    if (!m) return null;
    return { section: section, subsection: subsection, points: parseFloat(m[1]), text: m[2].trim() };
  }

  function parseNegative(line) {
    var m = NEG_RE.exec(line.trim());
    if (!m) return null;
    var rest = m[2].trim();
    var cm = CODE_RE.exec(rest);
    var code = cm ? cm[1] : "HALLUC_FACT";
    var text = cm ? rest.replace(/\[([A-Z_]+)\]/g, "").trim() : "【缺少负分代码】" + rest;
    return { code: code, points: parseFloat(m[1]), text: text };
  }

  /* ---------- intake → item (mirror of scaffold.scaffold) ---------- */

  var DEFAULT_GOLD_TODO = [
    "# {id} 参考答案",
    "",
    "<!-- TODO：先写「一名胜任律师会产出的回答」，再据此写 rubric（设计文档 §3.6）。",
    "     顺序不能反——先写 rubric 会锚定在你想到的东西上，参考答案就不完整。 -->",
    ""
  ].join("\n");

  function defaultRubric(schema, id, task) {
    var tpl = (schema && schema.default_rubric) || "";
    return tpl.split("{item_id}").join(id).split("{task}").join(task);
  }

  function asBool(value) {
    var v = String(value).trim().toLowerCase();
    if (["true", "yes", "y", "1", "是", "有", "有附件"].indexOf(v) >= 0) return true;
    if (["false", "no", "n", "0", "否", "无", "无附件"].indexOf(v) >= 0) return false;
    return null;
  }

  function splitBasis(value) {
    return String(value || "").split(/[,，、;；]/).map(function (p) { return p.trim(); })
      .filter(function (p) { return p.length > 0; });
  }

  function buildItem(intake, opts) {
    opts = opts || {};
    var schema = opts.schema || {};
    var paths = schema.paths || {};
    var goldDir = paths.gold_dir || "gold";
    var rubricSuffix = paths.rubric_suffix || ".rubric.md";
    var meta = intake.meta || {};
    var errors = (intake.errors || []).slice();
    var warnings = [];

    var id = (opts.id || meta.id || "").trim();
    if (!id) errors.push("缺少 id");
    ["track", "task_type", "task"].forEach(function (k) {
      if (!(meta[k] || "").trim()) errors.push("缺少 " + k);
    });
    if (!(intake.prompt || "").trim()) errors.push("缺少 '## Prompt' 段");

    var tracks = schema.valid_tracks || ["core", "workflows", "retrieval"];
    var track = (meta.track || "").trim();
    if (track && tracks.indexOf(track) < 0) {
      errors.push("无效 track " + JSON.stringify(track) + "；只能是 " + tracks.join(" / "));
    }
    if (errors.length) return { ok: false, errors: errors, warnings: warnings };

    var task = meta.task.trim();
    var notes = ((meta.notes || "") + (intake.notes ? "\n" + intake.notes : "")).trim();
    var rubricText = (intake.rubric || "").trim() || defaultRubric(schema, id, task);
    var rubric = parseRubric(rubricText);

    var hasCtx;
    if (meta.has_context) {
      hasCtx = asBool(meta.has_context);
      if (hasCtx === null) {
        errors.push("has_context 只能是 true/false，收到 " + JSON.stringify(meta.has_context));
        return { ok: false, errors: errors, warnings: warnings };
      }
    } else {
      hasCtx = (intake.documents || []).length > 0;
    }

    if (track === "retrieval" && !intake.retrieval_gold) {
      errors.push("检索题需要 '## Retrieval gold' 段（一行 'class:' 加若干 '- <tier> | <ref> | <note>'）");
      return { ok: false, errors: errors, warnings: warnings };
    }
    if (intake.retrieval_gold && track !== "retrieval") {
      // Same as scaffold.py: the section is ignored for other tracks, out loud.
      warnings.push("「## Retrieval gold」段在非 retrieval 轨道被忽略");
    }

    var item = {
      id: id,
      track: track,
      category: meta.category || "",
      task_type: meta.task_type.trim(),
      task: task,
      prompt: intake.prompt.trim(),
      documents: (intake.documents || []).map(function (p) { return { path: p }; }),
      has_context: hasCtx,
      jurisdiction: meta.jurisdiction || "CN-mainland",
      authority_basis: splitBasis(meta.authority_basis || ""),
      gold_answer: goldDir + "/" + id + ".md",
      rubric: id + rubricSuffix,
      max_positive_points: rubric.maxPositivePoints,
      notes: notes
    };
    if (intake.retrieval_gold && track === "retrieval") {
      item.retrieval_gold = {
        "class": intake.retrieval_gold.klass,
        gold_items: intake.retrieval_gold.items.map(function (g) {
          return { ref: g.ref, tier: g.tier, note: g.note };
        }),
        tier_points: Object.assign({}, schema.tier_points || { "高": 2.0, "中": 1.0, "低": 0.5 })
      };
    }

    var problems = validateItem(item, rubric, schema);
    if (problems.length) return { ok: false, errors: problems, warnings: warnings, item: item, rubric: rubric };

    if ((intake.documents || []).length) {
      warnings.push("记得把 " + intake.documents.length + " 份附件一起放进 items 目录（docs/ 下）");
    }
    return {
      ok: true, errors: [], warnings: warnings, id: id, item: item, rubric: rubric,
      rubricText: rubricText.charAt(rubricText.length - 1) === "\n" ? rubricText : rubricText + "\n",
      goldText: (intake.gold || "").trim() || DEFAULT_GOLD_TODO.split("{id}").join(id)
    };
  }

  /* Mirrors Item.from_dict + validate_item + validate_rubric, minus the
   * filesystem half (a browser cannot stat a relative document path). */
  function validateItem(item, rubric, schema) {
    var problems = [];
    var required = (schema && schema.required_fields) || [];
    required.forEach(function (k) {
      if (!(k in item)) problems.push("缺少必填字段：" + k);
    });
    var tracks = (schema && schema.valid_tracks) || ["core", "workflows", "retrieval"];
    if (tracks.indexOf(item.track) < 0) {
      problems.push("无效 track：" + item.track + "；只能是 " + tracks.join(" / "));
    }
    if (typeof item.has_context !== "boolean") problems.push("has_context 必须是布尔值");
    if (item.has_context && !(item.documents || []).length) {
      problems.push("has_context 为 true 但 documents[] 为空");
    }
    if (item.track === "retrieval" && !item.retrieval_gold) {
      problems.push("检索题必须带 retrieval_gold");
    }
    if (item.retrieval_gold && item.track !== "retrieval") {
      problems.push("retrieval_gold 只能出现在 retrieval 轨道");
    }
    if (item.retrieval_gold) {
      if (!item.retrieval_gold["class"]) problems.push("retrieval_gold 缺 class");
      if (!(item.retrieval_gold.gold_items || []).length) {
        problems.push("retrieval_gold.gold_items 为空");
      } else {
        var tiers = (schema && schema.valid_tiers) || ["高", "中", "低"];
        item.retrieval_gold.gold_items.forEach(function (g) {
          if (tiers.indexOf(g.tier) < 0) problems.push("无效 relevance tier：" + JSON.stringify(g.tier));
          if (!g.ref) problems.push("retrieval_gold 有一项缺 ref");
        });
      }
    }

    var codes = {};
    ((schema && schema.negatives) || []).forEach(function (n) { codes[n.code] = true; });
    var hasCodes = Object.keys(codes).length > 0;

    if (rubric) {
      if (!rubric.affirmative.length) problems.push("rubric 没有任何得分点");
      if (rubric.itemId && rubric.itemId !== item.id) {
        problems.push("rubric 头部的 id " + JSON.stringify(rubric.itemId) + " ≠ 题目 id " + JSON.stringify(item.id));
      }
      rubric.negative.forEach(function (n) {
        if (hasCodes && !codes[n.code]) problems.push("未知负分代码 " + n.code);
        if (!n.text || n.text.indexOf("【缺少负分代码】") === 0) {
          problems.push("负分行缺少 [CODE]：" + n.text);
        }
      });
      if (Math.abs(rubric.maxPositivePoints - item.max_positive_points) > 1e-9) {
        problems.push("max_positive_points 与 rubric 得分点之和不一致");
      }
    }
    return problems;
  }

  /* Mirrors `acnlb validate`'s TODO / shape checks. Warnings, not errors: a
   * draft with TODOs is a draft, not a broken file. */
  function lintItem(built, schema) {
    var out = [];
    var pattern = (schema && schema.id_pattern) || "";
    if (pattern) {
      try {
        if (built.id && !new RegExp(pattern).test(built.id)) {
          out.push("id " + JSON.stringify(built.id) + " 不像建议格式：" + ((schema && schema.id_hint) || ""));
        }
      } catch (e) { /* a bad pattern in schema.json must not brick the page */ }
    }
    (built.rubric ? built.rubric.affirmative : []).forEach(function (a) {
      if (a.text.indexOf("TODO") >= 0) out.push("得分点仍是 TODO 占位：" + a.text.slice(0, 40));
    });
    if ((built.goldText || "").indexOf("TODO") >= 0) out.push("参考答案仍是 TODO 占位");
    return out;
  }

  /* ---------- row ⇄ intake round trip ---------- */

  function rowToIntake(row) {
    var out = [];
    out.push("id: " + (row.id || ""));
    out.push("track: " + (row.track || ""));
    out.push("category: " + (row.category || ""));
    out.push("task_type: " + (row.task_type || ""));
    out.push("task: " + (row.task || ""));
    out.push("jurisdiction: " + (row.jurisdiction || "CN-mainland"));
    out.push("has_context: " + (row.has_context ? "true" : "false"));
    out.push("authority_basis: " + splitBasis(row.authority_basis_text || "").join(", "));
    out.push("notes: " + (row.notes || ""));
    out.push("", "## Prompt", "", row.prompt || "");
    out.push("", "## Documents", "");
    (row.documents || []).forEach(function (d) { out.push("- " + d); });
    out.push("", "## Gold answer", "", row.gold || "");
    out.push("", "## Rubric", "", row.rubric || "");
    if (row.track === "retrieval") {
      out.push("", "## Retrieval gold", "", "class: " + (row.retrieval_class || ""), "");
      (row.retrieval_items || []).forEach(function (g) {
        out.push("- " + g.tier + " | " + g.ref + " | " + (g.note || ""));
      });
    }
    return out.join("\n") + "\n";
  }

  function intakeToRow(intake) {
    var rg = intake.retrieval_gold;
    return {
      id: intake.meta.id || "",
      track: intake.meta.track || "core",
      category: intake.meta.category || "",
      task_type: intake.meta.task_type || "",
      task: intake.meta.task || "",
      jurisdiction: intake.meta.jurisdiction || "CN-mainland",
      has_context: (intake.meta.has_context || "").trim().toLowerCase() === "true" ||
                   (intake.documents || []).length > 0,
      authority_basis_text: intake.meta.authority_basis || "",
      notes: intake.meta.notes || "",
      prompt: intake.prompt || "",
      documents: intake.documents || [],
      gold: intake.gold || "",
      rubric: intake.rubric || "",
      retrieval_class: rg ? rg.klass : "",
      retrieval_items: rg ? rg.items.slice() : []
    };
  }

  /* The exact files `acnlb new` would write, as text. */
  function assembleFiles(built) {
    return [
      { name: built.id + ".json", data: JSON.stringify(built.item, null, 2) + "\n" },
      { name: built.id + ".rubric.md", data: built.rubricText },
      { name: "gold/" + built.id + ".md", data: built.goldText }
    ];
  }

  /* ---------- zip ---------- */

  var CRC_TABLE = null;
  function crcTable() {
    if (CRC_TABLE) return CRC_TABLE;
    CRC_TABLE = new Uint32Array(256);
    for (var n = 0; n < 256; n++) {
      var c = n;
      for (var k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
      CRC_TABLE[n] = c >>> 0;
    }
    return CRC_TABLE;
  }

  function crc32(bytes) {
    var table = crcTable();
    var c = 0xFFFFFFFF;
    for (var i = 0; i < bytes.length; i++) c = (c >>> 8) ^ table[(c ^ bytes[i]) & 0xFF];
    return (c ^ 0xFFFFFFFF) >>> 0;
  }

  /* Store-only zip. Fixed DOS timestamp and sorted input keep a re-export of
   * unchanged data byte-identical, same reason tools/build_bundle.py pins its
   * timestamps. */
  function makeZip(entries) {
    var enc = new TextEncoder();
    var parts = [];
    var central = [];
    var offset = 0;
    var entriesCount = 0;

    entries.forEach(function (e) {
      var nameBytes = enc.encode(e.name);
      var data = typeof e.data === "string" ? enc.encode(e.data) : e.data;
      var crc = crc32(data);

      var local = new Uint8Array(30 + nameBytes.length);
      var lv = new DataView(local.buffer);
      lv.setUint32(0, 0x04034b50, true);
      lv.setUint16(4, 20, true);
      lv.setUint16(6, 0x0800, true);
      lv.setUint16(8, 0, true);
      lv.setUint16(10, 0, true);
      lv.setUint16(12, 0x21, true);
      lv.setUint32(14, crc, true);
      lv.setUint32(18, data.length, true);
      lv.setUint32(22, data.length, true);
      lv.setUint16(26, nameBytes.length, true);
      lv.setUint16(28, 0, true);
      local.set(nameBytes, 30);
      parts.push(local, data);

      var cen = new Uint8Array(46 + nameBytes.length);
      var cv = new DataView(cen.buffer);
      cv.setUint32(0, 0x02014b50, true);
      cv.setUint16(4, 20, true);
      cv.setUint16(6, 20, true);
      cv.setUint16(8, 0x0800, true);
      cv.setUint16(10, 0, true);
      cv.setUint16(12, 0, true);
      cv.setUint16(14, 0x21, true);
      cv.setUint32(16, crc, true);
      cv.setUint32(20, data.length, true);
      cv.setUint32(24, data.length, true);
      cv.setUint16(28, nameBytes.length, true);
      cv.setUint16(30, 0, true);
      cv.setUint16(32, 0, true);
      cv.setUint16(34, 0, true);
      cv.setUint16(36, 0, true);
      cv.setUint32(38, 0x81A40000, true);
      cv.setUint32(42, offset, true);
      cen.set(nameBytes, 46);
      central.push(cen);
      entriesCount++;

      offset += local.length + data.length;
    });

    var cdSize = central.reduce(function (s, c) { return s + c.length; }, 0);
    var eocd = new Uint8Array(22);
    var ev = new DataView(eocd.buffer);
    ev.setUint32(0, 0x06054b50, true);
    ev.setUint16(8, entriesCount, true);
    ev.setUint16(10, entriesCount, true);
    ev.setUint32(12, cdSize, true);
    ev.setUint32(16, offset, true);

    var total = offset + cdSize + 22;
    var out = new Uint8Array(total);
    var pos = 0;
    parts.concat(central, [eocd]).forEach(function (chunk) {
      out.set(chunk, pos);
      pos += chunk.length;
    });
    return out;
  }

  function sha256Hex(bytes) {
    if (typeof crypto === "undefined" || !crypto.subtle) {
      return Promise.reject(new Error("crypto.subtle 不可用（需要 https 或 localhost）"));
    }
    return crypto.subtle.digest("SHA-256", bytes).then(function (buf) {
      return Array.prototype.map.call(new Uint8Array(buf), function (b) {
        return b.toString(16).padStart(2, "0");
      }).join("");
    });
  }

  return {
    parseIntake: parseIntake,
    splitIntakes: splitIntakes,
    parseIntakeList: function (text, schema) {
      return splitIntakes(text).map(function (b) { return parseIntake(b, schema); });
    },
    parseIntakeBlocks: function (text, schema) {
      return splitIntakes(text).map(function (b) {
        return { text: b, intake: parseIntake(b, schema) };
      });
    },
    intakeToRow: intakeToRow,
    rowToIntake: rowToIntake,
    buildItem: buildItem,
    validateItem: validateItem,
    lintItem: lintItem,
    parseRubric: parseRubric,
    defaultRubric: defaultRubric,
    assembleFiles: assembleFiles,
    splitBasis: splitBasis,
    makeZip: makeZip,
    crc32: crc32,
    sha256Hex: sha256Hex,
    round6: round6
  };
});
