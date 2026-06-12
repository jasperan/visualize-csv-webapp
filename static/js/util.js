/**
 * Shared DOM/HTML helpers used across dashboard modules.
 */
const Util = {
    /** Escape text for safe interpolation into innerHTML. */
    escapeHtml(text) {
        const el = document.createElement('span');
        el.textContent = text == null ? '' : text;
        return el.innerHTML;
    },

    /** Escape text for safe interpolation into a double-quoted HTML attribute. */
    escapeAttr(text) {
        return String(text == null ? '' : text)
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    },
};

// Convenience global so modules can call escapeHtml(...) directly.
const escapeHtml = Util.escapeHtml;
