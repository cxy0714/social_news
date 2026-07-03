// Reader interactions: theme toggle + mobile nav drawer. No dependencies.
(function () {
  var root = document.documentElement;
  var themeBtn = document.getElementById("theme-toggle");
  var navBtn = document.getElementById("nav-toggle");
  var sidebar = document.getElementById("sidebar");
  var scrim = document.getElementById("scrim");

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

  // Sidebar tabs: switch between Daily / Weekly panels.
  var tabs = document.querySelectorAll(".nav-tabs .tab");
  var panels = document.querySelectorAll(".nav-panel");
  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      var kind = tab.dataset.tab;
      tabs.forEach(function (t) { t.classList.toggle("active", t === tab); });
      panels.forEach(function (p) { p.hidden = p.dataset.panel !== kind; });
    });
  });

  // Scroll the active sidebar entry into view on load.
  var active = document.querySelector(".nav-panel a.active");
  if (active) active.scrollIntoView({ block: "center" });
})();
