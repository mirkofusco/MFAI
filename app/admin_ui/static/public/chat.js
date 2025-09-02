(function () {
    function qs(sel) { return document.querySelector(sel); }
    function el(tag, cls) { const e = document.createElement(tag); if (cls) e.className = cls; return e; }
    function appendMsg(who, text) {
      const log = qs('#chat-log');
      const wrap = el('div', 'msg ' + (who === 'you' ? 'user' : 'bot'));
      const whoEl = el('div', 'who'); whoEl.textContent = who === 'you' ? 'Tu' : 'MF.AI';
      const bubble = el('div', 'bubble'); bubble.textContent = text;
      wrap.appendChild(whoEl); wrap.appendChild(bubble);
      log.appendChild(wrap); log.scrollTop = log.scrollHeight;
    }
  
    async function sendMessage(slug, text) {
      const resp = await fetch(`/c/${encodeURIComponent(slug)}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user: text })
      });
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      const data = await resp.json();
      return data.reply || 'Nessuna risposta.';
    }
  
    function getSlug() {
      // path tipo: /c/{slug}[...]
      const parts = window.location.pathname.split('/').filter(Boolean);
      const idx = parts.indexOf('c');
      return idx >= 0 && parts[idx + 1] ? decodeURIComponent(parts[idx + 1]) : '';
    }
  
    window.addEventListener('DOMContentLoaded', () => {
      const form = qs('#chat-form');
      const input = qs('#chat-input');
      const btn = qs('#chat-send');
      const log = qs('#chat-log');
      const slug = log ? log.getAttribute('data-slug') || getSlug() : getSlug();
  
      if (!form || !input || !btn || !slug) return;
  
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;
        input.value = '';
        input.blur();
        btn.disabled = true;
        appendMsg('you', text);
        try {
          const reply = await sendMessage(slug, text);
          appendMsg('bot', reply);
        } catch (err) {
          appendMsg('bot', 'Errore nella risposta. Riprova.');
          console.error(err);
        } finally {
          btn.disabled = false;
          input.focus();
        }
      });
    });
  })();
  