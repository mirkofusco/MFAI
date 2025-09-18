// Helper: toast
function showToast(msg, ok = true) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast ' + (ok ? 'ok' : 'err');
  t.style.display = 'block';
  setTimeout(() => (t.style.display = 'none'), 3000);
}

// Helper: modali
function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.setAttribute('aria-hidden', 'false');
}
function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.setAttribute('aria-hidden', 'true');
}
document.addEventListener('click', (e) => {
  if (e.target.matches('[data-close]')) {
    const modal = e.target.closest('.modal');
    if (modal) modal.setAttribute('aria-hidden', 'true');
  }
});

// Stato locale
let CLIENTS = [];
let DEL_ID = null;

// Render tabella
function renderTable(filter = '') {
  const tbody = document.getElementById('clientsTbody');
  const empty = document.getElementById('emptyState');
  tbody.innerHTML = '';

  const q = filter.trim().toLowerCase();
  const data = CLIENTS.filter(c => {
    if (!q) return true;
    return (String(c.id).includes(q) ||
      (c.name || '').toLowerCase().includes(q) ||
      (c.email || '').toLowerCase().includes(q));
  });

  if (data.length === 0) {
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  for (const c of data) {
    const tr = document.createElement('tr');

    const created = c.created_at ? new Date(c.created_at).toLocaleString() : '-';

    tr.innerHTML = `
      <td>${c.id}</td>
      <td>${escapeHtml(c.name || '')}</td>
      <td>${escapeHtml(c.email || '')}</td>
      <td>${created}</td>
      <td style="text-align:right;">
        <div class="btn-group">
          <a class="btn small" href="/ui2/client/${c.id}">Gestione</a>
          <a class="btn small" href="/ui2/prompts/${c.id}">Prompt</a>
          <button class="btn small danger" data-del="${c.id}" data-name="${escapeHtml(c.name || '')}">Elimina</button>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  }
}

// Escape semplice per XSS
function escapeHtml(s) {
  return s.replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
}

// Fetch lista
async function loadClients() {
  try {
    const res = await fetch('/admin/clients');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    CLIENTS = await res.json();
    renderTable(document.getElementById('searchInput').value || '');
  } catch (e) {
    console.error(e);
    showToast('Errore nel caricare i clienti', false);
  }
}

// Crea cliente
async function createClient(payload) {
  const res = await fetch('/admin/clients', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const msg = (await safeJson(res))?.detail || 'Errore creazione';
    throw new Error(msg);
  }
  return res.json();
}

// Elimina cliente
async function deleteClient(id) {
  const res = await fetch(`/admin/clients/${id}`, { method: 'DELETE' });
  if (!res.ok) {
    const msg = (await safeJson(res))?.detail || 'Errore eliminazione';
    throw new Error(msg);
  }
  return true;
}

async function safeJson(res) {
  try { return await res.json(); } catch { return null; }
}

// Event wiring
document.addEventListener('DOMContentLoaded', () => {
  loadClients();

  // Cerca
  const search = document.getElementById('searchInput');
  search.addEventListener('input', () => renderTable(search.value));

  // Nuovo
  document.getElementById('btnNew').addEventListener('click', () => {
    const form = document.getElementById('formNewClient');
    form.reset();
    openModal('modalNew');
  });

  // Submit nuovo
  document.getElementById('formNewClient').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const name = (fd.get('name') || '').toString().trim();
    const email = (fd.get('email') || '').toString().trim() || null;
    if (!name) {
      showToast('Il nome è obbligatorio', false);
      return;
    }
    try {
      await createClient({ name, email });
      closeModal('modalNew');
      showToast('Cliente creato');
      await loadClients();
    } catch (err) {
      showToast(err.message, false);
    }
  });

  // Click su elimina
  document.getElementById('clientsTbody').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-del]');
    if (!btn) return;
    DEL_ID = btn.getAttribute('data-del');
    const nm = btn.getAttribute('data-name') || '';
    document.getElementById('delName').textContent = nm;
    openModal('modalDel');
  });

  // Conferma elimina
  document.getElementById('btnConfirmDel').addEventListener('click', async () => {
    if (!DEL_ID) return;
    try {
      await deleteClient(DEL_ID);
      closeModal('modalDel');
      showToast('Cliente eliminato');
      await loadClients();
    } catch (err) {
      showToast(err.message, false);
    } finally {
      DEL_ID = null;
    }
  });
});
