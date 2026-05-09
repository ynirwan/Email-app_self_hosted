// frontend/src/components/editor/blockDefinitions.js
//
// Block type catalog. The `id` here matches `block.type` in stored
// content_json — DO NOT rename existing ids without coordinating with
// backend/routes/templates.py:TemplateRenderer.render_drag_drop_template,
// which switches on these strings.
//
// `defaultContent` is what gets dropped into block.content when a user
// drags a fresh block onto the canvas. It must be email-safe HTML
// (table-based for buttons/columns, inline styles, no class hooks).
import {
  Type as TextIcon,
  Image,
  Square,
  Grid,
  Layout,
  Type,
  Link,
} from "lucide-react";

/**
 * @typedef {Object} BlockTypeDefinition
 * @property {string} id           Stable identifier — matches block.type
 * @property {string} name         Human-readable label
 * @property {React.ComponentType} icon
 * @property {string} defaultContent  Initial HTML for new blocks
 * @property {"content"|"media"|"interactive"|"layout"|"compliance"} category
 * @property {boolean} [richText]   true → block.content is editable as rich text
 *                                  (Tiptap renders an inline editor for it)
 */

/** @type {BlockTypeDefinition[]} */
export const EMAIL_BLOCK_TYPES = [
  {
    id: "text",
    name: "Text",
    icon: TextIcon,
    defaultContent: "<p>Click to edit text…</p>",
    category: "content",
    richText: true,
  },
  {
    id: "header",
    name: "Heading",
    icon: Type,
    defaultContent:
      '<h1 style="color:#1f2937;font-size:24px;margin:0 0 16px 0;">Your heading here</h1>',
    category: "content",
    richText: true,
  },
  {
    id: "image",
    name: "Image",
    icon: Image,
    defaultContent:
      '<img src="https://via.placeholder.com/600x300/e5e7eb/9ca3af?text=Click+to+set+image+URL" alt="" width="600" style="max-width:100%;height:auto;display:block;margin:0 auto;border:0;" />',
    category: "media",
    richText: false,
  },
  {
    id: "button",
    name: "Button",
    icon: Square,
    defaultContent:
      '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 auto;"><tr><td style="background-color:#2563eb;border-radius:6px;text-align:center;"><a href="#" style="color:#ffffff;text-decoration:none;font-weight:600;display:block;padding:12px 24px;font-family:Arial,sans-serif;">Click me</a></td></tr></table>',
    category: "interactive",
    richText: false,
  },
  {
    id: "divider",
    name: "Divider",
    icon: Grid,
    defaultContent:
      '<hr style="border:none;border-top:1px solid #e5e7eb;margin:0;" />',
    category: "layout",
    richText: false,
  },
  {
    id: "spacer",
    name: "Spacer",
    icon: Square,
    defaultContent: '<div style="height:24px;line-height:24px;">&nbsp;</div>',
    category: "layout",
    richText: false,
  },
  {
    id: "columns",
    name: "2 Columns",
    icon: Layout,
    defaultContent:
      '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td width="50%" valign="top" style="padding:0 8px 0 0;"><p style="margin:0;">Left column</p></td><td width="50%" valign="top" style="padding:0 0 0 8px;"><p style="margin:0;">Right column</p></td></tr></table>',
    category: "layout",
    richText: false,
  },
  {
    id: "unsubscribe",
    name: "Unsubscribe",
    icon: Link,
    defaultContent:
      '<p style="text-align:center;font-size:12px;color:#9ca3af;margin:0;font-family:Arial,sans-serif;"><a href="{{unsubscribe_url}}" style="color:#9ca3af;">Unsubscribe</a> &nbsp;|&nbsp; <a href="#" style="color:#9ca3af;">Update preferences</a></p>',
    category: "compliance",
    richText: false,
  },
];

/**
 * Look up a block definition by its `id`. Returns `undefined` for unknown
 * types (legacy block types from old templates) — callers should fall
 * back to rendering raw content.
 */
export function getBlockDefinition(typeId) {
  return EMAIL_BLOCK_TYPES.find((b) => b.id === typeId);
}

/** Group blocks by category for UI rendering. Order is the source order. */
export function groupBlocksByCategory(types = EMAIL_BLOCK_TYPES) {
  const order = [];
  const groups = {};
  for (const t of types) {
    if (!groups[t.category]) {
      groups[t.category] = [];
      order.push(t.category);
    }
    groups[t.category].push(t);
  }
  return order.map((cat) => ({ category: cat, items: groups[cat] }));
}

const CATEGORY_LABELS = {
  content:     "Content",
  media:       "Media",
  interactive: "Interactive",
  layout:      "Layout",
  compliance:  "Compliance",
};

export function getCategoryLabel(category) {
  return CATEGORY_LABELS[category] || category;
}
