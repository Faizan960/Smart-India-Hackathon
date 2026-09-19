export function initNavigation() {
  const nav = document.getElementById("mainNav");
  if (!nav) return;

  // Handle URL hash on load
  const hash = window.location.hash.replace("#", "");
  if (["overview", "stations", "anomalies"].includes(hash)) {
    navigateTo(hash);
  }

  nav.addEventListener("click", e => {
    e.preventDefault();
    const btn = e.target.closest("a[data-page]");
    if (!btn) return;
    
    navigateTo(btn.dataset.page);
  });
}

export function navigateTo(pageId) {
  // Update URL Hash without scrolling
  history.replaceState(null, null, `#${pageId}`);
  
  // Update Topbar Nav visually
  document.querySelectorAll("#mainNav a[data-page]").forEach(b => {
    if (b.dataset.page === pageId) {
      b.classList.add("active");
    } else {
      b.classList.remove("active");
    }
  });

  // Hide all pages, show the active one
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  const activePage = document.getElementById("page-" + pageId);
  if (activePage) {
    activePage.classList.add("active");
  }

  // Trigger global event so specific controllers can render if needed
  window.dispatchEvent(new CustomEvent("pageChanged", { detail: { page: pageId } }));
}

// Make globally available for inline onclick handlers (e.g. "View all anomalies" button)
window.navigateTo = navigateTo;
