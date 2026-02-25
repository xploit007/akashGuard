import os
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from openai import OpenAI

load_dotenv()

app = Flask(__name__)

START_TIME = time.monotonic()

client = OpenAI(
    api_key=os.getenv("AKASHML_API_KEY", ""),
    base_url=os.getenv("AKASHML_BASE_URL", "https://api.akashml.com/v1"),
)

MODEL = os.getenv("AKASHML_MODEL", "meta-llama/Llama-3.3-70B-Instruct")

SYSTEM_PROMPT = (
    "You are a helpful AI assistant powered by AkashGuard on the Akash decentralized cloud. "
    "Keep responses concise and friendly."
)


@app.get("/health")
def health():
    return jsonify(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat(),
        service="akashguard-chatbot",
        uptime_seconds=round(time.monotonic() - START_TIME, 2),
    )


@app.get("/")
def index():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AkashGuard Chatbot</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0f1117; color: #e0e0e0; height: 100vh; display: flex;
    flex-direction: column; align-items: center; justify-content: center;
  }
  .chat-container {
    width: 100%; max-width: 640px; height: 90vh; display: flex;
    flex-direction: column; background: #1a1d27; border-radius: 12px;
    overflow: hidden; box-shadow: 0 4px 24px rgba(0,0,0,.4);
  }
  .header {
    padding: 16px 20px; background: #23273a; font-size: 18px;
    font-weight: 600; border-bottom: 1px solid #2e3348;
    display: flex; align-items: center; gap: 10px;
  }
  .header .dot { width: 10px; height: 10px; background: #4ade80; border-radius: 50%; }
  .messages {
    flex: 1; overflow-y: auto; padding: 20px; display: flex;
    flex-direction: column; gap: 12px;
  }
  .msg { max-width: 80%; padding: 10px 14px; border-radius: 12px; line-height: 1.5; font-size: 14px; }
  .msg.user { align-self: flex-end; background: #3b82f6; color: #fff; border-bottom-right-radius: 4px; }
  .msg.bot { align-self: flex-start; background: #2a2d3a; border-bottom-left-radius: 4px; }
  .input-row {
    display: flex; padding: 12px; gap: 8px; background: #23273a;
    border-top: 1px solid #2e3348;
  }
  .input-row input {
    flex: 1; padding: 10px 14px; border-radius: 8px; border: 1px solid #2e3348;
    background: #1a1d27; color: #e0e0e0; font-size: 14px; outline: none;
  }
  .input-row input:focus { border-color: #3b82f6; }
  .input-row button {
    padding: 10px 20px; border-radius: 8px; border: none;
    background: #3b82f6; color: #fff; font-size: 14px; cursor: pointer;
    font-weight: 600;
  }
  .input-row button:disabled { opacity: .5; cursor: not-allowed; }
  .typing { font-style: italic; color: #888; font-size: 13px; }
</style>
</head>
<body>
<div class="chat-container">
  <div class="header"><span class="dot"></span> AkashGuard Chatbot</div>
  <div class="messages" id="messages">
    <div class="msg bot">Hey! I'm running on the Akash decentralized cloud. Ask me anything.</div>
  </div>
  <div class="input-row">
    <input type="text" id="input" placeholder="Type a message..." autocomplete="off" />
    <button id="send" onclick="sendMessage()">Send</button>
  </div>
</div>
<script>
  const msgBox = document.getElementById('messages');
  const input = document.getElementById('input');
  const btn = document.getElementById('send');

  input.addEventListener('keydown', e => { if (e.key === 'Enter' && !btn.disabled) sendMessage(); });

  async function sendMessage() {
    const text = input.value.trim();
    if (!text) return;
    addMsg(text, 'user');
    input.value = '';
    btn.disabled = true;

    const typing = document.createElement('div');
    typing.className = 'msg bot typing';
    typing.textContent = 'Thinking...';
    msgBox.appendChild(typing);
    msgBox.scrollTop = msgBox.scrollHeight;

    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message: text}),
      });
      const data = await res.json();
      typing.remove();
      addMsg(data.response, 'bot');
    } catch {
      typing.remove();
      addMsg('Something went wrong. Please try again.', 'bot');
    } finally {
      btn.disabled = false;
      input.focus();
    }
  }

  function addMsg(text, role) {
    const div = document.createElement('div');
    div.className = 'msg ' + role;
    div.textContent = text;
    msgBox.appendChild(div);
    msgBox.scrollTop = msgBox.scrollHeight;
  }
</script>
</body>
</html>"""


@app.post("/chat")
def chat():
    body = request.get_json(silent=True) or {}
    message = body.get("message", "").strip()
    if not message:
        return jsonify(response="Please send a message."), 200

    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            max_tokens=512,
            temperature=0.7,
        )
        reply = completion.choices[0].message.content.strip()
    except Exception:
        reply = "Sorry, I'm having trouble connecting to my brain right now. Try again in a moment!"

    return jsonify(response=reply)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
