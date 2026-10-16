(() => {
  "use strict";

  const STORAGE_KEY = "motives-assistant-state-v1";
  const PROFILE_KEY = "motives-assistant-profile-v1";

  const elements = {
    conversation: document.querySelector("#conversation"),
    welcome: document.querySelector("#welcome"),
    messageList: document.querySelector("#messageList"),
    typing: document.querySelector("#typingIndicator"),
    form: document.querySelector("#chatForm"),
    input: document.querySelector("#messageInput"),
    sendButton: document.querySelector("#sendButton"),
    newChatButton: document.querySelector("#newChatButton"),
    logButton: document.querySelector("#logButton"),
    traceInspectorButton: document.querySelector("#traceInspectorButton"),
    traceBackdrop: document.querySelector("#traceBackdrop"),
    traceDrawer: document.querySelector("#traceDrawer"),
    traceCloseButton: document.querySelector("#traceCloseButton"),
    workflowSteps: document.querySelector("#workflowSteps"),
    logDrawer: document.querySelector("#logDrawer"),
    logCloseButton: document.querySelector("#logCloseButton"),
    logConversationId: document.querySelector("#logConversationId"),
    logContent: document.querySelector("#logContent"),
    routerPrompt: document.querySelector("#routerPrompt"),
    routerResponse: document.querySelector("#routerResponse"),
    composerPrompt: document.querySelector("#composerPrompt"),
    composerResponse: document.querySelector("#composerResponse"),
    composerTraceStage: document.querySelector("#composerTraceStage"),
    composerTraceEmpty: document.querySelector("#composerTraceEmpty"),
    employeeName: document.querySelector("#employeeName"),
    employeeId: document.querySelector("#employeeId"),
    profileCard: document.querySelector("#profileCard"),
    profileError: document.querySelector("#profileError"),
    savedLabel: document.querySelector("#savedLabel"),
    toast: document.querySelector("#toast"),
  };

  let state = loadState();
  let isSending = false;
  let activeRequest = null;
  let currentTrace = null;
  let profileSaveTimer = null;
  let toastTimer = null;

  function createId() {
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return `conversation-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function loadState() {
    try {
      const stored = JSON.parse(localStorage.getItem(STORAGE_KEY));
      if (stored && typeof stored.conversationId === "string" && Array.isArray(stored.messages)) {
        return stored;
      }
    } catch (_) {
      // A clean state is safer than blocking the UI on malformed local storage.
    }
    return { conversationId: createId(), messages: [] };
  }

  function saveState() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  function loadProfile() {
    try {
      const profile = JSON.parse(localStorage.getItem(PROFILE_KEY));
      if (profile) {
        elements.employeeName.value = profile.name || "";
        elements.employeeId.value = profile.id || "";
      }
    } catch (_) {
      localStorage.removeItem(PROFILE_KEY);
    }
  }

  function saveProfile() {
    const profile = {
      name: elements.employeeName.value.trim(),
      id: elements.employeeId.value.trim(),
    };
    localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
    elements.savedLabel.classList.add("is-visible");
    window.setTimeout(() => elements.savedLabel.classList.remove("is-visible"), 1200);

    if (profile.name && profile.id) {
      elements.profileCard.classList.remove("has-error");
    }
  }

  function queueProfileSave() {
    window.clearTimeout(profileSaveTimer);
    profileSaveTimer = window.setTimeout(saveProfile, 350);
  }

  function getProfile() {
    return {
      name: elements.employeeName.value.trim(),
      id: elements.employeeId.value.trim(),
    };
  }

  function validateProfile() {
    const profile = getProfile();
    const valid = Boolean(profile.name && profile.id);
    elements.profileCard.classList.toggle("has-error", !valid);

    if (!valid) {
      showToast("Nhập tên và mã nhân viên trước khi gửi yêu cầu.");
      const firstEmpty = profile.name ? elements.employeeId : elements.employeeName;
      firstEmpty.focus({ preventScroll: true });
      elements.profileCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    return valid;
  }

  function formatTime(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat("vi-VN", {
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  function renderMessageText(container, text) {
    const boldPattern = /\*\*(.+?)\*\*/gs;
    let cursor = 0;
    let match;

    while ((match = boldPattern.exec(text)) !== null) {
      if (match.index > cursor) {
        container.append(document.createTextNode(text.slice(cursor, match.index)));
      }

      const strong = document.createElement("strong");
      strong.textContent = match[1];
      container.append(strong);
      cursor = boldPattern.lastIndex;
    }

    if (cursor < text.length) {
      container.append(document.createTextNode(text.slice(cursor)));
    }
  }

  function createMessageElement(message) {
    const wrapper = document.createElement("article");
    wrapper.className = `message message--${message.role}`;
    if (message.error) wrapper.classList.add("message--error");

    const content = document.createElement("div");
    content.className = "message-content";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    renderMessageText(bubble, message.text);

    const meta = document.createElement("div");
    meta.className = "message-meta";
    const metaText = message.role === "user"
      ? `Bạn · ${formatTime(message.createdAt)}`
      : `${message.error ? "Không gửi được" : "Motives Assistant"} · ${formatTime(message.createdAt)}`;
    meta.append(document.createTextNode(metaText));

    if (message.role === "assistant" && message.trace) {
      const traceButton = document.createElement("button");
      traceButton.className = "message-trace-button";
      traceButton.type = "button";
      traceButton.textContent = "Xem Router & Composer";
      traceButton.addEventListener("click", () => openTrace(message.trace));
      meta.append(traceButton);
    }

    content.append(bubble, meta);

    if (message.role === "assistant") {
      const avatar = document.createElement("div");
      avatar.className = "message-avatar";
      avatar.setAttribute("aria-hidden", "true");
      avatar.textContent = "M";
      wrapper.append(avatar, content);
    } else {
      wrapper.append(content);
    }
    return wrapper;
  }

  function renderMessages() {
    elements.messageList.replaceChildren();
    elements.welcome.hidden = state.messages.length > 0;
    for (const message of state.messages) {
      elements.messageList.append(createMessageElement(message));
    }
    updateLatestTrace();
    scrollToBottom(false);
  }

  function addMessage(role, text, error = false, trace = null) {
    const message = {
      role,
      text,
      error,
      trace,
      createdAt: new Date().toISOString(),
    };
    state.messages.push(message);
    saveState();
    elements.welcome.hidden = true;
    elements.messageList.append(createMessageElement(message));
    updateLatestTrace();
    scrollToBottom();
  }

  function updateLatestTrace() {
    const latest = [...state.messages].reverse().find((message) => message.trace);
    currentTrace = latest ? latest.trace : null;
    elements.traceInspectorButton.disabled = !currentTrace;
  }

  function prettyJson(value) {
    return typeof value === "string" ? value : JSON.stringify(value, null, 2);
  }

  function traceBlock(title, value) {
    const block = document.createElement("div");
    block.className = "trace-block";
    const heading = document.createElement("div");
    heading.className = "trace-block-title";
    const label = document.createElement("span");
    label.textContent = title;
    const copyButton = document.createElement("button");
    copyButton.type = "button";
    copyButton.textContent = "Sao chép";
    const content = document.createElement("pre");
    content.textContent = prettyJson(value);
    copyButton.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(content.textContent || "");
        showToast("Đã sao chép vào clipboard.");
      } catch (_) {
        showToast("Không thể sao chép tự động.");
      }
    });
    heading.append(label, copyButton);
    block.append(heading, content);
    return block;
  }

  function fallbackSteps(trace) {
    const steps = [{
      sequence: 1,
      step_name: "llm",
      call_number: 1,
      reason: "router",
      status: "success",
      request: trace.router?.prompt,
      response: trace.router?.response,
    }];
    if (trace.composer) {
      steps.push({
        sequence: 2,
        step_name: "llm",
        call_number: 2,
        reason: "composer",
        status: "success",
        request: trace.composer.prompt,
        response: trace.composer.response,
      });
    }
    return steps;
  }

  function renderWorkflowSteps(trace) {
    elements.workflowSteps.replaceChildren();
    const steps = Array.isArray(trace.steps) && trace.steps.length
      ? trace.steps
      : fallbackSteps(trace);
    steps.forEach((step, index) => {
      const details = document.createElement("details");
      details.className = "trace-stage";
      details.open = step.status !== "skipped";
      const summary = document.createElement("summary");
      const number = document.createElement("span");
      number.className = `trace-step${step.reason === "composer" ? " trace-step--composer" : ""}`;
      number.textContent = String(step.sequence || index + 1).padStart(2, "0");
      const labels = document.createElement("span");
      const title = document.createElement("strong");
      title.textContent = `${String(step.step_name || "step").toUpperCase()} #${step.call_number || 1}`;
      const meta = document.createElement("small");
      const duration = Number.isFinite(step.duration_ms) ? ` · ${step.duration_ms.toFixed(1)} ms` : "";
      meta.textContent = `${step.reason || "execute"} · ${step.status || "success"}${duration}`;
      labels.append(title, meta);
      const chevron = document.createElement("span");
      chevron.className = "trace-chevron";
      chevron.textContent = "⌄";
      summary.append(number, labels, chevron);
      details.append(summary);
      if (step.request !== undefined && step.request !== null) {
        details.append(traceBlock("Input", step.request));
      }
      if (step.response !== undefined && step.response !== null) {
        details.append(traceBlock("Output", step.response));
      }
      if (step.error) details.append(traceBlock("Error", step.error));
      elements.workflowSteps.append(details);
    });
  }

  function openTrace(trace) {
    if (!trace || !trace.router) return;

    currentTrace = trace;
    renderWorkflowSteps(trace);
    elements.routerPrompt.textContent = trace.router.prompt || "";
    elements.routerResponse.textContent = prettyJson(trace.router.response || {});

    const hasComposer = Boolean(trace.composer);
    elements.composerPrompt.textContent = hasComposer ? trace.composer.prompt || "" : "";
    elements.composerResponse.textContent = hasComposer
      ? prettyJson(trace.composer.response || {})
      : "";
    elements.composerTraceEmpty.hidden = hasComposer;
    elements.composerTraceStage.querySelectorAll(".trace-block").forEach((block) => {
      block.hidden = !hasComposer;
    });

    elements.traceBackdrop.hidden = false;
    elements.logDrawer.classList.remove("is-open");
    elements.logDrawer.setAttribute("aria-hidden", "true");
    elements.traceDrawer.setAttribute("aria-hidden", "false");
    window.requestAnimationFrame(() => {
      elements.traceBackdrop.classList.add("is-open");
      elements.traceDrawer.classList.add("is-open");
      elements.traceCloseButton.focus();
    });
  }

  function closeTrace() {
    elements.traceBackdrop.classList.remove("is-open");
    elements.traceDrawer.classList.remove("is-open");
    elements.traceDrawer.setAttribute("aria-hidden", "true");
    window.setTimeout(() => {
      elements.traceBackdrop.hidden = true;
      elements.traceInspectorButton.focus();
    }, 220);
  }

  function renderLocalLog() {
    elements.logConversationId.textContent = `Conversation: ${state.conversationId}`;
    elements.logContent.replaceChildren();
    if (!state.messages.length) {
      const empty = document.createElement("p");
      empty.className = "trace-empty";
      empty.textContent = "Chưa có tin nhắn.";
      elements.logContent.append(empty);
      return;
    }
    state.messages.forEach((message, index) => {
      const section = document.createElement("section");
      section.className = "log-entry";
      const heading = document.createElement("div");
      heading.className = "log-entry-heading";
      const role = document.createElement("strong");
      role.textContent = message.role === "user" ? "USER" : "OCHES";
      const time = document.createElement("span");
      time.textContent = formatTime(message.createdAt);
      heading.append(role, time);
      const content = document.createElement("p");
      content.textContent = message.text;
      section.append(heading, content);
      if (message.trace) {
        const calls = (message.trace.steps || []).filter(
          (step) => step.step_name === "llm" && step.status !== "skipped",
        );
        const traceButton = document.createElement("button");
        traceButton.type = "button";
        traceButton.className = "message-trace-button";
        traceButton.textContent = `${calls.length || (message.trace.composer ? 2 : 1)} lần gọi LLM · xem luồng`;
        traceButton.addEventListener("click", () => openTrace(message.trace));
        section.append(traceButton);
      }
      section.dataset.index = String(index);
      elements.logContent.append(section);
    });
  }

  function openLog() {
    renderLocalLog();
    elements.traceDrawer.classList.remove("is-open");
    elements.traceDrawer.setAttribute("aria-hidden", "true");
    elements.traceBackdrop.hidden = false;
    elements.logDrawer.setAttribute("aria-hidden", "false");
    window.requestAnimationFrame(() => {
      elements.traceBackdrop.classList.add("is-open");
      elements.logDrawer.classList.add("is-open");
      elements.logCloseButton.focus();
    });
  }

  function closeLog() {
    elements.traceBackdrop.classList.remove("is-open");
    elements.logDrawer.classList.remove("is-open");
    elements.logDrawer.setAttribute("aria-hidden", "true");
    window.setTimeout(() => { elements.traceBackdrop.hidden = true; }, 220);
  }

  function closeDrawers() {
    closeTrace();
    closeLog();
  }

  function setSending(sending) {
    isSending = sending;
    elements.sendButton.disabled = sending;
    elements.input.disabled = sending;
    elements.typing.hidden = !sending;
    if (sending) scrollToBottom();
  }

  function scrollToBottom(smooth = true) {
    window.requestAnimationFrame(() => {
      elements.conversation.scrollTo({
        top: elements.conversation.scrollHeight,
        behavior: smooth ? "smooth" : "auto",
      });
    });
  }

  function resizeComposer() {
    elements.input.style.height = "auto";
    elements.input.style.height = `${Math.min(elements.input.scrollHeight, 132)}px`;
  }

  function showToast(message) {
    window.clearTimeout(toastTimer);
    elements.toast.textContent = message;
    elements.toast.classList.add("is-visible");
    toastTimer = window.setTimeout(() => {
      elements.toast.classList.remove("is-visible");
    }, 2800);
  }

  async function readError(response) {
    try {
      const data = await response.json();
      if (typeof data.detail === "string") return data.detail;
      if (data.detail) return JSON.stringify(data.detail);
    } catch (_) {
      // Fall through to a concise HTTP error.
    }
    return `Máy chủ trả về lỗi HTTP ${response.status}.`;
  }

  async function sendMessage(text) {
    if (isSending || !validateProfile()) return;

    const profile = getProfile();
    addMessage("user", text);
    elements.input.value = "";
    resizeComposer();
    setSending(true);

    activeRequest = new AbortController();

    try {
      const response = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: state.conversationId,
          user_id: profile.id,
          emp_id: profile.id,
          emp_name: profile.name,
          message: text,
          debug: true,
        }),
        signal: activeRequest.signal,
      });

      if (!response.ok) {
        throw new Error(await readError(response));
      }

      const data = await response.json();
      if (!data || typeof data.response !== "string" || !data.response.trim()) {
        throw new Error("Trợ lý chưa trả về nội dung. Vui lòng thử lại.");
      }
      addMessage("assistant", data.response.trim(), false, data.trace || null);
    } catch (error) {
      if (error.name !== "AbortError") {
        addMessage(
          "assistant",
          `Mình chưa xử lý được yêu cầu này. ${error.message || "Vui lòng thử lại sau."}`,
          true,
        );
      }
    } finally {
      activeRequest = null;
      setSending(false);
      elements.input.focus();
    }
  }

  function startNewConversation() {
    if (activeRequest) activeRequest.abort();
    state = { conversationId: createId(), messages: [] };
    saveState();
    renderMessages();
    setSending(false);
    elements.input.value = "";
    resizeComposer();
    elements.input.focus();
    showToast("Đã bắt đầu cuộc trò chuyện mới.");
  }

  elements.form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = elements.input.value.trim();
    if (text) sendMessage(text);
  });

  elements.input.addEventListener("input", resizeComposer);
  elements.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      elements.form.requestSubmit();
    }
  });

  elements.employeeName.addEventListener("input", queueProfileSave);
  elements.employeeId.addEventListener("input", queueProfileSave);
  elements.newChatButton.addEventListener("click", startNewConversation);
  elements.logButton.addEventListener("click", openLog);
  elements.traceInspectorButton.addEventListener("click", () => openTrace(currentTrace));
  elements.traceCloseButton.addEventListener("click", closeTrace);
  elements.logCloseButton.addEventListener("click", closeLog);
  elements.traceBackdrop.addEventListener("click", closeDrawers);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeDrawers();
    }
  });

  document.querySelectorAll("[data-copy-target]").forEach((button) => {
    button.addEventListener("click", async () => {
      const target = document.querySelector(`#${button.dataset.copyTarget}`);
      if (!target) return;
      try {
        await navigator.clipboard.writeText(target.textContent || "");
        showToast("Đã sao chép vào clipboard.");
      } catch (_) {
        showToast("Không thể sao chép tự động.");
      }
    });
  });

  document.querySelectorAll("[data-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      elements.input.value = button.dataset.prompt || "";
      resizeComposer();
      elements.input.focus();
      elements.input.setSelectionRange(elements.input.value.length, elements.input.value.length);
    });
  });

  loadProfile();
  renderMessages();
  resizeComposer();
})();
