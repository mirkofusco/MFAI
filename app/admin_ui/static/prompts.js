const BASE = location.origin;
const BASIC = 'Basic ' + btoa('admin:' + prompt('Password admin:',''));

const elList = document.getElementById('list');
const dlg = document.getElementById('editDialog');
const dlgValue = document.getElementById('dlgValue');
const dlgTitle = document.getElementById('dlgTitle');
const btnSave = document.getElementById('saveBtn');
const btnCancel = document.getElementById('cancelBtn');

let currentKey = null;

async function apiList() {
  const res = await fetch(`${BASE}/admin/prompts`, { headers: { Authorization: BASIC }});
  if (!res.ok) throw new Error('Errore lista: ' + res.status);
  return res.json();
}

async function apiPut(key, value) {
  const res = await fetch(`${BASE}/admin/prompts/${encodeURIComponent(key)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', Authorization: BASIC },
    body: JSON.stringify({ value })
  });
  if (!res.ok) throw new Error('Errore salvataggio: ' + res.status);
  return res.json();
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}

function renderList(items) {
  const rows = items.map(it => `
    <tr>
      <td class="key">${it.key}</td>
      <td><pre style="white-space:pre-wrap;margin:0;">${escapeHtml(it.value)}</pre></td>
      <td style="width:1%;"><button data-key="${it.key}" class="secondary">Modifica</button></td>
    </tr>
  `).join('');
  elList.innerHTML = `
    <table role="grid">
      <thead><tr><th>Key</th><th>Value</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
  for (const btn of elList.querySelectorAll('button[data-key]')) {
    btn.addEventListener('click', () => openEdit(btn.dataset.key, items));
  }
}

function openEdit(key, items) {
  currentKey = key;
  const it = items.find(x => x.key === key);
  dlgTitle.textContent = 'Modifica: ' + key;
  dlgValue.value = it?.value || '';
  dlg.showModal();
  dlgValue.focus();
}

btnSave.addEventListener('click', async () => {
  try {
    await apiPut(currentKey, dlgValue.value);
    dlg.close();
    init();
  } catch (e) { alert(e); }
});
btnCancel.addEventListener('click', () => dlg.close());

async function init() {
  try {
    const items = await apiList();
    renderList(items);
  } catch (e) {
    elList.innerHTML = '<mark>Errore: ' + String(e) + '</mark>';
  }
}

init();
