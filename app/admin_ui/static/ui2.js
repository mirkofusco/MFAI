(function () {
    const openBtn = document.getElementById('btn-open-add-client');
    const closeBtn = document.getElementById('btn-close-add-client');
    const cancelBtn = document.getElementById('btn-cancel-add-client');
    const backdrop = document.getElementById('add-client-backdrop');
    const modal = document.getElementById('add-client-modal');
    const form = document.getElementById('add-client-form');
  
    if (!openBtn || !modal) return;
  
    function openModal() {
      modal.setAttribute('aria-hidden', 'false');
      backdrop.setAttribute('aria-hidden', 'false');
      const first = modal.querySelector('input[name="name"]');
      if (first) first.focus();
    }
    function closeModal() {
      modal.setAttribute('aria-hidden', 'true');
      backdrop.setAttribute('aria-hidden', 'true');
    }
  
    openBtn.addEventListener('click', openModal);
    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
    if (backdrop) backdrop.addEventListener('click', closeModal);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });
  
    form && form.addEventListener('submit', (e) => {
      const name = form.querySelector('input[name="name"]')?.value.trim();
      const ig = form.querySelector('input[name="instagram_username"]')?.value.trim();
      const api = form.querySelector('input[name="api_key"]')?.value.trim();
      if (!name || !ig || !api || api.length < 8) {
        e.preventDefault();
        alert('Compila Nome, Username IG e API Key (min 8 caratteri).');
      }
    });
  })();
  