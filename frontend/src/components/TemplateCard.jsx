// frontend/src/components/TemplateCard.jsx
//
// Visual card for a single template in the gallery. Renders an iframe
// thumbnail of the template's HTML scaled to fit a fixed-size preview
// area. Click the body to open the preview modal; hover reveals the
// action menu (Edit / Duplicate / Delete).
//
// Mode notes:
//   - Only "drag-drop" and "html" are active modes.
//   - Legacy templates saved with mode "visual" or "legacy" display as
//     "HTML" since those editor modes no longer exist.

import React, { useMemo, useState, useRef, useEffect } from "react";
import { Eye, Copy, Trash2, Pencil, MoreHorizontal, FileText } from "lucide-react";
import {
  getTemplateHtml,
  getTemplateMode,
  buildThumbnailSrcDoc,
} from "../utils/templateRender";

const THUMB_SOURCE_WIDTH = 600;
const THUMB_RENDER_SCALE = 0.42;

// Active modes only — visual/legacy fall back to HTML styling
const MODE_BADGE = {
  "drag-drop": { style: "bg-green-50 text-green-700 ring-1 ring-green-100", label: "Drag & Drop" },
  "html":      { style: "bg-purple-50 text-purple-700 ring-1 ring-purple-100", label: "HTML" },
};
const DEFAULT_BADGE = { style: "bg-gray-100 text-gray-600 ring-1 ring-gray-200", label: "HTML" };

function getModeBadge(mode) {
  return MODE_BADGE[mode] || DEFAULT_BADGE;
}

export default function TemplateCard({
  template,
  onPreview,
  onEdit,
  onDuplicate,
  onDelete,
  formatDate,
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  const mode    = getTemplateMode(template);
  const html    = useMemo(() => getTemplateHtml(template), [template]);
  const srcDoc  = useMemo(() => buildThumbnailSrcDoc(html), [html]);
  const isEmpty = !html.trim();
  const badge   = getModeBadge(mode);

  // Close the kebab menu on outside click / escape
  useEffect(() => {
    if (!menuOpen) return;
    const onDocClick = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
    };
    const onKey = (e) => { if (e.key === "Escape") setMenuOpen(false); };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  const stop = (fn) => (e) => {
    e.stopPropagation();
    setMenuOpen(false);
    fn(template);
  };

  const fieldCount = Array.isArray(template.fields) ? template.fields.length : 0;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onPreview(template)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPreview(template); }
      }}
      className="group relative flex flex-col bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md hover:border-gray-300 transition-all duration-150 overflow-hidden focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 cursor-pointer"
    >
      {/* ── Thumbnail ──────────────────────────────────────────── */}
      <div className="relative h-56 bg-gray-50 border-b border-gray-100 overflow-hidden">
        {isEmpty ? (
          <div className="h-full w-full flex flex-col items-center justify-center text-gray-300">
            <FileText size={32} />
            <p className="text-xs mt-2 text-gray-400">Empty template</p>
          </div>
        ) : (
          <div
            className="absolute top-0 left-0 origin-top-left pointer-events-none"
            style={{
              width: THUMB_SOURCE_WIDTH,
              height: 64 * 16,
              transform: `scale(${THUMB_RENDER_SCALE})`,
            }}
          >
            <iframe
              title={`Preview of ${template.name || "template"}`}
              srcDoc={srcDoc}
              sandbox=""
              loading="lazy"
              className="w-full h-full border-0 bg-white"
              tabIndex={-1}
              aria-hidden="true"
            />
          </div>
        )}

        {/* Hover overlay */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/30 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-150 flex items-end justify-center pb-4 pointer-events-none">
          <span className="px-3 py-1.5 bg-white/95 backdrop-blur text-xs font-medium text-gray-700 rounded-full shadow-sm flex items-center gap-1.5">
            <Eye size={12} /> Preview
          </span>
        </div>

        {/* Mode badge */}
        <span className={`absolute top-2.5 left-2.5 text-[10px] font-medium px-2 py-0.5 rounded-md ${badge.style}`}>
          {badge.label}
        </span>

        {/* Kebab menu */}
        <div ref={menuRef} className="absolute top-2 right-2">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setMenuOpen((v) => !v); }}
            aria-label="Template actions"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            className="p-1.5 rounded-md bg-white/90 backdrop-blur hover:bg-white text-gray-600 shadow-sm border border-gray-200 transition-opacity opacity-0 group-hover:opacity-100 focus:opacity-100"
          >
            <MoreHorizontal size={14} />
          </button>

          {menuOpen && (
            <div
              role="menu"
              className="absolute right-0 top-9 z-10 w-40 bg-white rounded-lg shadow-lg border border-gray-200 py-1 text-sm"
              onClick={(e) => e.stopPropagation()}
            >
              <button role="menuitem" onClick={stop(onEdit)}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-gray-700 hover:bg-gray-50">
                <Pencil size={13} /> Edit
              </button>
              <button role="menuitem" onClick={stop(onDuplicate)}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-gray-700 hover:bg-gray-50">
                <Copy size={13} /> Duplicate
              </button>
              <div className="my-1 border-t border-gray-100" />
              <button role="menuitem" onClick={stop(onDelete)}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-red-600 hover:bg-red-50">
                <Trash2 size={13} /> Delete
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ── Card body ──────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col px-4 py-3 gap-1.5">
        {/* Name */}
        <h3 className="font-semibold text-sm text-gray-900 truncate" title={template.name}>
          {template.name || "Untitled template"}
        </h3>

        {/* Description if present */}
        {template.description ? (
          <p className="text-xs text-gray-400 truncate" title={template.description}>
            {template.description}
          </p>
        ) : (
          <p className="text-xs text-gray-300 italic">No description</p>
        )}

        {/* Fields pill */}
        {fieldCount > 0 && (
          <div className="flex gap-1 flex-wrap">
            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-50 text-blue-600">
              {fieldCount} token{fieldCount === 1 ? "" : "s"}
            </span>
          </div>
        )}

        {/* Timestamps */}
        <div className="mt-auto pt-2 border-t border-gray-50 space-y-0.5 text-[11px] text-gray-400">
          {template.created_at && formatDate && (
            <div className="flex justify-between">
              <span className="text-gray-300">Created</span>
              <span>{formatDate(template.created_at)}</span>
            </div>
          )}
          {template.updated_at && formatDate && (
            <div className="flex justify-between">
              <span className="text-gray-300">Updated</span>
              <span>{formatDate(template.updated_at)}</span>
            </div>
          )}
          {!template.created_at && !template.updated_at && (
            <span className="text-gray-300 italic">No date info</span>
          )}
        </div>
      </div>
    </div>
  );
}
