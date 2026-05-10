import React, { useEffect, useState, useRef, useCallback } from 'react';
import API from '../api';
import EmailEditor from '../components/EmailEditor';
import TemplateCard from '../components/TemplateCard';
import { X, Monitor, Smartphone, Tablet, Plus, Search as SearchIcon } from 'lucide-react';
import { useSettings } from "../contexts/SettingsContext";
import { getTemplateHtml } from '../utils/templateRender';

// ─── helpers ────────────────────────────────────────────────

function useToast() {
  const [toasts, setToasts] = useState([]);
  const show = useCallback((message, type = 'info') => {
    const id = Date.now();
    setToasts(p => [...p, { id, message, type }]);
    // Errors stay longer so the user can read campaign names in the message
    const ttl = type === 'error' ? 8000 : 4000;
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), ttl);
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
    setEditTemplate({ name: '', subject: '', preheader_text: '', description: '', content_json: { mode: 'visual' }, fields: [] });
    setIsDirty(false);
  };

  // ── preview ──────────────────────────────────────────────
  const renderTemplatePreview = (template) => {
    const html = getTemplateHtml(template);
    if (html) return html;
    return `<p style="color:#aaa;padding:2rem;text-align:center">${t('templates.noPreview')}</p>`;
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
    <div className="space-y-5 animate-pulse">
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <div className="h-6 bg-gray-200 rounded w-40" />
          <div className="h-3 bg-gray-100 rounded w-64" />
        </div>
        <div className="h-9 bg-gray-200 rounded-lg w-36" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {[...Array(8)].map((_, i) => (
          <div key={i} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="h-64 bg-gray-100" />
            <div className="p-4 space-y-2">
              <div className="h-3 bg-gray-200 rounded w-3/4" />
              <div className="h-2 bg-gray-100 rounded w-1/2" />
            </div>
          </div>
        ))}
      </div>
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
                {saving ? t('common.saving') : t('common.save')}
              </button>
            </div>
          </div>

          {/* subject + preheader */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">{t('campaign.form.subject')}</label>
              <input type="text" placeholder="Subject line (pre-fills when used in campaign)"
                value={editTemplate.subject || ''}
                onChange={e => { setEditTemplate(p => ({ ...p, subject: e.target.value })); setIsDirty(true); }}
                className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                {t('templates.previewText')} <span className="text-gray-400 font-normal">({t('templates.previewTextHint')})</span>
              </label>
              <input type="text" placeholder="Brief preview text visible in inbox…" maxLength={90}
                value={editTemplate.preheader_text || ''}
                onChange={e => { setEditTemplate(p => ({ ...p, preheader_text: e.target.value })); setIsDirty(true); }}
                className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
            </div>
          </div>

          <div style={{ height: 620 }}>
            <EmailEditor
              ref={emailEditorRef}
              onLoad={handleEditorLoad}
              key={editTemplate._id || editTemplate.name || 'new'}
              onChange={() => setIsDirty(true)}
              templateMeta={editTemplate}
            />
          </div>
        </div>
      ) : (
        <>
          {/* ── Page header ── */}
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">
                {t('templates.title') || 'Email Templates'}
              </h1>
              <p className="text-sm text-gray-500 mt-1">
                {t('templates.subtitle') || 'Reusable email designs you can drop into any campaign.'}
              </p>
            </div>
            <button
              type="button"
              onClick={handleCreate}
              className="inline-flex items-center gap-2 px-4 py-2.5 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 transition-colors shadow-sm"
            >
              <Plus size={16} /> {t('templates.create')}
            </button>
          </div>

          {/* ── Toolbar ── */}
          <div className="flex flex-wrap items-center gap-3 bg-white rounded-xl border border-gray-200 shadow-sm px-4 py-3">
            <div className="relative flex-1 min-w-[200px] max-w-sm">
              <SearchIcon size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                placeholder={t('templates.search')}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-9 pr-8 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              {search && (
                <button
                  type="button"
                  onClick={() => setSearch('')}
                  aria-label="Clear search"
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100"
                >
                  <X size={12} />
                </button>
              )}
            </div>

            <select
              value={modeFilter}
              onChange={(e) => setModeFilter(e.target.value)}
              className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white text-gray-700 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="">{t('templates.allModes')}</option>
              <option value="visual">Visual</option>
              <option value="html">HTML</option>
              <option value="drag-drop">Drag & Drop</option>
              <option value="legacy">Legacy</option>
            </select>

            <span className="ml-auto text-xs text-gray-400">
              {filtered.length} of {templates.length} template{templates.length !== 1 ? 's' : ''}
            </span>
          </div>

          {errorMsg && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">{errorMsg}</div>
          )}

          {/* ── Empty / no-match state ── */}
          {filtered.length === 0 ? (
            <div className="bg-white rounded-xl border border-dashed border-gray-300 py-16 px-6 text-center">
              <div className="mx-auto w-12 h-12 rounded-full bg-gray-50 flex items-center justify-center mb-3">
                <span className="text-2xl">📄</span>
              </div>
              <p className="text-sm font-medium text-gray-700 mb-1">
                {search || modeFilter ? t('templates.noMatch') : t('templates.empty')}
              </p>
              {(search || modeFilter) ? (
                <button
                  type="button"
                  onClick={() => { setSearch(''); setModeFilter(''); }}
                  className="text-xs text-blue-600 mt-1 hover:underline"
                >
                  {t('common.clearFilters')}
                </button>
              ) : (
                <>
                  <p className="text-xs text-gray-400 mt-1 mb-4">
                    Build your first email template — you can reuse it across campaigns and automations.
                  </p>
                  <button
                    type="button"
                    onClick={handleCreate}
                    className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700"
                  >
                    <Plus size={14} /> {t('templates.create')}
                  </button>
                </>
              )}
            </div>
          ) : (
            /* ── Card grid ── */
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filtered.map((template) => (
                <TemplateCard
                  key={template._id || template.id}
                  template={template}
                  onPreview={setPreviewTemplate}
                  onEdit={handleEdit}
                  onDuplicate={handleDuplicate}
                  onDelete={handleDelete}
                  formatDate={formatDate}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}