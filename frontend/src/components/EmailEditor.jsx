// frontend/src/components/EmailEditor.jsx
//
// Email editor — drag-drop and HTML modes. The "visual" (contentEditable)
// mode of the prior version has been removed because it duplicated
// drag-drop functionality on top of a deprecated browser API.
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
// The drag-drop block shape (id, type, content, styles, position) MUST stay
// identical to what backend/routes/templates.py:TemplateRenderer reads.
//
// What changed inside:
//   - Drag-drop: Tiptap for text/header rich-text, @dnd-kit for sortable
//     blocks. No more document.execCommand. No more HTML5 native drag-drop.
//   - HTML mode: unchanged — textarea + spam analysis.
//   - Visual (contentEditable) mode: removed.

import React, {
  useState,
  useRef,
  useCallback,
  useEffect,
  forwardRef,
  useImperativeHandle,
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
} from "lucide-react";

import BlockPalette, { PALETTE_ID_PREFIX } from "./editor/BlockPalette";
import SortableBlock from "./editor/SortableBlock";
import BlockSettingsPanel from "./editor/BlockSettingsPanel";
import {
  getBlockDefinition,
  EMAIL_BLOCK_TYPES,
} from "./editor/blockDefinitions";

// ─── deliverability helpers (unchanged from prior version) ──────────

const SPAM_TRIGGER_WORDS = [
  "free",
  "guarantee",
  "limited time",
  "urgent",
  "click here",
  "buy now",
  "offer",
  "deal",
  "discount",
  "winner",
  "congratulations",
  "cash",
  "money",
  "earn",
  "income",
  "opportunity",
  "risk-free",
  "no obligation",
  "act now",
  "instant",
  "immediately",
  "order now",
  "limited offer",
  "exclusive",
  "special promotion",
  "clearance",
  "save up to",
  "percent off",
  "lowest price",
];

function analyzeDeliverability(html) {
  const text = (html || "").replace(/<[^>]+>/g, " ").toLowerCase();
  const warnings = [];
  for (const word of SPAM_TRIGGER_WORDS) {
    if (text.includes(word)) warnings.push(`Contains "${word}"`);
  }
  // Image-to-text ratio rough check
  const imgCount = (html || "").match(/<img/gi)?.length || 0;
  const wordCount = text.split(/\s+/).filter(Boolean).length;
  if (imgCount > 0 && wordCount < 20) {
    warnings.push("Image-heavy with little text — may trigger spam filters");
  }
  const score = Math.max(0, 100 - warnings.length * 8);
  return { score, warnings };
}

// ─── id helpers ─────────────────────────────────────────────────────

// Special droppable id used by the canvas itself. Anything dropped here
// (rather than on a specific block) gets appended to the end of the list.
// Letting palette items drop on the empty canvas is the difference between
// "I can't add blocks" and "this works." See Canvas + handleDragEnd.
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

// ─── main component ─────────────────────────────────────────────────

