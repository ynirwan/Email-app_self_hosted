import React, { useRef, useState, useEffect } from 'react';
import EmailEditor from '../components/EmailEditor';
import API from '../api';
import { useParams, useNavigate } from 'react-router-dom';

export default function FormDesigner() {
  const { formId } = useParams();
  const navigate = useNavigate();
  const emailEditorRef = useRef(null);
  const [formName, setFormName] = useState('');
  const [description, setDescription] = useState('');
  const [optInType, setOptInType] = useState('single');
  const [saving, setSaving] = useState(false);
  const [editorLoaded, setEditorLoaded] = useState(false);
  const [previewMode, setPreviewMode] = useState(false);
  const [previewHtml, setPreviewHtml] = useState('');
  const [loading, setLoading] = useState(formId ? true : false);

  // Load form if editing
  useEffect(() => {
    if (formId) {
      fetchForm();
    }
  }, [formId]);

  const fetchForm = async () => {
    try {
      const response = await API.get(`/forms/${formId}`);
      const form = response.data.form;
      setFormName(form.name);
      setDescription(form.description);
      setOptInType(form.opt_in_type);
    } catch (error) {
      console.error('Error fetching form:', error);
      alert('Failed to load form');
      navigate('/forms');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = () => {
    if (!formName.trim()) {
      alert('Form name is required');
      return;
    }

    setSaving(true);
    if (emailEditorRef.current) {
      emailEditorRef.current.editor.exportHtml((data) => {
        const { design, html } = data;

        const payload = {
          name: formName,
          description,
          opt_in_type: optInType,
          form_html: html,
          form_json: design,
        };

        const apiCall = formId 
          ? API.patch(`/forms/${formId}`, payload)
          : API.post('/forms', payload);

        apiCall
          .then((response) => {
            setSaving(false);
            alert(formId ? 'Form updated successfully!' : 'Form created successfully!');
            navigate('/forms');
          })
          .catch((err) => {
            alert('Failed to save form: ' + err.message);
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading form...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-6 bg-white rounded shadow flex flex-col">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold">
          {formId ? 'Edit Subscription Form' : 'Create Subscription Form'}
        </h2>
        <div className="flex space-x-3">
          <button
            onClick={togglePreview}
            className="px-4 py-2 bg-indigo-100 text-indigo-700 rounded hover:bg-indigo-200 transition"
            data-testid="button-preview-form"
          >
            {previewMode ? 'Exit Preview' : 'Preview Form'}
          </button>
          <button
            onClick={() => navigate('/forms')}
            className="px-4 py-2 bg-gray-500 text-white rounded hover:bg-gray-600 transition"
            data-testid="button-cancel-form"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !editorLoaded}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition disabled:opacity-50"
            data-testid="button-save-form"
          >
            {saving ? 'Saving...' : 'Save Form'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        <input
          placeholder="Form Name (e.g., Newsletter Signup)"
          value={formName}
          onChange={(e) => setFormName(e.target.value)}
          className="w-full px-3 py-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-600"
          data-testid="input-form-name-designer"
        />
        <textarea
          placeholder="Form Description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="w-full px-3 py-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-600 h-10"
          data-testid="input-form-description-designer"
        />
        <select
          value={optInType}
          onChange={(e) => setOptInType(e.target.value)}
          className="w-full px-3 py-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-600"
          data-testid="select-form-opt-in"
        >
          <option value="single">✅ Single Opt-In</option>
          <option value="double">📧 Double Opt-In</option>
        </select>
      </div>

      <div className="bg-blue-50 border border-blue-200 p-4 rounded mb-4 text-sm text-blue-700">
        <strong>Tip:</strong> Design your form using the editor below. Add text, input fields, and buttons to create a beautiful subscription form.
        Use <code className="bg-blue-100 px-2 py-1 rounded">{'{{email}}'}</code> to mark email input fields.
      </div>

      {previewMode ? (
        <div className="border rounded overflow-auto bg-gray-100 p-8" style={{ height: 600 }}>
          <div className="max-w-3xl mx-auto bg-white shadow-lg p-8 rounded">
            <div dangerouslySetInnerHTML={{ __html: previewHtml }} />
          </div>
        </div>
      ) : (
        <div className="my-6 border rounded overflow-hidden relative" style={{ height: 600 }}>
          <EmailEditor
            ref={emailEditorRef}
            onEditorLoaded={() => setEditorLoaded(true)}
          />
        </div>
      )}
    </div>
  );
}
