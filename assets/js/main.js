/* ManiScope docs: theme toggle, mobile nav, TOC highlight, sortable tables, client-side search. */
(function () {
  var rel = window.__REL__ || "";

  // ---- theme ----------------------------------------------------------------
  var toggle = document.querySelector(".theme-toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var cur = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", cur);
      try { localStorage.setItem("theme", cur); } catch (e) {}
    });
  }

  // ---- mobile nav -----------------------------------------------------------
  var menu = document.querySelector(".menu-toggle");
  if (menu) {
    menu.addEventListener("click", function () {
      var open = document.body.classList.toggle("nav-open");
      menu.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("click", function (e) {
      if (document.body.classList.contains("nav-open") && !e.target.closest(".sidebar") && !e.target.closest(".menu-toggle")) {
        document.body.classList.remove("nav-open");
      }
    });
  }

  // keep the active sidebar link in view
  var active = document.querySelector(".sidebar-nav .nav-link.active");
  if (active && active.scrollIntoView) {
    try { active.scrollIntoView({ block: "center" }); } catch (e) {}
  }

  // ---- TOC scroll spy -------------------------------------------------------
  var tocLinks = Array.prototype.slice.call(document.querySelectorAll(".toc a"));
  if (tocLinks.length && "IntersectionObserver" in window) {
    var map = {};
    tocLinks.forEach(function (a) { map[a.getAttribute("href").slice(1)] = a; });
    var headings = Object.keys(map).map(function (id) { return document.getElementById(id); }).filter(Boolean);
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          tocLinks.forEach(function (a) { a.classList.remove("active"); });
          var a = map[en.target.id];
          if (a) a.classList.add("active");
        }
      });
    }, { rootMargin: "-70px 0px -70% 0px" });
    headings.forEach(function (h) { obs.observe(h); });
  }

  // ---- embedded dependency graph (assets/depgraph) reports its height -------
  var graphFrames = Array.prototype.slice.call(document.querySelectorAll("iframe.depgraph"));
  if (graphFrames.length) {
    window.addEventListener("message", function (e) {
      if (!e.data || typeof e.data.depgraphHeight !== "number") return;
      graphFrames.forEach(function (f) {
        if (f.contentWindow !== e.source) return;
        var px = Math.ceil(e.data.depgraphHeight) + "px";
        if (f.style.height !== px) f.style.height = px;
      });
    });
    // Ask the frames to (re-)report: they may have loaded and posted before this
    // listener existed (srcdoc iframes need no network request).
    var ping = function () {
      graphFrames.forEach(function (f) {
        try { if (f.contentWindow) f.contentWindow.postMessage({ depgraphPing: 1 }, "*"); } catch (err) { /* not ready yet */ }
      });
    };
    graphFrames.forEach(function (f) { f.addEventListener("load", ping); });
    window.addEventListener("load", ping);
    ping();
  }

  // ---- leaderboard crosshair: highlight the hovered row and column ---------------
  // Cells get a logical column index that accounts for rowspan/colspan (family x level
  // tables put Policy / Overall / Pooled in cells spanning the three level rows), so the
  // column highlight is correct in every row, and hovering any level row also darkens the
  // spanning cells of that policy. Group header rows (single spanning cell) are skipped.
  document.querySelectorAll("body.leaderboard table").forEach(function (table) {
    var body = table.tBodies[0];
    if (!body) return;
    var rows = body.rows, taken = {};
    for (var r = 0; r < rows.length; r++) {
      if (rows[r].classList.contains("group")) continue;
      var col = 0, occ = taken[r] || {};
      for (var c = 0; c < rows[r].cells.length; c++) {
        while (occ[col]) col++;
        var cell = rows[r].cells[c], rs = cell.rowSpan || 1, cs = cell.colSpan || 1;
        cell.dataset.col = col;
        cell.dataset.r0 = r; cell.dataset.r1 = r + rs - 1;
        for (var k = 1; k < rs; k++) {
          taken[r + k] = taken[r + k] || {};
          for (var j = 0; j < cs; j++) taken[r + k][col + j] = true;
        }
        col += cs;
      }
    }
    var cells = Array.prototype.slice.call(body.querySelectorAll("td[data-col]"));
    var key = null;
    function clear() {
      cells.forEach(function (c) { c.classList.remove("col-hl", "row-hl"); });
      key = null;
    }
    table.addEventListener("mouseover", function (e) {
      var td = e.target.closest("td");
      if (!td || !table.contains(td) || td.dataset.col === undefined) { if (key !== null) clear(); return; }
      var col = td.dataset.col, r0 = +td.dataset.r0, r1 = +td.dataset.r1;
      var k = col + ":" + r0 + "-" + r1;
      if (k === key) return;
      clear();
      key = k;
      cells.forEach(function (c) {
        if (c.dataset.col === col) c.classList.add("col-hl");
        // rows covered by the hovered cell (one row, or three for a spanning cell) and the
        // spanning cells that cover the hovered row
        var c0 = +c.dataset.r0, c1 = +c.dataset.r1;
        if (c !== td && c1 >= r0 && c0 <= r1) c.classList.add("row-hl");
      });
    });
    table.addEventListener("mouseleave", clear);
  });

  // ---- sortable tables ------------------------------------------------------
  // Rows are emitted in the paper's order and stay that way until a header is clicked.
  // Two-row headers: only the first header row carries sortable cells; column index is
  // derived from the header's position among first-row cells (rowspan cells count once).
  document.querySelectorAll("table.sortable").forEach(function (table) {
    var firstRow = table.tHead && table.tHead.rows[0];
    if (!firstRow) return;
    var ths = firstRow.cells;
    Array.prototype.forEach.call(ths, function (th, idx) {
      if (!th.hasAttribute("data-sort")) return;
      th.addEventListener("click", function () {
        var asc = th.classList.contains("sorted") && !th.classList.contains("asc");
        Array.prototype.forEach.call(ths, function (t) { t.classList.remove("sorted", "asc"); });
        th.classList.add("sorted");
        if (asc) th.classList.add("asc");
        var tbody = table.tBodies[0];
        var all = Array.prototype.slice.call(tbody.rows);
        function key(r) {
          var c = r.cells[idx];
          var v = c ? parseFloat(c.getAttribute("data-sort") || c.textContent) : NaN;
          return isNaN(v) ? -Infinity : v;
        }
        // sort each segment between "group" header rows independently
        var out = [], segment = [];
        function flush() {
          segment.sort(function (a, b) { return asc ? key(a) - key(b) : key(b) - key(a); });
          out = out.concat(segment); segment = [];
        }
        all.forEach(function (r) {
          if (r.classList.contains("group")) { flush(); out.push(r); } else { segment.push(r); }
        });
        flush();
        out.forEach(function (r) { tbody.appendChild(r); });
      });
    });
  });

  // ---- search ---------------------------------------------------------------
  var input = document.getElementById("search-input");
  var box = document.getElementById("search-results");
  if (input && box) {
    var index = null, sel = -1, localizedIndex = null;
    var i18n = window.ManipScopeI18n;
    function localize(docs) {
      if (!i18n || i18n.getLanguage() !== "zh") return docs;
      if (!localizedIndex) localizedIndex = docs.map(function (d) {
        return { title: i18n.translate(d.title), url: d.url, text: i18n.searchText(d.text) };
      });
      return localizedIndex;
    }
    function load() {
      if (index) return Promise.resolve(index);
      return fetch(rel + "search-index.json").then(function (r) { return r.json(); }).then(function (d) { index = d; return d; });
    }
    function render(items) {
      if (!items.length) { box.hidden = true; box.innerHTML = ""; return; }
      var suffix = window.__CLEAN_URLS__ ? "" : "index.html";
      box.innerHTML = items.map(function (it) {
        return '<a href="' + rel + it.url + suffix + '?lang=' + (i18n ? i18n.getLanguage() : 'en') + '"><div class="t">' + escapeHtml(it.title) + '</div><div class="s">' + escapeHtml(it.snippet) + '</div></a>';
      }).join("");
      box.hidden = false; sel = -1;
    }
    function escapeHtml(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
    function search(q) {
      q = q.trim().toLowerCase();
      if (q.length < 2) { render([]); return; }
      load().then(function (docs) {
        var terms = q.split(/\s+/);
        var scored = [];
        localize(docs).forEach(function (d) {
          var title = d.title.toLowerCase(), text = d.text.toLowerCase(), score = 0;
          terms.forEach(function (t) {
            if (title.indexOf(t) !== -1) score += 10;
            var i = text.indexOf(t);
            if (i !== -1) score += 2;
          });
          if (score > 0) {
            var i = text.indexOf(terms[0]);
            var start = Math.max(0, i - 60);
            scored.push({ score: score, title: d.title, url: d.url, snippet: (start > 0 ? "…" : "") + d.text.slice(start, start + 140) + "…" });
          }
        });
        scored.sort(function (a, b) { return b.score - a.score; });
        render(scored.slice(0, 8));
      });
    }
    document.addEventListener("languagechange", function () {
      if (input.value) search(input.value);
      else { box.hidden = true; box.innerHTML = ""; }
    });
    var timer;
    input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(function () { search(input.value); }, 80); });
    input.addEventListener("focus", function () { if (input.value) search(input.value); });
    input.addEventListener("keydown", function (e) {
      var links = box.querySelectorAll("a");
      if (!links.length) return;
      if (e.key === "ArrowDown") { sel = Math.min(sel + 1, links.length - 1); }
      else if (e.key === "ArrowUp") { sel = Math.max(sel - 1, 0); }
      else if (e.key === "Enter" && sel >= 0) { links[sel].click(); return; }
      else if (e.key === "Escape") { box.hidden = true; return; }
      else return;
      e.preventDefault();
      links.forEach(function (l, i) { l.classList.toggle("sel", i === sel); });
    });
    document.addEventListener("click", function (e) { if (!e.target.closest(".search")) box.hidden = true; });
    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); input.focus(); }
    });
  }
})();