const EmailEditor = forwardRef((props, ref) => {
  const { onLoad, onChange } = props;

  // Mode: "drag-drop" or "html". Default is drag-drop.
  const [editMode, setEditMode] = useState("drag-drop");

  // Drag-drop state
  const [emailBlocks, setEmailBlocks] = useState([]);
  const [selectedBlockId, setSelectedBlockId] = useState(null);
  const [activeDragId, setActiveDragId] = useState(null);

  // HTML mode state (unchanged shape)
  const [htmlContent, setHtmlContent] = useState("");

  // Deliverability
  const [deliverability, setDeliverability] = useState({
    score: 100,
    warnings: [],
  });
  const [showDeliverabilityPanel, setShowDeliverabilityPanel] = useState(false);

  // Token reference into the currently-active rich-text editor
  const activeTextEditorRef = useRef(null);

  // Sensors — pointer for mouse/touch, keyboard for accessibility
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 4 }, // small distance to allow simple clicks
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  // Notify parent of changes — fired when blocks, html, or mode change
  const fireChange = useCallback(() => {
    if (onChange) onChange();
  }, [onChange]);

  // ─── recompute deliverability on content change ──────────────────
  useEffect(() => {
    let html = "";
    if (editMode === "drag-drop") {
      html = emailBlocks.map((b) => b.content || "").join("\n");
    } else {
      html = htmlContent;
    }
    setDeliverability(analyzeDeliverability(html));
  }, [emailBlocks, htmlContent, editMode]);

  // ─── onLoad callback ─────────────────────────────────────────────
  useEffect(() => {
    if (onLoad) onLoad();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── public API via ref ──────────────────────────────────────────
  useImperativeHandle(
    ref,
    () => ({
      editor: {
        exportHtml: (callback) => {
          let design;
          let html;
          if (editMode === "html") {
            design = { mode: "html", content: htmlContent };
            html = htmlContent;
          } else {
            // Re-stamp position from array index so the backend's position-sort
            // matches user intent regardless of stale position fields.
            const blocks = emailBlocks.map((b, i) => ({ ...b, position: i }));
            design = { mode: "drag-drop", blocks };
            html = blocks.map((b) => b.content || "").join("\n");
          }
          callback({ design, html });
        },

        loadDesign: (design) => {
          if (!design) {
            setEditMode("drag-drop");
            setEmailBlocks([]);
            setHtmlContent("");
            return;
          }

          if (design.mode === "html" && typeof design.content === "string") {
            setEditMode("html");
            setHtmlContent(design.content);
            return;
          }

          if (design.mode === "drag-drop" && Array.isArray(design.blocks)) {
            setEditMode("drag-drop");
            // Defensive — ensure every block has the fields we need
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

          // Legacy "visual" mode: surface the raw content into HTML mode
          // since we no longer have a contentEditable visual editor.
          if (design.mode === "visual" && typeof design.content === "string") {
            setEditMode("html");
            setHtmlContent(design.content);
            return;
          }

          // Legacy Unlayer-ish shape (body.rows[].columns[].contents[])
          if (design.body && Array.isArray(design.body.rows)) {
            const parts = [];
            for (const row of design.body.rows) {
              for (const col of row.columns || []) {
                for (const c of col.contents || []) {
                  if (c && c.type === "html" && c.values?.html) {
                    parts.push(c.values.html);
                  }
                }
              }
            }
            setEditMode("html");
            setHtmlContent(parts.join("\n"));
            return;
          }

          // Plain `html` field as a last resort
          if (typeof design.html === "string") {
            setEditMode("html");
            setHtmlContent(design.html);
            return;
          }

          setEditMode("drag-drop");
          setEmailBlocks([]);
          setHtmlContent("");
        },

        loadBlank: () => {
          setEditMode("drag-drop");
          setEmailBlocks([]);
          setHtmlContent("");
          setSelectedBlockId(null);
        },
      },
    }),
    [emailBlocks, htmlContent, editMode],
  );

  // ─── block mutators ──────────────────────────────────────────────

  const updateBlock = useCallback(
    (id, updater) => {
      setEmailBlocks((prev) =>
        prev.map((b) =>
          b.id === id
            ? typeof updater === "function"
              ? updater(b)
              : updater
            : b,
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

  // ─── drag-drop handlers ──────────────────────────────────────────

  const handleDragStart = (event) => {
    setActiveDragId(event.active.id);
  };

  const handleDragEnd = (event) => {
    setActiveDragId(null);
    const { active, over } = event;
    if (!over) return;

    const activeId = String(active.id);
    const overId = String(over.id);

    // Case 1: dragging a palette item onto the canvas
    if (activeId.startsWith(PALETTE_ID_PREFIX)) {
      const typeId = activeId.slice(PALETTE_ID_PREFIX.length);
      setEmailBlocks((prev) => {
        // If dropped on the canvas drop-zone (empty canvas, or empty space
        // below the last block), append to the end. Otherwise insert above
        // the block we landed on.
        let insertAt;
        if (overId === CANVAS_DROP_ID) {
          insertAt = prev.length;
        } else {
          const overIdx = prev.findIndex((b) => b.id === overId);
          insertAt = overIdx === -1 ? prev.length : overIdx;
        }
        const newBlock = makeBlockFromType(typeId, insertAt);
        const next = [...prev];
        next.splice(insertAt, 0, newBlock);
        // Re-stamp positions
        return next.map((b, i) => ({ ...b, position: i }));
      });
      fireChange();
      return;
    }

    // Case 2: reordering existing blocks
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

  // ─── selection ───────────────────────────────────────────────────

  const selectedBlock =
    emailBlocks.find((b) => b.id === selectedBlockId) || null;

  // ─── personalization token insertion (for the parent to wire up) ─
  // We don't render a token panel inside the editor (it's better placed in
  // the page chrome), but we expose the insertion mechanism via the active
  // text editor ref. If/when the parent wants a token picker, it can call
  // `emailEditorRef.current.editor.insertToken('{{first_name}}')`.
  // Adding this without breaking the public API is optional; uncomment in
  // imperative handle if needed.

  // ─── render ──────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Mode tabs + deliverability indicator */}
      <div className="flex items-center justify-between border-b border-gray-200 px-4 flex-shrink-0">
        <div className="flex items-center">
          <ModeTab
            active={editMode === "drag-drop"}
            onClick={() => setEditMode("drag-drop")}
            icon={<MousePointer size={14} />}
          >
            Drag &amp; drop
          </ModeTab>
          <ModeTab
            active={editMode === "html"}
            onClick={() => setEditMode("html")}
            icon={<Code size={14} />}
          >
            HTML
          </ModeTab>
        </div>
        <button
          type="button"
          onClick={() => setShowDeliverabilityPanel((v) => !v)}
          className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium ${
            deliverability.warnings.length === 0
              ? "text-green-700 bg-green-50 hover:bg-green-100"
              : "text-amber-700 bg-amber-50 hover:bg-amber-100"
          }`}
          title="Show deliverability checks"
        >
          {deliverability.warnings.length === 0 ? (
            <CheckCircle size={12} />
          ) : (
            <AlertTriangle size={12} />
          )}
          {deliverability.score}/100
        </button>
      </div>

      {/* Optional deliverability panel */}
      {showDeliverabilityPanel && (
        <div className="border-b border-gray-200 bg-amber-50/50 px-4 py-2">
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

      {/* Body */}
      {editMode === "drag-drop" ? (
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
              onTextEditorReady={(ed) => {
                activeTextEditorRef.current = ed;
              }}
            />
            <BlockSettingsPanel
              block={selectedBlock}
              onChange={(updated) => updateBlock(updated.id, updated)}
              onDelete={() => selectedBlock && deleteBlock(selectedBlock.id)}
              onDuplicate={() =>
                selectedBlock && duplicateBlock(selectedBlock.id)
              }
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
          onChange={(v) => {
            setHtmlContent(v);
            fireChange();
          }}
        />
      )}
    </div>
  );
});

EmailEditor.displayName = "EmailEditor";

export default EmailEditor;

// ─── subcomponents ──────────────────────────────────────────────────

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

function Canvas({
  blocks,
  selectedId,
  onSelect,
  onChangeBlock,
  onTextEditorReady,
}) {
  // The whole inner area is a droppable. When you drag a palette item
  // onto an empty canvas (or into the empty space *below* existing blocks),
  // dnd-kit's `over` resolves to this id and handleDragEnd appends the
  // new block. Without this, palette → empty canvas would no-op because
  // there's nothing to "land on."
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
              // Click on empty canvas area → deselect
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
                {/* Tail spacer — lets users drop at the very end of the
                    list by aiming below the last block. The Canvas's own
                    droppable already handles this, but giving it visible
                    space makes the intent obvious. */}
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
      <p
        className={`text-sm font-medium ${
          isOver ? "text-blue-700" : "text-gray-500"
        }`}
      >
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
      <div
        className="pointer-events-none"
        dangerouslySetInnerHTML={{ __html: block.content }}
      />
    </div>
  );
}

function HtmlMode({ value, onChange }) {
  return (
    <div className="flex-1 min-h-0 flex flex-col bg-gray-50">
      <div className="px-4 py-2 border-b border-gray-200 bg-white">
        <p className="text-xs text-gray-500">
          Edit raw HTML. Personalization tokens like{" "}
          <code className="px-1 py-0.5 bg-gray-100 rounded">
            {"{{first_name}}"}
          </code>{" "}
          are preserved on send.
        </p>
      </div>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        className="flex-1 w-full p-4 font-mono text-xs leading-relaxed bg-white border-0 focus:outline-none resize-none"
        placeholder="<!doctype html>&#10;<html>&#10;  <body>&#10;    <p>Hello {{first_name}},</p>&#10;  </body>&#10;</html>"
      />
    </div>
  );
}
