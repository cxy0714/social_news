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

// === future-tech bookmarks via GitHub Gist ================================
// Reads a secret Gist (watchlist.json) — reading needs no token; writing does.
// id + token live in localStorage only, never in the repo.
(function () {
  var LS_ID = "ft_gist_id", LS_TOKEN = "ft_gist_token", WL_FILE = "watchlist.json";
  var API = "https://api.github.com/gists/";
  var items = null;            // cached watchlist array
  var loaded = false;

  function cfg() {
    return {
      id: (localStorage.getItem(LS_ID) || "").trim(),
      token: (localStorage.getItem(LS_TOKEN) || "").trim(),
    };
  }
  function configured() { return !!cfg().id; }
  function norm(u) { return (u || "").split("#")[0].replace(/\/$/, ""); }

  // --- Gist I/O ------------------------------------------------------------
  function readWatchlist() {
    var c = cfg();
    if (!c.id) return Promise.resolve([]);
    var h = { Accept: "application/vnd.github+json" };
    if (c.token) h.Authorization = "Bearer " + c.token;
    return fetch(API + c.id, { headers: h }).then(function (r) {
      if (!r.ok) throw new Error("读取 Gist 失败 (" + r.status + ")");
      return r.json();
    }).then(function (g) {
      var f = g.files && g.files[WL_FILE];
      if (!f || !f.content) return [];
      try { return JSON.parse(f.content) || []; } catch (e) { return []; }
    });
  }
  function writeWatchlist(arr) {
    var c = cfg();
    if (!c.id) return Promise.reject(new Error("未配置 Gist ID"));
    if (!c.token) return Promise.reject(new Error("未配置 token，无法写入"));
    var body = { files: {} };
    body.files[WL_FILE] = { content: JSON.stringify(arr, null, 2) };
    return fetch(API + c.id, {
      method: "PATCH",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: "Bearer " + c.token,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    }).then(function (r) {
      if (!r.ok) throw new Error("写入 Gist 失败 (" + r.status + ")");
      return arr;
    });
  }

  function ensure() {
    if (loaded && items) return Promise.resolve(items);
    return readWatchlist().then(function (a) {
      items = a; loaded = true; return a;
    });
  }
  function has(url) {
    if (!items) return false;
    var n = norm(url);
    return items.some(function (it) { return norm(it.url) === n; });
  }

  // --- bookmark buttons on every news item --------------------------------
  // Digest items are "<li>… <a href=…>…</a> …"; add a ☆ toggle per <li>.
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

  function flash(btn, txt, ok) {
    var old = btn.textContent;
    btn.textContent = txt;
    btn.classList.toggle("err", !ok);
    setTimeout(function () { btn.classList.remove("err"); refreshButtons(); }, 1400);
  }
  function onBookmark(e) {
    var btn = e.currentTarget;
    if (!configured()) { openModal("请先设置 Gist（右上角未来技术页 ⚙）"); return; }
    ensure().then(function () {
      var url = btn.dataset.url, n = norm(url);
      if (has(url)) {
        items = items.filter(function (it) { return norm(it.url) !== n; });
      } else {
        items.unshift({ title: btn.dataset.title, url: url, added: nowISO() });
      }
      btn.textContent = "…";
      return writeWatchlist(items);
    }).then(function () {
      refreshButtons(); renderWatchlist();
    }).catch(function (err) {
      flash(btn, "!", false);
      console.error(err); toast(err.message);
    });
  }
  function nowISO() {
    try { return new Date().toISOString().slice(0, 10); } catch (e) { return ""; }
  }

  // --- watchlist widget on the future page --------------------------------
  function renderWatchlist() {
    var box = document.getElementById("wl-list");
    if (!box) return;
    if (!configured()) {
      box.innerHTML = '<p class="muted">未配置 Gist。点“⚙ 设置 Gist”即可开始收藏。</p>';
      return;
    }
    box.innerHTML = '<p class="muted">加载中…</p>';
    ensure().then(function (arr) {
      if (!arr.length) {
        box.innerHTML = '<p class="muted">清单为空。在任意新闻条目旁点 ☆ 即可收藏。</p>';
        return;
      }
      var ul = document.createElement("ul");
      ul.className = "wl-items";
      arr.forEach(function (it) {
        var li = document.createElement("li");
        var d = it.added ? '<span class="wl-date">' + it.added + "</span> " : "";
        li.innerHTML = d + '<a href="' + it.url + '" target="_blank" rel="noopener">' +
          escapeHtml(it.title || it.url) + "</a>";
        var rm = document.createElement("button");
        rm.type = "button"; rm.className = "wl-rm"; rm.textContent = "✕";
        rm.title = "移除"; rm.dataset.url = it.url;
        rm.addEventListener("click", onRemove);
        li.appendChild(rm);
        ul.appendChild(li);
      });
      box.innerHTML = "";
      box.appendChild(ul);
    }).catch(function (err) {
      box.innerHTML = '<p class="muted">读取失败：' + escapeHtml(err.message) + "</p>";
    });
  }
  function onRemove(e) {
    var url = e.currentTarget.dataset.url, n = norm(url);
    items = (items || []).filter(function (it) { return norm(it.url) !== n; });
    e.currentTarget.closest("li").style.opacity = ".4";
    writeWatchlist(items).then(function () {
      renderWatchlist(); refreshButtons();
    }).catch(function (err) { toast(err.message); renderWatchlist(); });
  }
  function escapeHtml(s) {
    return (s || "").replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // --- settings modal ------------------------------------------------------
  var modal = document.getElementById("gist-modal");
  function openModal(hint) {
    if (!modal) return;
    var c = cfg();
    var idEl = document.getElementById("gist-id");
    var tkEl = document.getElementById("gist-token");
    if (idEl) idEl.value = c.id;
    if (tkEl) tkEl.value = c.token;
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
    var clear = document.getElementById("gist-clear");
    save && save.addEventListener("click", function () {
      var id = (document.getElementById("gist-id").value || "").trim();
      var tk = (document.getElementById("gist-token").value || "").trim();
      // accept a full gist URL — keep the last path segment as the id
      id = id.replace(/^https?:\/\/[^/]+\//, "").split("/").pop().split("#")[0];
      localStorage.setItem(LS_ID, id);
      if (tk) localStorage.setItem(LS_TOKEN, tk);
      loaded = false; items = null;
      closeModal();
      renderWatchlist(); ensure().then(refreshButtons);
    });
    cancel && cancel.addEventListener("click", closeModal);
    clear && clear.addEventListener("click", function () {
      localStorage.removeItem(LS_ID); localStorage.removeItem(LS_TOKEN);
      loaded = false; items = null;
      document.getElementById("gist-id").value = "";
      document.getElementById("gist-token").value = "";
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
      loaded = false; items = null; renderWatchlist(); ensure().then(refreshButtons);
    });
    decorate();
    if (configured()) {
      ensure().then(function () { refreshButtons(); renderWatchlist(); })
        .catch(function (e) { console.error(e); });
    } else {
      renderWatchlist();
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else { init(); }
})();
