// frontend/src/components/editor/SortableBlock.jsx
//
// A single sortable block inside the drag-drop canvas.
//
// Props:
//   block              {Object}   — { id, type, content, styles, position }
//   selected           {boolean}
//   onSelect           {function} — () => void
//   onChange           {function} — (updatedBlock) => void
//   onTextEditorReady  {function|undefined} — passed down to TextBlockEditor
//                       as `onReady`; only provided when this block is selected

import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical } from "lucide-react";
import TextBlockEditor from "./TextBlockEditor";
import { getBlockDefinition } from "./blockDefinitions";

export default function SortableBlock({
  block,
  selected,
  onSelect,
  onChange,
  onTextEditorReady,
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: block.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const def = getBlockDefinition(block.type);
  const isRichText = def?.richText === true;

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`relative group rounded-md border-2 transition-colors ${
        isDragging ? "opacity-30 z-50" : ""
      } ${
        selected
          ? "border-blue-400 bg-blue-50/20"
          : "border-transparent hover:border-gray-200"
      }`}
      onClick={(e) => {
        e.stopPropagation();
        onSelect();
      }}
    >
      {/* ── Drag handle — visible on hover ─────────────────────────── */}
      <div
        {...attributes}
        {...listeners}
        className="absolute -left-5 top-1/2 -translate-y-1/2 w-5 h-8
          flex items-center justify-center
          cursor-grab active:cursor-grabbing
          text-gray-300 hover:text-gray-500
          opacity-0 group-hover:opacity-100 transition-opacity"
        // Don't propagate to block selection
        onClick={(e) => e.stopPropagation()}
      >
        <GripVertical size={14} />
      </div>

      {/* ── Block content ───────────────────────────────────────────── */}
      <div className="p-2">
        {isRichText ? (
          // Tiptap editor for text / header blocks.
          // The toolbar is shown inline above the content — clicking inside
          // the editor area already sets this block as selected via the
          // outer div's onClick, so TextBlockEditor only needs to
          // stopPropagation to prevent deselect.
          <TextBlockEditor
            content={block.content}
            onChange={(html) => onChange({ ...block, content: html })}
            onReady={onTextEditorReady}
          />
        ) : (
          // Static preview for non-rich-text blocks.
          // pointer-events-none so clicks fall through to the outer div,
          // triggering selection rather than activating links/buttons.
          <div
            className="pointer-events-none"
            dangerouslySetInnerHTML={{ __html: block.content }}
          />
        )}
      </div>
    </div>
  );
}
