// Single-file reader: hash routing + theme toggle + mobile drawer + sidebar tabs.
// Every "page" is a <section data-view="…"> in one document; we just show one.
// No dependencies, no server — works from a file:// double-click.
(function () {
  var root = document.documentElement;
  var themeBtn = document.getElementById("theme-toggle");
  var navBtn = document.getElementById("nav-toggle");
  var sidebar = document.getElementById("sidebar");
  var scrim = document.getElementById("scrim");
  var layout = document.querySelector(".layout");

  var views = Array.prototype.slice.call(document.querySelectorAll("[data-view]"));
  var sidebarLinks = document.querySelectorAll(".nav-panel a");
  var topnavLinks = document.querySelectorAll(".topnav a");
  var baseTitle = document.title;

  // --- theme ---------------------------------------------------------------
  function currentTheme() {
    if (root.dataset.theme) return root.dataset.theme;
    var mql = window.matchMedia("(prefers-color-scheme: dark)");
    return mql.matches ? "dark" : "light";
  }
  themeBtn && themeBtn.addEventListener("click", function () {
    var next = currentTheme() === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch (e) {}
  });

  // --- mobile drawer -------------------------------------------------------
  function closeNav() {
    sidebar && sidebar.classList.remove("open");
    scrim && scrim.classList.remove("show");
  }
  navBtn && navBtn.addEventListener("click", function () {
    if (!sidebar) return;
    var open = sidebar.classList.toggle("open");
    scrim && scrim.classList.toggle("show", open);
  });
  scrim && scrim.addEventListener("click", closeNav);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeNav();
  });

  // --- sidebar daily/weekly tabs ------------------------------------------
  var tabs = document.querySelectorAll(".nav-tabs .tab");
  var panels = document.querySelectorAll(".nav-panel");
  function showPanel(kind) {
    tabs.forEach(function (t) { t.classList.toggle("active", t.dataset.tab === kind); });
    panels.forEach(function (p) { p.hidden = p.dataset.panel !== kind; });
  }
  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () { showPanel(tab.dataset.tab); });
  });

  // --- view routing --------------------------------------------------------
  function viewEl(id) {
    for (var i = 0; i < views.length; i++) {
      if (views[i].dataset.view === id) return views[i];
    }
    return null;
  }
  function defaultView() {
    var d = document.querySelector("[data-view][data-default]");
    return d ? d.dataset.view : (views[0] ? views[0].dataset.view : "");
  }

  function show(id) {
    var el = viewEl(id);
    if (!el) { id = defaultView(); el = viewEl(id); }
    if (!el) return;

    views.forEach(function (v) { v.hidden = v.dataset.view !== id; });

    var kind = el.dataset.kind;               // daily | weekly | standalone
    var navKey = el.dataset.nav || kind;      // topnav group to light up
    layout && layout.classList.toggle("standalone-active", kind === "standalone");

    sidebarLinks.forEach(function (a) {
      a.classList.toggle("active", a.getAttribute("href") === "#" + id);
    });
    topnavLinks.forEach(function (a) {
      a.classList.toggle("active", a.dataset.nav === navKey);
    });

    // keep the sidebar tab in sync with the kind of digest being read
    if (kind === "daily" || kind === "weekly") showPanel(kind);

    document.title = (el.dataset.title || id) + " · " + baseTitle;

    var active = document.querySelector(".nav-panel a.active");
    if (active) active.scrollIntoView({ block: "nearest" });
    window.scrollTo(0, 0);
  }

  window.addEventListener("hashchange", function () {
    show(decodeURIComponent(location.hash.slice(1)));
    closeNav();
  });
  show(decodeURIComponent(location.hash.slice(1)) || defaultView());
})();

