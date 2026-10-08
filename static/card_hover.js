// ---------------------------------------------------------------------------
// Card image hover preview (used across app.js / campaigns.js)
//
// Any element with data-card-image-url shows the card image as a floating preview
// while the mouse is over it, and hides it as soon as the mouse leaves.
//   cardImageAttr(card)      → 'data-card-image-url="…"' to put on an existing element
//   cardName(card, inner?)   → '<span class="card-name" data-card-image-url="…">name</span>'
// One delegated listener on document handles every element, including ones rendered later.
// ---------------------------------------------------------------------------
function cardImageAttr(card) {
  if (!card || !card.image_url) return '';
  return `data-card-image-url="${esc(card.image_url)}"`;
}

function cardName(card, inner) {
  if (!card) return '';
  return `<span class="card-name" ${cardImageAttr(card)}>${inner ?? esc(card.name)}</span>`;
}

(() => {
  const thumb = document.getElementById('card-thumb');
  if (!thumb) return;
  const img = document.createElement('img');
  img.alt = '';
  thumb.appendChild(img);

  let current = null;  // element being hovered
  let mouse = { x: 0, y: 0 };

  function position() {
    const vw = window.innerWidth, vh = window.innerHeight;
    const w = thumb.offsetWidth || 162;
    const h = thumb.offsetHeight || 240;
    let left = mouse.x + 16;
    let top = mouse.y - h / 2;
    if (left + w > vw - 8) left = mouse.x - w - 16;
    if (top + h > vh - 8) top = vh - h - 8;
    if (top < 8) top = 8;
    thumb.style.left = left + 'px';
    thumb.style.top = top + 'px';
  }

  function show(el) {
    current = el;
    const url = el.dataset.cardImageUrl;
    if (img.getAttribute('src') !== url) img.src = url;
    // Stay invisible (but laid out) until the image is ready, so no empty box flashes
    thumb.style.visibility = img.complete && img.naturalWidth ? 'visible' : 'hidden';
    thumb.style.display = 'block';
    position();
  }

  function hide() {
    current = null;
    thumb.style.display = 'none';
  }

  // Real height is known only once the image has loaded
  img.addEventListener('load', () => {
    if (!current) return;
    thumb.style.visibility = 'visible';
    position();
  });
  img.addEventListener('error', hide);

  document.addEventListener('mousemove', e => {
    mouse = { x: e.clientX, y: e.clientY };
    if (current) position();
  });

  document.addEventListener('mouseover', e => {
    mouse = { x: e.clientX, y: e.clientY };
    const el = e.target.closest?.('[data-card-image-url]');
    if (el === current) return;
    if (el && el.dataset.cardImageUrl) show(el); else hide();
  });

  document.addEventListener('mouseout', e => {
    if (!current) return;
    const to = e.relatedTarget?.closest?.('[data-card-image-url]');
    if (to !== current) hide();
  });

  // Hovered element may be removed (navigation, re-render) without a mouseout
  document.addEventListener('click', hide, true);
  document.addEventListener('scroll', hide, true);
  window.addEventListener('hashchange', hide);
  window.addEventListener('blur', hide);
})();
