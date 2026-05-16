let pendingCommand = null;

function getSessionId() {
    let sessionId = localStorage.getItem("promptdb_session_id");
    if (!sessionId) {
        sessionId = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
        localStorage.setItem("promptdb_session_id", sessionId);
    }
    return sessionId;
}

function formatTime(value) {
    const date = value ? new Date(value) : new Date();
    return date.toLocaleString([], {
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    });
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const contentType = response.headers.get("content-type") || "";
    if (response.status === 401) {
        window.location.href = "/login";
        throw new Error("Authentication required.");
    }
    if (!contentType.includes("application/json")) {
        throw new Error(`Unexpected response from ${url}.`);
    }
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || data.response || "Request failed.");
    }
    return data;
}

function setText(id, text) {
    const element = document.getElementById(id);
    if (element) {
        element.textContent = text;
    }
}

function setStatus(id, status) {
    const element = document.getElementById(id);
    if (!element || !status) return;

    element.classList.toggle("ok", Boolean(status.ok));
    element.classList.toggle("bad", !status.ok);
    element.title = status.detail || "";

    const label = element.childNodes[element.childNodes.length - 1];
    if (label && label.nodeType === Node.TEXT_NODE) {
        label.textContent = ` ${status.label}`;
    }
}

function appendMessage({ role, title, content, variant = "" }) {
    const chatBox = document.getElementById("chat-box");
    if (!chatBox) return null;

    const message = document.createElement("div");
    message.className = `message ${role} ${variant}`.trim();

    const messageTitle = document.createElement("span");
    messageTitle.className = "message-title";
    messageTitle.textContent = title;
    message.appendChild(messageTitle);

    if (content instanceof Node) {
        message.appendChild(content);
    } else {
        const body = document.createElement("div");
        body.textContent = content;
        message.appendChild(body);
    }

    const meta = document.createElement("span");
    meta.className = "message-meta";
    meta.textContent = formatTime();
    message.appendChild(meta);

    chatBox.appendChild(message);
    chatBox.scrollTop = chatBox.scrollHeight;
    return message;
}

function renderResultList(users) {
    const wrapper = document.createElement("div");
    wrapper.className = "result-list";

    users.forEach((user) => {
        const row = document.createElement("div");
        row.className = "result-row";

        const name = document.createElement("strong");
        name.textContent = user.name || "Unnamed user";

        const age = document.createElement("span");
        age.textContent = user.age !== undefined ? `${user.age} yrs` : "Age unknown";

        const city = document.createElement("span");
        city.textContent = user.city || "City unknown";

        row.append(name, age, city);
        wrapper.appendChild(row);
    });

    return wrapper;
}

function updatePreview(data) {
    const preview = document.getElementById("response-preview");
    if (preview) {
        preview.textContent = JSON.stringify(data, null, 2);
    }
}

function updateCharCount() {
    const input = document.getElementById("user-input");
    setText("char-count", `${input ? input.value.length : 0}/500`);
}

function openConfirmModal(payload) {
    pendingCommand = payload;
    const modal = document.getElementById("confirm-modal");
    const preview = document.getElementById("command-preview");
    if (preview) {
        preview.textContent = JSON.stringify(payload.command, null, 2);
    }
    if (modal) {
        modal.hidden = false;
    }
}

function closeConfirmModal() {
    pendingCommand = null;
    const modal = document.getElementById("confirm-modal");
    if (modal) {
        modal.hidden = true;
    }
}

async function executeCommand(payload, confirmed = false) {
    const typing = appendMessage({
        role: "bot",
        title: "PromptDB",
        content: confirmed ? "Executing command..." : "Running command...",
    });

    try {
        const data = await fetchJson("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: payload.message,
                session_id: getSessionId(),
                command: payload.command,
                parser: payload.parser,
                confirmed,
            }),
        });

        typing?.remove();
        updatePreview(data);

        const reply = data.response;
        if (Array.isArray(reply)) {
            appendMessage({
                role: "bot",
                title: "PromptDB",
                content: reply.length ? renderResultList(reply) : "No matching records found.",
            });
        } else {
            const text = reply || "No response returned.";
            const isError = text.toLowerCase().includes("failed") || text.toLowerCase().includes("error");
            appendMessage({
                role: "bot",
                title: "PromptDB",
                content: text,
                variant: isError ? "error" : "",
            });
        }
    } catch (error) {
        typing?.remove();
        updatePreview({ error: String(error) });
        appendMessage({
            role: "bot",
            title: "PromptDB",
            content: String(error.message || error),
            variant: "error",
        });
    }
}

