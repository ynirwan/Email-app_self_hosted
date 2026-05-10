// frontend/src/components/EmailEditor.jsx
//
// Email editor — drag-drop, HTML, and preview modes.
//
// PUBLIC API — DO NOT BREAK. Consumers (TemplatesPage, TemplateEditor,
// CreateCampaign) drive this component through forwardRef:
//
//   editor.exportHtml(callback)  — callback({ design, html })
//     - design.mode is "drag-drop" or "html"
//     - design.blocks (drag-drop only) is [{id,type,content,styles,position}, ...]
//     - design.content (html only) is the raw HTML string
//   editor.loadDesign(design)    — accepts the same shape exportHtml returned
//   editor.loadBlank()
//
// Optional prop: templateMeta — { name, created_at, updated_at, fields, content_json }
//   When provided, an ℹ info button appears in the toolbar that shows a
//   popover with template metadata.
//
// The drag-drop block shape (id, type, content, styles, position) MUST stay
// identical to what backend/routes/templates.py:TemplateRenderer reads.

import React, {
  useState,
  useRef,
  useCallback,
  useEffect,
  forwardRef,
  useImperativeHandle,
  useMemo,
} from "react";
import {
  DndContext,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  closestCenter,
  DragOverlay,
  useDroppable,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  arrayMove,
  sortableKeyboardCoordinates,
} from "@dnd-kit/sortable";
import {
  Code,
  MousePointer,
  Eye,
  AlertTriangle,
  CheckCircle,
  Monitor,
  Tablet,
  Smartphone,
  Info,
  X,
} from "lucide-react";

import BlockPalette, { PALETTE_ID_PREFIX } from "./editor/BlockPalette";
import SortableBlock from "./editor/SortableBlock";
import BlockSettingsPanel from "./editor/BlockSettingsPanel";
import {
  getBlockDefinition,
  EMAIL_BLOCK_TYPES,
} from "./editor/blockDefinitions";

// ─── deliverability helpers ─────────────────────────────────────────

const SPAM_TRIGGER_WORDS = [
  "free","guarantee","limited time","urgent","click here","buy now","offer",
  "deal","discount","winner","congratulations","cash","money","earn","income",
  "opportunity","risk-free","no obligation","act now","instant","immediately",
  "order now","limited offer","exclusive","special promotion","clearance",
  "save up to","percent off","lowest price",
];

function analyzeDeliverability(html) {
  const text = (html || "").replace(/<[^>]+>/g, " ").toLowerCase();
  const warnings = [];
  for (const word of SPAM_TRIGGER_WORDS) {
    if (text.includes(word)) warnings.push(`Contains "${word}"`);
  }
  const imgCount = (html || "").match(/<img/gi)?.length || 0;
  const wordCount = text.split(/\s+/).filter(Boolean).length;
  if (imgCount > 0 && wordCount < 20) {
    warnings.push("Image-heavy with little text — may trigger spam filters");
  }
  const score = Math.max(0, 100 - warnings.length * 8);
  return { score, warnings };
}

// ─── preview HTML builder ────────────────────────────────────────────

