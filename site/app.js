/* acnlb front door — static, no build step.
 * Renders the committed results/latest.json, wires the language toggle, and
 * points the "Run this eval" button at this repo's workflow_dispatch page.
 *
 * No key is ever handled here; the site only reads a committed results file.
 */
(function () {
  "use strict";

  // Derive the repo from the Pages URL by default; allow an override.
  var REPO = (window.ACNLB_REPO || "").trim() || guessRepo();
  var WORKFLOW_FILE = "run-eval.yml";

  function guessRepo() {
    // user.github.io/<repo>/... -> owner/repo ; owner.github.io/ -> owner/owner.github.io
    var host = location.hostname;
    var parts = location.pathname.split("/").filter(Boolean);
    var m = host.match(/^([^.]+)\.github\.io$/i);
    if (m) {
      var owner = m[1];
      var repo = parts.length ? parts[0] : owner + ".github.io";
      return owner + "/" + repo;
    }
    return ""; // local file/server: buttons fall back to GitHub search
  }

  function workflowUrl() {
    if (!REPO) return "https://github.com/search?q=acnlb&type=repositories";
    return (
      "https://github.com/" + REPO + "/actions/workflows/" + WORKFLOW_FILE +
      "/../../../../actions/workflows/" + WORKFLOW_FILE + "/dispatches"
    );
  }

  function workflowPageUrl() {
    if (!REPO) return "https://github.com/search?q=acnlb&type=repositories";
    return "https://github.com/" + REPO + "/actions/workflows/" + WORKFLOW_FILE;
  }

  function colabUrl() {
    if (!REPO) return "https://colab.research.google.com/";
    return (
      "https://colab.research.google.com/github/" + REPO +
      "/blob/main/notebooks/acnlb_quickstart.ipynb"
    );
  }

  function wireButtons() {
    var run = document.getElementById("run-on-gh");
    if (run) {
      run.href = workflowPageUrl();
      run.title = "Opens the workflow page — click “Run workflow” to dispatch it";
    }
    var colab = document.getElementById("colab-link");
    if (colab) colab.href = colabUrl();
  }

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
    if (!saved) saved = (navigator.language || "en").toLowerCase().indexOf("zh") === 0 ? "zh" : "en";
    setLang(saved);
    var btn = document.getElementById("lang-toggle");
    if (btn) btn.addEventListener("click", function () {
      var cur = document.documentElement.lang.indexOf("zh") === 0 ? "zh" : "en";
      setLang(cur === "zh" ? "en" : "zh");
    });
  }

  function pctColor(p) { return p >= 70 ? "var(--ok)" : p >= 40 ? "var(--warn)" : "#e06c6c"; }

  function renderResults(data) {
    var status = document.getElementById("results-status");
    var body = document.getElementById("results-body");

    if (!data || !data.items || !data.items.length) {
      status.textContent = "No published run yet — trigger the workflow to publish one.";
      return;
    }
    var scored = data.items.filter(function (i) { return !i.error; });
    var earned = scored.reduce(function (s, i) { return s + i.score; }, 0);
    var max = scored.reduce(function (s, i) { return s + i.max_positive_points; }, 0);
    var overall = max ? (100 * earned / max) : 0;

    status.textContent = "Run " + (data.run_id || "?") + " · " + (data.started_at || "") +
      " · model " + (data.model || "?") + " · judge " + (data.judge_mode || "?");

    var cards = document.createElement("div");
    cards.className = "score-cards";
    cards.appendChild(card("Overall", overall.toFixed(1) + "%"));
    cards.appendChild(card("Items scored", scored.length + "/" + data.items.length));
    cards.appendChild(card("Model", data.model || "?"));
    cards.appendChild(card("Judge", data.judge_mode || "?"));
    body.appendChild(cards);

    var pt = data.per_track || {};
    var tracks = Object.keys(pt).sort();
    if (tracks.length) {
      var h = document.createElement("h3");
      h.textContent = "Per-track";
      body.appendChild(h);
      var t = document.createElement("table");
      t.innerHTML = "<thead><tr><th>Track</th><th>Items</th><th>Score</th><th>%</th></tr></thead>";
      var tb = document.createElement("tbody");
      tracks.forEach(function (k) {
        var v = pt[k];
        var tr = document.createElement("tr");
        tr.innerHTML = "<td>" + esc(k) + "</td><td>" + v.n + "</td><td>" +
          v.earned + " / " + v.max + "</td><td>" + v.pct.toFixed(1) + "%</td>";
        tb.appendChild(tr);
      });
      t.appendChild(tb);
      body.appendChild(t);
    }

    var h2 = document.createElement("h3");
    h2.textContent = "Per-item";
    body.appendChild(h2);
    var it = document.createElement("table");
    it.innerHTML = "<thead><tr><th>Item</th><th>Track</th><th>Task</th><th>Score</th><th>%</th></tr></thead>";
    var ib = document.createElement("tbody");
    data.items.forEach(function (i) {
      var tr = document.createElement("tr");
      var res = i.error
        ? '<span class="badge badge-warn">ERROR</span>'
        : (i.score + " / " + i.max_positive_points);
      tr.innerHTML = "<td><code>" + esc(i.item_id) + "</code></td><td>" + esc(i.track) +
        "</td><td>" + esc(i.task_type) + "</td><td>" + res + "</td><td>" +
        (i.error ? "—" : i.pct.toFixed(1) + "%") + "</td>";
      ib.appendChild(tr);
    });
    it.appendChild(ib);
    body.appendChild(it);

    if (data.notes && data.notes.length) {
      data.notes.forEach(function (n) {
        var p = document.createElement("p");
        p.className = "hint";
        p.textContent = "⚠️ " + n;
        body.appendChild(p);
      });
    }
  }

  function card(k, v) {
    var d = document.createElement("div");
    d.className = "score-card";
    d.innerHTML = '<div class="k">' + esc(k) + '</div><div class="v">' + esc(v) + "</div>";
    return d;
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function loadResults() {
    fetch("../results/latest.json", { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(renderResults)
      .catch(function () {
        var s = document.getElementById("results-status");
        if (s) s.textContent =
          "No results/latest.json published yet. Run the workflow, or run the CLI locally.";
      });
  }

  wireButtons();
  initLang();
  loadResults();
})();
