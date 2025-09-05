const BASIC = 'Basic ' + btoa('admin:' + prompt('Password admin:',''));
const listEl = document.getElementById('list');

async function fetchClients() {
  const r = await fetch('/admin/clients_list', { headers: { Authorization: BASIC }});
  if (!r.ok) throw new Error('Errore caricamento: ' + r.status);
  return r.json();
}

function render(items) {
  const rows = items.map(it => `
    <tr>
      <td>${it.id}</td>
      <td><a href="/ui/clients/${it.id}">${escapeHtml(it.name)}</a><br><small class="muted">${escapeHtml(it.email||'')}</small></td>
      <td style="text-align:center">${it.ig_accounts}</td>
      <td style="text-align:center">${it.public_spaces}</td>
    </tr>
  `).join('');
  listEl.innerHTML = `
    <table role="grid">
      <thead><tr><th>ID</th><th>Cliente</th><th>IG</th><th>Spazi</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function escapeHtml(s){return String(s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}

(async function init(){
  try{
    const data = await fetchClients();
    render(data.items||[]);
  }catch(e){
    listEl.innerHTML = '<mark>'+String(e)+'</mark>';
  }
})();


;(() => {
  const ta = document.getElementById('ai_prompt');
  const statusEl = document.getElementById('ai-prompt-status');
  if (!ta) return;

  async function loadClientAI() {
    try {
      statusEl && (statusEl.textContent = 'Caricamento...');
      const res = await fetch(`/api/clients/${window.CURRENT_CLIENT_ID}`, { credentials: 'include' });
      if (!res.ok) throw new Error('GET /api/clients/:id failed');
      const data = await res.json();
      ta.value = data.ai_prompt || '';
      statusEl && (statusEl.textContent = 'Pronto');
    } catch (e) {
      statusEl && (statusEl.textContent = 'Errore caricamento');
      console.error(e);
    }
  }

  async function saveClientAI() {
    try {
      statusEl && (statusEl.textContent = 'Salvataggio...');
      const res = await fetch(`/api/clients/${window.CURRENT_CLIENT_ID}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ ai_prompt: ta.value })
      });
      if (!res.ok) throw new Error('PATCH /api/clients/:id failed');
      statusEl && (statusEl.textContent = 'Salvato');
      setTimeout(() => { if(statusEl) statusEl.textContent=''; }, 1200);
    } catch (e) {
      statusEl && (statusEl.textContent = 'Errore salvataggio');
      console.error(e);
    }
  }

  document.getElementById('btn-save-ai-prompt')?.addEventListener('click', saveClientAI);
  loadClientAI();
})();
