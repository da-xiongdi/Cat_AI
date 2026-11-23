// Edge can restore the document scroll position without restoring the preview pane on reload.
window.addEventListener("pageshow", () => {
  if (window.location.hash === "#plan-section") {
    window.requestAnimationFrame(() => {
      document.getElementById("plan-section")?.scrollIntoView({ block: "nearest" });
    });
  }
});
