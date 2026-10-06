(function () {
  const symbols = { PHP: '₱', USD: '$', EUR: '€', GBP: '£', JPY: '¥' };
  const fmt = (code, n) => (symbols[code] || code + ' ') + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const rows = Array.from(document.querySelectorAll('.cart-row'));
  const countEl = document.getElementById('sel-count');
  const totalEl = document.getElementById('sel-total');
  const button = document.getElementById('checkout-btn');
  if (!rows.length) return;

  function recalc() {
    const totals = {};
    let selected = 0;
    rows.forEach((row) => {
      const box = row.querySelector('input[type="checkbox"]');
      if (!box.checked || box.disabled) return;
      const qty = parseFloat(row.querySelector('[data-qty]').value) || 0;
      const code = row.dataset.currency;
      totals[code] = (totals[code] || 0) + parseFloat(row.dataset.price) * qty;
      selected += 1;
    });
    countEl.textContent = selected;
    totalEl.textContent = Object.keys(totals).length
      ? Object.entries(totals).map(([c, n]) => fmt(c, n)).join(' + ')
      : fmt('PHP', 0);
    button.disabled = selected === 0;
  }

  rows.forEach((row) => {
    row.querySelector('input[type="checkbox"]').addEventListener('change', recalc);
    row.querySelector('[data-qty]').addEventListener('input', recalc);
  });

  // Changing a quantity saves it; the Update button stays as the no-JS fallback.
  document.querySelectorAll('form[data-autosubmit]').forEach((form) => {
    const input = form.querySelector('[data-qty]');
    const initial = input.value;
    input.addEventListener('change', () => { if (input.value !== initial && input.checkValidity()) form.submit(); });
  });

  recalc();
})();
