(function () {
  "use strict";

  // Fade out and remove the preloader. Triggered on DOMContentLoaded (doesn't
  // wait on slow/blocked external resources like CDN scripts) with a hard
  // timeout backstop in case even that is somehow delayed.
  function hidePreloader() {
    var el = document.getElementById("preloader-active");
    if (!el || el.dataset.hidden) return;
    el.dataset.hidden = "1";
    el.style.transition = "opacity 0.4s ease";
    el.style.opacity = "0";
    setTimeout(function () { el.style.display = "none"; }, 400);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", hidePreloader);
  } else {
    hidePreloader();
  }
  setTimeout(hidePreloader, 2000);

  // Bootstrap-style alert dismiss (`data-bs-dismiss="alert"`), without Bootstrap JS.
  document.addEventListener("click", function (e) {
    var btn = e.target.closest('[data-bs-dismiss="alert"]');
    if (!btn) return;
    var alert = btn.closest(".alert");
    if (alert) alert.remove();
  });
})();
