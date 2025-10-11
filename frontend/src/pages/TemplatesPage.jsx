import React, { useEffect, useState, useRef } from "react";
import API from "../api";
import EmailEditor from "../components/EmailEditor";
import { Eye, X, Monitor, Smartphone, Tablet } from "lucide-react";

export default function TemplatesPage() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [editTemplate, setEditTemplate] = useState(null);
  const [saving, setSaving] = useState(false);
  const [previewTemplate, setPreviewTemplate] = useState(null); // Preview state
  const [previewMode, setPreviewMode] = useState('desktop'); // Preview device mode
  const emailEditorRef = useRef(null);

  useEffect(() => {
    loadTemplates();
  }, []);

  const loadTemplates = async () => {
    setLoading(true);
    setErrorMsg("");
    try {
      const response = await API.get("/templates");
      setTemplates(response.data);
    } catch (err) {
      setErrorMsg("Failed to load templates.");
    }
    setLoading(false);
  };

  const handleEdit = (template) => {
    console.log("Editing template:", template);
    console.log("Template content_json:", template.content_json);
    setEditTemplate(template);
  };

  const handlePreview = (template) => {
    console.log("Previewing template:", template);
    setPreviewTemplate(template);
  };

  const handleDelete = async (template) => {
    if (!window.confirm(`Delete template "${template.name}"?`)) return;
    try {
      await API.delete(`/templates/${template._id || template.id}`);
      setTemplates((prev) =>
        prev.filter((t) => (t._id || t.id) !== (template._id || template.id))
      );
    } catch {
      alert("Failed to delete template.");
    }
  };

  const handleEditorLoad = () => {
    console.log("=== Editor Load Debug ===");
    console.log("editTemplate:", editTemplate);
    console.log("emailEditorRef.current:", emailEditorRef.current);
    
    setTimeout(() => {
      if (!emailEditorRef.current || !editTemplate) {
        console.log("Editor or template not ready");
        return;
      }
      
      console.log("Loading template:", editTemplate.name);
      console.log("Template content_json:", editTemplate.content_json);
      
      if (editTemplate.content_json && Object.keys(editTemplate.content_json).length > 0) {
        console.log("Calling loadDesign with:", editTemplate.content_json);
        emailEditorRef.current.editor.loadDesign(editTemplate.content_json);
      } else {
        console.log("Loading blank editor - no content_json");
        emailEditorRef.current.editor.loadBlank();
      }
    }, 300);
  };

  const handleSave = () => {
    if (!editTemplate.name || !editTemplate.name.trim()) {
      alert("Template name is required.");
      return;
    }
    setSaving(true);
    
    if (!emailEditorRef.current) {
      setSaving(false);
      return;
    }

    const extractFields = (html) => {
      const matches = html.match(/{{\s*[\w]+\s*}}/g) || [];
      return [...new Set(matches.map((f) => f.replace(/[{}]/g, "").trim()))];
    };

    emailEditorRef.current.editor.exportHtml((data) => {
      console.log("Export data:", data);
      const { design, html: exportedHtml } = data;
      const trueHtml = exportedHtml?.trim() || "";
      const templateId = editTemplate._id || editTemplate.id;
      
      const payload = {
        ...editTemplate,
        content_json: design,
        fields: extractFields(trueHtml),
        html: trueHtml,
      };

      console.log("Saving payload:", payload);

      const req = templateId
        ? API.put(`/templates/${templateId}`, payload)
        : API.post("/templates", payload);

      req
        .then(() => {
          setSaving(false);
          setEditTemplate(null);
          loadTemplates();
        })
        .catch((error) => {
          console.error("Save error:", error);
          alert("Failed to save template.");
          setSaving(false);
        });
    });
  };

  const handleCreate = () => {
    setEditTemplate({ 
      name: "", 
      description: "", 
      content_json: { mode: "visual" },
      fields: [] 
    });
  };

  // Render template content for preview
  const renderTemplatePreview = (template) => {
    if (!template) return "";

    const contentJson = template.content_json || {};
    
    // Handle different template modes
    if (contentJson.mode === 'html' && contentJson.content) {
      return contentJson.content;
    } else if (contentJson.mode === 'drag-drop' && contentJson.blocks) {
      return contentJson.blocks.map(block => block.content || '').join('\n');
    } else if (contentJson.mode === 'visual' && contentJson.content) {
      return contentJson.content;
    } else if (template.html) {
      // Fallback to stored HTML
      return template.html;
    } else if (contentJson.body && contentJson.body.rows) {
      // Handle legacy Unlayer format
      let extractedHtml = '';
      try {
        contentJson.body.rows.forEach(row => {
          row.columns?.forEach(column => {
            column.contents?.forEach(content => {
              if (content.type === 'html' && content.values?.html) {
                extractedHtml += content.values.html + '\n';
              }
            });
          });
        });
        return extractedHtml;
      } catch (e) {
        console.error('Error extracting HTML from legacy format:', e);
        return '<p>Error rendering template preview</p>';
      }
    }
    
    return '<p>No preview available</p>';
  };

  if (loading) {
    return (
      <div className="p-6 text-center text-lg font-semibold">
        Loading templates...
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-6 bg-white rounded shadow">
      <h1 className="text-3xl font-bold mb-6 border-b pb-2">Email Templates</h1>
      
      {/* Preview Modal */}
      {previewTemplate && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg max-w-6xl w-full max-h-[90vh] overflow-hidden">
            {/* Modal Header */}
            <div className="border-b p-4 flex justify-between items-center">
              <div>
                <h2 className="text-xl font-semibold">Preview: {previewTemplate.name}</h2>
                <p className="text-sm text-gray-600">
                  Mode: {previewTemplate.content_json?.mode || 'unknown'} • 
                  Fields: {previewTemplate.fields?.length || 0}
                </p>
              </div>
              
              {/* Device Mode Buttons */}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPreviewMode('desktop')}
                  className={`p-2 rounded flex items-center gap-1 ${previewMode === 'desktop' ? 'bg-blue-600 text-white' : 'hover:bg-gray-200'}`}
                  title="Desktop Preview"
                >
                  <Monitor size={16} />
                </button>
                <button
                  onClick={() => setPreviewMode('tablet')}
                  className={`p-2 rounded flex items-center gap-1 ${previewMode === 'tablet' ? 'bg-blue-600 text-white' : 'hover:bg-gray-200'}`}
                  title="Tablet Preview"
                >
                  <Tablet size={16} />
                </button>
                <button
                  onClick={() => setPreviewMode('mobile')}
                  className={`p-2 rounded flex items-center gap-1 ${previewMode === 'mobile' ? 'bg-blue-600 text-white' : 'hover:bg-gray-200'}`}
                  title="Mobile Preview"
                >
                  <Smartphone size={16} />
                </button>
                
                <div className="w-px h-6 bg-gray-300 mx-2"></div>
                
                <button
                  onClick={() => setPreviewTemplate(null)}
                  className="p-2 rounded hover:bg-gray-200"
                  title="Close Preview"
                >
                  <X size={20} />
                </button>
              </div>
            </div>

            {/* Modal Content */}
            <div className="p-4 bg-gray-100 flex justify-center overflow-auto max-h-[70vh]">
              <div
                className={`bg-white shadow-lg transition-all duration-300 ${
                  previewMode === 'desktop' ? 'w-full max-w-4xl' :
                  previewMode === 'tablet' ? 'w-[768px]' : 'w-[375px]'
                }`}
                style={{
                  minHeight: '400px',
                  border: previewMode !== 'desktop' ? '2px solid #ccc' : 'none',
                  borderRadius: previewMode !== 'desktop' ? '8px' : '0'
                }}
              >
                <div
                  className="p-4"
                  dangerouslySetInnerHTML={{
                    __html: renderTemplatePreview(previewTemplate)
                  }}
                />
              </div>
            </div>

            {/* Modal Footer */}
            <div className="border-t p-4 bg-gray-50 flex justify-between items-center">
              <div className="text-sm text-gray-600">
                Last updated: {previewTemplate.updated_at ? 
                  new Date(previewTemplate.updated_at).toLocaleDateString() : 'Unknown'}
              </div>
              <div className="flex gap-3">
                <button
                  onClick={() => {
                    setPreviewTemplate(null);
                    handleEdit(previewTemplate);
                  }}
                  className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition"
                >
                  Edit Template
                </button>
                <button
                  onClick={() => setPreviewTemplate(null)}
                  className="px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700 transition"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {!editTemplate ? (
        <>
          <button
            onClick={handleCreate}
            className="mb-6 px-5 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition"
          >
            + Create Template
          </button>
          
          {errorMsg ? (
            <p className="text-red-600 font-semibold">{errorMsg}</p>
          ) : templates.length === 0 ? (
            <p className="text-gray-600">
              No templates found. Click "Create Template" to start.
            </p>
          ) : (
            <ul className="divide-y border rounded">
              {templates.map((template) => (
                <li
                  key={template._id || template.id}
                  className="flex justify-between items-center px-4 py-3 hover:bg-gray-50"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <span className="font-medium">{template.name}</span>
                      <span className="text-xs px-2 py-1 bg-blue-100 text-blue-800 rounded-full">
                        {template.content_json?.mode || 'legacy'}
                      </span>
                    </div>
                    <div className="text-sm text-gray-500 mt-1">
                      {template.description && (
                        <span>{template.description} • </span>
                      )}
                      {template.fields?.length > 0 && (
                        <span>{template.fields.length} personalization field{template.fields.length !== 1 ? 's' : ''}</span>
                      )}
                    </div>
                  </div>
                  
                  <div className="flex items-center space-x-3">
                    <button
                      onClick={() => handlePreview(template)}
                      className="px-3 py-1 bg-purple-600 text-white rounded hover:bg-purple-700 transition flex items-center gap-1"
                      title="Preview Template"
                    >
                      <Eye size={14} />
                      Preview
                    </button>
                    <button
                      onClick={() => handleEdit(template)}
                      className="px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700 transition"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDelete(template)}
                      className="px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700 transition"
                    >
                      Delete
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <div>
          {/* Sticky header bar with Save/Cancel */}
          <div className="sticky top-0 bg-white z-20 pb-3 mb-4 border-b flex justify-between items-center">
            <h2 className="text-xl font-semibold">
              {editTemplate._id || editTemplate.id
                ? "Edit Template"
                : "Create New Template"}
            </h2>
            <div className="flex space-x-3">
              <button
                onClick={() => setEditTemplate(null)}
                disabled={saving}
                className="px-5 py-2 bg-gray-400 text-white rounded hover:bg-gray-500 transition"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-5 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition"
              >
                {saving ? "Saving..." : "Save Template"}
              </button>
            </div>
          </div>
          
          <input
            type="text"
            placeholder="Template Name"
            value={editTemplate.name}
            onChange={(e) =>
              setEditTemplate({ ...editTemplate, name: e.target.value })
            }
            className="block mb-3 w-full px-3 py-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-600"
            autoFocus
          />
          
          <textarea
            rows={3}
            placeholder="Description (optional)"
            value={editTemplate.description || ""}
            onChange={(e) =>
              setEditTemplate({ ...editTemplate, description: e.target.value })
            }
            className="block mb-4 w-full px-3 py-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-600"
          />
          
          <div style={{ height: 600 }}>
            <EmailEditor 
              ref={emailEditorRef} 
              onLoad={handleEditorLoad}
              key={editTemplate._id || editTemplate.name || 'new'}
            />
          </div>
        </div>
      )}
    </div>
  );
}

