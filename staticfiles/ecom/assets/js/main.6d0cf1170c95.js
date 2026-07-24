(function () {
  "use strict";

  // Fade out the preloader once the page has fully loaded.
  window.addEventListener("load", function () {
    var el = document.getElementById("preloader-active");
    if (!el) return;
    el.style.transition = "opacity 0.4s ease";
    el.style.opacity = "0";
    setTimeout(function () { el.style.display = "none"; }, 400);
  });

  // Bootstrap-style alert dismiss (`data-bs-dismiss="alert"`), without Bootstrap JS.
  document.addEventListener("click", function (e) {
    var btn = e.target.closest('[data-bs-dismiss="alert"]');
    if (!btn) return;
    var alert = btn.closest(".alert");
    if (alert) alert.remove();
  });
})();
