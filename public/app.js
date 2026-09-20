// public/app.js – Handles ChargeMate chat UI and communicates with FastAPI/Vercel backend

// Simple markdown formatter for messages
function formatMarkdown(text) {
  if (!text) return "";
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Bold **text**
  html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  // Italic _text_ or *text*
  html = html.replace(/(?:^|\s)_([^_]+)_(?:\s|$)/g, " <em>$1</em> ");
  // Inline code `code`
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  // Line breaks
  html = html.replace(/\n/g, "<br>");
  return html;
}

// Append a message (user or bot) to the chat history
function addMessage(content, type, tableHtml = "") {
  const container = document.getElementById("chat-history");
  const msgDiv = document.createElement("div");
  msgDiv.className = `chat-msg ${type}`;

  const avatar = document.createElement("div");
  avatar.className = "msg-avatar";
  avatar.textContent = type === "user" ? "👤" : "⚡";

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  bubble.innerHTML = formatMarkdown(content);

  if (tableHtml) {
    bubble.innerHTML += `<div class="result-table-container">${tableHtml}</div>`;
  }

  msgDiv.appendChild(avatar);
  msgDiv.appendChild(bubble);
  container.appendChild(msgDiv);
  container.scrollTop = container.scrollHeight;
}

// Render result rows as an HTML table
function renderTable(rows) {
  if (!rows || rows.length === 0) return "";
  let html = `
    <table class="result-table">
      <thead>
        <tr>
          <th>Station</th>
          <th>Dist (km)</th>
          <th>ETA (min)</th>
          <th>Power</th>
          <th>Price</th>
          <th>Score</th>
        </tr>
      </thead>
      <tbody>
  `;
  rows.forEach(r => {
    html += `
      <tr>
        <td><strong>${r.name}</strong></td>
        <td>${r.distance_km} km</td>
        <td>~${r.eta_min} min</td>
        <td>${Math.round(r.power_kw)} kW</td>
        <td>${r.price}</td>
        <td><span class="badge-score">${r.score}</span></td>
      </tr>
    `;
  });
  html += `</tbody></table>`;
  return html;
}

// Main send handler
async function sendMessage() {
  const messageInput = document.getElementById("message");
  const sendBtn = document.getElementById("sendBtn");
  const message = messageInput.value.trim();
  const lat = parseFloat(document.getElementById("lat").value);
  const lon = parseFloat(document.getElementById("lon").value);
  const range = parseFloat(document.getElementById("range").value);
  const radiusInput = document.getElementById("radius").value;
  const radius = radiusInput ? parseFloat(radiusInput) : null;
  const showDebug = document.getElementById("debug").checked;

  if (!message) return;
  if (isNaN(lat) || isNaN(lon) || isNaN(range)) {
    alert("Please enter valid numbers for latitude, longitude, and remaining range.");
    return;
  }

  // Show user message
  addMessage(message, "user");
  messageInput.value = "";
  sendBtn.disabled = true;
  sendBtn.textContent = "Searching...";

  const payload = {
    message,
    lat,
    lon,
    latitude: lat,
    longitude: lon,
    remaining_range_km: range,
    search_radius_km: radius,
    show_debug: showDebug,
  };

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      throw new Error(`Server returned HTTP ${resp.status}`);
    }

    const data = await resp.json();
    let reply = data.reply || "No response received.";
    let tableHtml = "";

    if (data.rows && data.rows.length) {
      tableHtml = renderTable(data.rows);
    }

    if (showDebug && data.intent) {
      const sourceNote = data.intent._source === "llm" 
        ? `LIVE LLM call (${data.intent._backend || "llm"})` 
        : "rule-based fallback - no LLM backend configured/reachable";
      reply += `\n\n<small>Intent parsed via <strong>${sourceNote}</strong> · <code>${JSON.stringify(data.intent)}</code></small>`;
    }

    addMessage(reply, "bot", tableHtml);
  } catch (e) {
    console.error(e);
    addMessage(`⚠️ Failed to communicate with ChargeMate API (${e.message}). Please check the server connection.`, "bot");
  } finally {
    sendBtn.disabled = false;
    sendBtn.textContent = "Send ➔";
    messageInput.focus();
  }
}

// Event Listeners
document.getElementById("sendBtn").addEventListener("click", sendMessage);

// Enter key to send
document.getElementById("message").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && !ev.shiftKey) {
    ev.preventDefault();
    sendMessage();
  }
});

// Example Pills click to populate and submit
document.querySelectorAll(".example-pill").forEach((pill) => {
  pill.addEventListener("click", () => {
    const messageInput = document.getElementById("message");
    messageInput.value = pill.textContent.trim();
    sendMessage();
  });
});

