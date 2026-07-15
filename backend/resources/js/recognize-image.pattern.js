/*
 * "Get image details" — classic-UI image-field integration (Patternslib pattern).
 *
 * Adds a "Get image details" button next to every image file field on
 * edit/add forms. When an image is chosen and the button is clicked, the
 * selected file is sent to the `@aitools-recognize-image` endpoint, which
 * returns a title, a description and a list of tags. Those are written into
 * the form's Title / Description / Subject (tags) fields — but ONLY the ones
 * that are currently empty, so existing values are never overwritten.
 *
 * Config (endpoint URL, translated labels) is read from the pattern's options —
 * the viewlet renders it into `data-pat-aitools-recognize-image`.
 */
import Base from "@patternslib/patternslib/src/core/base";
import {
    escapeHtml,
    findField,
    setTags,
    setTextField,
    SPARKLES,
} from "./lib/fields";
import "./recognize-image.scss";

// The document scan + MutationObserver are global; only wire them up once even
// if several trigger elements are present on the page.
let started = false;

function applyDetails(form, details) {
    setTextField(findField(form, "title"), details.title);
    setTextField(findField(form, "description"), details.description);
    setTags(findField(form, "subjects") || findField(form, "subject"), details.tags);
}

/* ---- UI ---- */

function setStatus(bar, kind, message) {
    const status = bar.querySelector(".aitools-ri-status");
    if (!status) {
        return;
    }
    status.className = "aitools-ri-status aitools-ri-status--" + kind;
    if (kind === "loading") {
        status.innerHTML =
            '<span class="aitools-ri-spinner" aria-hidden="true"></span>' +
            "<span>" + escapeHtml(message) + "</span>";
    } else {
        status.textContent = message;
    }
    status.hidden = false;
}

function clearStatus(bar) {
    const status = bar.querySelector(".aitools-ri-status");
    if (status) {
        status.hidden = true;
        status.textContent = "";
    }
}

function setBusy(bar, busy) {
    const btn = bar.querySelector(".aitools-ri-btn");
    if (btn) {
        btn.disabled = busy;
    }
}

function readFileAsDataURL(file) {
    return new Promise(function (resolve, reject) {
        const reader = new FileReader();
        reader.onload = function () {
            resolve(reader.result);
        };
        reader.onerror = function () {
            reject(new Error("read error"));
        };
        reader.readAsDataURL(file);
    });
}

function run(CONFIG, input, bar, form) {
    const L = CONFIG.labels || {};
    const file = input.files && input.files[0];
    if (!file) {
        setStatus(bar, "error", L.noImage || "Choose an image first.");
        return;
    }
    setBusy(bar, true);
    setStatus(bar, "loading", L.loading || "Analyzing image...");

    readFileAsDataURL(file)
        .then(function (dataUri) {
            return fetch(CONFIG.endpoint, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ image: dataUri }),
            });
        })
        .then(function (resp) {
            return resp
                .json()
                .catch(function () {
                    return {};
                })
                .then(function (data) {
                    if (!resp.ok) {
                        const msg =
                            (data && data.error && (data.error.message || data.error)) ||
                            L.error;
                        throw new Error(msg);
                    }
                    return data;
                });
        })
        .then(function (data) {
            const details = (data && data.result) || {};
            applyDetails(form, details);
            setBusy(bar, false);
            setStatus(bar, "success", L.done || "Done.");
        })
        .catch(function (err) {
            setBusy(bar, false);
            if (err && err.message === "read error") {
                setStatus(bar, "error", L.readError || L.error);
            } else {
                setStatus(bar, "error", (err && err.message) || L.error);
            }
        });
}

function attach(CONFIG, input) {
    if (input.__aitoolsRiAttached) {
        return;
    }
    input.__aitoolsRiAttached = true;
    const L = CONFIG.labels || {};
    const form = input.closest("form") || document;

    const bar = document.createElement("div");
    bar.className = "aitools-ri";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "aitools-ri-btn";
    btn.innerHTML =
        SPARKLES + "<span>" + escapeHtml(L.button || "Get image details") + "</span>";
    btn.addEventListener("click", function () {
        run(CONFIG, input, bar, form);
    });

    const status = document.createElement("div");
    status.className = "aitools-ri-status";
    status.hidden = true;

    // Re-arm the status line whenever a new file is picked.
    input.addEventListener("change", function () {
        clearStatus(bar);
    });

    bar.appendChild(btn);
    bar.appendChild(status);

    // Place the bar just after the file input (inside the widget wrapper).
    if (input.parentNode) {
        input.parentNode.insertBefore(bar, input.nextSibling);
    }
}

// Image file fields: <input type="file" accept="image/*" ...>.
function isImageInput(input) {
    if (input.type !== "file") {
        return false;
    }
    const accept = (input.getAttribute("accept") || "").toLowerCase();
    if (accept.indexOf("image") !== -1) {
        return true;
    }
    // Fall back to the widget wrapper's fieldname when accept is absent.
    const field = input.closest("[data-fieldname]");
    const name =
        (input.name || "") + " " + (field ? field.getAttribute("data-fieldname") : "");
    return /image/i.test(name);
}

function scan(CONFIG, root) {
    (root || document)
        .querySelectorAll('input[type="file"]')
        .forEach(function (input) {
            if (isImageInput(input)) {
                attach(CONFIG, input);
            }
        });
}

function setup(CONFIG) {
    scan(CONFIG, document);
    // Handle image fields added dynamically (e.g. datagrid / ajax reloads).
    if (window.MutationObserver) {
        const observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (m) {
                Array.prototype.forEach.call(m.addedNodes || [], function (node) {
                    if (node.nodeType === 1) {
                        if (node.matches && node.matches('input[type="file"]')) {
                            if (isImageInput(node)) {
                                attach(CONFIG, node);
                            }
                        } else if (node.querySelectorAll) {
                            scan(CONFIG, node);
                        }
                    }
                });
            });
        });
        observer.observe(document.body, { childList: true, subtree: true });
    }
}

export default Base.extend({
    name: "aitools-recognize-image",
    trigger: ".pat-aitools-recognize-image",
    parser: "mockup",
    defaults: {
        endpoint: "",
        labels: {},
    },
    init: function () {
        if (started) {
            return;
        }
        started = true;
        setup(this.options);
    },
});
