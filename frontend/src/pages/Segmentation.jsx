import { useEffect, useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import API from '../api';

// ─── helpers ─────────────────────────────────────────────────
const fmt  = (n) => Number(n ?? 0).toLocaleString();
const fmtD = (iso) => iso ? new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '—';

const STATUS_STYLE = {
  active:       'bg-green-100 text-green-700',
  inactive:     'bg-gray-100  text-gray-600',
  bounced:      'bg-red-100   text-red-700',
  unsubscribed: 'bg-orange-100 text-orange-700',
};

const CRITERIA_LABELS = {
  status:              'Status',
  lists:               'Lists',
  dateRange:           'Date',
  profileCompleteness: 'Profile',
  geographic:          'Geographic',
  engagement:          'Engagement',
  emailDomain:         'Domain',
  industry:            'Custom',
  companySize:         'Custom',
  customFields:        'Custom',
};

function getCriteriaTypes(criteria) {
  if (!criteria) return [];
  const types = new Set();
  if (criteria.status?.length)          types.add('Status');
  if (criteria.lists?.length)           types.add('Lists');
  if (criteria.dateRange)               types.add('Date');
  if (Object.keys(criteria.profileCompleteness || {}).length) types.add('Profile');
  if (criteria.geographic?.country || criteria.geographic?.city) types.add('Geographic');
  if (criteria.engagement?.length)      types.add('Engagement');
  if (criteria.emailDomain?.length)     types.add('Domain');
  if (criteria.industry || criteria.companySize || Object.keys(criteria.customFields || {}).length) types.add('Custom');
  return [...types];
}

const emptyForm = () => ({
  name: '',
  description: '',
  criteria: {
    status: [], lists: [], dateRange: null,
    profileCompleteness: {},
    geographic: { country: '', city: '' },
    engagement: [], emailDomain: [],
    industry: '', companySize: '', customFields: {}
  }
});

// ─── Toast ────────────────────────────────────────────────────
function Toast({ toasts, onDismiss }) {
  return (
    <div className="fixed top-4 right-4 z-50 space-y-2 pointer-events-none">
      {toasts.map(t => (
        <div key={t.id} onClick={() => onDismiss(t.id)}
          className={`pointer-events-auto flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg text-sm font-medium cursor-pointer
            ${t.type === 'success' ? 'bg-green-600 text-white' : t.type === 'error' ? 'bg-red-600 text-white' : 'bg-gray-800 text-white'}`}>
          {t.type === 'success' ? '✓' : t.type === 'error' ? '✕' : 'ℹ'} {t.message}
        </div>
      ))}
    </div>
  );
}

// ─── CustomFieldInput — replaces prompt() ────────────────────
function CustomFieldRow({ field, value, onChange, onRemove }) {
  return (
    <div className="flex gap-2 items-center">
      <input type="text" placeholder="Field name" value={field}
        className="flex-1 px-2 py-1.5 border rounded-lg text-sm bg-gray-50" readOnly />
      <input type="text" placeholder="Value" value={value}
        onChange={e => onChange(e.target.value)}
        className="flex-1 px-2 py-1.5 border rounded-lg text-sm focus:ring-1 focus:ring-blue-500" />
      <button onClick={onRemove} className="px-2 py-1 text-red-500 hover:text-red-700 text-sm">✕</button>
    </div>
  );
}

function AddCustomFieldInput({ onAdd }) {
  const [name, setName] = useState('');
  return (
    <div className="flex gap-2 mt-1">
      <input type="text" placeholder="New field name…" value={name}
        onChange={e => setName(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' && name.trim()) { onAdd(name.trim()); setName(''); } }}
        className="flex-1 px-2 py-1.5 border rounded-lg text-sm focus:ring-1 focus:ring-blue-500" />
      <button onClick={() => { if (name.trim()) { onAdd(name.trim()); setName(''); } }}
        className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700 whitespace-nowrap">
        Add
      </button>
    </div>
  );
}

// ─── SegmentModal ─────────────────────────────────────────────
function SegmentModal({ show, onClose, segmentForm, setSegmentForm, lists, onSave, isEditing, segmentId, showToast }) {
  const [previewCount, setPreviewCount] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const set = (field, value) => {
    if (field.includes('.')) {
      const [parent, child] = field.split('.');
      setSegmentForm(f => ({ ...f, criteria: { ...f.criteria, [parent]: { ...f.criteria[parent], [child]: value } } }));
    } else {
      setSegmentForm(f => ({ ...f, criteria: { ...f.criteria, [field]: value } }));
    }
  };

  const toggleArr = (field, val) => {
    const cur = segmentForm.criteria[field] || [];
    set(field, cur.includes(val) ? cur.filter(v => v !== val) : [...cur, val]);
  };

  const handlePreviewCount = async () => {
    setPreviewLoading(true);
    try {
      const res = await API.post('/segments/count', { criteria: segmentForm.criteria });
      setPreviewCount(res.data.count ?? 0);
    } catch { setPreviewCount(null); } finally { setPreviewLoading(false); }
  };

  const handleSave = async () => {
    if (!segmentForm.name.trim()) { showToast('Segment name is required', 'error'); return; }
    setSaving(true);
    try {
      const payload = { name: segmentForm.name.trim(), description: segmentForm.description.trim(), criteria: segmentForm.criteria, is_active: true };
      if (isEditing) {
        await API.put(`/segments/${segmentId}`, payload);
        showToast('Segment updated', 'success');
      } else {
        await API.post('/segments', payload);
        showToast('Segment created', 'success');
      }
      onSave(); onClose();
    } catch (err) { showToast(err.response?.data?.detail || 'Failed to save segment', 'error');
    } finally { setSaving(false); }
  };

  if (!show) return null;

  const c = segmentForm.criteria;
  const readOnly = false; // editing is now always allowed

  return (
    <div className="fixed inset-0 bg-black/50 flex items-start justify-center pt-4 z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-4xl max-h-[94vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b sticky top-0 bg-white z-10">
          <div>
            <h3 className="text-base font-semibold">{isEditing ? 'Edit Segment' : 'Create Segment'}</h3>
            <p className="text-xs text-gray-400 mt-0.5">8 criteria types available</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">✕</button>
        </div>

        <div className="p-6 space-y-6">
          {/* Name + Description */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Segment Name *</label>
              <input type="text" value={segmentForm.name}
                onChange={e => setSegmentForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. High Value Tech Users"
                className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Description</label>
              <input type="text" value={segmentForm.description}
                onChange={e => setSegmentForm(f => ({ ...f, description: e.target.value }))}
                placeholder="Describe this segment…"
                className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
            </div>
          </div>

          {/* 8 criteria types */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">

            {/* 1. Status */}
            <div className="border border-gray-100 rounded-xl p-4">
              <p className="text-sm font-semibold mb-3 text-gray-700">📊 Subscriber Status</p>
              <div className="grid grid-cols-2 gap-2">
                {['active', 'inactive', 'unsubscribed', 'bounced'].map(s => (
                  <label key={s} className="flex items-center gap-2 px-3 py-2 bg-gray-50 rounded-lg hover:bg-gray-100 cursor-pointer text-sm">
                    <input type="checkbox" checked={c.status?.includes(s)} onChange={() => toggleArr('status', s)} className="rounded" />
                    <span className="capitalize">{s}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* 2. Lists */}
            <div className="border border-gray-100 rounded-xl p-4">
              <p className="text-sm font-semibold mb-3 text-gray-700">📋 Lists</p>
              {lists.length === 0 ? (
                <p className="text-sm text-gray-400">No lists available</p>
              ) : (
                <div className="space-y-1 max-h-32 overflow-y-auto">
                  {lists.map(list => (
                    <label key={list._id} className="flex items-center justify-between hover:bg-gray-50 px-2 py-1.5 rounded-lg cursor-pointer">
                      <div className="flex items-center gap-2">
                        <input type="checkbox"
                          checked={c.lists?.includes(list._id)}
                          onChange={e => {
                            const cur = c.lists || [];
                            set('lists', e.target.checked ? [...cur, list._id] : cur.filter(l => l !== list._id));
                          }} className="rounded" />
                        <span className="text-sm">{list._id}</span>
                      </div>
                      <span className="text-xs text-gray-400">{fmt(list.total_count || list.count || 0)}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>

            {/* 3. Date Range */}
            <div className="border border-gray-100 rounded-xl p-4">
              <p className="text-sm font-semibold mb-3 text-gray-700">📅 Subscription Date</p>
              <div className="grid grid-cols-2 gap-2">
                {[
                  { label: 'Last 7 days', value: 7 }, { label: 'Last 30 days', value: 30 },
                  { label: 'Last 90 days', value: 90 }, { label: 'Last 6 months', value: 180 },
                  { label: 'Last year', value: 365 }, { label: 'All time', value: null },
                ].map(opt => (
                  <label key={opt.label} className="flex items-center gap-2 px-3 py-2 bg-gray-50 rounded-lg hover:bg-gray-100 cursor-pointer text-sm">
                    <input type="radio" name="dateRange" checked={c.dateRange === opt.value} onChange={() => set('dateRange', opt.value)} />
                    <span>{opt.label}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* 4. Profile Completeness */}
            <div className="border border-gray-100 rounded-xl p-4">
              <p className="text-sm font-semibold mb-3 text-gray-700">👤 Profile Completeness</p>
              <div className="space-y-2">
                {[{ field: 'first_name', label: 'Has First Name' }, { field: 'last_name', label: 'Has Last Name' }].map(item => (
                  <label key={item.field} className="flex items-center gap-2 px-3 py-2 bg-gray-50 rounded-lg hover:bg-gray-100 cursor-pointer text-sm">
                    <input type="checkbox"
                      checked={c.profileCompleteness?.[item.field] === true}
                      onChange={e => {
                        const cur = { ...c.profileCompleteness };
                        if (e.target.checked) cur[item.field] = true; else delete cur[item.field];
                        set('profileCompleteness', cur);
                      }} className="rounded" />
                    <span>{item.label}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* 5. Geographic */}
            <div className="border border-gray-100 rounded-xl p-4">
              <p className="text-sm font-semibold mb-3 text-gray-700">🌍 Geographic</p>
              <div className="space-y-2">
                <input type="text" placeholder="Country (e.g. United States)"
                  value={c.geographic?.country || ''}
                  onChange={e => set('geographic.country', e.target.value)}
                  className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
                <input type="text" placeholder="City (e.g. New York)"
                  value={c.geographic?.city || ''}
                  onChange={e => set('geographic.city', e.target.value)}
                  className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
              </div>
            </div>

            {/* 6. Engagement */}
            <div className="border border-gray-100 rounded-xl p-4">
              <p className="text-sm font-semibold mb-3 text-gray-700">📈 Engagement Level</p>
              <div className="grid grid-cols-3 gap-2">
                {['high', 'medium', 'low'].map(level => (
                  <label key={level} className="flex items-center gap-2 px-3 py-2 bg-gray-50 rounded-lg hover:bg-gray-100 cursor-pointer text-sm">
                    <input type="checkbox" checked={c.engagement?.includes(level)} onChange={() => toggleArr('engagement', level)} className="rounded" />
                    <span className="capitalize">{level}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* 7. Email Domain */}
            <div className="border border-gray-100 rounded-xl p-4">
              <p className="text-sm font-semibold mb-3 text-gray-700">📧 Email Domain</p>
              <div className="grid grid-cols-2 gap-2">
                {[{ label: 'Gmail', value: 'gmail.com' }, { label: 'Yahoo', value: 'yahoo.com' },
                  { label: 'Outlook', value: 'outlook.com' }, { label: 'Corporate', value: 'corporate' }].map(d => (
                  <label key={d.value} className="flex items-center gap-2 px-3 py-2 bg-gray-50 rounded-lg hover:bg-gray-100 cursor-pointer text-sm">
                    <input type="checkbox" checked={c.emailDomain?.includes(d.value)} onChange={() => toggleArr('emailDomain', d.value)} className="rounded" />
                    <span>{d.label}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* 8. Custom Fields */}
            <div className="border border-gray-100 rounded-xl p-4">
              <p className="text-sm font-semibold mb-3 text-gray-700">🏷️ Custom Fields</p>
              <div className="space-y-2">
                <input type="text" placeholder="Industry (e.g. Technology)"
                  value={c.industry || ''}
                  onChange={e => set('industry', e.target.value)}
                  className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
                <input type="text" placeholder="Company Size (e.g. 50-200)"
                  value={c.companySize || ''}
                  onChange={e => set('companySize', e.target.value)}
                  className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
                {Object.entries(c.customFields || {}).map(([field, value]) => (
                  <CustomFieldRow key={field} field={field} value={value}
                    onChange={v => { const cf = { ...c.customFields, [field]: v }; set('customFields', cf); }}
                    onRemove={() => { const cf = { ...c.customFields }; delete cf[field]; set('customFields', cf); }} />
                ))}
                <AddCustomFieldInput onAdd={name => set('customFields', { ...c.customFields, [name]: '' })} />
              </div>
            </div>
          </div>

          {/* Preview count bar */}
          <div className="flex items-center gap-4 p-4 bg-blue-50 rounded-xl border border-blue-100">
            <div className="flex-1">
              <p className="text-sm font-medium text-blue-800">
                {previewCount !== null ? (
                  <><span className="text-xl font-bold">{fmt(previewCount)}</span> subscribers match</>
                ) : (
                  <span className="text-blue-500">Click Count to preview matching subscribers</span>
                )}
              </p>
            </div>
            <button onClick={handlePreviewCount} disabled={previewLoading}
              className="px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2">
              {previewLoading ? <><span className="animate-spin">↻</span> Counting…</> : '🔍 Count Matches'}
            </button>
          </div>
        </div>

        {/* Footer */}
        <div className="flex gap-3 px-6 py-4 border-t bg-gray-50 rounded-b-xl sticky bottom-0">
          <button onClick={handleSave} disabled={saving || !segmentForm.name.trim()}
            className="flex-1 py-2.5 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50">
            {saving ? 'Saving…' : isEditing ? 'Update Segment' : 'Create Segment'}
          </button>
          <button onClick={onClose} className="px-5 py-2.5 border text-sm font-medium rounded-lg hover:bg-gray-100">
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── PreviewModal ─────────────────────────────────────────────
function PreviewModal({ show, onClose, segment, previewData, totalMatching, onExport }) {
  if (!show) return null;
  return (
    <div className="fixed inset-0 bg-black/50 flex items-start justify-center pt-6 z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-4xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b sticky top-0 bg-white z-10">
          <div>
            <h3 className="text-base font-semibold">{segment?.name}</h3>
            <p className="text-xs text-gray-400 mt-0.5">
              {fmt(totalMatching)} subscribers match · showing first {Math.min(previewData.length, 50)}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {onExport && (
              <button onClick={onExport}
                className="px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600">
                📥 Export
              </button>
            )}
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">✕</button>
          </div>
        </div>

        {previewData.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-3xl mb-2">🔍</p>
            <p className="text-sm text-gray-600 font-medium">No subscribers match this criteria</p>
            <p className="text-xs text-gray-400 mt-1">Try adjusting your segment filters</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Email</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">List</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Joined</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {previewData.slice(0, 50).map((sub, i) => (
                  <tr key={sub._id || i} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 text-gray-700">
                      {[sub.standard_fields?.first_name, sub.standard_fields?.last_name].filter(Boolean).join(' ') || <span className="text-gray-300">—</span>}
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-900">{sub.email}</td>
                    <td className="px-4 py-3">
                      <span className="inline-block px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full text-xs">{sub.list}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLE[sub.status] || STATUS_STYLE.inactive}`}>
                        {sub.status || 'active'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-400 text-right whitespace-nowrap">{fmtD(sub.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="px-6 py-4 border-t flex justify-end">
          <button onClick={onClose} className="px-4 py-2 border text-sm font-medium rounded-lg hover:bg-gray-100">Close</button>
        </div>
      </div>
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────
export default function Segmentation() {
  const navigate = useNavigate();
  const [segments, setSegments]           = useState([]);
  const [loading, setLoading]             = useState(true);
  const [lists, setLists]                 = useState([]);
  const [showModal, setShowModal]         = useState(false);
  const [showPreview, setShowPreview]     = useState(false);
  const [previewData, setPreviewData]     = useState([]);
  const [previewTotal, setPreviewTotal]   = useState(0);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [selectedSegment, setSelectedSegment] = useState(null);
  const [segmentForm, setSegmentForm]     = useState(emptyForm());
  const [showInactive, setShowInactive]   = useState(false);
  const [search, setSearch]               = useState('');
  const [toasts, setToasts]               = useState([]);

  const showToast = useCallback((message, type = 'info') => {
    const id = Date.now();
    setToasts(p => [...p, { id, message, type }]);
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 4000);
  }, []);

  const dismissToast = (id) => setToasts(p => p.filter(t => t.id !== id));

  const fetchSegments = useCallback(async () => {
    try {
      setLoading(true);
      const res = await API.get(`/segments?active_only=${!showInactive}`);
      const data = Array.isArray(res.data) ? res.data : (res.data?.segments || []);
      setSegments(data);
    } catch { setSegments([]); } finally { setLoading(false); }
  }, [showInactive]);

  const fetchLists = async () => {
    try {
      const res = await API.get('/subscribers/lists');
      setLists(Array.isArray(res.data) ? res.data : (res.data?.lists || []));
    } catch { setLists([]); }
  };

  useEffect(() => { fetchSegments(); }, [fetchSegments]);
  useEffect(() => { fetchLists(); }, []);

  // filtered segments
  const filtered = useMemo(() => {
    if (!search.trim()) return segments;
    const q = search.toLowerCase();
    return segments.filter(s =>
      (s.name || '').toLowerCase().includes(q) ||
      (s.description || '').toLowerCase().includes(q)
    );
  }, [segments, search]);

  const openCreate = () => { setSelectedSegment(null); setSegmentForm(emptyForm()); setShowModal(true); };
  const openEdit   = (seg) => {
    setSelectedSegment(seg);
    setSegmentForm({ name: seg.name, description: seg.description || '', criteria: seg.criteria || emptyForm().criteria });
    setShowModal(true);
  };

  const handlePreview = async (seg) => {
    setPreviewLoading(true);
    setSelectedSegment(seg);
    try {
      const res = await API.post('/segments/preview', { criteria: seg.criteria || seg.query });
      setPreviewData(res.data.subscribers || []);
      setPreviewTotal(res.data.total_matching ?? res.data.subscribers?.length ?? 0);
      setShowPreview(true);
    } catch { showToast('Failed to load preview', 'error'); } finally { setPreviewLoading(false); }
  };

  const handleDelete = async (seg) => {
    if (!confirm(`Delete "${seg.name}"? This cannot be undone.`)) return;
    try {
      await API.delete(`/segments/${seg._id}`);
      showToast(`"${seg.name}" deleted`, 'success');
      setSegments(p => p.filter(s => s._id !== seg._id));
    } catch { showToast('Delete failed', 'error'); }
  };

  const handleExportPreview = async () => {
    if (!selectedSegment?._id) return;
    try {
      const res = await API.get(`/segments/${selectedSegment._id}/subscribers?limit=10000`);
      const subs = res.data.subscribers || [];
      const keys = ['email', 'status', 'list', 'first_name', 'last_name'];
      const rows = [keys.join(',')];
      subs.forEach(s => rows.push([
        s.email, s.status, s.list,
        s.standard_fields?.first_name || '',
        s.standard_fields?.last_name || '',
      ].map(v => `"${v || ''}"`).join(',')));
      const blob = new Blob([rows.join('\n')], { type: 'text/csv' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `${selectedSegment.name.replace(/\s+/g, '_')}_subscribers.csv`;
      a.click(); URL.revokeObjectURL(a.href);
      showToast('Export started', 'success');
    } catch { showToast('Export failed', 'error'); }
  };

  // summary stats
  const totalSegmented = segments.reduce((s, seg) => s + (seg.subscriber_count || 0), 0);
  const activeCount    = segments.filter(s => s.is_active).length;

  return (
    <div className="space-y-6">
      <Toast toasts={toasts} onDismiss={dismissToast} />

      {/* ── Summary cards ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { value: segments.length,   label: 'Total Segments',    color: 'text-blue-600' },
          { value: activeCount,       label: 'Active',            color: 'text-green-600' },
          { value: fmt(totalSegmented), label: 'Total Segmented', color: 'text-orange-600' },
          { value: lists.length,      label: 'Available Lists',   color: 'text-purple-600' },
        ].map(card => (
          <div key={card.label} className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <p className={`text-2xl font-bold tabular-nums ${card.color}`}>{card.value}</p>
            <p className="text-xs text-gray-500 mt-0.5">{card.label}</p>
          </div>
        ))}
      </div>

      {/* ── Segments table ── */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {/* Toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-semibold text-gray-700">Segments</h2>
            {filtered.length !== segments.length && (
              <span className="text-xs text-gray-400">({filtered.length} of {segments.length})</span>
            )}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {/* Search */}
            <div className="relative">
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs">🔍</span>
              <input type="text" placeholder="Search segments…"
                value={search} onChange={e => setSearch(e.target.value)}
                className="pl-7 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 w-44" />
            </div>
            {/* Show inactive toggle */}
            <label className="flex items-center gap-1.5 text-xs text-gray-500 cursor-pointer select-none">
              <input type="checkbox" checked={showInactive} onChange={e => setShowInactive(e.target.checked)} className="rounded" />
              Show inactive
            </label>
            {/* Create */}
            <button onClick={openCreate}
              className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 transition-colors">
              ➕ Create Segment
            </button>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16 gap-2 text-gray-400 text-sm">
            <div className="animate-spin h-4 w-4 border-2 border-gray-300 border-t-blue-500 rounded-full" />
            Loading segments…
          </div>
        ) : filtered.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-3xl mb-2">🎯</p>
            <p className="text-sm font-medium text-gray-700">
              {search ? `No segments match "${search}"` : 'No segments yet'}
            </p>
            {search
              ? <button onClick={() => setSearch('')} className="text-xs text-blue-600 mt-2 hover:underline">Clear search</button>
              : <p className="text-xs text-gray-400 mt-1 mb-4">Create your first segment with 8 criteria types</p>
            }
            {!search && (
              <button onClick={openCreate}
                className="px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700">
                Create Segment
              </button>
            )}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Segment</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-24">Size</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Criteria</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-20">Status</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-48">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filtered.map((seg, i) => (
                <tr key={seg._id || i} className="hover:bg-gray-50 transition-colors">
                  <td className="px-5 py-3.5">
                    <p className="font-medium text-gray-900">{seg.name}</p>
                    {seg.description && <p className="text-xs text-gray-400 mt-0.5 truncate max-w-xs">{seg.description}</p>}
                    <p className="text-xs text-gray-300 mt-0.5">{fmtD(seg.updated_at)}</p>
                  </td>
                  <td className="px-4 py-3.5 text-right">
                    <span className="text-base font-bold text-gray-800 tabular-nums">{fmt(seg.subscriber_count)}</span>
                    <span className="block text-xs text-gray-400">subs</span>
                  </td>
                  <td className="px-4 py-3.5">
                    <div className="flex flex-wrap gap-1">
                      {getCriteriaTypes(seg.criteria).map(t => (
                        <span key={t} className="px-2 py-0.5 bg-purple-100 text-purple-700 rounded-full text-xs font-medium">{t}</span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3.5">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${seg.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
                      {seg.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="px-4 py-3.5">
                    <div className="flex items-center justify-end gap-1.5 flex-wrap">
                      <button onClick={() => handlePreview(seg)} disabled={previewLoading}
                        className="px-2.5 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600 disabled:opacity-50 transition-colors">
                        {previewLoading && selectedSegment?._id === seg._id ? '⏳' : 'Preview'}
                      </button>
                      <button onClick={() => openEdit(seg)}
                        className="px-2.5 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600 transition-colors">
                        Edit
                      </button>
                      <button onClick={() => navigate(`/campaigns/create?segment=${seg._id}`)}
                        className="px-2.5 py-1.5 text-xs font-medium border border-blue-200 rounded-lg hover:bg-blue-50 text-blue-600 transition-colors"
                        title="Create campaign targeting this segment">
                        Campaign
                      </button>
                      <button onClick={() => handleDelete(seg)}
                        className="px-2.5 py-1.5 text-xs font-medium border border-red-200 rounded-lg hover:bg-red-50 text-red-600 transition-colors">
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Modals */}
      <SegmentModal
        show={showModal} onClose={() => setShowModal(false)}
        segmentForm={segmentForm} setSegmentForm={setSegmentForm}
        lists={lists} onSave={fetchSegments}
        isEditing={!!selectedSegment} segmentId={selectedSegment?._id}
        showToast={showToast}
      />

      <PreviewModal
        show={showPreview} onClose={() => setShowPreview(false)}
        segment={selectedSegment} previewData={previewData}
        totalMatching={previewTotal} onExport={handleExportPreview}
      />
    </div>
  );
}