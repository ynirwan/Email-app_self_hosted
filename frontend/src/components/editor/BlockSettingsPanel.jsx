// frontend/src/components/editor/BlockSettingsPanel.jsx
//
// Right-hand panel shown when a block is selected.
//
// Shows:
//   - Block type label + close button
//   - Duplicate / Delete actions
//   - Block-type-specific content fields:
//       image   → URL input + alt text
//       button  → href + label
//       spacer  → height (px)
//       other non-richText → raw HTML textarea
//   - richText blocks (text / header) are edited inline via Tiptap;
//     the settings panel only shows actions for them.

import { Trash2, Copy, X } from "lucide-react";
import { getBlockDefinition } from "./blockDefinitions";

// ── Helpers ──────────────────────────────────────────────────────────────────

function extractImgSrc(html = "") {
  const m = html.match(/src="([^"]*)"/);
  return m ? m[1] : "";
}

function extractImgAlt(html = "") {
  const m = html.match(/alt="([^"]*)"/);
  return m ? m[1] : "";
}

function extractHref(html = "") {
  const m = html.match(/href="([^"]*)"/);
  return m ? m[1] : "#";
}

function extractButtonText(html = "") {
  // Matches the visible text inside the <a> tag
  const m = html.match(/<a[^>]*>([^<]+)<\/a>/);
  return m ? m[1] : "Click me";
}

function extractSpacerHeight(html = "") {
  const m = html.match(/height:(\d+)px/);
  return m ? m[1] : "24";
}

// ── Shared field components ───────────────────────────────────────────────────

function Label({ children }) {
  return (
    <label className="block text-[11px] font-medium text-gray-500 mb-1">
      {children}
    </label>
  );
}

function TextInput({ value, onChange, placeholder, type = "text" }) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full text-xs border border-gray-200 rounded-md px-2 py-1.5
        focus:outline-none focus:ring-1 focus:ring-blue-500"
    />
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function BlockSettingsPanel({
  block,
  onChange,
  onDelete,
  onDuplicate,
  onClose,
}) {
  // Empty state — no block selected
  if (!block) {
    return (
      <div className="w-64 flex-shrink-0 border-l border-gray-200 bg-gray-50 flex items-center justify-center">
        <p className="text-xs text-gray-400 text-center px-4 leading-relaxed">
          Select a block to&nbsp;see&nbsp;its settings
        </p>
      </div>
    );
  }

  const def = getBlockDefinition(block.type);
  const Icon = def?.icon;
  const isRichText = def?.richText === true;

  return (
    <div className="w-64 flex-shrink-0 border-l border-gray-200 bg-white overflow-y-auto flex flex-col">

      {/* ── Header ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 flex-shrink-0">
        <div className="flex items-center gap-2">
          {Icon && <Icon size={13} className="text-gray-500" />}
          <span className="text-sm font-medium text-gray-700 truncate">
            {def?.name ?? block.type}
          </span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 transition-colors"
          title="Deselect"
        >
          <X size={14} />
        </button>
      </div>

      {/* ── Actions ─────────────────────────────────────────────────── */}
      <div className="px-4 py-3 space-y-1 flex-shrink-0">
        <button
          type="button"
          onClick={onDuplicate}
          className="flex items-center gap-2 w-full px-3 py-2 text-sm text-gray-700
            rounded-md hover:bg-gray-100 transition-colors"
        >
          <Copy size={13} />
          Duplicate block
        </button>
        <button
          type="button"
          onClick={onDelete}
          className="flex items-center gap-2 w-full px-3 py-2 text-sm text-red-600
            rounded-md hover:bg-red-50 transition-colors"
        >
          <Trash2 size={13} />
          Delete block
        </button>
      </div>

      {/* ── Block-type-specific settings ────────────────────────────── */}
      {isRichText ? (
        // richText blocks are edited inline — settings panel only shows actions
        <div className="px-4 py-3 border-t border-gray-100">
          <p className="text-[11px] text-gray-400 leading-relaxed">
            Click the block on the canvas to edit text using the inline toolbar.
          </p>
        </div>
      ) : (
        <BlockFields block={block} onChange={onChange} />
      )}
    </div>
  );
}

// ── Block-type-specific field sections ───────────────────────────────────────

function BlockFields({ block, onChange }) {
  const update = (partial) => onChange({ ...block, ...partial });
  const updateContent = (content) => update({ content });

  // Image block
  if (block.type === "image") {
    return (
      <div className="px-4 py-3 border-t border-gray-100 space-y-3">
        <div>
          <Label>Image URL</Label>
          <TextInput
            type="url"
            value={extractImgSrc(block.content)}
            placeholder="https://example.com/image.png"
            onChange={(url) =>
              updateContent(
                block.content.replace(/src="[^"]*"/, `src="${url}"`)
              )
            }
          />
        </div>
        <div>
          <Label>Alt text</Label>
          <TextInput
            value={extractImgAlt(block.content)}
            placeholder="Describe the image"
            onChange={(alt) =>
              updateContent(
                block.content.replace(/alt="[^"]*"/, `alt="${alt}"`)
              )
            }
          />
        </div>
      </div>
    );
  }

  // Button block
  if (block.type === "button") {
    return (
      <div className="px-4 py-3 border-t border-gray-100 space-y-3">
        <div>
          <Label>Button label</Label>
          <TextInput
            value={extractButtonText(block.content)}
            placeholder="Click me"
            onChange={(text) =>
              updateContent(
                block.content.replace(/<a([^>]*)>[^<]+<\/a>/, `<a$1>${text}</a>`)
              )
            }
          />
        </div>
        <div>
          <Label>Link URL</Label>
          <TextInput
            type="url"
            value={extractHref(block.content)}
            placeholder="https://"
            onChange={(url) =>
              updateContent(
                block.content.replace(/href="[^"]*"/, `href="${url}"`)
              )
            }
          />
        </div>
      </div>
    );
  }

  // Spacer block — height control
  if (block.type === "spacer") {
    return (
      <div className="px-4 py-3 border-t border-gray-100">
        <Label>Height (px)</Label>
        <TextInput
          type="number"
          value={extractSpacerHeight(block.content)}
          placeholder="24"
          onChange={(h) => {
            const px = Math.max(4, parseInt(h, 10) || 24);
            updateContent(
              `<div style="height:${px}px;line-height:${px}px;">&nbsp;</div>`
            );
          }}
        />
      </div>
    );
  }

  // Generic: raw HTML textarea for any other non-richText block
  return (
    <div className="px-4 py-3 border-t border-gray-100">
      <Label>Content HTML</Label>
      <textarea
        value={block.content || ""}
        onChange={(e) => updateContent(e.target.value)}
        className="w-full text-[11px] font-mono border border-gray-200 rounded-md
          p-2 resize-none focus:outline-none focus:ring-1 focus:ring-blue-500 h-36"
        spellCheck={false}
      />
    </div>
  );
}
