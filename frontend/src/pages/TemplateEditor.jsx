// frontend/src/pages/TemplateEditor.jsx
import React, { useRef, useState } from 'react';
import EmailEditor from '../components/EmailEditor';
import API from '../api';

export default function TemplateEditor({ onSaved }) {
  const emailEditorRef = useRef(null);
  const [templateName, setTemplateName] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);
  const [editorLoaded, setEditorLoaded] = useState(false);
  const [placeholders, setPlaceholders] = useState([]);

  const extractFields = (html) => {
    const matches = html.match(/{{\s*[\w]+\s*}}/g) || [];
    return [...new Set(matches.map(f => f.replace(/[{}]/g, '').trim()))];
  };

  const handleSave = () => {
    if (!templateName.trim()) {
      alert('Template name is required');
      return;
    }

    setSaving(true);
    if (emailEditorRef.current) {
      emailEditorRef.current.editor.exportHtml((data) => {
        const { design, html } = data;
        const fields = extractFields(html);
        setPlaceholders(fields);

        API.post('/templates', {
          name: templateName,
          description,
          content_json: design,
          fields,
          html,
        })
          .then(() => {
            setSaving(false);
            if (onSaved) onSaved();
          })
          .catch((err) => {
            alert('Failed to save template: ' + err.message);
            setSaving(false);
          });
      });
    }
  };

  return (
    <div className="max-w-6xl mx-auto p-6 bg-white rounded shadow flex flex-col">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold">Create/Edit Email Template</h2>
        <div className="flex space-x-3">
          <button
            onClick={() => onSaved && onSaved()}
            className="px-4 py-2 bg-gray-500 text-white rounded hover:bg-gray-600 transition"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !editorLoaded}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Template'}
          </button>
        </div>
      </div>

      <input
        placeholder="Template Name"
        value={templateName}
        onChange={(e) => setTemplateName(e.target.value)}
        className="block mb-3 w-full px-3 py-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-600"
      />

      <textarea
        placeholder="Description"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        rows={3}
        className="block mb-4 w-full px-3 py-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-600"
      />

      <div className="my-6 border rounded overflow-hidden" style={{ height: 600 }}>
        <EmailEditor
          ref={emailEditorRef}
          onLoad={() => setEditorLoaded(true)}
          minHeight={500}
        />
      </div>

      {placeholders.length > 0 && (
        <div className="mt-6">
          <h3 className="font-semibold">Placeholders Detected:</h3>
          <ul className="list-disc ml-6 text-sm text-gray-600">
            {placeholders.map((field) => (
              <li key={field}>{field}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

