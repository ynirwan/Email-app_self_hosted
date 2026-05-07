// frontend/src/utils/templateRender.js
//
// Single source of truth for turning a template document (any of our 4
// historical shapes) into a renderable HTML string. Used by the templates
// gallery, the preview modal, and any other place that needs to display
// a template *without* sending it.
//
// Modes we handle, in order of precedence:
//   1. content_json.mode === 'html'        → content_json.content
//   2. content_json.mode === 'drag-drop'   → joined block.content
//   3. content_json.mode === 'visual'      → content_json.content
//   4. legacy template.html                → as-is
//   5. legacy Unlayer (content_json.body.rows) → extracted HTML chunks
//
// This is *display* HTML only. Personalization ({{first_name}} etc.) is
// intentionally left untouched — that happens server-side via TemplateRenderer
// at send time. For previews we render the placeholders verbatim.

/**
 * @typedef {Object} TemplateDoc
 * @property {string} [name]
 * @property {string} [html]
 * @property {Object} [content_json]
 */

/**
 * Returns a renderable HTML string for a template, or "" if nothing is found.
 * Never throws — returns "" on malformed input so callers can render an
 * empty-state placeholder instead of breaking.
 *
 * @param {TemplateDoc | null | undefined} template
 * @returns {string}
 */
export function getTemplateHtml(template) {
  if (!template) return "";

  const cj = template.content_json || {};

  if (cj.mode === "html" && typeof cj.content === "string") {
    return cj.content;
  }

  if (cj.mode === "drag-drop" && Array.isArray(cj.blocks)) {
    return cj.blocks.map((b) => (b && b.content) || "").join("\n");
  }

  if (cj.mode === "visual" && typeof cj.content === "string") {
    return cj.content;
  }

  if (typeof template.html === "string" && template.html.trim()) {
    return template.html;
  }

  // Legacy Unlayer shape — content_json.body.rows[].columns[].contents[]
  if (cj.body && Array.isArray(cj.body.rows)) {
    const parts = [];
    for (const row of cj.body.rows) {
      for (const col of row.columns || []) {
        for (const c of col.contents || []) {
          if (c && c.type === "html" && c.values && c.values.html) {
            parts.push(c.values.html);
          }
        }
      }
    }
    return parts.join("\n");
  }

  return "";
}

/**
 * Returns a short human label for the template's editor mode.
 * Defaults to "legacy" for templates that predate the mode field.
 *
 * @param {TemplateDoc | null | undefined} template
 * @returns {"visual"|"html"|"drag-drop"|"legacy"}
 */
export function getTemplateMode(template) {
  const m = template && template.content_json && template.content_json.mode;
  if (m === "visual" || m === "html" || m === "drag-drop") return m;
  return "legacy";
}

/**
 * Wraps a fragment of email HTML in a minimal full-document shell so it
 * renders sensibly inside an <iframe srcdoc>. We force a white background
 * and disable pointer events so the iframe is purely decorative.
 *
 * @param {string} bodyHtml
 * @returns {string}
 */
export function buildThumbnailSrcDoc(bodyHtml) {
  const safe = bodyHtml || "";
  return `<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=600, initial-scale=1" />
<style>
  html, body {
    margin: 0;
    padding: 0;
    background: #ffffff;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #1f2937;
    -webkit-font-smoothing: antialiased;
  }
  body { padding: 12px; pointer-events: none; }
  img { max-width: 100%; height: auto; }
  a { color: inherit; text-decoration: none; pointer-events: none; }
  /* Neutralise any fixed/absolute positioning that would escape the frame */
  * { position: static !important; }
</style>
</head>
<body>${safe}</body>
</html>`;
}