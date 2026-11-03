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

// How often to poll an async task for its result; also the delay before the
// first poll.
export const POLL_INTERVAL_MS = 2000;
// Delay before the one automatic retry of a call interrupted by a server
// restart (a 503 from the start endpoint, or a "retryable" task error).
export const RETRY_DELAY_MS = 2000;

// Run a tool endpoint as a polled task and resolve with the body it answers —
// the same body the endpoint returns when called synchronously.
//
// POSTs `payload` with `async: true`. A 202 carries a task id, polled at
// `statusEndpoint + "/" + id` until it is done (resolve with its `result`) or
// failed (reject with its message); a 200 is a synchronous answer and resolves
// as it is.
//
// - A server restart (503 on the start, or a task error marked `retryable`)
//   re-runs the whole call once, silently. Every tool is read-only, so running
//   it again is safe.
// - `syncFallback`: a poll answered 404 means the task lives in another Zope
//   process (several processes, no shared task store). The call is then sent
//   once more without `async` and its synchronous answer used.
// - `isCurrent()` returning false stops the polling and leaves the promise
//   unsettled, for callers whose context went away (a reset conversation).
export function runTask(options) {
    const endpoint = options.endpoint;
    const statusEndpoint = options.statusEndpoint;
    const payload = options.payload || {};
    const fallbackError = options.fallbackError;
    const headers = options.headers;
    const isCurrent =
        options.isCurrent ||
        function () {
            return true;
        };

    return new Promise(function (resolve, reject) {
        let retried = false;

        function retry() {
            retried = true;
            window.setTimeout(start, RETRY_DELAY_MS);
        }

        function runSync() {
            postJSON(endpoint, payload, fallbackError, headers).then(resolve, reject);
        }

        function poll(taskId) {
            if (!isCurrent()) {
                return;
            }
            getJSON(statusEndpoint + "/" + encodeURIComponent(taskId), fallbackError)
                .then(function (data) {
                    if (!isCurrent()) {
                        return;
                    }
                    const status = data && data.status;
                    if (status === "done") {
                        resolve((data && data.result) || {});
                    } else if (status === "error" && data.retryable && !retried) {
                        retry();
                    } else if (status === "error") {
                        reject(new Error((data && data.error) || fallbackError));
                    } else {
                        window.setTimeout(function () {
                            poll(taskId);
                        }, POLL_INTERVAL_MS);
                    }
                })
                .catch(function (err) {
                    if (!isCurrent()) {
                        return;
                    }
                    if (err && err.status === 404 && options.syncFallback) {
                        runSync();
                        return;
                    }
                    reject(err);
                });
        }

        function start() {
            if (!isCurrent()) {
                return;
            }
            postJSON(
                endpoint,
                Object.assign({}, payload, { async: true }),
                fallbackError,
                headers
            )
                .then(function (data) {
                    if (!isCurrent()) {
                        return;
                    }
                    if (data && data.task_id) {
                        window.setTimeout(function () {
                            poll(data.task_id);
                        }, POLL_INTERVAL_MS);
                    } else {
                        // Answered synchronously (a server without async).
                        resolve(data);
                    }
                })
                .catch(function (err) {
                    if (!isCurrent()) {
                        return;
                    }
                    if (err && err.status === 503 && !retried) {
                        retry();
                        return;
                    }
                    reject(err);
                });
        }

        start();
    });
}
