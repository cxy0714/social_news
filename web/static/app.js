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
