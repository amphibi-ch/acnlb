/* acnlb front door. Static; no build step.
 * Reads the committed results/latest.json, wires the language toggle, and points
 * the repo-relative links at the right GitHub paths. No key is handled here. */
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

  // Paths inside site/ are static while developing; on Pages they resolve against
  // the repo root. Rewrite them once we know the repo.
  function repoTarget(kind) {
    if (!REPO) return null;
    var base = "https://github.com/" + REPO;
    switch (kind) {
      case "workflow": return base + "/actions/workflows/" + WORKFLOW;
      case "items": return base + "/tree/main/items/sample";
      case "report": return base + "/blob/main/results/latest.md";
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

  /* ---------- language ---------- */

  var LANG_KEY = "acnlb-lang";

  function setLang(lang) {
    document.querySelectorAll("[data-lang]").forEach(function (el) {
      el.hidden = el.getAttribute("data-lang") !== lang;
    });
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
    var btn = document.getElementById("lang-toggle");
    if (btn) btn.textContent = lang === "zh" ? "EN" : "中文";
    try { localStorage.setItem(LANG_KEY, lang); } catch (e) {}
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
      var cur = document.documentElement.lang.indexOf("zh") === 0 ? "zh" : "en";
      setLang(cur === "zh" ? "en" : "zh");
    });
  }

  /* ---------- results ---------- */

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

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
      status.textContent = "No run published yet. Trigger the workflow to publish one.";
      return;
    }

    var scored = data.items.filter(function (i) { return !i.error; });
    var earned = scored.reduce(function (s, i) { return s + i.score; }, 0);
    var max = scored.reduce(function (s, i) { return s + i.max_positive_points; }, 0);
    var overall = max ? (100 * earned / max) : 0;

    status.className = "tagline-run";
    status.textContent =
      (data.run_id || "run") + " · " + (data.started_at || "").replace("T", " ").slice(0, 16) +
      " · " + (data.model || "?") + " · judged by " + (data.judge_mode || "?");

    var row = el("div", "stat-row");
    row.appendChild(stat("Overall", overall.toFixed(1) + "%"));
    row.appendChild(stat("Items scored", scored.length + " / " + data.items.length));
    row.appendChild(stat("Model", data.model || "?"));
    body.appendChild(row);

    var pt = data.per_track || {};
    var tracks = Object.keys(pt).sort();
    if (tracks.length) {
      var wrap = el("div", "tracks");
      tracks.forEach(function (name) {
        var t = pt[name];
        var pct = Number(t.pct) || 0;
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
          var t = pt[tracks[idx]];
          f.style.width = Math.max(0, Math.min(100, Number(t.pct) || 0)) + "%";
        });
      });
      wrap.querySelectorAll(".rail > span").forEach(function (f) { f.style.width = "0%"; });
    }

    var table = el("table");
    table.innerHTML =
      "<thead><tr><th>Item</th><th>Task</th><th>Track</th>" +
      '<th class="num">Score</th><th class="num">%</th></tr></thead>';
    var tb = el("tbody");
    data.items.forEach(function (i) {
      var tr = document.createElement("tr");
      tr.appendChild(el("td", null, i.item_id));
      tr.appendChild(el("td", null, i.task_type));
      tr.appendChild(el("td", null, i.track));
      tr.appendChild(el("td", "num", i.error ? "err" : i.score + " / " + i.max_positive_points));
      tr.appendChild(el("td", "num", i.error ? "—" : i.pct.toFixed(1) + "%"));
      tb.appendChild(tr);
    });
    table.appendChild(tb);
    body.appendChild(table);

    if (data.notes && data.notes.length) {
      data.notes.forEach(function (n) {
        body.appendChild(el("p", "soft", n));
      });
    }
  }

  function load() {
    fetch("../results/latest.json", { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(render)
      .catch(function () {
        var s = document.getElementById("results-status");
        if (s) s.textContent =
          "No results published yet. Trigger the workflow, or run the CLI locally.";
      });
  }

  wireLinks();
  initLang();
  load();
})();
