/*
 * Shared helpers for the edit-form AI tools: locating Plone widget fields,
 * filling them only when empty, driving the select2 tags widget, and reading
 * the current content body text out of the form.
 */

export const SPARKLES =
    '<svg class="aitools-tool-stars" viewBox="0 0 24 24" width="16" ' +
    'height="16" aria-hidden="true" focusable="false">' +
    '<path fill="currentColor" d="M12 2l1.6 4.6L18 8l-4.4 1.4L12 14l-1.6-4.6' +
    'L6 8l4.4-1.4L12 2zm6 10l.9 2.6L21 15l-2.1.7L18 18l-.9-2.3L15 15l2.1-.4' +
    'L18 12zM6 13l.8 2.4L9 16l-2.2.7L6 19l-.8-2.3L3 16l2.2-.6L6 13z"/></svg>';

export function escapeHtml(text) {
    const div = document.createElement("div");
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
}

export function stripHtml(html) {
    const div = document.createElement("div");
    div.innerHTML = html || "";
    return (div.textContent || div.innerText || "").trim();
}

// Dexterity metadata behaviors that carry the title / description / tags
// fields; the widget name is prefixed with whichever one the form uses.
const BEHAVIORS = ["IDublinCore", "IBasic", "ICategorization", "IShortName"];

// Find the first form control whose name/id targets `.suffix` (e.g. "title",
// "subjects") within `form`, trying the behavior-prefixed names first and
// falling back to any widget whose name ends with the suffix.
export function findField(form, suffix) {
    const selectors = [
        "#form-widgets-" + suffix,
        '[name="form.widgets.' + suffix + '"]',
    ];
    BEHAVIORS.forEach(function (b) {
        selectors.push("#form-widgets-" + b + "-" + suffix);
        selectors.push('[name="form.widgets.' + b + "." + suffix + '"]');
    });
    selectors.push('[name$=".' + suffix + '"]');
    for (let i = 0; i < selectors.length; i++) {
        const el = form.querySelector(selectors[i]);
        if (el) {
            return el;
        }
    }
    return null;
}

export function setTextField(el, value) {
    // Only fill when empty; never clobber an existing value.
    if (!el || !value || (el.value || "").trim() !== "") {
        return false;
    }
    el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
}

// Return the jQuery select2 (v3, "pat-select2") instance bound to `el`, or
// null when select2 is not initialised on it. We use the page's global jQuery
// (not a bundled copy) so we share Plone's select2 plugin instance.
function select2Of(el) {
    const $ = window.jQuery;
    if (!$ || typeof $.fn !== "object" || !$.fn.select2) {
        return null;
    }
    const $el = $(el);
    return $el.data("select2") ? $el : null;
}

// The separator select2 uses to serialise tokens into the hidden input
// (Plone's Keywords widget configures ";"); default to ";".
function separatorFor(el) {
    try {
        const cfg = JSON.parse(el.getAttribute("data-pat-select2") || "{}");
        if (cfg && cfg.separator) {
            return cfg.separator;
        }
    } catch (e) {
        /* fall through */
    }
    return ";";
}

// Is the tags widget currently empty? Prefer select2's own state (the hidden
// input keeps a stale value), then the rendered choices, then the raw value.
function tagsAreEmpty(el) {
    const $el = select2Of(el);
    if ($el) {
        try {
            const data = $el.select2("data");
            return !(data && data.length);
        } catch (e) {
            /* fall through */
        }
    }
    const container = el.previousElementSibling;
    if (container && container.querySelector) {
        const chosen = container.querySelector(".select2-search-choice");
        if (chosen) {
            return false;
        }
    }
    return (el.value || "").trim() === "";
}

export function setTags(el, tags) {
    if (!el || !tags || !tags.length || !tagsAreEmpty(el)) {
        return false;
    }
    const $el = select2Of(el);
    if ($el) {
        // Drive select2 through its API so the rendered choices and the hidden
        // input value stay in sync. `data` accepts {id, text} objects and works
        // for free-tagging (allowNewItems) keyword widgets.
        try {
            $el.select2(
                "data",
                tags.map(function (t) {
                    return { id: t, text: t };
                })
            );
            $el.trigger("change");
            return true;
        } catch (e) {
            /* fall back to writing the raw input below */
        }
    }
    // No select2 yet (or a plain token input): store the ";"-separated tokens.
    el.value = tags.join(separatorFor(el));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
}

// Collect the current text of the item being edited from the form: the title,
// plus every rich-text body (read from TinyMCE when live, else the textarea).
export function getBodyText(form) {
    const parts = [];

    const title = findField(form, "title");
    if (title && (title.value || "").trim()) {
        parts.push(title.value.trim());
    }

    const editors = (window.tinymce && window.tinymce.editors) || [];
    const covered = new Set();
    editors.forEach(function (ed) {
        const el = ed.getElement && ed.getElement();
        if (form !== document && el && !form.contains(el)) {
            return; // editor belongs to another form on the page
        }
        const text = (ed.getContent({ format: "text" }) || "").trim();
        if (text) {
            parts.push(text);
        }
        if (el && el.name) {
            covered.add(el.name);
        }
    });

    // Rich-text fields without a live editor: strip the textarea's HTML.
    form.querySelectorAll("textarea").forEach(function (ta) {
        if (ta.name && covered.has(ta.name)) {
            return;
        }
        if (!/\.text$|richtext/i.test(ta.name || ta.id || "")) {
            return;
        }
        const text = stripHtml(ta.value);
        if (text) {
            parts.push(text);
        }
    });

    return parts.join("\n\n").trim();
}
