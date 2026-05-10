import React, { useEffect, useState, useRef, useCallback } from 'react';
import API from '../api';
import EmailEditor from '../components/EmailEditor';
import { Eye, X, Monitor, Smartphone, Tablet, Copy, ArrowLeft } from 'lucide-react';
import { useSettings } from "../contexts/SettingsContext";

// ─── helpers ────────────────────────────────────────────────

function useToast() {
  const [toasts, setToasts] = useState([]);
  const show = useCallback((message, type = 'info') => {
    const id = Date.now();
    setToasts(p => [...p, { id, message, type }]);
    const ttl = type === 'error' ? 8000 : 4000;
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), ttl);
  }, []);
  const dismiss = (id) => setToasts(p => p.filter(t => t.id !== id));
  return { toasts, show, dismiss };
}

function ToastContainer({ toasts, dismiss }) {
  return (
    <div className="fixed top-4 right-4 z-[100] space-y-2 pointer-events-none">
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

/** Normalize template mode: visual/legacy → html for display/filter purposes */
function normalizeMode(mode) {
  if (!mode || mode === 'legacy' || mode === 'visual') return 'html';
  return mode; // 'html' | 'drag-drop'
}

export default function TemplatesPage() {
  const { t, formatDate } = useSettings();
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
    if (isDirty && !confirm(t('templates.unsavedChanges'))) return;
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
        toast(t('templates.saved'), 'success');
      }).catch(err => {
        toast(err.response?.data?.detail || 'Failed to save template.', 'error');
        setSaving(false);
      });
    });
  };

  const handleEdit = (template) => { setEditTemplate(template); setIsDirty(false); };

  const handleDelete = async (template) => {
    if (!confirm(t('templates.deleteConfirm'))) return;
    try {
      await API.delete(`/templates/${template._id || template.id}`);
      setTemplates(prev => prev.filter(t => (t._id || t.id) !== (template._id || template.id)));
      toast(t('templates.deleted'), 'success');
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
    setEditTemplate({ name: '', preheader_text: '', description: '', content_json: { mode: 'drag-drop' }, fields: [] });
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
    return `<p style="color:#aaa;padding:2rem;text-align:center">${t('templates.noPreview')}</p>`;
  };

  // ── filter ───────────────────────────────────────────────
  // Normalize visual/legacy → html before comparing so those templates still show under "HTML"
  const filtered = templates.filter(tmpl => {
    if (modeFilter) {
      const effectiveMode = normalizeMode(tmpl.content_json?.mode);
      if (effectiveMode !== modeFilter) return false;
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      if (!(tmpl.name || '').toLowerCase().includes(q) &&
          !(tmpl.description || '').toLowerCase().includes(q)) return false;
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
                  {normalizeMode(previewTemplate.content_json?.mode).replace('-', ' ')} ·{' '}
                  {previewTemplate.fields?.length || 0} fields
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
                {previewTemplate.updated_at ? `Updated ${formatDate(previewTemplate.updated_at)}` : ''}
              </p>
              <div className="flex gap-2">
                <button onClick={() => { setPreviewTemplate(null); handleEdit(previewTemplate); }}
                  className="px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700">
                  {t('templates.edit')}
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

      {/* ── Full-screen Editor Overlay ── */}
      {editTemplate && (
        <div className="fixed inset-0 z-50 bg-white flex flex-col">
          {/* Single-row compact toolbar */}
          <div className="flex items-center gap-2 px-3 py-2 border-b bg-white flex-shrink-0 min-w-0">
            {/* Back button */}
            <button onClick={safeClose} disabled={saving}
              className="flex items-center gap-1 px-2 py-1.5 text-sm font-medium text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors flex-shrink-0 disabled:opacity-50">
              <ArrowLeft size={15} />
              <span className="hidden sm:inline">Templates</span>
            </button>

            <div className="w-px h-5 bg-gray-200 flex-shrink-0" />

            {/* Template name */}
            <input
              type="text"
              placeholder={t("templates.namePlaceholder")}
              value={editTemplate.name}
              onChange={e => { setEditTemplate(p => ({ ...p, name: e.target.value })); setIsDirty(true); }}
              className="w-48 sm:w-64 px-2.5 py-1.5 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none flex-shrink-0"
              autoFocus
            />

            {/* Preheader text — stretches to fill remaining space */}
            <input
              type="text"
              placeholder="Preheader text (inbox preview)…"
              maxLength={90}
              value={editTemplate.preheader_text || ''}
              onChange={e => { setEditTemplate(p => ({ ...p, preheader_text: e.target.value })); setIsDirty(true); }}
              className="flex-1 min-w-0 px-2.5 py-1.5 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />

            {/* Unsaved indicator */}
            {isDirty && (
              <span className="flex-shrink-0 text-xs text-amber-500 font-medium hidden sm:inline">● Unsaved</span>
            )}

            {/* Actions */}
            <button onClick={safeClose} disabled={saving}
              className="flex-shrink-0 px-3 py-1.5 border text-sm font-medium rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors">
              {t("common.cancel")}
            </button>
            <button onClick={handleSave} disabled={saving}
              className="flex-shrink-0 px-4 py-1.5 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors">
              {saving ? t('common.saving') : t('common.save')}
            </button>
          </div>

          {/* Editor fills remaining height */}
          <div className="flex-1 min-h-0">
            <EmailEditor
              ref={emailEditorRef}
              onLoad={handleEditorLoad}
              key={editTemplate._id || editTemplate.name || 'new'}
              onChange={() => setIsDirty(true)}
              templateMeta={editTemplate}
            />
          </div>
        </div>
      )}

      {/* ── List view (only shown when no editor overlay) ── */}
      {!editTemplate && (
        <>
          {/* List toolbar */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <button onClick={handleCreate}
              className="px-5 py-2.5 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 transition-colors">
              + {t('templates.create')}
            </button>
            <div className="flex items-center gap-2">
              <select value={modeFilter} onChange={e => setModeFilter(e.target.value)}
                className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-white text-gray-600 focus:ring-2 focus:ring-blue-500">
                <option value="">{t('templates.allModes')}</option>
                <option value="html">HTML</option>
                <option value="drag-drop">Drag &amp; Drop</option>
              </select>
              <div className="relative">
                <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs">🔍</span>
                <input type="text" placeholder={t('templates.search')} value={search}
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

          {/* Template list */}
          {filtered.length === 0 ? (
            <div className="bg-white rounded-xl border border-gray-200 py-16 text-center shadow-sm">
              <p className="text-3xl mb-2">📄</p>
              <p className="text-sm font-medium text-gray-700 mb-1">
                {search || modeFilter ? t('templates.noMatch') : t('templates.empty')}
              </p>
              {(search || modeFilter)
                ? <button onClick={() => { setSearch(''); setModeFilter(''); }} className="text-xs text-blue-600 mt-1 hover:underline">{t('common.clearFilters')}</button>
                : <p className="text-xs text-gray-400 mt-1 mb-4">Click "{t('templates.create')}" to build your first email template</p>
              }
              {!search && !modeFilter && (
                <button onClick={handleCreate} className="px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700">
                  {t('templates.create')}
                </button>
              )}
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
                <p className="text-xs text-gray-500">{t("templates.count" + (filtered.length !== 1 ? "_plural" : ""), { count: filtered.length })}</p>
              </div>
              <ul className="divide-y divide-gray-50">
                {filtered.map(template => {
                  const id = template._id || template.id;
                  const displayMode = normalizeMode(template.content_json?.mode);
                  return (
                    <li key={id} className="flex items-center justify-between px-5 py-3.5 hover:bg-gray-50 transition-colors">
                      <div className="flex-1 min-w-0 mr-4">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-medium text-sm text-gray-900">{template.name}</span>
                          <span className={`text-xs px-2 py-0.5 rounded-full ${
                            displayMode === 'drag-drop'
                              ? 'bg-purple-100 text-purple-700'
                              : 'bg-blue-100 text-blue-700'
                          }`}>
                            {displayMode === 'drag-drop' ? 'Drag & Drop' : 'HTML'}
                          </span>
                          {template.fields?.length > 0 && (
                            <span className="text-xs text-gray-400">{template.fields.length} field{template.fields.length !== 1 ? 's' : ''}</span>
                          )}
                        </div>
                        {template.description && (
                          <p className="text-xs text-gray-400 mt-0.5 truncate">{template.description}</p>
                        )}
                        <p className="text-xs text-gray-400 mt-1 flex items-center gap-2">
                          {template.created_at && (
                            <span>{t('templates.created')} {formatDate(template.created_at)}</span>
                          )}
                          {template.updated_at && template.updated_at !== template.created_at && (
                            <span className="text-gray-300">·</span>
                          )}
                          {template.updated_at && template.updated_at !== template.created_at && (
                            <span>{t('templates.edited')} {formatDate(template.updated_at)}</span>
                          )}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <button onClick={() => setPreviewTemplate(template)}
                          className="px-3 py-1.5 text-xs font-medium border border-purple-200 rounded-lg hover:bg-purple-50 text-purple-700 transition-colors flex items-center gap-1">
                          <Eye size={12} /> {t("common.preview")}
                        </button>
                        <button onClick={() => handleEdit(template)}
                          className="px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600 transition-colors">
                          {t("common.edit")}
                        </button>
                        <button onClick={() => handleDuplicate(template)}
                          className="px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600 transition-colors flex items-center gap-1">
                          <Copy size={12} /> {t("common.duplicate")}
                        </button>
                        <button onClick={() => handleDelete(template)}
                          className="px-3 py-1.5 text-xs font-medium border border-red-200 rounded-lg hover:bg-red-50 text-red-600 transition-colors">
                          {t("common.delete")}
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
