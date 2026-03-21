import React, { useEffect, useState, useRef, useCallback } from 'react';
import API from '../api';
import EmailEditor from '../components/EmailEditor';
import { Eye, X, Monitor, Smartphone, Tablet, Copy } from 'lucide-react';

// ─── helpers ────────────────────────────────────────────────
function useToast() {
  const [toasts, setToasts] = useState([]);
  const show = useCallback((message, type = 'info') => {
    const id = Date.now();
    setToasts(p => [...p, { id, message, type }]);
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 4000);
  }, []);
  const dismiss = (id) => setToasts(p => p.filter(t => t.id !== id));
  return { toasts, show, dismiss };
}

function ToastContainer({ toasts, dismiss }) {
  return (
    <div className="fixed top-4 right-4 z-50 space-y-2 pointer-events-none">
      {toasts.map(t => (
        <div key={t.id} onClick={() => dismiss(t.id)}
          className={`pointer-events-auto flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg text-sm font-medium cursor-pointer max-w-sm
            ${t.type === 'success' ? 'bg-green-600 text-white' : t.type === 'error' ? 'bg-red-600 text-white' : 'bg-gray-800 text-white'}`}>
          {t.type === 'success' ? '✓' : t.type === 'error' ? '✕' : 'ℹ'} {t.message}
        </div>
      ))}
    </div>
  );
}

