(function(){
  const API_BASE = window.WIDGET_API_BASE || "http://localhost:8000";

  const btn = document.createElement('button');
  btn.id = 'oh-chat-fab';
  btn.textContent = 'Chat';
  Object.assign(btn.style, {
    position: 'fixed', right: '20px', bottom: '20px', zIndex: 9999,
    borderRadius: '24px', padding: '12px 16px', border: 'none', cursor: 'pointer',
    boxShadow: '0 4px 14px rgba(0,0,0,0.2)'
  });

  const modal = document.createElement('div');
  modal.id = 'oh-chat-modal';
  Object.assign(modal.style, {
    position: 'fixed', right: '20px', bottom: '70px', width: '360px', height: '480px',
    background: 'white', borderRadius: '12px', boxShadow: '0 10px 30px rgba(0,0,0,0.25)',
    display: 'none', flexDirection: 'column', overflow: 'hidden', zIndex: 9999
  });

  const header = document.createElement('div');
  header.textContent = 'Ortahaus Product Guide';
  Object.assign(header.style, { padding: '10px 12px', fontWeight: '600', borderBottom: '1px solid #eee' });

  const transcript = document.createElement('div');
  Object.assign(transcript.style, { flex: 1, padding: '10px', overflowY: 'auto', fontSize: '14px' });

  const footer = document.createElement('div');
  Object.assign(footer.style, { display: 'flex', gap: '8px', padding: '10px', borderTop: '1px solid #eee' });

  const input = document.createElement('input');
  input.type = 'text'; input.placeholder = 'Tell me about your hair…';
  Object.assign(input.style, { flex: 1, padding: '10px', border: '1px solid #ddd', borderRadius: '8px' });

  const send = document.createElement('button');
  send.textContent = 'Send';
  Object.assign(send.style, { padding: '10px 12px', border: 'none', borderRadius: '8px', cursor: 'pointer' });

  footer.appendChild(input); footer.appendChild(send);
  modal.appendChild(header); modal.appendChild(transcript); modal.appendChild(footer);
  document.body.appendChild(btn); document.body.appendChild(modal);

  function addBubble(text, me){
    const b = document.createElement('div');
    b.textContent = text;
    Object.assign(b.style, { margin: '8px 0', maxWidth: '85%', padding: '8px 10px', borderRadius: '10px',
      background: me ? '#e6f2ff' : '#f5f5f5', alignSelf: me ? 'flex-end' : 'flex-start' });
    transcript.appendChild(b); transcript.scrollTop = transcript.scrollHeight;
  }

  btn.onclick = () => { modal.style.display = modal.style.display === 'none' ? 'flex' : 'none'; };

  async function sendMsg(){
    const msg = input.value.trim(); if(!msg) return;
    addBubble(msg, true); input.value = '';
    addBubble('…', false);
    try{
      const r = await fetch(`${API_BASE}/api/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: msg }) });
      const j = await r.json();
      transcript.lastChild.textContent = j.reply || 'Sorry, something went wrong.';
    }catch(e){ transcript.lastChild.textContent = 'Network error. Check API URL.'; }
  }

  send.onclick = sendMsg; input.addEventListener('keydown', e => { if(e.key === 'Enter') sendMsg(); });
})();