// === future-tech watchlist via a private GitHub Gist ======================
// Token-only: paste a PAT with `gist` scope; the client auto-finds or creates
// ONE private gist (watchlist.json). Token + resolved gist id live in
// localStorage only, never in the repo. Logged-out visitors see the public
// read-only snapshot inlined as window.__WATCHLIST_PUBLIC__ (published by a
// scheduled Action). Logged-in owner sees the live gist and can edit/note.
(function () {
  var LS_TOKEN = "sn_gist_token", LS_ID = "sn_gist_id";
  var WL_FILE = "watchlist.json";
  var GIST_DESC = "social_news · 未来技术待调研 watchlist（请勿删除）";
  var API = "https://api.github.com";
  var items = null;            // cached live watchlist array (owner)
  var loaded = false;
  var saveTimer = null;

  function token() { return (localStorage.getItem(LS_TOKEN) || "").trim(); }
  function gistId() { return (localStorage.getItem(LS_ID) || "").trim(); }
  function loggedIn() { return !!token(); }
  function norm(u) { return (u || "").split("#")[0].replace(/\/$/, ""); }
  function publicItems() {
    var p = window.__WATCHLIST_PUBLIC__;
    return Array.isArray(p) ? p : [];
  }

  function ghFetch(path, opts) {
    opts = opts || {};
    var h = { Accept: "application/vnd.github+json" };
    if (token()) h.Authorization = "Bearer " + token();
    if (opts.body) h["Content-Type"] = "application/json";
    return fetch(API + path, {
      method: opts.method || "GET",
      headers: h,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    }).then(function (r) {
      if (!r.ok) throw new Error("GitHub API " + r.status);
      return r.json();
    });
  }

  // Find the watchlist gist for this token, or create it. Caches the id.
  function ensureGist() {
    if (gistId()) return Promise.resolve(gistId());
    return ghFetch("/gists?per_page=100").then(function (gists) {
      var found = (gists || []).filter(function (g) {
        return g.description === GIST_DESC || (g.files && g.files[WL_FILE]);
      })[0];
      if (found) return found.id;
      var body = { description: GIST_DESC, public: false, files: {} };
      body.files[WL_FILE] = { content: "[]" };
      return ghFetch("/gists", { method: "POST", body: body }).then(function (g) {
        return g.id;
      });
    }).then(function (id) {
      localStorage.setItem(LS_ID, id);
      return id;
    });
  }

  function readGist() {
    return ensureGist().then(function (id) {
      return ghFetch("/gists/" + id);
    }).then(function (g) {
      var f = g.files && g.files[WL_FILE];
      if (!f || !f.content) return [];
      try { return JSON.parse(f.content) || []; } catch (e) { return []; }
    });
  }

  function writeGist(arr) {
    var id = gistId();
    if (!id) return Promise.reject(new Error("未登录"));
    var body = { files: {} };
    body.files[WL_FILE] = { content: JSON.stringify(arr, null, 2) };
    return ghFetch("/gists/" + id, { method: "PATCH", body: body });
  }
  // Debounce writes so rapid note edits collapse into one PATCH.
  function scheduleSave() {
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(function () {
      writeGist(items).catch(function (e) { toast("同步失败：" + e.message); });
    }, 700);
  }

  function ensure() {
    if (loaded && items) return Promise.resolve(items);
    if (!loggedIn()) { items = []; loaded = true; return Promise.resolve(items); }
    return readGist().then(function (a) { items = a; loaded = true; return a; });
  }
  function has(url) {
    var n = norm(url);
    var list = loggedIn() ? (items || []) : publicItems();
    return list.some(function (it) { return norm(it.url) === n; });
  }

  function escapeHtml(s) {
    return (s || "").replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function nowISO() {
    try { return new Date().toISOString().slice(0, 10); } catch (e) { return ""; }
  }

  // --- ☆ bookmark buttons on every news item ------------------------------
  function decorate() {
    var lis = document.querySelectorAll(".view-digest .prose li");
    lis.forEach(function (li) {
      if (li.querySelector(".bm-btn")) return;
      var a = li.querySelector('a[href^="http"]');
      if (!a) return;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "bm-btn";
      btn.title = "收藏到未来技术 Watchlist";
      btn.setAttribute("aria-label", "收藏");
      btn.textContent = "☆";
      btn.dataset.url = a.href;
      btn.dataset.title = (a.textContent || "").trim() ||
        (li.textContent || "").trim().slice(0, 60);
      li.appendChild(btn);
      btn.addEventListener("click", onBookmark);
    });
    refreshButtons();
  }
  function refreshButtons() {
    document.querySelectorAll(".bm-btn").forEach(function (b) {
      var on = has(b.dataset.url);
      b.classList.toggle("on", on);
      b.textContent = on ? "★" : "☆";
    });
  }
  function flash(btn, txt) {
    btn.textContent = txt;
    btn.classList.add("err");
    setTimeout(function () { btn.classList.remove("err"); refreshButtons(); }, 1400);
  }

  function onBookmark(e) {
    var btn = e.currentTarget;
    if (!loggedIn()) { openModal("请先登录：粘贴一个有 gist 权限的 token"); return; }
    ensure().then(function () {
      var url = btn.dataset.url, n = norm(url);
      if (has(url)) {
        items = items.filter(function (it) { return norm(it.url) !== n; });
      } else {
        items.unshift({ title: btn.dataset.title, url: url, added: nowISO(), note: "" });
      }
      btn.textContent = "…";
      return writeGist(items);
    }).then(function () {
      refreshButtons(); renderWatchlist();
    }).catch(function (err) {
      flash(btn, "!"); console.error(err); toast(err.message);
    });
  }

  // --- watchlist widget on the future page --------------------------------
  function itemRow(it, editable) {
    var date = it.added ? '<span class="wl-date">' + escapeHtml(it.added) + "</span> " : "";
    var src = it.source ? ' <span class="wl-src">· ' + escapeHtml(it.source) + "</span>" : "";
    var head = date + '<a href="' + encodeURI(it.url) + '" target="_blank" rel="noopener">' +
      escapeHtml(it.title || it.url) + "</a>" + src;
    var note = it.note || "";
    if (editable) {
      return '<li data-url="' + escapeHtml(it.url) + '">' +
        '<div class="wl-row">' + head +
        '<button type="button" class="wl-rm" title="移除">✕</button></div>' +
        '<textarea class="wl-note" placeholder="备注（会随公开快照公开）">' +
        escapeHtml(note) + "</textarea></li>";
    }
    var noteRo = note ? '<div class="wl-note-ro">' + escapeHtml(note) + "</div>" : "";
    return "<li>" + '<div class="wl-row">' + head + "</div>" + noteRo + "</li>";
  }

  function renderList(box, arr, editable) {
    if (!arr.length) {
      box.innerHTML = '<p class="muted">' +
        (editable ? "清单为空。在任意新闻条目旁点 ☆ 即可收藏。"
                  : "暂无公开收藏。") + "</p>";
      return;
    }
    var html = '<ul class="wl-items">';
    arr.forEach(function (it) { html += itemRow(it, editable); });
    html += "</ul>";
    box.innerHTML = html;
    if (editable) wireEditable(box);
  }

  function wireEditable(box) {
    box.querySelectorAll(".wl-rm").forEach(function (rm) {
      rm.addEventListener("click", function () {
        var url = rm.closest("li").dataset.url, n = norm(url);
        items = (items || []).filter(function (it) { return norm(it.url) !== n; });
        writeGist(items).then(function () { renderWatchlist(); refreshButtons(); })
          .catch(function (e) { toast(e.message); });
      });
    });
    box.querySelectorAll(".wl-note").forEach(function (ta) {
      ta.addEventListener("input", function () {
        var url = ta.closest("li").dataset.url, n = norm(url);
        var it = (items || []).filter(function (x) { return norm(x.url) === n; })[0];
        if (it) { it.note = ta.value; scheduleSave(); }
      });
    });
  }

  function renderWatchlist() {
    var box = document.getElementById("wl-list");
    if (!box) return;
    if (!loggedIn()) {
      renderList(box, publicItems(), false);
      return;
    }
    box.innerHTML = '<p class="muted">加载中…</p>';
    ensure().then(function (arr) { renderList(box, arr, true); })
      .catch(function (err) {
        box.innerHTML = '<p class="muted">读取失败：' + escapeHtml(err.message) +
          '（token 是否有 gist 权限？）</p>';
      });
  }

  // --- login modal (token only) -------------------------------------------
  var modal = document.getElementById("gist-modal");
  function openModal(hint) {
    if (!modal) return;
    var tkEl = document.getElementById("gist-token");
    if (tkEl) tkEl.value = token();
    var msg = document.getElementById("gist-msg");
    if (msg) {
      msg.hidden = !hint; msg.textContent = hint || "";
      msg.className = "modal-msg" + (hint ? " warn" : "");
    }
    modal.hidden = false;
  }
  function closeModal() { if (modal) modal.hidden = true; }

  function wireModal() {
    if (!modal) return;
    var save = document.getElementById("gist-save");
    var cancel = document.getElementById("gist-cancel");
    var logout = document.getElementById("gist-clear");
    save && save.addEventListener("click", function () {
      var tk = (document.getElementById("gist-token").value || "").trim();
      if (!tk) { openModal("请粘贴 token"); return; }
      localStorage.setItem(LS_TOKEN, tk);
      localStorage.removeItem(LS_ID);   // re-discover under the new token
      loaded = false; items = null;
      closeModal();
      renderWatchlist();
      ensure().then(refreshButtons).catch(function (e) { toast(e.message); });
    });
    cancel && cancel.addEventListener("click", closeModal);
    logout && logout.addEventListener("click", function () {
      localStorage.removeItem(LS_TOKEN); localStorage.removeItem(LS_ID);
      loaded = false; items = null;
      var tkEl = document.getElementById("gist-token");
      if (tkEl) tkEl.value = "";
      closeModal(); renderWatchlist(); refreshButtons();
    });
    modal.addEventListener("click", function (e) {
      if (e.target === modal) closeModal();
    });
  }

  function toast(msg) {
    var t = document.createElement("div");
    t.className = "toast"; t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () { t.classList.add("show"); }, 10);
    setTimeout(function () {
      t.classList.remove("show");
      setTimeout(function () { t.remove(); }, 300);
    }, 2600);
  }

  // --- init ----------------------------------------------------------------
  function init() {
    wireModal();
    var sBtn = document.getElementById("wl-settings");
    var rBtn = document.getElementById("wl-refresh");
    sBtn && sBtn.addEventListener("click", function () { openModal(""); });
    rBtn && rBtn.addEventListener("click", function () {
      loaded = false; items = null; renderWatchlist();
      ensure().then(refreshButtons).catch(function () {});
    });
    decorate();
    renderWatchlist();
    if (loggedIn()) {
      ensure().then(refreshButtons).catch(function (e) { console.error(e); });
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else { init(); }
})();

