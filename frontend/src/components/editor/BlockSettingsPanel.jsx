// frontend/src/components/editor/BlockSettingsPanel.jsx
//
// Right-hand panel shown when a block is selected.
//
// Shows:
//   - Block type label + close button
//   - Duplicate / Delete actions
//   - Block-type-specific content fields:
//       image   → URL input / file upload, width, border-radius, alt text
//       button  → label, href, bg color, text color, border-radius, font size
//       spacer  → height (px)
//       quote   → quote text + author via fields
//       other non-richText → raw HTML textarea
//   - richText blocks (text / header) are edited inline via Tiptap;
//     the settings panel only shows actions for them.

import { useRef } from "react";
import { Trash2, Copy, X } from "lucide-react";
import { getBlockDefinition } from "./blockDefinitions";

// ── Style parsing helpers ─────────────────────────────────────────────

/**
 * Parse a `style="..."` attribute value from the first tag matching tagRegex.
 * Returns an object of { property: value } pairs.
 */
function parseTagStyles(html, tagRegex) {
  const tagMatch = html.match(tagRegex);
  if (!tagMatch) return {};
  const styleMatch = tagMatch[0].match(/style="([^"]*)"/);
  if (!styleMatch) return {};
  const styles = {};
  styleMatch[1].split(";").forEach((part) => {
    const colonIdx = part.indexOf(":");
    if (colonIdx === -1) return;
    const k = part.slice(0, colonIdx).trim();
    const v = part.slice(colonIdx + 1).trim();
    if (k) styles[k] = v;
  });
  return styles;
}

// ── Button value extractors ────────────────────────────────────────────

function extractButtonValues(html) {
  const tdStyles  = parseTagStyles(html, /<td[^>]*style="[^"]*"/);
  const aStyles   = parseTagStyles(html, /<a[^>]*style="[^"]*"/);
  const hrefMatch = html.match(/href="([^"]*)"/);
  const textMatch = html.match(/<a[^>]*>([^<]*)<\/a>/);
  return {
    label:        textMatch ? textMatch[1] : "Click me",
    href:         hrefMatch ? hrefMatch[1] : "#",
    bgColor:      tdStyles["background-color"] || "#2563eb",
    borderRadius: tdStyles["border-radius"] || "6px",
    textColor:    aStyles["color"] || "#ffffff",
    padding:      aStyles["padding"] || "12px 24px",
    fontSize:     aStyles["font-size"] || "14px",
  };
}

function buildButtonHtml({ label, href, bgColor, textColor, borderRadius, fontSize, padding }) {
  return (
    `<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 auto;">` +
    `<tr><td style="background-color:${bgColor};border-radius:${borderRadius};text-align:center;">` +
    `<a href="${href}" style="color:${textColor};text-decoration:none;font-weight:600;display:block;` +
    `padding:${padding};font-family:Arial,sans-serif;font-size:${fontSize};">${label}</a>` +
    `</td></tr></table>`
  );
}

// ── Image value extractors ─────────────────────────────────────────────

function extractImageValues(html) {
  const imgMatch = html.match(/<img[^>]*>/);
  if (!imgMatch) return { src: "", alt: "", width: "600", borderRadius: "0" };
  const tag = imgMatch[0];
  const srcMatch    = tag.match(/src="([^"]*)"/);
  const altMatch    = tag.match(/alt="([^"]*)"/);
  const widthMatch  = tag.match(/width="(\d+)"/);
  const imgStyles   = parseTagStyles(html, /<img[^>]*style="[^"]*"/);
  return {
    src:          srcMatch    ? srcMatch[1]   : "",
    alt:          altMatch    ? altMatch[1]   : "",
    width:        widthMatch  ? widthMatch[1] : "600",
    borderRadius: imgStyles["border-radius"] || "0",
  };
}

function buildImageHtml({ src, alt, width, borderRadius }) {
  const radiusStyle =
    borderRadius && borderRadius !== "0" && borderRadius !== "0px"
      ? `border-radius:${borderRadius};`
      : "";
  return (
    `<img src="${src}" alt="${alt}" width="${width}" ` +
    `style="max-width:100%;height:auto;display:block;margin:0 auto;border:0;${radiusStyle}" />`
  );
}

// ── Spacer helpers ────────────────────────────────────────────────────

function extractSpacerHeight(html = "") {
  const m = html.match(/height:(\d+)px/);
  return m ? m[1] : "24";
}

// ── Quote helpers ─────────────────────────────────────────────────────

function extractQuoteText(html = "") {
  const m = html.match(/<p[^>]*>"([^"]*)"<\/p>/);
  return m ? m[1] : "Your quote here.";
}

