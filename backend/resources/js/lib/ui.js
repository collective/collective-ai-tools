/*
 * Shared "sparkle button + status line" UI used by the content edit-form tools
 * (Summarize, Suggest tags). Returns the bar element plus small helpers to
 * drive its busy/status state.
 */
import { SPARKLES, escapeHtml } from "./fields";
import "./ui.scss";

export function createBar(label, onClick) {
    const bar = document.createElement("div");
    bar.className = "aitools-tool";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "aitools-tool-btn";
    btn.innerHTML = SPARKLES + "<span>" + escapeHtml(label) + "</span>";
    btn.addEventListener("click", onClick);

    const status = document.createElement("div");
    status.className = "aitools-tool-status";
    status.hidden = true;

    bar.appendChild(btn);
    bar.appendChild(status);

    function setStatus(kind, message) {
        status.className = "aitools-tool-status aitools-tool-status--" + kind;
        if (kind === "loading") {
            status.innerHTML =
                '<span class="aitools-tool-spinner" aria-hidden="true"></span>' +
                "<span>" + escapeHtml(message) + "</span>";
        } else {
            status.textContent = message;
        }
        status.hidden = false;
    }

    function clearStatus() {
        status.hidden = true;
        status.textContent = "";
    }

    function setBusy(busy) {
        btn.disabled = busy;
    }

    return { bar: bar, btn: btn, setStatus: setStatus, clearStatus: clearStatus, setBusy: setBusy };
}

// Resolve `resp` to its parsed JSON body, throwing an Error carrying the
// server's message on a non-2xx response.
function handleJSON(resp, fallbackError) {
    return resp
        .json()
        .catch(function () {
            return {};
        })
        .then(function (data) {
            if (!resp.ok) {
                const msg =
                    (data && data.error && (data.error.message || data.error)) ||
                    fallbackError;
                const err = new Error(msg);
                // Lets callers tell e.g. a 503 (retry elsewhere) from a 4xx.
                err.status = resp.status;
                throw err;
            }
            return data;
        });
}

// POST JSON to `endpoint` and resolve with the parsed body, throwing an Error
// carrying the server's message on a non-2xx response.
export function postJSON(endpoint, payload, fallbackError, extraHeaders) {
    return fetch(endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: Object.assign(
            {
                Accept: "application/json",
                "Content-Type": "application/json",
            },
            extraHeaders || {}
        ),
        body: JSON.stringify(payload),
    }).then(function (resp) {
        return handleJSON(resp, fallbackError);
    });
}

// GET JSON from `endpoint`, same error semantics as postJSON. Used to poll an
// async task's status.
export function getJSON(endpoint, fallbackError, extraHeaders) {
    return fetch(endpoint, {
        method: "GET",
        credentials: "same-origin",
        headers: Object.assign({ Accept: "application/json" }, extraHeaders || {}),
    }).then(function (resp) {
        return handleJSON(resp, fallbackError);
    });
}
