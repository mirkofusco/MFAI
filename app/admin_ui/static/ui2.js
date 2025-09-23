(function () {
    const modal = document.getElementById('add-client-modal');
    const backdrop = document.getElementById('add-client-backdrop');
    const form = document.getElementById('add-client-form');
  
    // Se il bottone non esiste (template diverso), lo crea il middleware; in ogni caso prova a trovarlo
    let openBtn = document.getElementById('btn-open-add-client');
    const closeBtn = document.getElementById('btn-close-add-client');
    const cancelBtn = document.getElementById('btn-cancel-add-client');
  
    if (!modal) return;
  
    function show(open) {
      if (open) {
        modal.style.display = 'grid';
        if (backdrop) backdrop.style.display = 'block';
        modal.setAttribute('aria-hidden', 'false');
        const first = modal.querySelector('input[name="name"]');
        if (first) { try { first.focus(); } catch (_) {} }
      } else {
        modal.style.display = 'none';
        if (backdrop) backdrop.style.display = 'none';
        modal.setAttribute('aria-hidden', 'true');
      }
    }
  
    // Fallback: crea il bottone se manca
    if (!openBtn) {
      openBtn = document.createElement('button');
      openBtn.id = 'btn-open-add-client';
      openBtn.className = 'btn btn-primary';
      openBtn.textContent = '+ Aggiungi cliente';
      openBtn.style.position = 'fixed';
      openBtn.style.right = '16px';
      openBtn.style.bottom = '16px';
      openBtn.style.zIndex = '10000';
      document.body.appendChild(openBtn);
    }
  
    openBtn && openBtn.addEventListener('click', () => show(true));
    closeBtn && closeBtn.addEventListener('click', () => show(false));
    cancelBtn && cancelBtn.addEventListener('click', () => show(false));
    backdrop && backdrop.addEventListener('click', () => show(false));
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') show(false); });
  
    // Validazione semplice
    form && form.addEventListener('submit', (e) => {
      const name = form.querySelector('input[name="name"]')?.value.trim();
      const ig = form.querySelector('input[name="instagram_username"]')?.value.trim();
      const api = form.querySelector('input[name="api_key"]')?.value.trim();
      if (!name || !ig || !api || api.length < 8) {
        e.preventDefault();
        alert('Compila Nome, Username IG e API Key (min 8 caratteri).');
        return;
      }
    });
  
    // Assicurati che parta chiuso
    show(false);
  })();
  