function extractQuoteAuthor(html = "") {
  const m = html.match(/<cite[^>]*>—\s*([^<]+)<\/cite>/);
  return m ? m[1].trim() : "Author Name";
}

function extractQuoteBorderColor(html = "") {
  const m = html.match(/border-left:[^;]*?([#][0-9a-fA-F]{3,6})/);
  return m ? m[1] : "#2563eb";
}

function buildQuoteHtml({ text, author, accentColor }) {
  return (
    `<blockquote style="margin:0;padding:16px 20px;border-left:4px solid ${accentColor};background:#f8fafc;border-radius:4px;">` +
    `<p style="font-size:16px;font-style:italic;color:#374151;margin:0 0 10px 0;">"${text}"</p>` +
    `<cite style="font-size:13px;color:#6b7280;font-style:normal;">— ${author}</cite>` +
    `</blockquote>`
  );
}

// ── Shared field components ────────────────────────────────────────────

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

function ColorInput({ value, onChange }) {
  return (
    <div className="flex items-center gap-1.5">
      <input
        type="color"
        value={value.startsWith("#") ? value : "#000000"}
        onChange={(e) => onChange(e.target.value)}
        className="w-7 h-7 rounded border border-gray-200 cursor-pointer p-0.5 flex-shrink-0"
      />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="flex-1 text-[11px] border border-gray-200 rounded-md px-2 py-1.5
          focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
        placeholder="#2563eb"
        maxLength={20}
      />
    </div>
  );
}

function PresetRow({ value, options, onChange }) {
  return (
    <div className="flex gap-1">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          title={o.label}
          className={`flex-1 px-1.5 py-1 text-[10px] rounded border transition-colors ${
            value === o.value
              ? "bg-blue-600 text-white border-blue-600"
              : "border-gray-200 text-gray-600 hover:border-blue-300 hover:bg-blue-50"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

const RADIUS_PRESETS = [
  { label: "Square", value: "0px" },
  { label: "Rounded", value: "6px" },
  { label: "Pill", value: "100px" },
];

const IMG_RADIUS_PRESETS = [
  { label: "None", value: "0" },
  { label: "4px", value: "4px" },
  { label: "8px", value: "8px" },
  { label: "Circle", value: "50%" },
];

const FONT_SIZE_PRESETS = [
  { label: "Sm", value: "12px" },
  { label: "Md", value: "14px" },
  { label: "Lg", value: "16px" },
  { label: "XL", value: "18px" },
];

const PADDING_PRESETS = [
  { label: "Compact", value: "8px 16px" },
  { label: "Normal", value: "12px 24px" },
  { label: "Spacious", value: "16px 32px" },
];

// ── Main component ────────────────────────────────────────────────────

export default function BlockSettingsPanel({
  block,
  onChange,
  onDelete,
  onDuplicate,
  onClose,
}) {
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

// ── Block-type-specific field sections ────────────────────────────────

function BlockFields({ block, onChange }) {
  const update = (partial) => onChange({ ...block, ...partial });
  const updateContent = (content) => update({ content });

  // ── Image ──────────────────────────────────────────────────────────
  if (block.type === "image") {
    return <ImageFields block={block} onChange={onChange} />;
  }

  // ── Button ─────────────────────────────────────────────────────────
  if (block.type === "button") {
    return <ButtonFields block={block} onChange={onChange} />;
  }

  // ── Quote ──────────────────────────────────────────────────────────
  if (block.type === "quote") {
    const quoteText    = extractQuoteText(block.content);
    const quoteAuthor  = extractQuoteAuthor(block.content);
    const accentColor  = extractQuoteBorderColor(block.content);
    const rebuild = (overrides) =>
      updateContent(
        buildQuoteHtml({ text: quoteText, author: quoteAuthor, accentColor, ...overrides })
      );

    return (
      <div className="px-4 py-3 border-t border-gray-100 space-y-3">
        <div>
          <Label>Quote text</Label>
          <textarea
            value={quoteText}
            onChange={(e) => rebuild({ text: e.target.value })}
            className="w-full text-xs border border-gray-200 rounded-md px-2 py-1.5
              focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none h-20"
            placeholder="Your quote here."
          />
        </div>
        <div>
          <Label>Author</Label>
          <TextInput
            value={quoteAuthor}
            placeholder="Author Name"
            onChange={(v) => rebuild({ author: v })}
          />
        </div>
        <div>
          <Label>Accent color</Label>
          <ColorInput value={accentColor} onChange={(v) => rebuild({ accentColor: v })} />
        </div>
      </div>
    );
  }

  // ── Spacer ─────────────────────────────────────────────────────────
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

  // ── Generic HTML editor for everything else ────────────────────────
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

// ── Image fields component ────────────────────────────────────────────

function ImageFields({ block, onChange }) {
  const uploadRef = useRef(null);
  const vals = extractImageValues(block.content);

  const rebuild = (overrides) => {
    const next = { ...vals, ...overrides };
    onChange({ ...block, content: buildImageHtml(next) });
  };

  const handleFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      rebuild({ src: ev.target.result });
    };
    reader.readAsDataURL(file);
    // Reset so same file can be re-selected
    e.target.value = "";
  };

  return (
    <div className="px-4 py-3 border-t border-gray-100 space-y-3">
      {/* URL input */}
      <div>
        <Label>Image URL</Label>
        <TextInput
          type="url"
          value={vals.src.startsWith("data:") ? "" : vals.src}
          placeholder="https://example.com/image.png"
          onChange={(url) => rebuild({ src: url })}
        />
      </div>

      {/* File upload */}
      <div>
        <Label>Upload image</Label>
        <input
          ref={uploadRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handleFileUpload}
        />
        <button
          type="button"
          onClick={() => uploadRef.current?.click()}
          className="w-full px-3 py-1.5 text-xs border border-dashed border-gray-300
            rounded-md text-gray-500 hover:border-blue-400 hover:text-blue-600
            hover:bg-blue-50 transition-colors"
        >
          {vals.src.startsWith("data:")
            ? "✓ Image uploaded — click to replace"
            : "Choose file…"}
        </button>
      </div>

      {/* Alt text */}
      <div>
        <Label>Alt text</Label>
        <TextInput
          value={vals.alt}
          placeholder="Describe the image"
          onChange={(alt) => rebuild({ alt })}
        />
      </div>

      {/* Width slider */}
      <div>
        <Label>Width: {vals.width}px</Label>
        <input
          type="range"
          min={100}
          max={600}
          step={10}
          value={parseInt(vals.width) || 600}
          onChange={(e) => rebuild({ width: e.target.value })}
          className="w-full h-1.5 rounded appearance-none bg-gray-200 accent-blue-600 cursor-pointer"
        />
        <div className="flex justify-between text-[10px] text-gray-400 mt-0.5">
          <span>100px</span>
          <span>600px</span>
        </div>
      </div>

      {/* Border radius presets */}
      <div>
        <Label>Corners</Label>
        <PresetRow
          value={vals.borderRadius}
          options={IMG_RADIUS_PRESETS}
          onChange={(v) => rebuild({ borderRadius: v })}
        />
      </div>
    </div>
  );
}

// ── Button fields component ───────────────────────────────────────────

function ButtonFields({ block, onChange }) {
  const vals = extractButtonValues(block.content);

  const rebuild = (overrides) => {
    const next = { ...vals, ...overrides };
    onChange({ ...block, content: buildButtonHtml(next) });
  };

  return (
    <div className="px-4 py-3 border-t border-gray-100 space-y-3">
      {/* Label */}
      <div>
        <Label>Button label</Label>
        <TextInput
          value={vals.label}
          placeholder="Click me"
          onChange={(v) => rebuild({ label: v })}
        />
      </div>

      {/* Link URL */}
      <div>
        <Label>Link URL</Label>
        <TextInput
          type="url"
          value={vals.href}
          placeholder="https://"
          onChange={(v) => rebuild({ href: v })}
        />
      </div>

      {/* Colors */}
      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label>Background</Label>
          <ColorInput value={vals.bgColor} onChange={(v) => rebuild({ bgColor: v })} />
        </div>
        <div>
          <Label>Text color</Label>
          <ColorInput value={vals.textColor} onChange={(v) => rebuild({ textColor: v })} />
        </div>
      </div>

      {/* Shape */}
      <div>
        <Label>Shape</Label>
        <PresetRow
          value={vals.borderRadius}
          options={RADIUS_PRESETS}
          onChange={(v) => rebuild({ borderRadius: v })}
        />
      </div>

      {/* Font size */}
      <div>
        <Label>Font size</Label>
        <PresetRow
          value={vals.fontSize}
          options={FONT_SIZE_PRESETS}
          onChange={(v) => rebuild({ fontSize: v })}
        />
      </div>

      {/* Padding */}
      <div>
        <Label>Padding</Label>
        <PresetRow
          value={vals.padding}
          options={PADDING_PRESETS}
          onChange={(v) => rebuild({ padding: v })}
        />
      </div>
    </div>
  );
}
