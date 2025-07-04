async function sendMessage() {
  const input = document.getElementById("user-input");
  const message = input.value.trim();
  if (message === "") return;

  const chatBox = document.getElementById("chat-box");
  const now = new Date();
  const timeString = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  // ✅ Show user message with timestamp
  chatBox.innerHTML += `
    <div class="user-message">
      <b>You:</b> ${message}
      <span class="timestamp">${timeString}</span>
    </div>`;
  input.value = "";

  // ✅ Show typing animation
  const typingEl = document.createElement("div");
  typingEl.className = "bot-message typing";
  typingEl.innerHTML = `<i>PromptDB is typing...</i>`;
  chatBox.appendChild(typingEl);
  chatBox.scrollTop = chatBox.scrollHeight;

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message })
    });

    const data = await response.json();

    // ✅ Remove typing
    typingEl.remove();

    let botReply = data.response;

    // ✅ Format array of users if it's an array
    if (Array.isArray(botReply)) {
      if (botReply.length === 0) {
        botReply = "No matching records found.";
      } else {
        botReply = botReply.map(user => {
          const name = user.name || "N/A";
          const age = user.age !== undefined ? `${user.age} yrs` : "Age: N/A";
          const city = user.city || "City: N/A";
          return `👤 ${name}, ${age}, ${city}`;
        }).join("<br>");
      }
    }

    // ✅ Show bot reply with timestamp
    const botTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    chatBox.innerHTML += `
      <div class="bot-message">
        <b>PromptDB:</b><br>${botReply}
        <span class="timestamp">${botTime}</span>
      </div>`;
    chatBox.scrollTop = chatBox.scrollHeight;

  } catch (error) {
    typingEl.remove();
    chatBox.innerHTML += `
      <div class="bot-message">
        <b>PromptDB:</b> Something went wrong while fetching data.
        <span class="timestamp">${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
      </div>`;
  }
}

// ✅ Send message on ENTER key
document.getElementById("user-input").addEventListener("keydown", function (e) {
  if (e.key === "Enter") {
    sendMessage();
  }
});

// ✅ Clear chat button functionality
function clearChat() {
  document.getElementById("chat-box").innerHTML = "";
  document.getElementById("user-input").value = "";
  localStorage.removeItem("session_id"); // Optional: Clear session ID
  location.reload(); // Optional: Reset session memory from server
}

// ✅ Attach clearChat to clear button click event
document.getElementById("clear-chat").addEventListener("click", clearChat);
