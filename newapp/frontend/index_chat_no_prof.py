<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Simple FastAPI Chatbot</title>
  <style>
    body {
      background: linear-gradient(120deg, #dbeafe 0%, #e0e7ff 100%);
      font-family: system-ui, sans-serif;
      min-height: 100vh;
      margin: 0;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .chat-container {
      background: #fff;
      border-radius: 1.5rem;
      box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.15);
      width: 400px;
      max-width: 100vw;
      display: flex;
      flex-direction: column;
      height: 70vh;
      overflow: hidden;
    }
    .messages {
      flex: 1;
      padding: 1.5rem;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }
    .msg {
      max-width: 80%;
      padding: 0.7rem 1rem;
      border-radius: 1.2rem;
      font-size: 1rem;
      word-break: break-word;
      box-shadow: 0 2px 8px rgba(80,80,160,0.08);
    }
    .user { align-self: flex-end; background: #2563eb; color: white;}
    .bot  { align-self: flex-start; background: #f1f5f9; color: #333;}
    form {
      display: flex;
      gap: 0.5rem;
      padding: 1rem;
      background: #f1f5f9;
      border-top: 1px solid #e5e7eb;
    }
    input[type="text"] {
      flex: 1;
      border-radius: 999px;
      border: 1px solid #d1d5db;
      padding: 0.75rem 1rem;
      font-size: 1rem;
      outline: none;
    }
    button {
      padding: 0.75rem 1.2rem;
      background: #6366f1;
      color: #fff;
      border: none;
      border-radius: 999px;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.15s;
    }
    button:disabled {
      background: #a5b4fc;
      cursor: not-allowed;
    }
  </style>
</head>
<body>
	<button id="logout-btn" style="
	  position: fixed;
	  top: 2rem;
	  right: 2rem;
	  background: #6366f1;
	  color: #fff;
	  border: none;
	  border-radius: 999px;
	  padding: 0.5rem 1.3rem;
	  font-size: 1rem;
	  cursor: pointer;
	  box-shadow: 0 2px 8px rgba(80,80,160,0.08);
	  z-index: 9990;
	">Logout</button>

  <div class="chat-container">
    <div class="messages" id="messages"></div>
    <form id="chat-form" autocomplete="off">
      <input type="text" id="msg-input" placeholder="Type a message..." required />
      <button type="submit" id="send-btn">Send</button>
    </form>
    <button id="save-btn" style="margin: 1rem;">Press when done to save</button>
    <pre id="elect-analysis" style="padding:1rem;margin:1rem;background:#f1f5f9;border-radius:1rem;white-space:pre-wrap;max-height:10rem;overflow:auto;display:none"></pre>
  </div>
  
    <script>
    const form = document.getElementById('chat-form');
    const input = document.getElementById('msg-input');
    const messagesDiv = document.getElementById('messages');
    const sendBtn = document.getElementById('send-btn');
    const saveBtn = document.getElementById('save-btn');
    const analysisBox = document.getElementById('elect-analysis');
    const chatContainer = document.getElementById('chat-container');
    let locked = false;
    const messages = [];

    function addMessage(text, role) {
      const el = document.createElement('div');
      el.className = `msg ${role}`;
      el.textContent = text;
      messagesDiv.appendChild(el);
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }

    // Helper: fetch with 401 redirect handling
    async function authFetch(url, options = {}) {
      options.credentials = 'include'; // always send cookies
      let res;
      try {
        res = await fetch(url, options);
      } catch (e) {
        // network or CORS error
        window.location.href = "/auth";
        throw e;
      }
      if (res.status === 401) {
        window.location.href = "/auth";
        throw new Error("Unauthorized");
      }
      return res;
    }

    // On page load: check auth
    window.addEventListener('DOMContentLoaded', async () => {
      try {
        const whoami = await authFetch('/whoami');
        if (!whoami.ok) {
          // This should be unreachable, but just in case
          window.location.href = "/auth";
          return;
        }
        chatContainer.style.display = ""; // Show UI only if logged in

        // Start chat
        if (messages.length === 0) {
          const chatRes = await authFetch('/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ history: [] })
          });
          const data = await chatRes.json();
          addMessage(data.response, 'bot');
          messages.push({ role: "assistant", content: data.response });
        }
      } catch (err) {
        // We already redirect on error in authFetch
        return;
      }
    });

    // Chat submission
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (locked || !input.value.trim()) return;

      const userText = input.value.trim();
      addMessage(userText, 'user');
      messages.push({ role: "user", content: userText });

      input.value = '';
      input.disabled = true;
      sendBtn.disabled = true;
      locked = true;

      try {
        const res = await authFetch('/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ history: messages })
        });
        const data = await res.json();
        addMessage(data.response, 'bot');
        messages.push({ role: "assistant", content: data.response });
      } catch (err) {
        // If 401, page will already redirect
        if (err.message !== "Unauthorized") {
          addMessage('Sorry, something went wrong.', 'bot');
        }
      }
      input.disabled = false;
      sendBtn.disabled = false;
      input.focus();
      locked = false;
    });

    // Save chat
    saveBtn.addEventListener('click', async () => {
      saveBtn.disabled = true;
      saveBtn.textContent = 'Saving...';
      try {
        const res = await authFetch('/save_chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ history: messages })
        });
        const data = await res.json();
        if (data.success) {
          alert('Chat saved as: ' + data.filename);
          if (data.elect_analysis) {
            analysisBox.style.display = "block";
            analysisBox.textContent = data.elect_analysis;
          }
        } else {
          alert('Failed to save: ' + (data.error || 'Unknown error'));
          analysisBox.style.display = "none";
        }
      } catch (err) {
        // 401 triggers redirect; for other errors:
        if (err.message !== "Unauthorized") {
          alert('Error saving chat.');
          analysisBox.style.display = "none";
        }
      }
      saveBtn.disabled = false;
      saveBtn.textContent = 'Save Chat';
    });
	document.getElementById('logout-btn').onclick = async function() {
	  try {
		const res = await fetch('/auth/jwt/logout', {
		  method: 'POST',
		  credentials: 'include'
		});
		// On success or failure, go to login
		window.location.href = "/auth";
	  } catch (e) {
		window.location.href = "/auth";
	  }
	};

  </script>
</body>
</html>
