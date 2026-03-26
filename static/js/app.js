// MovieFinder - Frontend JS
// Handles: live search, smooth scrolling, lazy load, section tabs

document.addEventListener('DOMContentLoaded', () => {
  initSectionScrollButtons();
  initImageFallbacks();
});

// ────────────────────────────────────────────────
// Horizontal scroll buttons for movie sections
// ────────────────────────────────────────────────
function initSectionScrollButtons() {
  document.querySelectorAll('.section-scroll').forEach(container => {
    // Keyboard arrow scroll when focused
    container.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowRight') container.scrollBy({ left: 200, behavior: 'smooth' });
      if (e.key === 'ArrowLeft') container.scrollBy({ left: -200, behavior: 'smooth' });
    });
  });
}

// ────────────────────────────────────────────────
// Image fallbacks
// ────────────────────────────────────────────────
function initImageFallbacks() {
  document.querySelectorAll('img[onerror]').forEach(img => {
    if (!img.complete || img.naturalWidth === 0) {
      img.onerror = () => { img.src = '/static/img/no-poster.svg'; };
    }
  });
}

// ────────────────────────────────────────────────
// Debounce utility
// ────────────────────────────────────────────────
function debounce(fn, delay) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), delay); };
}

// ────────────────────────────────────────────────
// Smooth scroll to section by hash
// ────────────────────────────────────────────────
window.addEventListener('load', () => {
  const hash = window.location.hash;
  if (hash) {
    const el = document.querySelector(hash);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
});
