/* acnlb front door. Static; no build step.
 * Reads the committed site/items.json (item set) and results/latest.json (latest
 * run), wires the language toggle, and points the repo-relative links at the
 * right GitHub paths. No key is handled here. */
(function () {
  "use strict";

  var REPO = (window.ACNLB_REPO || "").trim() || guessRepo();
  var WORKFLOW = "run-eval.yml";

  function guessRepo() {
    var m = location.hostname.match(/^([^.]+)\.github\.io$/i);
    if (m) {
      var parts = location.pathname.split("/").filter(Boolean);
      return m[1] + "/" + (parts.length ? parts[0] : m[1] + ".github.io");
    }
    return "";
  }

  // "HEAD" instead of a branch name: GitHub resolves it to the default branch,
  // so the links survive a main/master rename and work from any fork.
  function repoTarget(kind) {
    if (!REPO) return null;
    var base = "https://github.com/" + REPO;
    switch (kind) {
      case "workflow": return base + "/actions/workflows/" + WORKFLOW;
      case "items": return base + "/tree/HEAD/items/bench10";
      case "report": return base + "/blob/HEAD/results/latest.md";
      default: return base;
    }
  }

  function wireLinks() {
    if (!REPO) return; // keep the relative hrefs so local preview still works
    document.querySelectorAll("[data-repo-link]").forEach(function (a) {
      var t = repoTarget(a.getAttribute("data-repo-link"));
      if (t) a.href = t;
    });
  }

  /* ---------- small helpers ---------- */

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function fmt(n) {
    n = Number(n) || 0;
    return n % 1 === 0 ? String(n) : n.toFixed(1);
  }

  function headRow(list, numeric) {
    return "<thead><tr>" + list.map(function (label, i) {
      var num = numeric.indexOf(i) >= 0 ? ' class="num"' : "";
      return "<th" + num + ">" + label + "</th>";
    }).join("") + "</tr></thead>";
  }

  /* ---------- copy ---------- */

  var T = {
    zh: {
      itemsHead: headRow(["编号", "轨道", "任务", "得分点", "材料", "依据"], [3, 4]),
      loading: "加载中…",
      itemsEmpty: "题集索引未生成。运行 python tools/build_items_index.py 后刷新。",
      itemsSummary: function (d) {
        return d.count + " 道题 · 合计 " + fmt(d.total_points) + " 分得分点 · 来源 " + (d.source || "");
      },
      docs: function (n) { return n ? n + " 份" : "开卷"; },
      basisSep: "、",
      noRun: "还没有发布的 run。触发工作流，或在本地跑一遍 CLI。",
      runMeta: function (d) {
        return (d.run_id || "run") + " · " + stamp(d.started_at) + " · " + (d.model || "?") +
               " · 评阅：" + (d.judge_mode || "?");
      },
      overall: "总体",
      scored: "已评分",
      model: "模型",
      resultHead: headRow(["题目", "任务类型", "轨道", "得分", "%"], [3, 4]),
      err: "错误"
    },
    en: {
      itemsHead: headRow(["ID", "Track", "Task", "Points", "Docs", "Authority"], [3, 4]),
      loading: "Loading…",
      itemsEmpty: "Item index not built. Run python tools/build_items_index.py and reload.",
      itemsSummary: function (d) {
        return d.count + " items · " + fmt(d.total_points) + " points · from " + (d.source || "");
      },
      docs: function (n) { return n ? String(n) : "open-book"; },
      basisSep: ", ",
      noRun: "No run published yet. Trigger the workflow, or run the CLI locally.",
      runMeta: function (d) {
        return (d.run_id || "run") + " · " + stamp(d.started_at) + " · " + (d.model || "?") +
               " · judged by " + (d.judge_mode || "?");
      },
      overall: "Overall",
      scored: "Items scored",
      model: "Model",
      resultHead: headRow(["Item", "Task", "Track", "Score", "%"], [3, 4]),
      err: "err"
    }
  };

  var LANG = "en";
  function t() { return T[LANG]; }

  // Fixed layout: with auto layout the 依据 column (long CJK strings, 1-char
  // min-content) collapses and wraps one character per line. Widths live in CSS.
  var ITEM_COLS = "<colgroup>" +
    '<col class="c-id"><col class="c-track"><col class="c-task">' +
    '<col class="c-pts"><col class="c-docs"><col class="c-basis"></colgroup>';

  function stamp(s) {
    return (s || "").replace("T", " ").slice(0, 16);
  }

  /* ---------- language ---------- */

  var LANG_KEY = "acnlb-lang";

  function setLang(lang) {
    LANG = lang === "zh" ? "zh" : "en";
    document.querySelectorAll("[data-lang]").forEach(function (el) {
      el.hidden = el.getAttribute("data-lang") !== LANG;
    });
    // One element per control: swap the label instead of shipping an en + a zh copy.
    document.querySelectorAll("[data-label-en][data-label-zh]").forEach(function (el) {
      var v = el.getAttribute(LANG === "zh" ? "data-label-zh" : "data-label-en");
      if (v) el.textContent = v;
    });
    document.documentElement.lang = LANG === "zh" ? "zh-CN" : "en";
    var btn = document.getElementById("lang-toggle");
    if (btn) btn.textContent = LANG === "zh" ? "EN" : "中文";
    try { localStorage.setItem(LANG_KEY, LANG); } catch (e) {}
    if (RUN_DATA) render(RUN_DATA);
    if (ITEM_DATA) renderItems(ITEM_DATA);
  }

  function initLang() {
    var saved = null;
    try { saved = localStorage.getItem(LANG_KEY); } catch (e) {}
    if (!saved) {
      saved = (navigator.language || "en").toLowerCase().indexOf("zh") === 0 ? "zh" : "en";
    }
    setLang(saved);
    var btn = document.getElementById("lang-toggle");
    if (btn) btn.addEventListener("click", function () {
      setLang(LANG === "zh" ? "en" : "zh");
    });
  }

  /* ---------- item set (site/items.json) ---------- */

  var ITEM_DATA = null;

  function renderItems(data) {
    var status = document.getElementById("items-status");
    var body = document.getElementById("items-body");
    if (!status || !body) return;
    body.textContent = "";

    if (!data || !data.items || !data.items.length) {
      status.textContent = t().itemsEmpty;
      return;
    }

    status.textContent = t().itemsSummary(data);

    var table = el("table", "items-table");
    table.innerHTML = ITEM_COLS + t().itemsHead;
    var tb = el("tbody");
    data.items.forEach(function (it) {
      var tr = document.createElement("tr");
      tr.appendChild(el("td", "mono", it.id));
      tr.appendChild(el("td", null, it.track_label || it.track));

      var task = el("td");
      task.appendChild(el("div", "cell-main", it.task_type));
      if (it.task) task.appendChild(el("div", "cell-sub", it.task));
      tr.appendChild(task);

      tr.appendChild(el("td", "num", fmt(it.points)));
      tr.appendChild(el("td", "num", t().docs(it.documents)));
      tr.appendChild(el("td", "basis",
        (it.authority_basis || []).join(t().basisSep) || "—"));
      tb.appendChild(tr);
    });
    table.appendChild(tb);

    var wrap = el("div", "table-wrap");
    wrap.appendChild(table);
    body.appendChild(wrap);
  }

  /* ---------- latest run (results/latest.json) ---------- */

  var RUN_DATA = null;

  function stat(k, v) {
    var d = el("div", "stat");
    d.appendChild(el("div", "k", k));
    d.appendChild(el("div", "v", v));
    return d;
  }

  function render(data) {
    var status = document.getElementById("results-status");
    var body = document.getElementById("results-body");
    body.textContent = "";

    if (!data || !data.items || !data.items.length) {
      status.className = "muted";
      status.textContent = t().noRun;
      return;
    }

    var scored = data.items.filter(function (i) { return !i.error; });
    var earned = scored.reduce(function (s, i) { return s + i.score; }, 0);
    var max = scored.reduce(function (s, i) { return s + i.max_positive_points; }, 0);
    var overall = max ? (100 * earned / max) : 0;

    status.className = "tagline-run";
    status.textContent = t().runMeta(data);

    var row = el("div", "stat-row");
    row.appendChild(stat(t().overall, overall.toFixed(1) + "%"));
    row.appendChild(stat(t().scored, scored.length + " / " + data.items.length));
    row.appendChild(stat(t().model, data.model || "?"));
    body.appendChild(row);

    var pt = data.per_track || {};
    var tracks = Object.keys(pt).sort();
    if (tracks.length) {
      var wrap = el("div", "tracks");
      tracks.forEach(function (name) {
        var pct = Number(pt[name].pct) || 0;
        var line = el("div", "track");
        line.appendChild(el("div", "name", name));
        var rail = el("div", "rail");
        var fill = el("span");
        fill.style.width = Math.max(0, Math.min(100, pct)) + "%";
        rail.appendChild(fill);
        line.appendChild(rail);
        line.appendChild(el("div", "pct", pct.toFixed(1) + "%"));
        wrap.appendChild(line);
      });
      body.appendChild(wrap);
      // paint after insertion so the width transition reads as a reveal
      requestAnimationFrame(function () {
        wrap.querySelectorAll(".rail > span").forEach(function (f, idx) {
          var pct = Number(pt[tracks[idx]].pct) || 0;
          f.style.width = Math.max(0, Math.min(100, pct)) + "%";
        });
      });
      wrap.querySelectorAll(".rail > span").forEach(function (f) { f.style.width = "0%"; });
    }

    var table = el("table");
    table.innerHTML = t().resultHead;
    var tb = el("tbody");
    data.items.forEach(function (i) {
      var tr = document.createElement("tr");
      tr.appendChild(el("td", "mono", i.item_id));
      tr.appendChild(el("td", null, i.task_type));
      tr.appendChild(el("td", null, i.track));
      tr.appendChild(el("td", "num",
        i.error ? t().err : fmt(i.score) + " / " + fmt(i.max_positive_points)));
      tr.appendChild(el("td", "num", i.error ? "—" : i.pct.toFixed(1) + "%"));
      tb.appendChild(tr);
    });
    table.appendChild(tb);

    var wrap2 = el("div", "table-wrap");
    wrap2.appendChild(table);
    body.appendChild(wrap2);

    if (data.notes && data.notes.length) {
      data.notes.forEach(function (n) {
        body.appendChild(el("p", "soft", n));
      });
    }
  }

  /* The page is served from the site root on Pages (results/ sits next to it)
   * and from site/ during local preview (results/ one level up). Try both so the
   * same file works in either layout. items.json always sits next to the page. */
  var RESULT_PATHS = ["results/latest.json", "../results/latest.json"];
  var ITEM_PATHS = ["items.json"];

  function fetchFirst(paths, i) {
    if (i >= paths.length) return Promise.reject(new Error("not found"));
    return fetch(paths[i], { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .catch(function () { return fetchFirst(paths, i + 1); });
  }

  function loadItems() {
    fetchFirst(ITEM_PATHS, 0)
      .then(function (d) { ITEM_DATA = d; renderItems(d); })
      .catch(function () {
        var s = document.getElementById("items-status");
        if (s) s.textContent = t().itemsEmpty;
      });
  }

  function loadRun() {
    fetchFirst(RESULT_PATHS, 0)
      .then(function (d) { RUN_DATA = d; render(d); })
      .catch(function () {
        var s = document.getElementById("results-status");
        if (s) s.className = "muted";
        if (s) s.textContent = t().noRun;
      });
  }

  function primeStatus() {
    ["items-status", "results-status"].forEach(function (id) {
      var n = document.getElementById(id);
      if (n) n.textContent = t().loading;
    });
  }

  wireLinks();
  initLang();
  primeStatus();
  loadItems();
  loadRun();
})();
