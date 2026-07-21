/*
 * "Help me write" — classic-UI TinyMCE integration (Patternslib pattern).
 *
 * Adds a "Help me write" button above every TinyMCE rich-text editor on
 * edit/add forms. The button opens a menu of writing operations. "draft"
 * (and any operation flagged needsInput) shows an input + Send; the result is
 * inserted at the cursor. The other operations transform the selected text
 * (or the whole field when nothing is selected) and replace it in place,
 * leaving non-text nodes (images, etc.) untouched.
 *
 * Editors are discovered through the global TinyMCE registry
 * (`window.tinymce.editors` + the AddEditor/init events) rather than by
 * scanning the DOM, so this works regardless of the editor's markup.
 *
 * Config (endpoint URL, operations, translated labels) is read from the
 * pattern's options — the viewlet renders it into `data-pat-aitools-help-me-write`.
 */
import Base from "@patternslib/patternslib/src/core/base";
import "./help-me-write.scss";

const SPARKLES =
    '<svg class="aitools-hmw-stars" viewBox="0 0 24 24" width="16" ' +
    'height="16" aria-hidden="true" focusable="false">' +
    '<path fill="currentColor" d="M12 2l1.6 4.6L18 8l-4.4 1.4L12 14l-1.6-4.6' +
    'L6 8l4.4-1.4L12 2zm6 10l.9 2.6L21 15l-2.1.7L18 18l-.9-2.3L15 15l2.1-.4' +
    'L18 12zM6 13l.8 2.4L9 16l-2.2.7L6 19l-.8-2.3L3 16l2.2-.6L6 13z"/></svg>';

// The TinyMCE hook is global; guard against attaching it more than once even
// if several trigger elements are present on the page.
let hooked = false;