export default function TemplatesPage() {
  const [templates, setTemplates]         = useState([]);
  const [loading, setLoading]             = useState(false);
  const [errorMsg, setErrorMsg]           = useState('');
  const [editTemplate, setEditTemplate]   = useState(null);
  const [saving, setSaving]               = useState(false);
  const [isDirty, setIsDirty]             = useState(false);
  const [previewTemplate, setPreviewTemplate] = useState(null);
  const [previewMode, setPreviewMode]     = useState('desktop');
  const [search, setSearch]               = useState('');
  const [modeFilter, setModeFilter]       = useState('');
  const emailEditorRef                    = useRef(null);
  const { toasts, show: toast, dismiss }  = useToast();

  useEffect(() => { loadTemplates(); }, []);

  const loadTemplates = async () => {
    setLoading(true); setErrorMsg('');
    try {
      const res = await API.get('/templates');
      setTemplates(res.data);
    } catch { setErrorMsg('Failed to load templates.'); }
    setLoading(false);
  };

  // ── unsaved guard ────────────────────────────────────────
  const safeClose = useCallback(() => {
    if (isDirty && !confirm('You have unsaved changes. Leave without saving?')) return;
    setEditTemplate(null); setIsDirty(false);
  }, [isDirty]);

  // ── editor callbacks ─────────────────────────────────────
  const handleEditorLoad = () => {
    setTimeout(() => {
      if (!emailEditorRef.current || !editTemplate) return;
      if (editTemplate.content_json && Object.keys(editTemplate.content_json).length > 0) {
        emailEditorRef.current.editor.loadDesign(editTemplate.content_json);
      } else {
        emailEditorRef.current.editor.loadBlank();
      }
    }, 300);
  };

  const handleSave = () => {
    if (!editTemplate.name?.trim()) { toast('Template name is required.', 'error'); return; }
    setSaving(true);
    if (!emailEditorRef.current) { setSaving(false); return; }

    const extractFields = (html) => {
      const matches = html.match(/{{\s*[\w]+\s*}}/g) || [];
      return [...new Set(matches.map(f => f.replace(/[{}]/g, '').trim()))];
    };

    emailEditorRef.current.editor.exportHtml((data) => {
      const { design, html: exportedHtml } = data;
      const trueHtml = exportedHtml?.trim() || '';
      const templateId = editTemplate._id || editTemplate.id;
      const payload = { ...editTemplate, content_json: design, fields: extractFields(trueHtml), html: trueHtml };

      const req = templateId ? API.put(`/templates/${templateId}`, payload) : API.post('/templates', payload);
      req.then(() => {
        setSaving(false); setIsDirty(false); setEditTemplate(null); loadTemplates();
        toast('Template saved', 'success');
      }).catch(err => {
        toast(err.response?.data?.detail || 'Failed to save template.', 'error');
        setSaving(false);
      });
    });
  };

  const handleEdit = (template) => { setEditTemplate(template); setIsDirty(false); };

  const handleDelete = async (template) => {
    if (!confirm(`Delete "${template.name}"?`)) return;
    try {
      await API.delete(`/templates/${template._id || template.id}`);
      setTemplates(prev => prev.filter(t => (t._id || t.id) !== (template._id || template.id)));
      toast('Template deleted', 'success');
    } catch { toast('Failed to delete template.', 'error'); }
  };

  const handleDuplicate = async (template) => {
    try {
      await API.post(`/templates/${template._id || template.id}/duplicate`);
      toast(`"${template.name}" duplicated`, 'success');
      loadTemplates();
    } catch { toast('Failed to duplicate template.', 'error'); }
  };

  const handleCreate = () => {
    setEditTemplate({ name: '', subject: '', preheader_text: '', description: '', content_json: { mode: 'visual' }, fields: [] });
    setIsDirty(false);
  };

  // ── preview ──────────────────────────────────────────────
  const renderTemplatePreview = (template) => {
    if (!template) return '';
    const j = template.content_json || {};
    if (j.mode === 'html' && j.content)          return j.content;
    if (j.mode === 'drag-drop' && j.blocks)       return j.blocks.map(b => b.content || '').join('\n');
    if (j.mode === 'visual' && j.content)         return j.content;
    if (template.html)                            return template.html;
    return '<p style="color:#aaa;padding:2rem;text-align:center">No preview available</p>';
  };

  // ── filter ───────────────────────────────────────────────
  const filtered = templates.filter(t => {
    if (modeFilter && (t.content_json?.mode || 'legacy') !== modeFilter) return false;
    if (search.trim()) {
      const q = search.toLowerCase();
      if (!(t.name || '').toLowerCase().includes(q) && !(t.subject || '').toLowerCase().includes(q) && !(t.description || '').toLowerCase().includes(q)) return false;
    }
    return true;
  });

  if (loading) return (
    <div className="space-y-4 animate-pulse">
      <div className="h-10 bg-gray-200 rounded-lg w-48" />
      {[...Array(3)].map((_, i) => <div key={i} className="h-16 bg-gray-200 rounded-xl" />)}
    </div>
  );

  return (
    <div className="space-y-5">
      <ToastContainer toasts={toasts} dismiss={dismiss} />

      {/* ── Preview Modal ── */}
      {previewTemplate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-5xl max-h-[92vh] flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3.5 border-b flex-shrink-0">
              <div>
                <p className="font-semibold text-sm">{previewTemplate.name}</p>
                <p className="text-xs text-gray-400">
                  {previewTemplate.content_json?.mode || 'legacy'} ·{' '}
                  {previewTemplate.fields?.length || 0} fields
                  {previewTemplate.subject && ` · "${previewTemplate.subject}"`}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {[
                  { mode: 'desktop', Icon: Monitor },
                  { mode: 'tablet',  Icon: Tablet },
                  { mode: 'mobile',  Icon: Smartphone },
                ].map(({ mode, Icon }) => (
                  <button key={mode} onClick={() => setPreviewMode(mode)}
                    className={`p-2 rounded-lg transition-colors ${previewMode === mode ? 'bg-blue-600 text-white' : 'hover:bg-gray-100 text-gray-500'}`}>
                    <Icon size={15} />
                  </button>
                ))}
                <div className="w-px h-5 bg-gray-200 mx-1" />
                <button onClick={() => setPreviewTemplate(null)} className="p-2 rounded-lg hover:bg-gray-100 text-gray-400">
                  <X size={16} />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-auto bg-gray-100 flex justify-center p-4">
              <div className={`bg-white shadow-lg transition-all duration-200 ${
                previewMode === 'desktop' ? 'w-full max-w-3xl' : previewMode === 'tablet' ? 'w-[768px]' : 'w-[375px]'
              }`} style={{ minHeight: 400, border: previewMode !== 'desktop' ? '2px solid #ccc' : 'none', borderRadius: previewMode !== 'desktop' ? 8 : 0 }}>
                <div className="p-4" dangerouslySetInnerHTML={{ __html: renderTemplatePreview(previewTemplate) }} />
              </div>
            </div>
            <div className="flex items-center justify-between px-5 py-3 border-t bg-gray-50 flex-shrink-0">
              <p className="text-xs text-gray-400">
                {previewTemplate.updated_at ? `Updated ${new Date(previewTemplate.updated_at).toLocaleDateString()}` : ''}
              </p>
              <div className="flex gap-2">
                <button onClick={() => { setPreviewTemplate(null); handleEdit(previewTemplate); }}
                  className="px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700">
                  Edit Template
                </button>
                <button onClick={() => setPreviewTemplate(null)}
                  className="px-4 py-2 border text-sm font-medium rounded-lg hover:bg-gray-100">
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Edit view ── */}
      {editTemplate ? (
        <div>
          {/* sticky editor toolbar */}
          <div className="sticky top-0 bg-white z-20 py-3 mb-4 border-b flex items-center justify-between gap-4">
            <div className="flex-1 min-w-0">
              <input type="text" placeholder="Template Name *"
                value={editTemplate.name}
                onChange={e => { setEditTemplate(p => ({ ...p, name: e.target.value })); setIsDirty(true); }}
                className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
                autoFocus />
            </div>
            <div className="flex gap-2 flex-shrink-0">
              <button onClick={safeClose} disabled={saving}
                className="px-4 py-2 border text-sm font-medium rounded-lg hover:bg-gray-50 disabled:opacity-50">
                Cancel
              </button>
              <button onClick={handleSave} disabled={saving}
                className="px-5 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50">
                {saving ? 'Saving…' : 'Save Template'}
              </button>
            </div>
          </div>

          {/* subject + preheader */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Subject Line</label>
              <input type="text" placeholder="Subject line (pre-fills when used in campaign)"
                value={editTemplate.subject || ''}
                onChange={e => { setEditTemplate(p => ({ ...p, subject: e.target.value })); setIsDirty(true); }}
                className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Preview Text <span className="text-gray-400 font-normal">(shown after subject in inbox)</span>
              </label>
              <input type="text" placeholder="Brief preview text visible in inbox…" maxLength={90}
                value={editTemplate.preheader_text || ''}
                onChange={e => { setEditTemplate(p => ({ ...p, preheader_text: e.target.value })); setIsDirty(true); }}
                className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
            </div>
          </div>

          <div style={{ height: 600 }}>
            <EmailEditor
              ref={emailEditorRef}
              onLoad={handleEditorLoad}
              key={editTemplate._id || editTemplate.name || 'new'}
              onChange={() => setIsDirty(true)}
            />
          </div>
        </div>
      ) : (
        <>
          {/* ── List toolbar ── */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <button onClick={handleCreate}
              className="px-5 py-2.5 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 transition-colors">
              + Create Template
            </button>
            <div className="flex items-center gap-2">
              <select value={modeFilter} onChange={e => setModeFilter(e.target.value)}
                className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-white text-gray-600 focus:ring-2 focus:ring-blue-500">
                <option value="">All modes</option>
                <option value="visual">Visual</option>
                <option value="html">HTML</option>
                <option value="drag-drop">Drag & Drop</option>
                <option value="legacy">Legacy</option>
              </select>
              <div className="relative">
                <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs">🔍</span>
                <input type="text" placeholder="Search templates…" value={search}
                  onChange={e => setSearch(e.target.value)}
                  className="pl-7 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 w-48" />
                {search && (
                  <button onClick={() => setSearch('')}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-300 hover:text-gray-500 text-xs">✕</button>
                )}
              </div>
            </div>
          </div>

          {errorMsg && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">{errorMsg}</div>
          )}

          {/* ── Template list ── */}
          {filtered.length === 0 ? (
            <div className="bg-white rounded-xl border border-gray-200 py-16 text-center shadow-sm">
              <p className="text-3xl mb-2">📄</p>
              <p className="text-sm font-medium text-gray-700 mb-1">
                {search || modeFilter ? 'No templates match your filters' : 'No templates yet'}
              </p>
              {(search || modeFilter)
                ? <button onClick={() => { setSearch(''); setModeFilter(''); }} className="text-xs text-blue-600 mt-1 hover:underline">Clear filters</button>
                : <p className="text-xs text-gray-400 mt-1 mb-4">Click "Create Template" to build your first email template</p>
              }
              {!search && !modeFilter && (
                <button onClick={handleCreate} className="px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700">
                  Create Template
                </button>
              )}
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
                <p className="text-xs text-gray-500">{filtered.length} template{filtered.length !== 1 ? 's' : ''}</p>
              </div>
              <ul className="divide-y divide-gray-50">
                {filtered.map(template => {
                  const id = template._id || template.id;
                  return (
                    <li key={id} className="flex items-center justify-between px-5 py-3.5 hover:bg-gray-50 transition-colors">
                      <div className="flex-1 min-w-0 mr-4">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-medium text-sm text-gray-900">{template.name}</span>
                          <span className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full">
                            {template.content_json?.mode || 'legacy'}
                          </span>
                          {template.fields?.length > 0 && (
                            <span className="text-xs text-gray-400">{template.fields.length} field{template.fields.length !== 1 ? 's' : ''}</span>
                          )}
                        </div>
                        {template.subject && (
                          <p className="text-xs text-gray-400 mt-0.5 truncate">Subject: {template.subject}</p>
                        )}
                        {template.description && !template.subject && (
                          <p className="text-xs text-gray-400 mt-0.5 truncate">{template.description}</p>
                        )}
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <button onClick={() => setPreviewTemplate(template)}
                          className="px-3 py-1.5 text-xs font-medium border border-purple-200 rounded-lg hover:bg-purple-50 text-purple-700 transition-colors flex items-center gap-1">
                          <Eye size={12} /> Preview
                        </button>
                        <button onClick={() => handleEdit(template)}
                          className="px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600 transition-colors">
                          Edit
                        </button>
                        <button onClick={() => handleDuplicate(template)}
                          className="px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600 transition-colors flex items-center gap-1">
                          <Copy size={12} /> Duplicate
                        </button>
                        <button onClick={() => handleDelete(template)}
                          className="px-3 py-1.5 text-xs font-medium border border-red-200 rounded-lg hover:bg-red-50 text-red-600 transition-colors">
                          Delete
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}