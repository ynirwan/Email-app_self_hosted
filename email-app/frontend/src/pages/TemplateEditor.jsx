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

  const [previewMode, setPreviewMode] = useState(false);
  const [previewHtml, setPreviewHtml] = useState('');

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

  const togglePreview = () => {
    if (!previewMode && emailEditorRef.current) {
      emailEditorRef.current.editor.exportHtml((data) => {
        setPreviewHtml(data.html);
        setPreviewMode(true);
      });
    } else {
      setPreviewMode(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto p-6 bg-white rounded shadow flex flex-col">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold">Create/Edit Email Template</h2>
        <div className="flex space-x-3">
          <button
            onClick={togglePreview}
            className="px-4 py-2 bg-indigo-100 text-indigo-700 rounded hover:bg-indigo-200 transition"
          >
            {previewMode ? 'Exit Preview' : 'Preview Mode'}
          </button>
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

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <input
          placeholder="Template Name"
          value={templateName}
          onChange={(e) => setTemplateName(e.target.value)}
          className="w-full px-3 py-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-600"
        />
        <div className="flex items-center gap-2 px-3 py-2 bg-blue-50 text-blue-700 text-sm rounded">
          <span>Tip: Use <b>{"{{first_name}}"}</b> for personalization</span>
        </div>
      </div>

      <textarea
        placeholder="Short description for this template..."
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        rows={2}
        className="block mb-4 w-full px-3 py-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-600"
      />

      <div className="my-6 border rounded overflow-hidden relative" style={{ height: 600 }}>
        {previewMode && (
          <div className="absolute inset-0 z-10 bg-gray-100 p-4 overflow-auto">
             <div className="max-w-3xl mx-auto bg-white shadow-lg p-8 rounded min-h-full">
                <div className="mb-4 border-b pb-2 text-gray-500 text-xs uppercase tracking-widest font-bold">
                   Template Preview
                </div>
                <div dangerouslySetInnerHTML={{ __html: previewHtml || '<p>Loading preview...</p>' }} />
             </div>
          </div>
        )}
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

