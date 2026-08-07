/*
 * "Help me write" — classic-UI TinyMCE integration (Patternslib pattern).
 *
 * Adds a "Help me write" button above every TinyMCE rich-text editor on
 * edit/add forms. The button opens a menu of writing operations, and each one
 * carries the `mode` that says what to send and how to apply the answer. The
 * operations work on the selection, or on the whole field when nothing is
 * selected.
 *
 * - "draft" shows an input + Send and inserts the result at the cursor.
 *
 * - "correct" (grammar) only fixes the wording, so it must not disturb the
 *   markup. The selection is split into the text nodes it covers and sent as
 *   `segments`; the backend answers with `corrections`, only the segments it
 *   changed, each keyed by its index. Every correction is written straight into
 *   the text node it came from, so inline formatting keeps its own text and
 *   non-text nodes (images, etc.) are untouched. Sending one concatenated string
 *   instead would leave no way to put the answer back without emptying the
 *   inline elements the selection spanned.
 *
 * - "rewrite" (the tone changes) is *supposed* to restructure the passage —
 *   resplitting paragraphs, moving emphasis — so per-node patching is the wrong
 *   tool: it gets the selection as `html`, and the fragment it returns replaces
 *   the selection through TinyMCE, which parses and sanitizes it on the way in.
 *
 * Editors are discovered through the global TinyMCE registry
 * (`window.tinymce.editors` + the AddEditor/init events) rather than by
 * scanning the DOM, so this works regardless of the editor's markup.
 *
 * In Mosaic the bar lives inside the tile's own control bar, which Mosaic
 * rebuilds as the tile selection moves — silently taking our bar with it,
 * without tearing the editor down (so TinyMCE fires no `remove`). The bar is
 * therefore never assumed to still be there: `ensureBar` re-creates it whenever
 * it has left the document. It is driven by the editor's own `focus` event and
 * by Mosaic's tile selection, which is observed through the
 * `mosaic-selected-tile` class — Mosaic emits no event of its own when the
 * selection moves, so that class is the only signal there is.
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

    function looksLikeHtml(text) {
        return /<[a-z][^>]*>/i.test(text);
    }

    // Fallback for a model that ignored the "return an HTML fragment"
    // instruction and sent plain text: keep its paragraph breaks at least.
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

    // Text that is quoted verbatim must not be "corrected", so skip it here
    // rather than asking the model to leave it alone — the walker knows which
    // element a text node lives in, the model only sees the text.
    const VERBATIM = "code,pre,kbd,samp,script,style";

    function isVerbatim(node) {
        const parent = node.parentNode;
        return !!(parent && parent.closest && parent.closest(VERBATIM));
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
            if (isVerbatim(node)) {
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

    function partText(p) {
        return p.node.nodeValue.slice(p.start, p.end);
    }

    function getSelectionParts(editor) {
        let range = editor.selection.getRng();
        if (range.collapsed) {
            // Nothing selected: operate on the whole field.
            range = editor.getDoc().createRange();
            range.selectNodeContents(editor.getBody());
        }
        const parts = collectTextParts(editor, range);
        return { parts: parts, segments: parts.map(partText) };
    }

    /* Write the changed segments back, each into its own text node.
     *
     * `corrections` is the backend's list of {id, text}, where `id` indexes
     * info.parts. Segments the model left alone are simply absent, so their
     * nodes are never written to at all. Each node appears in `parts` at most
     * once (the walker yields it once), so the clipped offsets stay valid.
     *
     * Returns the number of segments actually changed. */
    function applyCorrections(editor, info, corrections) {
        const parts = info.parts;
        const pending = [];
        (corrections || []).forEach(function (correction) {
            const p = correction && parts[correction.id];
            if (p && typeof correction.text === "string") {
                pending.push({ part: p, text: correction.text });
            }
        });
        if (!pending.length) {
            return 0;
        }
        editor.undoManager.transact(function () {
            pending.forEach(function (item) {
                const p = item.part;
                const value = p.node.nodeValue;
                p.node.nodeValue =
                    value.slice(0, p.start) + item.text + value.slice(p.end);
            });
        });
        editor.fire("change");
        if (editor.save) {
            editor.save();
        }
        editor.setDirty(true);
        return pending.length;
    }

    /* ---- rewrite: replace the selection with the returned fragment ---- */

    /* Grab what a rewrite should work on.
     *
     * With nothing selected the whole field is the target. With a real selection
     * we also take a bookmark: the answer arrives after an await, by which time
     * focus has been on our button and the selection may be gone, so it has to
     * be restored before we can replace it. */
    function getRewriteTarget(editor) {
        if (editor.selection.getRng().collapsed) {
            return {
                whole: true,
                html: editor.getContent({ format: "html" }),
                // For "is there anything to work on?" — an empty field still
                // serializes to something like "<p></p>".
                text: editor.getBody().textContent || "",
            };
        }
        return {
            whole: false,
            html: editor.selection.getContent({ format: "html" }),
            text: editor.selection.getContent({ format: "text" }) || "",
            bookmark: editor.selection.getBookmark(2, true),
        };
    }

    function applyRewrite(editor, target, html) {
        if (!html) {
            return 0;
        }
        editor.undoManager.transact(function () {
            if (target.whole) {
                editor.setContent(html);
            } else {
                editor.focus();
                editor.selection.moveToBookmark(target.bookmark);
                editor.selection.setContent(html);
            }
        });
        editor.fire("change");
        if (editor.save) {
            editor.save();
        }
        editor.setDirty(true);
        return 1;
    }

    function insertAtCursor(editor, result) {
        editor.focus();
        editor.undoManager.transact(function () {
            // A draft arrives as an HTML fragment — headings, lists, tables —
            // so insert it as-is and let TinyMCE parse and sanitize it.
            editor.insertContent(
                looksLikeHtml(result) ? result : textToHtml(result)
            );
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

        if (op.mode === "draft") {
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
            if (op.mode === "correct") {
                info = getSelectionParts(editor);
                if (!info.segments.join("").trim()) {
                    setStatus(bar, "error", L.noText || "Select some text first.");
                    return;
                }
                payload.segments = info.segments;
            } else {
                info = getRewriteTarget(editor);
                if (!info.text.trim()) {
                    setStatus(bar, "error", L.noText || "Select some text first.");
                    return;
                }
                payload.html = info.html;
            }
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
                let changed = 1;
                if (op.mode === "draft") {
                    insertAtCursor(editor, (data && data.result) || "");
                } else if (op.mode === "correct") {
                    changed = applyCorrections(editor, info, data && data.corrections);
                } else {
                    changed = applyRewrite(editor, info, (data && data.result) || "");
                }
                setBusy(bar, false);
                if (changed) {
                    clearStatus(bar);
                    closeMenu(bar);
                } else {
                    // The model read the text and had nothing to change; say so
                    // instead of silently looking like the button did nothing.
                    setStatus(bar, "info", L.noChanges || "No changes suggested.");
                }
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
        if (op.mode === "draft") {
            showInputRow(op, editor, bar);
        } else {
            runOperation(op, editor, bar, null);
        }
    }

    /* The bar built for this editor, if it is still in the document.
     *
     * Mosaic rebuilds a tile's controls whenever the selection moves, which
     * takes our bar down with them — but it does *not* tear the editor down, so
     * TinyMCE fires no "remove" and a boolean "already attached" flag would
     * stay true forever and the bar would never come back. Asking the node
     * itself cannot go stale that way. */
    function barFor(editor) {
        const bar = editor.__aitoolsHmwBar;
        return bar && bar.isConnected ? bar : null;
    }

    function ensureBar(editor) {
        if (!editor || barFor(editor)) {
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

        editor.__aitoolsHmwBar = bar;
    }

    function removeBar(editor) {
        const bar = editor.__aitoolsHmwBar;
        if (bar && bar.parentNode) {
            bar.parentNode.removeChild(bar);
        }
        editor.__aitoolsHmwBar = null;
    }

    // Re-check every inline editor. ensureBar is a no-op when the bar is
    // already in place, so an extra pass costs nothing; the delayed one is
    // there because Mosaic finishes rebuilding a tile's controls a beat after
    // it marks the tile selected.
    let rescanQueued = false;

    function rescanInlineEditors() {
        if (rescanQueued) {
            return;
        }
        rescanQueued = true;
        const pass = function () {
            const tinymce = window.tinymce;
            (tinymce ? tinymce.editors || [] : []).forEach(function (editor) {
                if (editor.inline) {
                    ensureBar(editor);
                }
            });
        };
        window.requestAnimationFrame(function () {
            rescanQueued = false;
            pass();
        });
        window.setTimeout(pass, 150);
    }

    /* Watch Mosaic's tile selection.
     *
     * Mosaic emits no event when the selection moves — no jQuery custom event,
     * no CustomEvent; the only thing it does is add and remove the
     * `mosaic-selected-tile` class on the `.mosaic-tile`. So that class is what
     * we watch. Filtering on `class` attributes keeps this cheap: they change
     * when the selection moves, not on every keystroke the way the tile's
     * child nodes do. */
    function watchTileSelection() {
        new MutationObserver(function (records) {
            for (let i = 0; i < records.length; i += 1) {
                const target = records[i].target;
                if (target.classList && target.classList.contains("mosaic-tile")) {
                    rescanInlineEditors();
                    return;
                }
            }
        }).observe(document.body, {
            subtree: true,
            attributes: true,
            attributeFilter: ["class"],
        });
    }

    function onEditorReady(editor) {
        if (!editor || editor.__aitoolsHmwHooked) {
            return;
        }
        editor.__aitoolsHmwHooked = true;

        if (editor.initialized) {
            ensureBar(editor);
        } else {
            editor.on("init", function () {
                ensureBar(editor);
            });
        }
        // Clicking into a tile focuses its inline editor, which is the moment
        // Mosaic has finished putting the tile's controls back.
        editor.on("focus", function () {
            ensureBar(editor);
        });
        editor.on("remove", function () {
            editor.__aitoolsHmwHooked = false;
            removeBar(editor);
        });
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

        if (CONFIG.mosaicInline) {
            // Selecting a tile does not always focus its editor (clicking the
            // tile's chrome selects it without entering the text), so watch the
            // selection itself too. This is what makes the bar come back on the
            // second and later clicks, and appear on every rich-text tile
            // rather than only the one that happened to be first.
            watchTileSelection();
        }
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