function buildPreviewHtml(bodyContent) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  * { box-sizing: border-box; }
  body { margin: 0; padding: 0; font-family: Arial, Helvetica, sans-serif; background: #f4f5f6; }
  .email-wrapper { max-width: 600px; margin: 0 auto; background: #ffffff; }
  .email-body { padding: 24px; }
  img { max-width: 100%; height: auto; }
  a { color: inherit; }
  blockquote { margin: 0; }
  p { margin: 0 0 1em 0; }
  h1, h2, h3, h4 { margin: 0 0 0.75em 0; }
</style>
</head>
<body>
<div class="email-wrapper">
  <div class="email-body">
    ${bodyContent}
  </div>
</div>
</body>
</html>`;
}

// ─── id helpers ─────────────────────────────────────────────────────

const CANVAS_DROP_ID = "canvas-drop-zone";

function newBlockId() {
  return `b_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function makeBlockFromType(typeId, position) {
  const def = getBlockDefinition(typeId) || EMAIL_BLOCK_TYPES[0];
  return {
    id: newBlockId(),
    type: def.id,
    content: def.defaultContent,
    styles: {},
    position,
  };
}

// ─── date formatting helper ──────────────────────────────────────────

function fmtDate(iso) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric", month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

// ─── main component ─────────────────────────────────────────────────

const EmailEditor = forwardRef((props, ref) => {
  const { onLoad, onChange, templateMeta } = props;

  // "drag-drop" | "html" | "preview"
  const [editMode, setEditMode] = useState("drag-drop");
  // track which non-preview mode was active before entering preview
  const contentModeRef = useRef("drag-drop");

  // Drag-drop state
  const [emailBlocks, setEmailBlocks] = useState([]);
  const [selectedBlockId, setSelectedBlockId] = useState(null);
  const [activeDragId, setActiveDragId] = useState(null);

  // HTML mode state
  const [htmlContent, setHtmlContent] = useState("");

  // Deliverability
  const [deliverability, setDeliverability] = useState({ score: 100, warnings: [] });
  const [showDeliverabilityPanel, setShowDeliverabilityPanel] = useState(false);

  // Template info popover
  const [showInfoPanel, setShowInfoPanel] = useState(false);

  // Preview viewport
  const [previewViewport, setPreviewViewport] = useState("desktop");

  const activeTextEditorRef = useRef(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const fireChange = useCallback(() => {
    if (onChange) onChange();
  }, [onChange]);

  // ─── recompute deliverability ──────────────────────────────────────
  useEffect(() => {
    let html = editMode === "html" ? htmlContent : emailBlocks.map((b) => b.content || "").join("\n");
    setDeliverability(analyzeDeliverability(html));
  }, [emailBlocks, htmlContent, editMode]);

  // ─── onLoad callback ──────────────────────────────────────────────
  useEffect(() => {
    if (onLoad) onLoad();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── mode switching helpers ────────────────────────────────────────
  const switchMode = useCallback((mode) => {
    if (mode !== "preview") {
      contentModeRef.current = mode;
    }
    setEditMode(mode);
    setSelectedBlockId(null);
    setShowInfoPanel(false);
    setShowDeliverabilityPanel(false);
  }, []);

  // ─── public API via ref ───────────────────────────────────────────
  useImperativeHandle(
    ref,
    () => ({
      editor: {
        exportHtml: (callback) => {
          // Use contentModeRef to export the actual content mode even if currently previewing
          const mode = contentModeRef.current;
          let design, html;
          if (mode === "html") {
            design = { mode: "html", content: htmlContent };
            html = htmlContent;
          } else {
            const blocks = emailBlocks.map((b, i) => ({ ...b, position: i }));
            design = { mode: "drag-drop", blocks };
            html = blocks.map((b) => b.content || "").join("\n");
          }
          callback({ design, html });
        },

        loadDesign: (design) => {
          if (!design) {
            setEditMode("drag-drop");
            contentModeRef.current = "drag-drop";
            setEmailBlocks([]);
            setHtmlContent("");
            return;
          }
          if (design.mode === "html" && typeof design.content === "string") {
            setEditMode("html");
            contentModeRef.current = "html";
            setHtmlContent(design.content);
            return;
          }
          if (design.mode === "drag-drop" && Array.isArray(design.blocks)) {
            setEditMode("drag-drop");
            contentModeRef.current = "drag-drop";
            const safeBlocks = design.blocks
              .filter((b) => b && b.type)
              .map((b, i) => ({
                id: b.id ?? newBlockId(),
                type: b.type,
                content: typeof b.content === "string" ? b.content : "",
                styles: b.styles || {},
                position: typeof b.position === "number" ? b.position : i,
              }))
              .sort((a, b) => a.position - b.position);
            setEmailBlocks(safeBlocks);
            return;
          }
          // Legacy visual mode
          if (design.mode === "visual" && typeof design.content === "string") {
            setEditMode("html");
            contentModeRef.current = "html";
            setHtmlContent(design.content);
            return;
          }
          // Legacy Unlayer-ish shape
          if (design.body && Array.isArray(design.body.rows)) {
            const parts = [];
            for (const row of design.body.rows) {
              for (const col of row.columns || []) {
                for (const c of col.contents || []) {
                  if (c?.type === "html" && c.values?.html) parts.push(c.values.html);
                }
              }
            }
            setEditMode("html");
            contentModeRef.current = "html";
            setHtmlContent(parts.join("\n"));
            return;
          }
          if (typeof design.html === "string") {
            setEditMode("html");
            contentModeRef.current = "html";
            setHtmlContent(design.html);
            return;
          }
          setEditMode("drag-drop");
          contentModeRef.current = "drag-drop";
          setEmailBlocks([]);
          setHtmlContent("");
        },

        loadBlank: () => {
          setEditMode("drag-drop");
          contentModeRef.current = "drag-drop";
          setEmailBlocks([]);
          setHtmlContent("");
          setSelectedBlockId(null);
        },
      },
    }),
    [emailBlocks, htmlContent],
  );

  // ─── block mutators ───────────────────────────────────────────────

  const updateBlock = useCallback(
    (id, updater) => {
      setEmailBlocks((prev) =>
        prev.map((b) =>
          b.id === id ? (typeof updater === "function" ? updater(b) : updater) : b,
        ),
      );
      fireChange();
    },
    [fireChange],
  );

  const deleteBlock = useCallback(
    (id) => {
      setEmailBlocks((prev) => prev.filter((b) => b.id !== id));
      setSelectedBlockId((cur) => (cur === id ? null : cur));
      fireChange();
    },
    [fireChange],
  );

  const duplicateBlock = useCallback(
    (id) => {
      setEmailBlocks((prev) => {
        const idx = prev.findIndex((b) => b.id === id);
        if (idx === -1) return prev;
        const copy = { ...prev[idx], id: newBlockId() };
        const next = [...prev];
        next.splice(idx + 1, 0, copy);
        return next.map((b, i) => ({ ...b, position: i }));
      });
      fireChange();
    },
    [fireChange],
  );

  // ─── drag-drop handlers ───────────────────────────────────────────

  const handleDragStart = (event) => setActiveDragId(event.active.id);

  const handleDragEnd = (event) => {
    setActiveDragId(null);
    const { active, over } = event;
    if (!over) return;
    const activeId = String(active.id);
    const overId   = String(over.id);

    if (activeId.startsWith(PALETTE_ID_PREFIX)) {
      const typeId = activeId.slice(PALETTE_ID_PREFIX.length);
      setEmailBlocks((prev) => {
        let insertAt = overId === CANVAS_DROP_ID
          ? prev.length
          : (() => {
              const overIdx = prev.findIndex((b) => b.id === overId);
              return overIdx === -1 ? prev.length : overIdx;
            })();
        const newBlock = makeBlockFromType(typeId, insertAt);
        const next = [...prev];
        next.splice(insertAt, 0, newBlock);
        return next.map((b, i) => ({ ...b, position: i }));
      });
      fireChange();
      return;
    }

    if (activeId !== overId) {
      setEmailBlocks((prev) => {
        const oldIndex = prev.findIndex((b) => b.id === activeId);
        const newIndex = prev.findIndex((b) => b.id === overId);
        if (oldIndex === -1 || newIndex === -1) return prev;
        const moved = arrayMove(prev, oldIndex, newIndex);
        return moved.map((b, i) => ({ ...b, position: i }));
      });
      fireChange();
    }
  };

  const handleDragCancel = () => setActiveDragId(null);

  const selectedBlock = emailBlocks.find((b) => b.id === selectedBlockId) || null;

  // ─── preview HTML (memoized) ──────────────────────────────────────
  const previewHtml = useMemo(() => {
    const body =
      contentModeRef.current === "html"
        ? htmlContent
        : emailBlocks.map((b) => b.content || "").join("\n");
    return buildPreviewHtml(body);
    // recompute whenever blocks or html changes, regardless of current view mode
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emailBlocks, htmlContent]);

  // ─── render ───────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full bg-white">

      {/* ── Mode tabs + toolbar ───────────────────────────────────── */}
      <div className="flex items-center justify-between border-b border-gray-200 px-4 flex-shrink-0">
        <div className="flex items-center">
          <ModeTab
            active={editMode === "drag-drop"}
            onClick={() => switchMode("drag-drop")}
            icon={<MousePointer size={14} />}
          >
            Drag &amp; drop
          </ModeTab>
          <ModeTab
            active={editMode === "html"}
            onClick={() => switchMode("html")}
            icon={<Code size={14} />}
          >
            HTML
          </ModeTab>
          <ModeTab
            active={editMode === "preview"}
            onClick={() => switchMode("preview")}
            icon={<Eye size={14} />}
          >
            Preview
          </ModeTab>
        </div>

        <div className="flex items-center gap-1.5">
          {/* Template info button */}
          {templateMeta && (
            <div className="relative">
              <button
                type="button"
                onClick={() => {
                  setShowInfoPanel((v) => !v);
                  setShowDeliverabilityPanel(false);
                }}
                className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  showInfoPanel
                    ? "bg-gray-200 text-gray-800"
                    : "text-gray-500 hover:bg-gray-100"
                }`}
                title="Template info"
              >
                <Info size={13} />
              </button>
              {showInfoPanel && (
                <TemplateInfoPopover
                  meta={templateMeta}
                  onClose={() => setShowInfoPanel(false)}
                />
              )}
            </div>
          )}

          {/* Deliverability score */}
          <button
            type="button"
            onClick={() => {
              setShowDeliverabilityPanel((v) => !v);
              setShowInfoPanel(false);
            }}
            className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium ${
              deliverability.warnings.length === 0
                ? "text-green-700 bg-green-50 hover:bg-green-100"
                : "text-amber-700 bg-amber-50 hover:bg-amber-100"
            }`}
            title="Show deliverability checks"
          >
            {deliverability.warnings.length === 0
              ? <CheckCircle size={12} />
              : <AlertTriangle size={12} />
            }
            {deliverability.score}/100
          </button>
        </div>
      </div>

      {/* ── Deliverability panel ──────────────────────────────────── */}
      {showDeliverabilityPanel && (
        <div className="border-b border-gray-200 bg-amber-50/50 px-4 py-2 flex-shrink-0">
          {deliverability.warnings.length === 0 ? (
            <p className="text-xs text-green-700 flex items-center gap-1.5">
              <CheckCircle size={12} /> No deliverability issues detected.
            </p>
          ) : (
            <ul className="text-xs text-amber-800 space-y-0.5">
              {deliverability.warnings.map((w, i) => (
                <li key={i} className="flex items-start gap-1.5">
                  <AlertTriangle size={11} className="mt-0.5 flex-shrink-0" />
                  <span>{w}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* ── Body ──────────────────────────────────────────────────── */}
      {editMode === "preview" ? (
        <PreviewMode
          previewHtml={previewHtml}
          viewport={previewViewport}
          setViewport={setPreviewViewport}
        />
      ) : editMode === "drag-drop" ? (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragStart={handleDragStart}
          onDragEnd={handleDragEnd}
          onDragCancel={handleDragCancel}
        >
          <div className="flex flex-1 min-h-0 overflow-hidden">
            <BlockPalette />
            <Canvas
              blocks={emailBlocks}
              selectedId={selectedBlockId}
              onSelect={setSelectedBlockId}
              onChangeBlock={(updated) => updateBlock(updated.id, updated)}
              onTextEditorReady={(ed) => { activeTextEditorRef.current = ed; }}
            />
            <BlockSettingsPanel
              block={selectedBlock}
              onChange={(updated) => updateBlock(updated.id, updated)}
              onDelete={() => selectedBlock && deleteBlock(selectedBlock.id)}
              onDuplicate={() => selectedBlock && duplicateBlock(selectedBlock.id)}
              onClose={() => setSelectedBlockId(null)}
            />
          </div>

          <DragOverlay dropAnimation={{ duration: 150 }}>
            {activeDragId ? (
              <DragPreview activeDragId={activeDragId} blocks={emailBlocks} />
            ) : null}
          </DragOverlay>
        </DndContext>
      ) : (
        <HtmlMode
          value={htmlContent}
          onChange={(v) => { setHtmlContent(v); fireChange(); }}
        />
      )}
    </div>
  );
});

EmailEditor.displayName = "EmailEditor";
export default EmailEditor;

// ─── ModeTab ──────────────────────────────────────────────────────────

function ModeTab({ active, onClick, icon, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-4 py-2.5 border-b-2 text-sm font-medium transition-colors flex items-center gap-1.5 ${
        active
          ? "border-blue-500 text-blue-700"
          : "border-transparent text-gray-500 hover:text-gray-800"
      }`}
    >
      {icon}
      {children}
    </button>
  );
}

// ─── Canvas ───────────────────────────────────────────────────────────

function Canvas({ blocks, selectedId, onSelect, onChangeBlock, onTextEditorReady }) {
  const { setNodeRef, isOver } = useDroppable({ id: CANVAS_DROP_ID });

  return (
    <div className="flex-1 min-w-0 overflow-auto bg-gray-100 px-6 py-8">
      <div
        ref={setNodeRef}
        className={`max-w-[640px] mx-auto bg-white shadow-sm border rounded-lg min-h-[400px] transition-colors ${
          isOver ? "border-blue-400 ring-2 ring-blue-200" : "border-gray-200"
        }`}
      >
        <SortableContext
          items={blocks.map((b) => b.id)}
          strategy={verticalListSortingStrategy}
        >
          <div
            className="p-6 space-y-2 min-h-[400px]"
            onClick={(e) => {
              if (e.target === e.currentTarget) onSelect(null);
            }}
          >
            {blocks.length === 0 ? (
              <EmptyCanvasHint isOver={isOver} />
            ) : (
              <>
                {blocks.map((block) => (
                  <SortableBlock
                    key={block.id}
                    block={block}
                    selected={selectedId === block.id}
                    onSelect={() => onSelect(block.id)}
                    onChange={onChangeBlock}
                    onTextEditorReady={
                      selectedId === block.id ? onTextEditorReady : undefined
                    }
                  />
                ))}
                <div className="h-6" aria-hidden="true" />
              </>
            )}
          </div>
        </SortableContext>
      </div>
    </div>
  );
}

function EmptyCanvasHint({ isOver }) {
  return (
    <div
      className={`border-2 border-dashed rounded-md py-16 px-6 text-center transition-colors ${
        isOver ? "border-blue-400 bg-blue-50" : "border-gray-200"
      }`}
    >
      <p className={`text-sm font-medium ${isOver ? "text-blue-700" : "text-gray-500"}`}>
        {isOver
          ? "Drop here to add the block"
          : "Drag blocks from the left to start building your email"}
      </p>
      <p className="text-xs text-gray-400 mt-1">
        You can reorder, duplicate, or delete blocks at any time
      </p>
    </div>
  );
}

// ─── DragPreview ──────────────────────────────────────────────────────

function DragPreview({ activeDragId, blocks }) {
  const id = String(activeDragId);
  if (id.startsWith(PALETTE_ID_PREFIX)) {
    const typeId = id.slice(PALETTE_ID_PREFIX.length);
    const def = getBlockDefinition(typeId);
    if (!def) return null;
    const Icon = def.icon;
    return (
      <div className="inline-flex items-center gap-2 px-3 py-2 bg-white rounded-md border border-blue-400 shadow-lg text-xs font-medium text-gray-700">
        <Icon size={14} className="text-blue-600" />
        {def.name}
      </div>
    );
  }
  const block = blocks.find((b) => b.id === id);
  if (!block) return null;
  return (
    <div className="bg-white shadow-lg rounded-md border border-blue-400 px-4 py-3 max-w-md opacity-90">
      <div className="pointer-events-none" dangerouslySetInnerHTML={{ __html: block.content }} />
    </div>
  );
}

// ─── HtmlMode ─────────────────────────────────────────────────────────

function HtmlMode({ value, onChange }) {
  return (
    <div className="flex-1 min-h-0 flex flex-col bg-gray-50">
      <div className="px-4 py-2 border-b border-gray-200 bg-white flex-shrink-0">
        <p className="text-xs text-gray-500">
          Edit raw HTML. Personalization tokens like{" "}
          <code className="px-1 py-0.5 bg-gray-100 rounded">{"{{first_name}}"}</code>{" "}
          are preserved on send.
        </p>
      </div>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        className="flex-1 w-full p-4 font-mono text-xs leading-relaxed bg-white border-0 focus:outline-none resize-none"
        placeholder={"<!doctype html>\n<html>\n  <body>\n    <p>Hello {{first_name}},</p>\n  </body>\n</html>"}
      />
    </div>
  );
}

// ─── PreviewMode ──────────────────────────────────────────────────────

function PreviewMode({ previewHtml, viewport, setViewport }) {
  const iframeRef = useRef(null);

  const viewportWidth = {
    desktop: "100%",
    tablet: "768px",
    mobile: "375px",
  }[viewport];

  // Auto-resize iframe to fit content height
  const handleIframeLoad = (e) => {
    try {
      const doc = e.target.contentDocument || e.target.contentWindow?.document;
      if (doc) {
        const h = doc.documentElement.scrollHeight || doc.body.scrollHeight;
        e.target.style.height = Math.max(h + 32, 400) + "px";
      }
    } catch {
      // cross-origin safety — no-op
    }
  };

  return (
    <div className="flex-1 min-h-0 flex flex-col bg-gray-100">
      {/* Viewport controls */}
      <div className="px-4 py-2 bg-white border-b border-gray-200 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-1">
          {[
            { mode: "desktop", Icon: Monitor,    label: "Desktop" },
            { mode: "tablet",  Icon: Tablet,     label: "Tablet"  },
            { mode: "mobile",  Icon: Smartphone, label: "Mobile"  },
          ].map(({ mode, Icon, label }) => (
            <button
              key={mode}
              type="button"
              onClick={() => setViewport(mode)}
              title={label}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                viewport === mode
                  ? "bg-blue-600 text-white"
                  : "text-gray-500 hover:bg-gray-100"
              }`}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </div>
        <p className="text-[11px] text-gray-400">
          Live preview · personalization tokens shown as-is
        </p>
      </div>

      {/* Preview pane */}
      <div className="flex-1 overflow-auto flex justify-center p-6">
        <div
          className="bg-white shadow-lg transition-all duration-200 overflow-hidden"
          style={{
            width: viewportWidth,
            maxWidth: "100%",
            minHeight: 400,
            border: viewport !== "desktop" ? "2px solid #d1d5db" : "none",
            borderRadius: viewport !== "desktop" ? 8 : 0,
          }}
        >
          <iframe
            ref={iframeRef}
            srcDoc={previewHtml}
            title="Email preview"
            className="w-full border-0 block"
            style={{ minHeight: 400 }}
            onLoad={handleIframeLoad}
          />
        </div>
      </div>
    </div>
  );
}

// ─── TemplateInfoPopover ──────────────────────────────────────────────

function TemplateInfoPopover({ meta, onClose }) {
  const mode = meta?.content_json?.mode || "new";
  const fields = Array.isArray(meta?.fields) ? meta.fields : [];

  return (
    <div className="absolute right-0 top-full mt-1 w-64 bg-white border border-gray-200 rounded-lg shadow-lg z-50 text-xs">
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-100">
        <span className="font-semibold text-gray-700 truncate pr-2">
          {meta?.name || "Untitled template"}
        </span>
        <button
          type="button"
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 flex-shrink-0"
        >
          <X size={12} />
        </button>
      </div>
      <div className="px-3 py-2.5 space-y-1.5">
        <InfoRow label="Mode" value={mode} />
        {meta?.created_at && (
          <InfoRow label="Created" value={fmtDate(meta.created_at)} />
        )}
        {meta?.updated_at && (
          <InfoRow label="Last saved" value={fmtDate(meta.updated_at)} />
        )}
        {meta?.subject && (
          <InfoRow label="Subject" value={meta.subject} />
        )}
        <InfoRow
          label="Tokens"
          value={
            fields.length > 0
              ? fields.map((f) => `{{${f}}}`).join(", ")
              : "None detected"
          }
        />
      </div>
    </div>
  );
}

function InfoRow({ label, value }) {
  return (
    <div className="flex gap-2">
      <span className="text-gray-400 w-20 flex-shrink-0">{label}</span>
      <span className="text-gray-700 break-all">{value}</span>
    </div>
  );
}
