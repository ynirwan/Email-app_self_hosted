// frontend/src/components/editor/TextBlockEditor.jsx
//
// Tiptap-powered inline rich-text editor for "text" and "header" blocks.
//
// CONTRACT:
//   Props:
//     content  {string}   — HTML string read from block.content
//     onChange {function} — called with new HTML string on every change
//     onReady  {function} — optional; called with the Tiptap editor instance
//                          once it is initialised (used by EmailEditor to
//                          expose token-insertion via activeTextEditorRef)
//
//   The component is "controlled" in the sense that external `content`
//   changes (e.g. loadDesign) are applied to the editor. To avoid infinite
//   update loops we compare incoming HTML against the editor's current HTML
//   before calling setContent.
//
// NOTE: Inline styles already present in the initial content (e.g. the
//   default heading color/size) are preserved by Tiptap's HTML parser.
//   Styles applied via the toolbar use marks/node attrs; for deeper style
//   control add @tiptap/extension-text-style + @tiptap/extension-color.

import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import Link from "@tiptap/extension-link";
import TextAlign from "@tiptap/extension-text-align";
import { useEffect, useRef } from "react";
import {
  Bold,
  Italic,
  Underline as UnderlineIcon,
  Link as LinkIcon,
  AlignLeft,
  AlignCenter,
  AlignRight,
} from "lucide-react";

// ── Tiptap configuration ─────────────────────────────────────────────────────

const EXTENSIONS = [
  StarterKit.configure({
    // Disable code block — not needed for email
    codeBlock: false,
    // Keep paragraph, bold, italic, strike, heading, lists, etc.
  }),
  Underline,
  Link.configure({
    openOnClick: false,   // don't navigate on click inside the editor
    autolink: false,
    HTMLAttributes: { target: "_blank", rel: "noopener noreferrer" },
  }),
  TextAlign.configure({
    types: ["heading", "paragraph"],
  }),
];

// ── Component ────────────────────────────────────────────────────────────────

export default function TextBlockEditor({ content, onChange, onReady }) {
  // Track the last content we set externally so we don't re-apply on internal
  // keystrokes (which would reset cursor position).
  const lastExternalContent = useRef(content);

  const editor = useEditor({
    extensions: EXTENSIONS,
    content,
    // onUpdate fires on every keystroke / paste / undo
    onUpdate: ({ editor }) => {
      const html = editor.getHTML();
      lastExternalContent.current = html; // keep in sync so useEffect skips it
      onChange(html);
    },
    editorProps: {
      attributes: {
        class: "outline-none min-h-[1.5em] focus:outline-none",
      },
    },
  });

  // Sync when content changes from outside (e.g., loadDesign, undo from parent)
  useEffect(() => {
    if (!editor) return;
    if (content === lastExternalContent.current) return;   // already current
    const current = editor.getHTML();
    if (content !== current) {
      // false = don't fire onUpdate callback, avoiding the loop
      editor.commands.setContent(content, false);
      lastExternalContent.current = content;
    }
  }, [content, editor]);

  // Expose the raw Tiptap editor instance to the parent
  useEffect(() => {
    if (editor && onReady) {
      onReady(editor);
    }
  }, [editor, onReady]);

  if (!editor) return null;

  return (
    // Stop click propagation so block selection doesn't toggle when clicking
    // inside the text area.
    <div
      className="text-block-editor"
      onClick={(e) => e.stopPropagation()}
    >
      <Toolbar editor={editor} />
      <EditorContent
        editor={editor}
        className="prose prose-sm max-w-none px-1 py-0.5 cursor-text"
      />
    </div>
  );
}

// ── Toolbar ──────────────────────────────────────────────────────────────────

function Toolbar({ editor }) {
  if (!editor) return null;

  // Use onMouseDown + preventDefault so the editor never loses focus when
  // a toolbar button is clicked (standard Tiptap pattern).
  const Btn = ({ title, active, onMouseDown, children }) => (
    <button
      type="button"
      title={title}
      onMouseDown={(e) => {
        e.preventDefault();
        onMouseDown(e);
      }}
      className={`p-1 rounded transition-colors ${
        active
          ? "bg-blue-100 text-blue-700"
          : "text-gray-500 hover:bg-gray-100 hover:text-gray-800"
      }`}
    >
      {children}
    </button>
  );

  const handleLink = (e) => {
    e.preventDefault();
    if (editor.isActive("link")) {
      editor.chain().focus().unsetLink().run();
    } else {
      const url = window.prompt("URL", "https://");
      if (url) {
        editor.chain().focus().setLink({ href: url }).run();
      }
    }
  };

  return (
    <div
      className="flex items-center flex-wrap gap-0.5 border-b border-gray-100 pb-1 mb-1"
      // Prevent the whole toolbar row from bubbling up and triggering block
      // selection/deselection.
      onMouseDown={(e) => e.stopPropagation()}
    >
      {/* Text style */}
      <Btn
        title="Bold"
        active={editor.isActive("bold")}
        onMouseDown={() => editor.chain().focus().toggleBold().run()}
      >
        <Bold size={12} />
      </Btn>
      <Btn
        title="Italic"
        active={editor.isActive("italic")}
        onMouseDown={() => editor.chain().focus().toggleItalic().run()}
      >
        <Italic size={12} />
      </Btn>
      <Btn
        title="Underline"
        active={editor.isActive("underline")}
        onMouseDown={() => editor.chain().focus().toggleUnderline().run()}
      >
        <UnderlineIcon size={12} />
      </Btn>

      <span className="w-px h-4 bg-gray-200 mx-0.5" />

      {/* Headings */}
      {[1, 2, 3].map((level) => (
        <Btn
          key={level}
          title={`Heading ${level}`}
          active={editor.isActive("heading", { level })}
          onMouseDown={() =>
            editor.chain().focus().toggleHeading({ level }).run()
          }
        >
          <span className="text-[10px] font-bold leading-none">H{level}</span>
        </Btn>
      ))}

      <span className="w-px h-4 bg-gray-200 mx-0.5" />

      {/* Alignment */}
      <Btn
        title="Align left"
        active={editor.isActive({ textAlign: "left" })}
        onMouseDown={() =>
          editor.chain().focus().setTextAlign("left").run()
        }
      >
        <AlignLeft size={12} />
      </Btn>
      <Btn
        title="Align centre"
        active={editor.isActive({ textAlign: "center" })}
        onMouseDown={() =>
          editor.chain().focus().setTextAlign("center").run()
        }
      >
        <AlignCenter size={12} />
      </Btn>
      <Btn
        title="Align right"
        active={editor.isActive({ textAlign: "right" })}
        onMouseDown={() =>
          editor.chain().focus().setTextAlign("right").run()
        }
      >
        <AlignRight size={12} />
      </Btn>

      <span className="w-px h-4 bg-gray-200 mx-0.5" />

      {/* Link */}
      <Btn
        title={editor.isActive("link") ? "Remove link" : "Add link"}
        active={editor.isActive("link")}
        onMouseDown={handleLink}
      >
        <LinkIcon size={12} />
      </Btn>
    </div>
  );
}
