(function () {
  const model = JSON.parse(document.getElementById('variant-model').textContent);
  const form = document.getElementById('buy-form');
  const priceEl = document.getElementById('price');
  const stockEl = document.getElementById('stock');
  const variantInput = document.getElementById('variant-id');
  const qtyInput = document.getElementById('quantity');
  const currency = document.getElementById('price-box').dataset.currency || 'PHP';
  const symbols = { PHP: '₱', USD: '$', EUR: '€', GBP: '£', JPY: '¥' };

  const money = (n) => (symbols[currency] || currency + ' ') + Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  // Photo thumbnails
  const mainPhoto = document.getElementById('main-photo');
  document.querySelectorAll('.thumbs button').forEach((btn) => {
    btn.addEventListener('click', () => {
      mainPhoto.src = btn.dataset.photo;
      document.querySelectorAll('.thumbs button').forEach((b) => b.removeAttribute('aria-current'));
      btn.setAttribute('aria-current', 'true');
    });
  });

  function setBuyable(variant) {
    const ok = !!variant && variant.stock > 0;
    form.querySelectorAll('[data-needs-variant]').forEach((b) => { b.disabled = !ok; });
    if (qtyInput) {
      if (variant) qtyInput.max = variant.stock;
      else qtyInput.removeAttribute('max');
    }
  }

  function show(variant, hint) {
    if (!variant) {
      priceEl.className = 'price-tag xl';
      priceEl.textContent = hint || 'Choose options';
      stockEl.textContent = '';
      variantInput.value = '';
      setBuyable(null);
      return;
    }
    const sale = variant.original_price && variant.original_price > variant.price;
    priceEl.className = 'price-tag xl' + (sale ? ' sale' : '');
    priceEl.textContent = money(variant.price) + ' ';
    if (sale) {
      const s = document.createElement('s');
      s.textContent = money(variant.original_price);
      priceEl.appendChild(s);
    }
    stockEl.className = 'stock' + (variant.stock > 0 && variant.stock <= 5 ? ' low' : '');
    stockEl.textContent = variant.stock <= 0 ? 'Out of stock' : variant.stock <= 5 ? 'Only ' + variant.stock + ' left' : variant.stock + ' in stock';
    variantInput.value = variant.id;
    setBuyable(variant);
  }

  if (model.mode === 'matrix') {
    const groups = Array.from(form.querySelectorAll('.option-group'));

    const chosen = () => groups.map((g) => {
      const checked = g.querySelector('input:checked');
      return checked ? Number(checked.value) : null;
    });

    // Grey out options that no in-stock combination can reach given the other choices.
    function refresh() {
      const picks = chosen();
      groups.forEach((group, gi) => {
        group.querySelectorAll('input').forEach((input) => {
          const id = Number(input.value);
          const reachable = model.variants.some((v) => v.stock > 0 && v.option_ids.includes(id) &&
            picks.every((p, pi) => pi === gi || p === null || v.option_ids.includes(p)));
          input.disabled = !reachable;
        });
      });

      if (picks.some((p) => p === null)) {
        show(null, 'Choose options');
        return;
      }
      const match = model.variants.find((v) => picks.every((p) => v.option_ids.includes(p)));
      show(match || null, 'Not available');
    }

    groups.forEach((g) => g.addEventListener('change', refresh));
    refresh();
  } else if (model.mode === 'list') {
    const pick = () => {
      const checked = form.querySelector('input[name="variant-choice"]:checked');
      show(model.variants.find((v) => v.id === Number(checked && checked.value)));
    };
    form.addEventListener('change', pick);
    pick();
  } else {
    show(model.variants[0] || null, 'Unavailable');
  }
})();
