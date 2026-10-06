(function () {
  const root = document.getElementById('chat');
  if (!root) return;

  const me = Number(root.dataset.me);
  const active = Number(root.dataset.active) || null;
  const listEl = document.getElementById('convo-items');
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const errorEl = document.getElementById('chat-error');

  async function api(path, options = {}) {
    const res = await fetch(path, {
      credentials: 'same-origin',
      ...options,
      headers: { 'X-CSRF-Token': csrf, ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) },
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) { window.location.href = '/login'; throw new Error('Signed out'); }
    if (!res.ok) throw new Error(data.error || 'Something went wrong. Try again.');
    return data;
  }

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };
  const initials = (name) => (name || '?').replace(/_/g, ' ').split(/\s+/).slice(0, 2).map((p) => p[0]).join('').toUpperCase();
  const clock = (iso) => {
    const d = new Date(iso);
    const sameDay = d.toDateString() === new Date().toDateString();
    return sameDay ? d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
      : d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ', ' + d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  };

  function avatar(person, extra) {
    const a = el('span', 'avatar' + (extra ? ' ' + extra : ''));
    if (person && person.avatar_url) {
      const img = el('img');
      img.src = person.avatar_url;
      img.alt = '';
      a.appendChild(img);
    } else {
      a.textContent = initials(person && person.username);
    }
    return a;
  }

  // ── conversation list ────────────────────────────────────────────────
  async function loadList() {
    try {
      const { conversations } = await api('/api/chat/conversations');
      listEl.replaceChildren();
      if (!conversations.length) {
        const p = el('p', 'muted small', 'No conversations yet. Message a seller from a product or order page.');
        p.style.padding = '0 18px 16px';
        listEl.appendChild(p);
        return;
      }
      conversations.forEach((c) => {
        const other = c.other_participant || {};
        const a = el('a', 'convo');
        a.href = root.dataset.threadUrl.replace(/\/$/, '') + '/' + c.conversation_id;
        if (c.conversation_id === active) a.setAttribute('aria-current', 'true');
        a.appendChild(avatar(other));
        const mid = el('div');
        mid.style.minWidth = '0';
        mid.appendChild(el('b', '', other.username || 'Unknown user'));
        mid.appendChild(el('span', 'preview', c.last_message_preview || 'No messages yet'));
        const ctx = c.order_id ? 'Order #' + c.order_id : c.product_id ? 'Product question' : '';
        if (ctx) mid.appendChild(el('span', 'tag', ctx));
        a.appendChild(mid);
        if (c.unread_count && c.conversation_id !== active) a.appendChild(el('span', 'unread', String(c.unread_count)));
        listEl.appendChild(a);
      });
    } catch (e) { /* keep the previous list on a failed refresh */ }
  }

  loadList();
  setInterval(loadList, 10000);
  if (!active) return;

  // ── thread ───────────────────────────────────────────────────────────
  const box = document.getElementById('messages');
  const form = document.getElementById('composer');
  const input = document.getElementById('body');
  const msgs = new Map();
  let hasMore = false;
  let oldestId = null;

  function refCard(m) {
    if (m.message_type === 'order_card' && m.ref_order) {
      const a = el('a', 'ref', 'Order #' + m.ref_order.order_id + ' · ' + m.ref_order.status.replace(/_/g, ' '));
      a.href = '/orders/' + m.ref_order.order_id;
      return a;
    }
    if (m.message_type === 'product_card' && m.ref_product) {
      const a = el('a', 'ref', m.ref_product.title);
      a.href = '/product/' + m.ref_product.product_id;
      return a;
    }
    if (m.message_type === 'location' && m.location) {
      const a = el('a', 'ref', 'Shared a location');
      a.href = 'https://www.openstreetmap.org/?mlat=' + m.location.lat + '&mlon=' + m.location.lng + '#map=17/' + m.location.lat + '/' + m.location.lng;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      return a;
    }
    return null;
  }

  function bubble(m) {
    const mine = m.sender_id === me;
    const b = el('div', 'msg' + (mine ? ' mine' : '') + (m.is_deleted ? ' deleted' : ''));
    b.dataset.id = m.message_id;
    if (m.is_deleted) {
      b.textContent = 'This message was deleted';
      return b;
    }
    const card = refCard(m);
    if (card) b.appendChild(card);
    if (m.body) b.appendChild(document.createTextNode(m.body));
    const t = el('time', '', clock(m.created_at));
    if (mine) {
      const del = el('button', 'del', 'Delete');
      del.type = 'button';
      del.addEventListener('click', async () => {
        if (!confirm('Delete this message?')) return;
        try { await api('/api/chat/messages/' + m.message_id, { method: 'DELETE' }); m.is_deleted = true; render(); }
        catch (e) { showError(e.message); }
      });
      t.appendChild(del);
    }
    b.appendChild(t);
    return b;
  }

  function render(stickToBottom) {
    const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
    const prevHeight = box.scrollHeight;
    box.replaceChildren();
    if (hasMore) {
      const more = el('button', 'btn ghost small load-earlier', 'Load earlier messages');
      more.type = 'button';
      more.addEventListener('click', loadEarlier);
      box.appendChild(more);
    }
    if (!msgs.size) box.appendChild(el('p', 'muted small', 'No messages yet. Say hello.'));
    [...msgs.values()].sort((a, b) => a.message_id - b.message_id).forEach((m) => box.appendChild(bubble(m)));
    if (stickToBottom === 'older') box.scrollTop = box.scrollHeight - prevHeight;
    else if (stickToBottom || nearBottom) box.scrollTop = box.scrollHeight;
  }

  function showError(message) {
    errorEl.textContent = message;
    errorEl.hidden = !message;
  }

  async function poll(first) {
    try {
      const data = await api('/api/chat/' + active + '/messages?limit=40');
      let changed = first;
      data.messages.forEach((m) => {
        const old = msgs.get(m.message_id);
        if (!old || old.is_deleted !== m.is_deleted) changed = true;
        msgs.set(m.message_id, m);
      });
      if (first) { hasMore = !!data.has_more; oldestId = data.next_before_id; }
      if (changed) {
        render(first);
        api('/api/chat/' + active + '/read', { method: 'POST' }).catch(() => {});
      }
    } catch (e) { /* transient; try again on the next tick */ }
  }

  async function loadEarlier() {
    if (!oldestId) return;
    try {
      const data = await api('/api/chat/' + active + '/messages?limit=40&before_id=' + oldestId);
      data.messages.forEach((m) => msgs.set(m.message_id, m));
      hasMore = !!data.has_more;
      oldestId = data.next_before_id;
      render('older');
    } catch (e) { showError(e.message); }
  }

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const body = input.value.trim();
    if (!body) return;
    const button = form.querySelector('button');
    button.disabled = true;
    showError('');
    try {
      const m = await api('/api/chat/' + active + '/messages', { method: 'POST', body: JSON.stringify({ body }) });
      msgs.set(m.message_id, m);
      input.value = '';
      input.style.height = '';
      render(true);
      loadList();
    } catch (e) {
      showError(e.message);
    } finally {
      button.disabled = false;
      input.focus();
    }
  });

  // Enter sends, Shift+Enter adds a line.
  input.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); form.requestSubmit(); }
  });
  input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 120) + 'px'; });

  poll(true);
  setInterval(() => { if (!document.hidden) poll(false); }, 4000);
})();