function setup(CONFIG) {
    const L = CONFIG.labels || {};
    const OPERATIONS = CONFIG.operations || [];

    function escapeHtml(text) {
        const div = document.createElement("div");
        div.appendChild(document.createTextNode(text));
        return div.innerHTML;
    }

    function textToHtml(text) {
        return escapeHtml(text)
            .split(/\n{2,}/)
            .map(function (para) {
                return "<p>" + para.replace(/\n/g, "<br>") + "</p>";
            })
            .join("");
    }

    /* ---- selection / replacement preserving non-text nodes ---- */

    function rangeIntersectsNode(range, node) {
        if (range.intersectsNode) {
            return range.intersectsNode(node);
        }
        const nodeRange = node.ownerDocument.createRange();
        nodeRange.selectNodeContents(node);
        return (
            range.compareBoundaryPoints(Range.END_TO_START, nodeRange) < 0 &&
            range.compareBoundaryPoints(Range.START_TO_END, nodeRange) > 0
        );
    }

    // Collect the text nodes (with clipped offsets) covered by the range.
    function collectTextParts(editor, range) {
        const doc = editor.getDoc();
        const root = editor.getBody();
        const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
        const parts = [];
        let node;
        while ((node = walker.nextNode())) {
            if (!rangeIntersectsNode(range, node)) {
                continue;
            }
            let start = 0;
            let end = node.nodeValue.length;
            if (node === range.startContainer && range.startContainer.nodeType === 3) {
                start = range.startOffset;
            }
            if (node === range.endContainer && range.endContainer.nodeType === 3) {
                end = range.endOffset;
            }
            if (end > start) {
                parts.push({ node: node, start: start, end: end });
            }
        }
        return parts;
    }

    function getSelectionParts(editor) {
        let range = editor.selection.getRng();
        if (range.collapsed) {
            // Nothing selected: operate on the whole field.
            range = editor.getDoc().createRange();
            range.selectNodeContents(editor.getBody());
        }
        const parts = collectTextParts(editor, range);
        const text = parts
            .map(function (p) {
                return p.node.nodeValue.slice(p.start, p.end);
            })
            .join("");
        return { parts: parts, text: text };
    }

    function applyReplacement(editor, info, result) {
        const parts = info.parts;
        if (!parts.length) {
            return;
        }
        editor.undoManager.transact(function () {
            parts.forEach(function (p, idx) {
                const value = p.node.nodeValue;
                const before = value.slice(0, p.start);
                const after = value.slice(p.end);
                // The full result goes into the first text node; the remaining
                // selected text nodes are emptied. Non-text nodes are untouched.
                const replacement = idx === 0 ? result : "";
                p.node.nodeValue = before + replacement + after;
            });
        });
        editor.fire("change");
        if (editor.save) {
            editor.save();
        }
        editor.setDirty(true);
    }

    function insertAtCursor(editor, result) {
        editor.focus();
        editor.undoManager.transact(function () {
            editor.insertContent(textToHtml(result));
        });
        editor.fire("change");
        if (editor.save) {
            editor.save();
        }
        editor.setDirty(true);
    }

    /* ---- UI ---- */

    function closeMenu(bar) {
        const menu = bar.querySelector(".aitools-hmw-menu");
        if (menu) {
            menu.hidden = true;
        }
        removeInputRow(bar);
    }

    function removeInputRow(bar) {
        const row = bar.querySelector(".aitools-hmw-input-row");
        if (row) {
            row.parentNode.removeChild(row);
        }
    }

    function setStatus(bar, kind, message) {
        const status = bar.querySelector(".aitools-hmw-status");
        if (!status) {
            return;
        }
        status.className = "aitools-hmw-status aitools-hmw-status--" + kind;
        if (kind === "loading") {
            status.innerHTML =
                '<span class="aitools-hmw-spinner" aria-hidden="true"></span>' +
                "<span>" + escapeHtml(message) + "</span>";
        } else {
            status.textContent = message;
        }
        status.hidden = false;
    }

    function clearStatus(bar) {
        const status = bar.querySelector(".aitools-hmw-status");
        if (status) {
            status.hidden = true;
            status.textContent = "";
        }
    }

    function setBusy(bar, busy) {
        bar.querySelectorAll("button, input").forEach(function (el) {
            el.disabled = busy;
        });
    }

    function runOperation(op, editor, bar, inputValue) {
        const payload = { operation: op.id };
        let info = null;

        if (op.needsInput) {
            const topic = (inputValue || "").trim();
            if (!topic) {
                setStatus(bar, "error", L.noText || "Enter some text first.");
                return;
            }
            payload.topic = topic;
        } else {
            if (!editor) {
                setStatus(bar, "error", L.error || "Editor not ready.");
                return;
            }
            info = getSelectionParts(editor);
            if (!info.text.trim()) {
                setStatus(bar, "error", L.noText || "Select some text first.");
                return;
            }
            payload.text = info.text;
        }

        setBusy(bar, true);
        setStatus(bar, "loading", L.loading || "Generating...");

        fetch(CONFIG.endpoint, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                Accept: "application/json",
                "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
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
                const result = (data && data.result) || "";
                if (op.needsInput) {
                    insertAtCursor(editor, result);
                } else {
                    applyReplacement(editor, info, result);
                }
                setBusy(bar, false);
                clearStatus(bar);
                closeMenu(bar);
            })
            .catch(function (err) {
                setBusy(bar, false);
                setStatus(bar, "error", (err && err.message) || L.error);
            });
    }

    function showInputRow(op, editor, bar) {
        removeInputRow(bar);
        clearStatus(bar);
        const row = document.createElement("div");
        row.className = "aitools-hmw-input-row";

        const input = document.createElement("input");
        input.type = "text";
        input.className = "aitools-hmw-input";
        input.placeholder = L.draftPlaceholder || "";

        const send = document.createElement("button");
        send.type = "button";
        send.className = "aitools-hmw-send";
        send.textContent = L.send || "Send";

        function doSend() {
            runOperation(op, editor, bar, input.value);
        }
        send.addEventListener("click", doSend);
        input.addEventListener("keydown", function (e) {
            if (e.key === "Enter") {
                e.preventDefault();
                doSend();
            }
        });

        row.appendChild(input);
        row.appendChild(send);
        bar.appendChild(row);
        input.focus();
    }

    function onOperation(op, editor, bar) {
        clearStatus(bar);
        const menu = bar.querySelector(".aitools-hmw-menu");
        if (menu) {
            menu.hidden = true;
        }
        if (op.needsInput) {
            showInputRow(op, editor, bar);
        } else {
            runOperation(op, editor, bar, null);
        }
    }

    function attachBar(editor) {
        if (!editor || editor.__aitoolsHmwAttached) {
            return;
        }
        // Inline editors (Mosaic rich-text tiles) have no iframe container and
        // are only present in the Mosaic editor; only wire them up when the
        // viewlet signalled Mosaic is installed. Iframe editors (classic edit
        // forms) keep their existing placement.
        let anchor;
        if (editor.inline) {
            if (!CONFIG.mosaicInline) {
                return;
            }
            anchor = editor.getElement && editor.getElement();
        } else {
            anchor = editor.getContainer && editor.getContainer();
        }
        if (!anchor || !anchor.parentNode) {
            return;
        }
        editor.__aitoolsHmwAttached = true;

        const bar = document.createElement("div");
        bar.className = "aitools-hmw";

        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "aitools-hmw-btn";
        btn.innerHTML =
            SPARKLES + "<span>" + escapeHtml(L.button || "Help me write") + "</span>";

        const menu = document.createElement("div");
        menu.className = "aitools-hmw-menu";
        menu.hidden = true;
        OPERATIONS.forEach(function (op) {
            const item = document.createElement("button");
            item.type = "button";
            item.className = "aitools-hmw-item";
            item.textContent = op.label;
            item.addEventListener("click", function () {
                onOperation(op, editor, bar);
            });
            menu.appendChild(item);
        });

        btn.addEventListener("click", function () {
            const hidden = menu.hidden;
            removeInputRow(bar);
            clearStatus(bar);
            menu.hidden = !hidden;
        });

        const status = document.createElement("div");
        status.className = "aitools-hmw-status";
        status.hidden = true;

        bar.appendChild(btn);
        bar.appendChild(menu);
        bar.appendChild(status);

        if (editor.inline) {
            // Inline (Mosaic tile) editors show a floating toolbar docked
            // against the *top* edge of the editable element (appended to
            // <body> with a high z-index), so a bar placed above it gets
            // covered. Drop ours into the tile's own control bar
            // (`.mosaic-tile-control.mosaic-tile-buttons`) as its first child,
            // which sits clear of the floating toolbar. Fall back to placing
            // it below the editable if that control isn't present.
            bar.classList.add("aitools-hmw--inline");
            const tile = anchor.closest(".mosaic-tile");
            const buttons =
                tile &&
                tile.querySelector(".mosaic-tile-control.mosaic-tile-buttons");
            if (buttons) {
                buttons.insertBefore(bar, buttons.firstChild);
            } else {
                anchor.parentNode.insertBefore(bar, anchor.nextSibling);
            }
        } else {
            anchor.parentNode.insertBefore(bar, anchor);
        }

        // Drop our marker (and the bar) if the editor is torn down.
        editor.on("remove", function () {
            editor.__aitoolsHmwAttached = false;
            if (bar.parentNode) {
                bar.parentNode.removeChild(bar);
            }
        });
    }

    function onEditorReady(editor) {
        if (!editor) {
            return;
        }
        if (editor.initialized) {
            attachBar(editor);
        } else {
            editor.on("init", function () {
                attachBar(editor);
            });
        }
    }

    function hookTinyMCE(tinymce) {
        (tinymce.editors || []).forEach(onEditorReady);
        tinymce.on("AddEditor", function (e) {
            onEditorReady(e.editor);
        });

        document.addEventListener("click", function (e) {
            document.querySelectorAll(".aitools-hmw").forEach(function (bar) {
                if (!bar.contains(e.target)) {
                    const menu = bar.querySelector(".aitools-hmw-menu");
                    if (menu && !menu.hidden) {
                        menu.hidden = true;
                    }
                }
            });
        });
    }

    function whenTinyMCE(cb) {
        if (window.tinymce) {
            cb(window.tinymce);
            return;
        }
        let tries = 0;
        const timer = setInterval(function () {
            tries += 1;
            if (window.tinymce) {
                clearInterval(timer);
                cb(window.tinymce);
            } else if (tries > 150) {
                // ~30s: no TinyMCE on this page, give up quietly.
                clearInterval(timer);
            }
        }, 200);
    }

    whenTinyMCE(hookTinyMCE);
}

export default Base.extend({
    name: "aitools-help-me-write",
    trigger: ".pat-aitools-help-me-write",
    parser: "mockup",
    defaults: {
        endpoint: "",
        operations: [],
        labels: {},
    },
    init: function () {
        if (hooked) {
            return;
        }
        hooked = true;
        setup(this.options);
    },
});