async function sendMessage() {
    const input = document.getElementById("user-input");
    const sendButton = document.getElementById("send-button");
    const message = (input?.value || "").trim();
    if (!message) return;

    appendMessage({ role: "user", title: "You", content: message });
    input.value = "";
    updateCharCount();
    if (sendButton) sendButton.disabled = true;

    const thinking = appendMessage({
        role: "bot",
        title: "PromptDB",
        content: "Preparing command preview...",
    });

    try {
        const preview = await fetchJson("/api/preview", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message, session_id: getSessionId() }),
        });
        thinking?.remove();
        updatePreview(preview);

        const payload = { ...preview, message };
        if (preview.requires_confirmation) {
            appendMessage({
                role: "system",
                title: "Review required",
                content: "Review the command before execution.",
            });
            openConfirmModal(payload);
        } else {
            await executeCommand(payload, false);
        }
    } catch (error) {
        thinking?.remove();
        updatePreview({ error: String(error) });
        appendMessage({
            role: "bot",
            title: "PromptDB",
            content: String(error.message || error),
            variant: "error",
        });
    } finally {
        if (sendButton) sendButton.disabled = false;
        input?.focus();
    }
}

async function clearChat() {
    const chatBox = document.getElementById("chat-box");
    const sessionId = getSessionId();
    if (chatBox) chatBox.innerHTML = "";

    try {
        await fetchJson(`/api/session/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
    } catch (error) {
        updatePreview({ warning: "Server session could not be cleared.", detail: String(error) });
    }

    localStorage.removeItem("promptdb_session_id");
    appendMessage({
        role: "system",
        title: "Session",
        content: "Chat cleared.",
    });
}

async function loadStatus() {
    try {
        const status = await fetchJson("/api/status");
        setStatus("app-status", status.app);
        setStatus("mongo-status", status.mongo);
        setStatus("openrouter-status", status.openrouter);
    } catch (error) {
        setStatus("app-status", { ok: false, label: "Offline", detail: String(error) });
    }
}

async function loadExamples() {
    const list = document.getElementById("example-list");
    if (!list) return;

    list.textContent = "Loading examples...";
    try {
        const data = await fetchJson("/api/examples");
        list.innerHTML = "";

        data.examples.forEach((example) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "example-button";

            const label = document.createElement("strong");
            label.textContent = example.label;

            const prompt = document.createElement("span");
            prompt.textContent = example.prompt;

            button.append(label, prompt);
            button.addEventListener("click", () => {
                const input = document.getElementById("user-input");
                if (input) {
                    input.value = example.prompt;
                    updateCharCount();
                    input.focus();
                }
            });
            list.appendChild(button);
        });
    } catch (error) {
        list.textContent = "Examples could not be loaded.";
        updatePreview({ error: String(error) });
    }
}

async function loadUsers() {
    const tbody = document.getElementById("users-table-body");
    if (!tbody) return;

    const query = document.getElementById("user-search")?.value || "";
    const sort = document.getElementById("user-sort")?.value || "name";
    tbody.innerHTML = "<tr><td colspan=\"4\">Loading users...</td></tr>";

    try {
        const data = await fetchJson(`/api/users?q=${encodeURIComponent(query)}&sort=${encodeURIComponent(sort)}`);
        tbody.innerHTML = "";

        if (!data.users.length) {
            tbody.innerHTML = "<tr><td colspan=\"4\">No users found.</td></tr>";
            return;
        }

        data.users.forEach((user) => {
            const row = document.createElement("tr");
            row.innerHTML = `
                <td><input class="table-input" value="${escapeAttribute(user.name || "")}" data-field="name"></td>
                <td><input class="table-input" type="number" value="${escapeAttribute(user.age ?? "")}" data-field="age"></td>
                <td><input class="table-input" value="${escapeAttribute(user.city || "")}" data-field="city"></td>
                <td class="row-actions">
                    <button class="secondary-button" data-action="save">Save</button>
                    <button class="danger-button" data-action="delete">Delete</button>
                </td>
            `;

            row.querySelector('[data-action="save"]').addEventListener("click", async () => {
                const payload = {};
                row.querySelectorAll("[data-field]").forEach((input) => {
                    payload[input.dataset.field] = input.dataset.field === "age" ? Number(input.value) : input.value;
                });
                await fetchJson(`/api/users/${user._id}`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload),
                });
                loadUsers();
            });

            row.querySelector('[data-action="delete"]').addEventListener("click", async () => {
                if (!window.confirm(`Delete ${user.name || "this user"}?`)) return;
                await fetchJson(`/api/users/${user._id}`, { method: "DELETE" });
                loadUsers();
            });

            tbody.appendChild(row);
        });
    } catch (error) {
        tbody.innerHTML = `<tr><td colspan="4">${escapeHtml(String(error.message || error))}</td></tr>`;
    }
}

function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\"": "&quot;",
        "'": "&#039;",
    }[char]));
}

function escapeAttribute(value) {
    return escapeHtml(value);
}

function wireUsersPage() {
    const form = document.getElementById("user-form");
    const search = document.getElementById("user-search");
    const sort = document.getElementById("user-sort");
    const refresh = document.getElementById("refresh-users");

    if (!form) return;

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const note = document.getElementById("user-form-note");
        try {
            await fetchJson("/api/users", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: document.getElementById("new-name").value,
                    age: Number(document.getElementById("new-age").value),
                    city: document.getElementById("new-city").value,
                }),
            });
            form.reset();
            if (note) note.textContent = "User created.";
            loadUsers();
        } catch (error) {
            if (note) note.textContent = String(error.message || error);
        }
    });

    search?.addEventListener("input", () => window.clearTimeout(search._timer));
    search?.addEventListener("input", () => {
        search._timer = window.setTimeout(loadUsers, 250);
    });
    sort?.addEventListener("change", loadUsers);
    refresh?.addEventListener("click", loadUsers);
    loadUsers();
}

async function loadLogs() {
    const tbody = document.getElementById("logs-table-body");
    if (!tbody) return;

    tbody.innerHTML = "<tr><td colspan=\"6\">Loading audit logs...</td></tr>";
    try {
        const data = await fetchJson("/api/logs");
        tbody.innerHTML = "";

        if (!data.logs.length) {
            tbody.innerHTML = "<tr><td colspan=\"6\">No audit logs yet.</td></tr>";
            return;
        }

        data.logs.forEach((log) => {
            const row = document.createElement("tr");
            row.innerHTML = `
                <td>${escapeHtml(formatTime(log.timestamp))}</td>
                <td><span class="badge">${escapeHtml(log.action || "")}</span></td>
                <td>${escapeHtml(log.status || "")}</td>
                <td>${escapeHtml(log.parser || "")}</td>
                <td>${escapeHtml(log.prompt || "")}</td>
                <td>${escapeHtml(log.result_summary || "")}</td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        tbody.innerHTML = `<tr><td colspan="6">${escapeHtml(String(error.message || error))}</td></tr>`;
    }
}

function wireLogsPage() {
    const refresh = document.getElementById("refresh-logs");
    if (!refresh) return;
    refresh.addEventListener("click", loadLogs);
    loadLogs();
}

function wireConsole() {
    const input = document.getElementById("user-input");
    const sendButton = document.getElementById("send-button");
    const clearButton = document.getElementById("clear-chat");
    const refreshExamples = document.getElementById("refresh-examples");
    const confirmButton = document.getElementById("confirm-command");
    const cancelButton = document.getElementById("cancel-command");

    input?.addEventListener("input", updateCharCount);
    input?.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    });
    sendButton?.addEventListener("click", sendMessage);
    clearButton?.addEventListener("click", clearChat);
    refreshExamples?.addEventListener("click", loadExamples);
    cancelButton?.addEventListener("click", closeConfirmModal);
    confirmButton?.addEventListener("click", async () => {
        if (!pendingCommand) return;
        const payload = pendingCommand;
        closeConfirmModal();
        await executeCommand(payload, true);
    });

    if (document.getElementById("chat-box")) {
        appendMessage({
            role: "system",
            title: "PromptDB",
            content: "Ready.",
        });
        updateCharCount();
        loadStatus();
        loadExamples();
        window.setInterval(loadStatus, 30000);
    }
}

function wireContactForm() {
    const form = document.getElementById("contact-form");
    const note = document.getElementById("contact-note");

    form?.addEventListener("submit", (event) => {
        event.preventDefault();
        if (note) {
            note.textContent = "Message validated.";
        }
        form.reset();
    });
}

document.addEventListener("DOMContentLoaded", () => {
    wireConsole();
    wireUsersPage();
    wireLogsPage();
    wireContactForm();
});
