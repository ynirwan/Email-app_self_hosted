// src/components/RichTextEditor.jsx
import { Editor } from '@tinymce/tinymce-react';
import { useRef } from 'react';

export default function RichTextEditor({ value, onChange }) {
  const editorRef = useRef(null);

  return (
    <Editor
      value={value}
      onEditorChange={(newValue) => onChange(newValue)}
      onInit={(evt, editor) => (editorRef.current = editor)}
      init={{
        height: 300,
        menubar: false,
        plugins: [
          'advlist autolink lists link image charmap preview anchor',
          'searchreplace visualblocks code fullscreen',
          'insertdatetime media table paste code help wordcount'
        ],
        toolbar:
          'undo redo | formatselect | bold italic backcolor | ' +
          'alignleft aligncenter alignright alignjustify | ' +
          'bullist numlist outdent indent | removeformat | help',

        // 👇 Use local TinyMCE
        base_url: '/tinymce', // Path to public/tinymce
        suffix: '.min'        // Looks for tinymce.min.js, etc.

        // ✅ GPL version doesn't require license_key
        // If you do add one, keep it as: license_key: 'gpl'
      }}
    />
  );
}

