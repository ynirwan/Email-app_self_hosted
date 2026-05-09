// frontend/src/components/editor/BlockPalette.jsx
//
// Left-hand palette of draggable block types. Each item uses @dnd-kit/core's
// `useDraggable` — not `useSortable` — because palette items are dragged
// FROM the palette ONTO the canvas, not reordered within it.
//
// PALETTE_ID_PREFIX is prepended to every palette drag id so that
// handleDragEnd in EmailEditor can distinguish "new block from palette"
// vs "reorder existing block".

import { useDraggable } from "@dnd-kit/core";
import {
  groupBlocksByCategory,
  getCategoryLabel,
} from "./blockDefinitions";

export const PALETTE_ID_PREFIX = "palette:";

// ── Single draggable palette item ────────────────────────────────────────────

function PaletteItem({ def }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `${PALETTE_ID_PREFIX}${def.id}`,
  });

  const Icon = def.icon;

  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm text-gray-700
        bg-white border border-gray-200 select-none
        hover:border-blue-400 hover:bg-blue-50
        cursor-grab active:cursor-grabbing
        transition-colors duration-100
        ${isDragging ? "opacity-30" : ""}`}
    >
      <Icon size={13} className="text-gray-400 flex-shrink-0" />
      <span className="truncate leading-none">{def.name}</span>
    </div>
  );
}

// ── Palette panel ─────────────────────────────────────────────────────────────

export default function BlockPalette() {
  const groups = groupBlocksByCategory();

  return (
    <div className="w-52 flex-shrink-0 border-r border-gray-200 overflow-y-auto bg-gray-50 p-3 space-y-4">
      {groups.map(({ category, items }) => (
        <div key={category}>
          <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1.5 px-1">
            {getCategoryLabel(category)}
          </p>
          <div className="space-y-1">
            {items.map((def) => (
              <PaletteItem key={def.id} def={def} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
