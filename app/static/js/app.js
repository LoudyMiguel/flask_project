(function () {
  // Dismiss flash messages
  document.querySelectorAll('[data-dismiss]').forEach((btn) => {
    btn.addEventListener('click', () => btn.closest('.flash').remove());
  });

  // Confirm destructive forms
  document.querySelectorAll('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (ev) => {
      if (!window.confirm(form.dataset.confirm)) ev.preventDefault();
    });
  });

  // Keep "Mark ready" off until every item is ticked
  const ready = document.querySelector('[data-ready-form]');
  if (ready) {
    const boxes = Array.from(ready.querySelectorAll('input[name="prepared"]'));
    const btn = ready.querySelector('[data-ready-btn]');
    const sync = () => { btn.disabled = !boxes.every((b) => b.checked); };
    boxes.forEach((b) => b.addEventListener('change', sync));
    sync();
  }

  // Header badges (cart count, unread messages)
  if (document.body.dataset.auth !== 'yes') return;
  const badges = {
    cart: document.querySelector('[data-badge="cart"]'),
    unread: document.querySelector('[data-badge="unread"]'),
  };
  async function refresh() {
    try {
      const res = await fetch('/api/badges', { credentials: 'same-origin' });
      if (!res.ok) return;
      const data = await res.json();
      Object.entries(badges).forEach(([key, node]) => {
        if (!node) return;
        const n = data[key] || 0;
        node.textContent = n > 99 ? '99+' : n;
        node.classList.toggle('on', n > 0);
      });
    } catch (e) { /* header badges are decoration; ignore failures */ }
  }
  refresh();
  setInterval(() => { if (!document.hidden) refresh(); }, 30000);
})();
