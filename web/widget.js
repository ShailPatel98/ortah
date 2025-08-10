(function () {
  const api = {
    chat: "/chat",
  };

  const widget = document.getElementById("widget");
  const fab = document.getElementById("fab");
  const chatEl = document.getElementById("chat");
  const input = document.getElementById("msg");
  const sendBtn = document.getElementById("send");
  const sessionId = localStorage.getItem("ortahaus_session") || (() => {
    const id = Math.random().toString(36).slice(2);
    localStorage.setItem("ortahaus_session", id);
    return id;
  })();

  function openWidget() {
    widget.classList.add("open");
    if (!chatEl.dataset.greeted) {
      chatEl.dataset.greeted = "1";
      addBot("Hi! I’m the Ortahaus Product Guide. Tell me your hair type and your main concern (e.g., volume, hold, frizz, or shine) and I’ll make a single, tailored recommendation.");
    }
    input.focus();
  }

  fab.addEventListener("click", () => {
    if (widget.classList.contains("open")) {
      widget.classList.remove("open");
    } else {
      openWidget();
    }
  });

  function addYou(text) {
    const row = document.createElement("div");
    row.className = "m you";
    row.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
    chatEl.appendChild(row);
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  function addBot(html) {
    const row = document.createElement("div");
    row.className = "m bot";
    row.innerHTML = `<div class="bubble">${html}</div>`;
    chatEl.appendChild(row);
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  function escapeHtml(s) {
    return s.replace(/[&<>]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[ch]));
  }

  async function send() {
    const text = input.value.trim();
    if (!text) return;
    addYou(text);
    input.value = "";
    try {
      const res = await fetch(api.chat, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });
      const data = await res.json();
      addBot(data.reply || "Hmm, I didn't catch that.");
    } catch (e) {
      addBot("Server error. Try again in a moment.");
    }
  }

  sendBtn.addEventListener("click", send);
  input.addEventListener("keydown", e => {
    if (e.key === "Enter") send();
  });

  // Auto-open on load to make it obvious
  window.addEventListener("load", () => setTimeout(openWidget, 400));
})();
