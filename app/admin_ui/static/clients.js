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
