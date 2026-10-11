/*
 * Tiny, safe Markdown → HTML renderer for assistant replies.
 *
 * The input is model-generated text, so this is XSS-sensitive: we HTML-escape
 * everything FIRST, then layer on a small, closed set of inline constructs
 * (links, bold, italic, inline code) plus line breaks. Link hrefs are scheme-
 * checked, so only http(s)/mailto and site-relative targets become anchors;
 * anything else is left as plain text. No raw HTML from the model is ever
 * emitted.
 */

const SAFE_HREF = /^(https?:\/\/|mailto:|\/|#)/i;

function escapeHtml(text) {
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

// A url that has already been HTML-escaped is safe to place in an attribute
// (quotes are escaped); we only need to gate the scheme.
function safeHref(url) {
    // `&amp;` in a query string is fine; unescape only for the scheme test.
    const probe = url.replace(/&amp;/g, "&");
    return SAFE_HREF.test(probe) ? url : null;
}

export function renderMarkdown(text) {
    let html = escapeHtml(text || "");

    // Inline code: `code` (do this before emphasis so * inside isn't touched).
    html = html.replace(/`([^`]+)`/g, function (_m, code) {
        return "<code>" + code + "</code>";
    });

    // Links: [label](url)
    html = html.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, function (_m, label, url) {
        const href = safeHref(url);
        if (!href) {
            return label;
        }
        return (
            '<a href="' + href + '" target="_blank" rel="noopener noreferrer">' + label + "</a>"
        );
    });

    // Autolink bare http(s) URLs not already inside an anchor.
    html = html.replace(/(^|[\s(])((?:https?:\/\/)[^\s<]+)/g, function (_m, pre, url) {
        return pre + '<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + url + "</a>";
    });

    // Bold then italic (bold first so ** isn't eaten by the * rule).
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");

    // Line breaks.
    html = html.replace(/\n/g, "<br>");

    return html;
}
