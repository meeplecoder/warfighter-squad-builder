// ---------------------------------------------------------------------------
// Search boxes: <input class="search-input"> shows an ✕ at its right edge while it has
// text. Clicking it clears the box and fires 'input', so each view's own handler re-runs
// the search. One delegated listener covers inputs rendered later.
// ---------------------------------------------------------------------------
(() => {
  const ZONE = 26;  // px from the right edge that act as the clear button

  const overClear = (el, e) =>
    el.value !== '' && e.clientX >= el.getBoundingClientRect().right - ZONE;

  document.addEventListener('mousemove', e => {
    const el = e.target;
    if (el.classList?.contains('search-input')) el.classList.toggle('search-clear-hover', overClear(el, e));
  });

  document.addEventListener('mousedown', e => {
    const el = e.target;
    if (!el.classList?.contains('search-input') || !overClear(el, e)) return;
    e.preventDefault();
    el.value = '';
    el.classList.remove('search-clear-hover');
    el.focus();
    el.dispatchEvent(new Event('input', { bubbles: true }));
  });
})();
