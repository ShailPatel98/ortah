/* Ortahaus floating chat widget — modern minimal UI */
(function(){
  const API_BASE = window.WIDGET_API_BASE || "http://localhost:8000";

  // ---- Styles (modern, clean) ----
  const css = `
  :root { --oh-bg:#111827; --oh-panel:#ffffff; --oh-accent:#111827; --oh-muted:#6b7280; }
  #oh-fab {
    position: fixed; right: 20px; bottom: 20px; z-index: 9999;
    background: var(--oh-accent); color: #fff; border: none;
    border-radius: 999px; padding: 12px 16px; cursor: pointer;
    font: 600 14px/1 ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto;
    box-shadow: 0 10px 24px rgba(0,0,0,.25);
  }
  #oh-modal {
    position: fixed; right: 20px; bottom: 80px; width: 380px; height: 520px; z-index: 9999;
    background: var(--oh-panel); border-radius: 16px; display: none; flex-direction: column; overflow: hidden;
    box-shadow: 0 20px 50px rgba(0,0,0,.35);
    font: 14px/1.45 ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto;
  }
  .oh-header {
    background: #f9fafb; padding: 14px 16px; display: flex; align-items: center; gap: 8px; border-bottom: 1px solid #eee;
    font-weight: 700; color: #111827;
  }
  .oh-header .oh-dot { width:10px;height:10px;border-radius:999px;background:#10b981; }
  .oh-body { flex: 1; padding: 14px; overflow-y: auto; background: #fff; }
  .oh-bubble {
    max-width: 85%; margin: 8px 0; padding: 10px 12px; border-radius: 12px;
    box-shadow: 0 1px 2px rgba(0,0,0,.04);
  }
  .oh-bubble.me { background: #e6f2ff; align-self: flex-end; }
  .oh-bubble.bot { background: #f3f4f6; align-self: flex-start; }
  .oh-footer { display: flex; gap: 8px; padding: 12px; border-top: 1px solid #eee; background: #fafafa; }
  .oh-input {
    flex: 1; padding: 10px 12px; border: 1px solid #e5e7eb; border-radius: 10px; outline: none;
    font: inherit;
  }
  .oh-send {
    padding: 10px 14px; border: none; border-radius: 10px; cursor: pointer; background: var(--oh-accent); color: #fff; font-weight: 600;
  }
  .oh-body a { color: #0ea5e9; text-decoration: none; }
  .oh-body a:hover { text-decoration: underline; }
  `;

  const style = document.createElement('style'); style.textContent = css; document.head.appendChild(style);

  // ---- Elements ----
  const fab = document.createElement('button'); fab.id = 'oh-fab'; fab.textContent = 'Chat';
  const modal = document.createElement('div'); modal.id = 'oh-modal';

  const header = document.createElement('div'); header.className = 'oh-header';
  header.innerHTML = `<span class="oh-dot"></span> Ortahaus Product Guide`;

  const body = document.createElement('div'); body.className = 'oh-body'; body.style.display = 'flex'; body.style.flexDirection = 'column';
  const footer = document.createElement('div'); footer.className = 'oh-footer';
  const input = document.createElement('input'); input.className = 'oh-input'; input.type = 'text'; input.placeholder = 'Tell me about your hair…';
  const send = document.createElement('button'); send.className = 'oh-send'; send.textContent = 'Send';

  footer.appendChild(input); footer.appendChild(send);
  modal.appendChild(header); modal.appendChild(body); modal.appendChild(footer);
  document.body.appendChild(fab); document.body.appendChild(modal);

  // ---- Helpers ----
  function addBubble(html, me=false){
    const b = document.createElement('div');
    b.className = 'oh-bubble ' + (me ? 'me' : 'bot');
    b.innerHTML = html; // render HTML (the API returns sanitized product lines)
    body.appendChild(b);
    body.scrollTop = body.scrollHeight;
  }

  async function sendMsg(){
    const msg = input.value.trim();
    if(!msg) return;
    addBubble(msg, true);
    input.value = '';
    addBubble('…', false);
    try{
      const r = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg })
      });
      const j = await r.json();
      body.lastChild.innerHTML = j.reply || 'Sorry, something went wrong.';
    }catch(e){
      body.lastChild.innerHTML = 'Network error. Check API URL.';
    }
  }

  let greeted = false;
  fab.onclick = () => {
    const open = modal.style.display !== 'flex';
    modal.style.display = open ? 'flex' : 'none';
    if (open && !greeted) {
      addBubble(
        "Hi! I’m the <b>Ortahaus</b> Product Guide. Tell me your hair type, main concern, and desired finish or hold, and I’ll recommend at least two products.",
        false
      );
      greeted = true;
    }
    if (open) input.focus();
  };

  send.onclick = sendMsg;
  input.addEventListener('keydown', e => { if(e.key === 'Enter') sendMsg(); });
})();
