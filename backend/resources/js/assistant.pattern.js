/*
 * "Assistant" — a floating chat widget for authenticated users. Config is read
 * from `data-pat-aitools-assistant` on the viewlet element (endpoints + labels).
 *
 * A launcher button (bottom-right) toggles a chat panel. Each turn POSTs the
 * full conversation history to `@aitools-assistant`; the reply is appended and
 * any `proposals` are rendered as confirm cards that POST to
 * `@aitools-assistant-apply` (the only place content is actually created).
 *
 * The transcript and the open/closed state are persisted to sessionStorage so
 * navigating to another page (a full reload) keeps the conversation and, if it
 * was open, re-opens the widget where the user left off.
 */
import Base from "@patternslib/patternslib/src/core/base";
import { postJSON } from "./lib/ui";
import { renderMarkdown } from "./lib/markdown";
import "./assistant.scss";

const STORE_KEY = "aitools-assistant-session";

export default Base.extend({
    name: "aitools-assistant",
    trigger: ".pat-aitools-assistant",
    parser: "mockup",
    defaults: {
        endpoint: "",
        applyEndpoint: "",
        labels: {},
    },

    init: function () {
        const CONFIG = this.options;
        const L = CONFIG.labels || {};
        const root = this.$el[0];

        // -- persisted session ----------------------------------------------
        // transcript: [{role: "user"|"assistant", content, proposals?}]
        let state = { open: false, transcript: [] };
        try {
            const saved = window.sessionStorage.getItem(STORE_KEY);
            if (saved) {
                const parsed = JSON.parse(saved);
                if (parsed && Array.isArray(parsed.transcript)) {
                    state = { open: !!parsed.open, transcript: parsed.transcript };
                }
            }
        } catch (e) {
            // storage unavailable / malformed — start fresh.
        }
        function save() {
            try {
                window.sessionStorage.setItem(STORE_KEY, JSON.stringify(state));
            } catch (e) {
                // ignore (private mode, quota, …)
            }
        }
        // The history sent to the backend: only role + content.
        function messages() {
            return state.transcript.map(function (m) {
                return { role: m.role, content: m.content };
            });
        }

        // POST including the CSRF token (plone.protect's X-CSRF-TOKEN header),
        // needed for the write (apply) request; harmless on the read one.
        function post(endpoint, payload) {
            const headers = CONFIG.token ? { "X-CSRF-TOKEN": CONFIG.token } : {};
            return postJSON(endpoint, payload, L.error, headers);
        }

        // -- helpers ---------------------------------------------------------
        const el = function (tag, cls, text) {
            const node = document.createElement(tag);
            if (cls) {
                node.className = cls;
            }
            if (text != null) {
                node.textContent = text;
            }
            return node;
        };

        // -- launcher + panel ------------------------------------------------
        const launcher = el("button", "aitools-assistant-launcher");
        launcher.type = "button";
        launcher.setAttribute("aria-label", L.open || "Open the assistant");
        launcher.innerHTML = "<span aria-hidden='true'>✨</span>";

        const panel = el("div", "aitools-assistant-panel");
        panel.hidden = true;

        const header = el("div", "aitools-assistant-header");
        header.appendChild(el("span", "aitools-assistant-title", L.title || "Assistant"));
        const actions = el("div", "aitools-assistant-actions");
        const newBtn = el("button", "aitools-assistant-new", "↻");
        newBtn.type = "button";
        newBtn.setAttribute("aria-label", L.new_chat || "Start new chat");
        newBtn.title = L.new_chat || "Start new chat";
        const closeBtn = el("button", "aitools-assistant-close", "×");
        closeBtn.type = "button";
        closeBtn.setAttribute("aria-label", L.close || "Close");
        actions.appendChild(newBtn);
        actions.appendChild(closeBtn);
        header.appendChild(actions);

        const log = el("div", "aitools-assistant-log");

        const form = el("form", "aitools-assistant-input");
        const input = el("input", "aitools-assistant-text");
        input.type = "text";
        input.placeholder = L.placeholder || "Ask…";
        const send = el("button", "aitools-assistant-send", L.send || "Send");
        send.type = "submit";
        form.appendChild(input);
        form.appendChild(send);

        panel.appendChild(header);
        panel.appendChild(log);
        panel.appendChild(form);
        root.appendChild(launcher);
        root.appendChild(panel);

        // -- rendering -------------------------------------------------------
        function addBubble(role, text) {
            const bubble = el("div", "aitools-assistant-msg aitools-assistant-" + role);
            if (role === "assistant") {
                bubble.innerHTML = renderMarkdown(text);
            } else {
                bubble.textContent = text;
            }
            log.appendChild(bubble);
            log.scrollTop = log.scrollHeight;
            return bubble;
        }

        function renderProposal(proposal) {
            const card = el("div", "aitools-assistant-proposal");
            const label =
                proposal.portal_type +
                " · " +
                (proposal.title || "") +
                " → " +
                (proposal.container_title || proposal.container_path || "");
            card.appendChild(el("div", "aitools-assistant-proposal-label", label));

            const btn = el("button", "aitools-assistant-proposal-btn", L.create || "Create draft");
            btn.type = "button";
            btn.addEventListener("click", function () {
                btn.disabled = true;
                btn.textContent = L.creating || "Creating…";
                post(CONFIG.applyEndpoint, { proposal: proposal })
                    .then(function (data) {
                        card.innerHTML = "";
                        card.appendChild(
                            el("span", "aitools-assistant-created", L.created || "Draft created:")
                        );
                        const link = el("a", "aitools-assistant-link", data.title || data.url);
                        link.href = data.url;
                        card.appendChild(link);
                    })
                    .catch(function (err) {
                        btn.disabled = false;
                        btn.textContent = L.create || "Create draft";
                        card.appendChild(
                            el("div", "aitools-assistant-proposal-error", (err && err.message) || L.error)
                        );
                    });
            });
            card.appendChild(btn);
            log.appendChild(card);
            log.scrollTop = log.scrollHeight;
        }

        // Replay the persisted transcript into the log.
        function renderTranscript() {
            log.innerHTML = "";
            state.transcript.forEach(function (m) {
                addBubble(m.role, m.content);
                (m.proposals || []).forEach(renderProposal);
            });
        }

        // -- ask -------------------------------------------------------------
        function ask() {
            const text = (input.value || "").trim();
            if (!text) {
                return;
            }
            input.value = "";
            state.transcript.push({ role: "user", content: text });
            save();
            addBubble("user", text);
            const status = addBubble("status", L.loading || "Thinking…");
            send.disabled = true;

            post(CONFIG.endpoint, { messages: messages() })
                .then(function (data) {
                    log.removeChild(status);
                    const reply = (data && data.reply) || "";
                    const proposals = (data && data.proposals) || [];
                    state.transcript.push({
                        role: "assistant",
                        content: reply,
                        proposals: proposals,
                    });
                    save();
                    addBubble("assistant", reply);
                    proposals.forEach(renderProposal);
                    send.disabled = false;
                    input.focus();
                })
                .catch(function (err) {
                    status.classList.add("aitools-assistant-error-msg");
                    status.textContent = (err && err.message) || L.error;
                    send.disabled = false;
                });
        }

        // -- new chat --------------------------------------------------------
        function newChat() {
            state.transcript = [];
            save();
            log.innerHTML = "";
            input.value = "";
            send.disabled = false;
            input.focus();
        }

        // -- open/close ------------------------------------------------------
        function toggle(open) {
            state.open = open;
            save();
            panel.hidden = !open;
            launcher.classList.toggle("is-open", open);
            if (open) {
                input.focus();
            }
        }
        launcher.addEventListener("click", function () {
            toggle(panel.hidden);
        });
        newBtn.addEventListener("click", newChat);
        closeBtn.addEventListener("click", function () {
            toggle(false);
        });
        form.addEventListener("submit", function (e) {
            e.preventDefault();
            ask();
        });

        // -- restore ---------------------------------------------------------
        renderTranscript();
        toggle(state.open);
    },
});
