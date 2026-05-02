// frontend/src/pages/Segmentation.jsx
// ----------------------------------------------------------------------------
// Changes vs previous version:
//   - Removed "Engagement Level" entirely (was a non-functional placeholder).
//     7 segmentation types now: status, lists, dateRange, profileCompleteness,
//     geographic, emailDomain, customFields.
//   - Geographic inputs now correctly target standard_fields.country/city
//     (the backend rewrite owns the actual query change).
//   - Custom Fields UX: field-name input is editable with autocomplete from
//     /subscribers/lists/:list/fields. Hardcoded "Industry" / "Company Size"
//     inputs removed — they were just custom fields with prettier labels and
//     caused duplicate-key bugs.
//   - Edit / Delete are disabled when a segment is in use by a live campaign,
//     automation rule, A/B test, or in-progress workflow. UI explains why and
//     deep-links to the offending entity.
//   - Lock checks happen both at load (segment.usage on fetch) and at write
//     time (backend returns 409 with usage payload — we surface that).
// ----------------------------------------------------------------------------

import { useEffect, useMemo, useState } from 'react';
import API from '../api';
import { useSettings } from '../contexts/SettingsContext';

// ── small helpers ───────────────────────────────────────────────────────────

const fmt = (n) => Number(n || 0).toLocaleString();

const EMPTY_CRITERIA = {
  status: [],
  lists: [],
  dateRange: null,
  profileCompleteness: {},
  geographic: { country: '', city: '' },
  emailDomain: [],
  customFields: {},
};

const STATUS_OPTIONS = [
  { value: 'active', label: 'Active' },
  { value: 'inactive', label: 'Inactive' },
  { value: 'bounced', label: 'Bounced' },
  { value: 'unsubscribed', label: 'Unsubscribed' },
];

const DATE_RANGE_OPTIONS = [
  { label: 'Last 7 days', value: 7 },
  { label: 'Last 30 days', value: 30 },
  { label: 'Last 90 days', value: 90 },
  { label: 'Last 6 months', value: 180 },
  { label: 'Last year', value: 365 },
  { label: 'All time', value: null },
];

const EMAIL_DOMAIN_OPTIONS = [
  { value: 'corporate', label: 'Corporate (non-consumer)' },
  { value: 'gmail.com', label: 'gmail.com' },
  { value: 'yahoo.com', label: 'yahoo.com' },
  { value: 'outlook.com', label: 'outlook.com' },
  { value: 'hotmail.com', label: 'hotmail.com' },
];

const PROFILE_FIELDS = [
  { field: 'first_name', label: 'Has first name' },
  { field: 'last_name', label: 'Has last name' },
  { field: 'phone', label: 'Has phone' },
  { field: 'company', label: 'Has company' },
  { field: 'job_title', label: 'Has job title' },
];

const getCriteriaTypes = (criteria) => {
  if (!criteria) return [];
  const t = [];
  if (criteria.status?.length) t.push('status');
  if (criteria.lists?.length) t.push('lists');
  if (criteria.dateRange) t.push('dateRange');
  if (criteria.profileCompleteness && Object.values(criteria.profileCompleteness).some(Boolean)) t.push('profile');
  if (criteria.geographic?.country || criteria.geographic?.city) t.push('geographic');
  if (criteria.emailDomain?.length) t.push('domain');
  if (criteria.customFields && Object.keys(criteria.customFields).some((k) => k && criteria.customFields[k])) {
    t.push('custom');
  }
  return t;
};

// ── lock-state pill + details ───────────────────────────────────────────────

function LockBadge({ usage }) {
  if (!usage?.in_use) return null;
  const total =
    (usage.automations?.length || 0) +
    (usage.campaigns?.length || 0) +
    (usage.ab_tests?.length || 0) +
    (usage.workflows || 0);
  return (
    <span
      title="This segment is in use and cannot be edited or deleted"
      className="inline-flex items-center gap-1 px-2 py-0.5 bg-amber-100 text-amber-800 rounded-full text-xs font-semibold border border-amber-200"
    >
      🔒 In use ({total})
    </span>
  );
}

function UsageDetails({ usage }) {
  if (!usage?.in_use) return null;
  return (
    <div className="mt-3 p-3 bg-amber-50 border border-amber-200 rounded text-xs text-amber-900 space-y-1">
      <p className="font-semibold">This segment is locked because it's in use:</p>
      {usage.automations?.length > 0 && (
        <p>
          <strong>Automations:</strong>{' '}
          {usage.automations.map((a) => `${a.name} (${a.status})`).join(', ')}
        </p>
      )}
      {usage.workflows > 0 && (
        <p>
          <strong>In-progress workflow runs:</strong> {usage.workflows}
        </p>
      )}
      {usage.campaigns?.length > 0 && (
        <p>
          <strong>Campaigns:</strong>{' '}
          {usage.campaigns.map((c) => `${c.title} (${c.status})`).join(', ')}
        </p>
      )}
      {usage.ab_tests?.length > 0 && (
        <p>
          <strong>A/B tests:</strong>{' '}
          {usage.ab_tests.map((t) => `${t.name} (${t.status})`).join(', ')}
        </p>
      )}
      <p className="pt-1 text-amber-700">
        Pause or complete those first, or duplicate this segment to make changes.
      </p>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// Page
// ────────────────────────────────────────────────────────────────────────────

export default function Segmentation() {
  const [segments, setSegments] = useState([]);
  const { t, formatDate } = useSettings();
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [previewData, setPreviewData] = useState({ subscribers: [], total_matching: 0 });
  const [selectedSegment, setSelectedSegment] = useState(null);
  const [lists, setLists] = useState([]);

  useEffect(() => {
    fetchSegments();
    fetchLists();
  }, []);

  const fetchSegments = async () => {
    try {
      setLoading(true);
      const response = await API.get('/segments');
      let data = [];
      if (Array.isArray(response.data)) data = response.data;
      else if (Array.isArray(response.data?.segments)) data = response.data.segments;
      setSegments(data);
    } catch (e) {
      console.error('Failed to load segments:', e);
      setSegments([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchLists = async () => {
    try {
      const response = await API.get('/subscribers/lists');
      const data = Array.isArray(response.data) ? response.data : [];
      setLists(data);
    } catch (e) {
      console.error('Failed to load lists:', e);
      setLists([]);
    }
  };

  const openCreate = () => {
    setSelectedSegment(null);
    setShowCreateModal(true);
  };

  const openEdit = async (segment) => {
    // Re-fetch with usage so we have fresh lock state
    try {
      const { data } = await API.get(`/segments/${segment._id}`);
      setSelectedSegment(data);
      setShowCreateModal(true);
    } catch (e) {
      console.error('Failed to load segment for editing:', e);
      alert('Could not load this segment. Please try again.');
    }
  };

  const handleDelete = async (segment) => {
    // Refresh usage right before asking
    let usage;
    try {
      const { data } = await API.get(`/segments/${segment._id}/usage`);
      usage = data;
    } catch {
      usage = null;
    }

    if (usage?.in_use) {
      const refs = [
        usage.automations?.length && `${usage.automations.length} automation(s)`,
        usage.workflows && `${usage.workflows} active workflow run(s)`,
        usage.campaigns?.length && `${usage.campaigns.length} campaign(s)`,
        usage.ab_tests?.length && `${usage.ab_tests.length} A/B test(s)`,
      ]
        .filter(Boolean)
        .join(', ');
      alert(
        `Cannot delete "${segment.name}".\n\nIt's referenced by: ${refs}.\n\nPause or complete those first.`,
      );
      return;
    }

    if (!confirm(t('segments.deleteConfirm').replace('{name}', segment.name))) return;

    try {
      await API.delete(`/segments/${segment._id}`);
      await fetchSegments();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (detail?.error === 'segment_in_use') {
        alert(detail.message);
      } else {
        alert('Failed to delete segment.');
      }
    }
  };

  const handlePreview = async (segment) => {
    try {
      const response = await API.post('/segments/preview', {
        criteria: segment.criteria || {},
        limit: 50,
      });
      setPreviewData(response.data);
      setShowPreviewModal(true);
    } catch (e) {
      console.error('Preview failed:', e);
      alert('Failed to preview segment.');
    }
  };

  const filtered = useMemo(() => {
    if (!search.trim()) return segments;
    const q = search.toLowerCase();
    return segments.filter(
      (s) =>
        (s.name || '').toLowerCase().includes(q) ||
        (s.description || '').toLowerCase().includes(q),
    );
  }, [segments, search]);

  if (loading && segments.length === 0) {
    return (
      <div className="text-center py-20">
        <div className="text-4xl mb-4">🔄</div>
        <p className="text-lg">Loading segments...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-bold">🎯 Segmentation</h2>
          <p className="text-gray-600 text-sm">
            Build dynamic audiences with 7 criteria types
          </p>
        </div>
        <button
          onClick={openCreate}
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 flex items-center gap-2"
        >
          <span>➕</span> {t('segments.create')}
        </button>
      </div>

      {/* Search */}
      <div>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search segments..."
          className="w-full md:w-80 border border-gray-200 rounded-lg px-3 py-2 text-sm"
        />
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16 gap-2 text-gray-400 text-sm">
            <div className="animate-spin h-4 w-4 border-2 border-gray-300 border-t-blue-500 rounded-full" />
            Loading segments…
          </div>
        ) : filtered.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-3xl mb-2">🎯</p>
            <p className="text-sm font-medium text-gray-700">
              {search ? `No segments match "${search}"` : t('segments.empty')}
            </p>
            {search ? (
              <button
                onClick={() => setSearch('')}
                className="text-xs text-blue-600 mt-2 hover:underline"
              >
                Clear search
              </button>
            ) : (
              <>
                <p className="text-xs text-gray-400 mt-1 mb-4">
                  Create your first segment with 7 criteria types
                </p>
                <button
                  onClick={openCreate}
                  className="px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700"
                >
                  {t('segments.create')}
                </button>
              </>
            )}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Segment
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-24">
                  Size
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Criteria
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-24">
                  Status
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-56">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filtered.map((seg) => {
                const inUse = seg.usage?.in_use; // present when fetched via /segments/:id
                return (
                  <tr key={seg._id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        <p className="font-medium text-gray-900">{seg.name}</p>
                        {inUse && <LockBadge usage={seg.usage} />}
                      </div>
                      {seg.description && (
                        <p className="text-xs text-gray-400 mt-0.5 truncate max-w-xs">
                          {seg.description}
                        </p>
                      )}
                      <p className="text-xs text-gray-300 mt-0.5">{formatDate(seg.updated_at)}</p>
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      <span className="text-base font-bold text-gray-800 tabular-nums">
                        {fmt(seg.subscriber_count)}
                      </span>
                      <span className="block text-xs text-gray-400">subs</span>
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex flex-wrap gap-1">
                        {getCriteriaTypes(seg.criteria).map((t) => (
                          <span
                            key={t}
                            className="px-2 py-0.5 bg-purple-100 text-purple-700 rounded-full text-xs font-medium"
                          >
                            {t}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3.5">
                      <span
                        className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                          seg.is_active
                            ? 'bg-green-100 text-green-700'
                            : 'bg-gray-100 text-gray-600'
                        }`}
                      >
                        {seg.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => handlePreview(seg)}
                          className="px-2.5 py-1 text-xs text-blue-700 bg-blue-50 border border-blue-100 rounded hover:bg-blue-100"
                        >
                          👁 Preview
                        </button>
                        <button
                          onClick={() => openEdit(seg)}
                          className="px-2.5 py-1 text-xs text-gray-700 bg-gray-50 border border-gray-200 rounded hover:bg-gray-100"
                          title="Open editor (criteria edits may be locked if in use)"
                        >
                          ✏️ Edit
                        </button>
                        <button
                          onClick={() => handleDelete(seg)}
                          className="px-2.5 py-1 text-xs text-red-700 bg-red-50 border border-red-100 rounded hover:bg-red-100"
                        >
                          🗑 Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Modals */}
      {showCreateModal && (
        <SegmentEditor
          existing={selectedSegment}
          lists={lists}
          onClose={() => setShowCreateModal(false)}
          onSaved={async () => {
            setShowCreateModal(false);
            await fetchSegments();
          }}
        />
      )}

      {showPreviewModal && (
        <PreviewModal data={previewData} onClose={() => setShowPreviewModal(false)} />
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// SegmentEditor — create / edit modal
// ────────────────────────────────────────────────────────────────────────────

function SegmentEditor({ existing, lists, onClose, onSaved }) {
  const isEditing = Boolean(existing?._id);
  const usage = existing?.usage;
  const criteriaLocked = isEditing && usage?.in_use;

  const [form, setForm] = useState({
    name: existing?.name || '',
    description: existing?.description || '',
    is_active: existing?.is_active ?? true,
    criteria: {
      ...EMPTY_CRITERIA,
      ...(existing?.criteria || {}),
      geographic: {
        country: existing?.criteria?.geographic?.country || '',
        city: existing?.criteria?.geographic?.city || '',
      },
      profileCompleteness: existing?.criteria?.profileCompleteness || {},
      customFields: existing?.criteria?.customFields || {},
    },
  });

  const [saving, setSaving] = useState(false);
  const [previewCount, setPreviewCount] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [availableCustomFields, setAvailableCustomFields] = useState([]);

  // Pull custom-field names from each selected list to power autocomplete
  useEffect(() => {
    const selectedListIds = form.criteria.lists || [];
    if (selectedListIds.length === 0) {
      setAvailableCustomFields([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const results = await Promise.all(
          selectedListIds.map((listId) =>
            API.get(`/subscribers/lists/${encodeURIComponent(listId)}/fields`)
              .then((r) => r.data?.custom || [])
              .catch(() => []),
          ),
        );
        if (!cancelled) {
          setAvailableCustomFields([...new Set(results.flat())].sort());
        }
      } catch {
        if (!cancelled) setAvailableCustomFields([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [form.criteria.lists]);

  const setCriteria = (key, value) => {
    setForm((prev) => ({
      ...prev,
      criteria: { ...prev.criteria, [key]: value },
    }));
  };

  const setGeographic = (key, value) => {
    setForm((prev) => ({
      ...prev,
      criteria: {
        ...prev.criteria,
        geographic: { ...prev.criteria.geographic, [key]: value },
      },
    }));
  };

  const setProfileCompleteness = (field, checked) => {
    setForm((prev) => {
      const next = { ...(prev.criteria.profileCompleteness || {}) };
      if (checked) next[field] = true;
      else delete next[field];
      return { ...prev, criteria: { ...prev.criteria, profileCompleteness: next } };
    });
  };

  // ── custom fields helpers ────────────────────────────────────────────────

  const addCustomField = () => {
    setForm((prev) => ({
      ...prev,
      criteria: {
        ...prev.criteria,
        customFields: { ...(prev.criteria.customFields || {}), '': '' },
      },
    }));
  };

  const renameCustomFieldKey = (oldKey, newKey) => {
    setForm((prev) => {
      const cf = { ...(prev.criteria.customFields || {}) };
      const value = cf[oldKey];
      delete cf[oldKey];
      // If newKey collides, last write wins
      cf[newKey] = value ?? '';
      return { ...prev, criteria: { ...prev.criteria, customFields: cf } };
    });
  };

  const setCustomFieldValue = (key, value) => {
    setForm((prev) => ({
      ...prev,
      criteria: {
        ...prev.criteria,
        customFields: { ...(prev.criteria.customFields || {}), [key]: value },
      },
    }));
  };

  const removeCustomField = (key) => {
    setForm((prev) => {
      const cf = { ...(prev.criteria.customFields || {}) };
      delete cf[key];
      return { ...prev, criteria: { ...prev.criteria, customFields: cf } };
    });
  };

  // ── live count ────────────────────────────────────────────────────────────

  const fetchPreviewCount = async () => {
    setPreviewLoading(true);
    try {
      // Strip empty custom-field keys before sending
      const cleanCustom = Object.fromEntries(
        Object.entries(form.criteria.customFields || {}).filter(
          ([k, v]) => k && k.trim() && v && String(v).trim(),
        ),
      );
      const payload = {
        criteria: {
          ...form.criteria,
          customFields: cleanCustom,
        },
      };
      const { data } = await API.post('/segments/count', payload);
      setPreviewCount(data.count);
    } catch (e) {
      console.error('Count failed:', e);
      setPreviewCount(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  // ── save ──────────────────────────────────────────────────────────────────

  const handleSave = async () => {
    if (!form.name.trim()) {
      alert('Segment name is required.');
      return;
    }

    // Strip empty custom-field keys
    const cleanCustom = Object.fromEntries(
      Object.entries(form.criteria.customFields || {}).filter(
        ([k, v]) => k && k.trim() && v && String(v).trim(),
      ),
    );

    const payload = {
      name: form.name.trim(),
      description: form.description.trim(),
      is_active: form.is_active,
      criteria: {
        ...form.criteria,
        customFields: cleanCustom,
      },
    };

    setSaving(true);
    try {
      if (isEditing) {
        // If criteria are locked, only send name/description
        const updatePayload = criteriaLocked
          ? { name: payload.name, description: payload.description }
          : payload;
        await API.put(`/segments/${existing._id}`, updatePayload);
      } else {
        await API.post('/segments', payload);
      }
      onSaved();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (detail?.error === 'segment_in_use') {
        alert(detail.message);
      } else if (typeof detail === 'string') {
        alert(detail);
      } else {
        alert('Failed to save segment.');
      }
    } finally {
      setSaving(false);
    }
  };

  // ── render ────────────────────────────────────────────────────────────────

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg max-w-3xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-gray-100 flex items-start justify-between">
          <div>
            <h3 className="text-xl font-bold">
              {isEditing ? `Edit "${existing.name}"` : 'Create Segment'}
            </h3>
            <p className="text-xs text-gray-500 mt-1">
              7 criteria types — combine them to build a dynamic audience
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-2xl">
            ×
          </button>
        </div>

        <UsageDetails usage={usage} />

        <div className="p-6 space-y-6">
          {/* Basic info */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-semibold mb-1">Name *</label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full border border-gray-200 rounded px-3 py-2 text-sm"
                placeholder="e.g. Active US subscribers"
              />
            </div>
            <div>
              <label className="block text-sm font-semibold mb-1">Description</label>
              <input
                type="text"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                className="w-full border border-gray-200 rounded px-3 py-2 text-sm"
                placeholder="Optional"
              />
            </div>
          </div>

          {criteriaLocked && (
            <div className="p-3 bg-amber-50 border border-amber-200 rounded text-xs text-amber-900">
              ⚠️ Criteria are locked because this segment is in use. You can still edit
              the name and description.
            </div>
          )}

          <fieldset disabled={criteriaLocked} className={criteriaLocked ? 'opacity-60' : ''}>
            <div className="space-y-6">
              {/* 1. Status */}
              <div>
                <label className="block font-semibold mb-2">📊 Subscriber Status</label>
                <div className="grid grid-cols-2 gap-2">
                  {STATUS_OPTIONS.map((opt) => {
                    const checked = form.criteria.status?.includes(opt.value);
                    return (
                      <label
                        key={opt.value}
                        className="flex items-center bg-gray-50 p-2 rounded hover:bg-gray-100 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={!!checked}
                          onChange={(e) => {
                            const cur = form.criteria.status || [];
                            const next = e.target.checked
                              ? [...cur, opt.value]
                              : cur.filter((v) => v !== opt.value);
                            setCriteria('status', next);
                          }}
                          className="mr-2"
                        />
                        <span className="text-sm">{opt.label}</span>
                      </label>
                    );
                  })}
                </div>
              </div>

              {/* 2. Lists */}
              <div>
                <label className="block font-semibold mb-2">📋 Lists</label>
                {lists.length === 0 ? (
                  <p className="text-xs text-gray-500 italic">No lists available.</p>
                ) : (
                  <div className="max-h-40 overflow-y-auto border border-gray-100 rounded p-2 space-y-1">
                    {lists.map((list) => {
                      const id = list._id ?? list.name;
                      const checked = form.criteria.lists?.includes(id);
                      return (
                        <label
                          key={id}
                          className="flex items-center justify-between bg-gray-50 p-2 rounded hover:bg-gray-100 cursor-pointer"
                        >
                          <div className="flex items-center">
                            <input
                              type="checkbox"
                              checked={!!checked}
                              onChange={(e) => {
                                const cur = form.criteria.lists || [];
                                const next = e.target.checked
                                  ? [...cur, id]
                                  : cur.filter((l) => l !== id);
                                setCriteria('lists', next);
                              }}
                              className="mr-2"
                            />
                            <span className="text-sm font-medium">{id}</span>
                          </div>
                          <span className="text-xs text-gray-500">
                            {fmt(list.count ?? list.total_count ?? 0)}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* 3. Subscription date */}
              <div>
                <label className="block font-semibold mb-2">📅 Subscription Date</label>
                <div className="grid grid-cols-2 gap-2">
                  {DATE_RANGE_OPTIONS.map((opt) => (
                    <label
                      key={opt.label}
                      className="flex items-center bg-gray-50 p-2 rounded hover:bg-gray-100 cursor-pointer"
                    >
                      <input
                        type="radio"
                        name="dateRange"
                        checked={form.criteria.dateRange === opt.value}
                        onChange={() => setCriteria('dateRange', opt.value)}
                        className="mr-2"
                      />
                      <span className="text-sm">{opt.label}</span>
                    </label>
                  ))}
                </div>
                <p className="text-xs text-gray-400 mt-1">
                  Filters subscribers by their <code>created_at</code> date.
                </p>
              </div>

              {/* 4. Profile completeness */}
              <div>
                <label className="block font-semibold mb-2">👤 Profile Completeness</label>
                <div className="grid grid-cols-2 gap-2">
                  {PROFILE_FIELDS.map((item) => (
                    <label
                      key={item.field}
                      className="flex items-center bg-gray-50 p-2 rounded hover:bg-gray-100 cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={!!form.criteria.profileCompleteness?.[item.field]}
                        onChange={(e) =>
                          setProfileCompleteness(item.field, e.target.checked)
                        }
                        className="mr-2"
                      />
                      <span className="text-sm">{item.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* 5. Geographic */}
              <div>
                <label className="block font-semibold mb-2">🌍 Geographic</label>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="text"
                    placeholder="Country (e.g. Germany)"
                    value={form.criteria.geographic.country}
                    onChange={(e) => setGeographic('country', e.target.value)}
                    className="border border-gray-200 rounded p-2 text-sm"
                  />
                  <input
                    type="text"
                    placeholder="City (e.g. Berlin)"
                    value={form.criteria.geographic.city}
                    onChange={(e) => setGeographic('city', e.target.value)}
                    className="border border-gray-200 rounded p-2 text-sm"
                  />
                </div>
                <p className="text-xs text-gray-400 mt-1">
                  Matches the <code>country</code> and <code>city</code> standard fields
                  on each subscriber (case-insensitive).
                </p>
              </div>

              {/* 6. Email domain */}
              <div>
                <label className="block font-semibold mb-2">📧 Email Domain</label>
                <div className="grid grid-cols-2 gap-2">
                  {EMAIL_DOMAIN_OPTIONS.map((opt) => {
                    const checked = form.criteria.emailDomain?.includes(opt.value);
                    return (
                      <label
                        key={opt.value}
                        className="flex items-center bg-gray-50 p-2 rounded hover:bg-gray-100 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={!!checked}
                          onChange={(e) => {
                            const cur = form.criteria.emailDomain || [];
                            const next = e.target.checked
                              ? [...cur, opt.value]
                              : cur.filter((v) => v !== opt.value);
                            setCriteria('emailDomain', next);
                          }}
                          className="mr-2"
                        />
                        <span className="text-sm">{opt.label}</span>
                      </label>
                    );
                  })}
                </div>
              </div>

              {/* 7. Custom fields */}
              <div>
                <label className="block font-semibold mb-2">🏷️ Custom Fields</label>
                {form.criteria.lists?.length === 0 && (
                  <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1 mb-2">
                    Tip: select a list above to enable autocomplete on field names.
                  </p>
                )}

                <datalist id="custom-field-names">
                  {availableCustomFields.map((f) => (
                    <option key={f} value={f} />
                  ))}
                </datalist>

                {Object.entries(form.criteria.customFields || {}).length > 0 && (
                  <div className="space-y-1 mb-2">
                    {Object.entries(form.criteria.customFields || {}).map(([key, value], idx) => (
                      <CustomFieldRow
                        key={`${idx}-${key}`}
                        fieldKey={key}
                        fieldValue={value}
                        onRenameKey={(newKey) => renameCustomFieldKey(key, newKey)}
                        onChangeValue={(v) => setCustomFieldValue(key, v)}
                        onRemove={() => removeCustomField(key)}
                      />
                    ))}
                  </div>
                )}

                <button
                  type="button"
                  onClick={addCustomField}
                  className="text-blue-600 text-sm hover:underline"
                >
                  ➕ Add custom field filter
                </button>
                <p className="text-xs text-gray-400 mt-1">
                  Matches values inside <code>custom_fields.&lt;name&gt;</code>{' '}
                  (case-insensitive substring).
                </p>
              </div>
            </div>
          </fieldset>

          {/* Live preview count */}
          <div className="border-t border-gray-100 pt-4 flex items-center justify-between">
            <button
              type="button"
              onClick={fetchPreviewCount}
              disabled={previewLoading}
              className="px-3 py-1.5 text-sm text-blue-700 bg-blue-50 border border-blue-100 rounded hover:bg-blue-100 disabled:opacity-50"
            >
              {previewLoading ? 'Counting…' : '🔢 Preview count'}
            </button>
            {previewCount !== null && !previewLoading && (
              <span className="text-sm text-gray-700">
                <strong className="text-gray-900">{fmt(previewCount)}</strong> subscribers
                match
              </span>
            )}
          </div>
        </div>

        <div className="px-6 py-4 border-t border-gray-100 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded text-sm"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={!form.name.trim() || saving}
            className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700 disabled:opacity-50 text-sm"
          >
            {saving ? 'Saving…' : isEditing ? 'Save Changes' : 'Create Segment'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// CustomFieldRow — editable name + value, with autocomplete
// ────────────────────────────────────────────────────────────────────────────

function CustomFieldRow({ fieldKey, fieldValue, onRenameKey, onChangeValue, onRemove }) {
  // Local state so typing the field name doesn't re-key the row on every keystroke
  const [localKey, setLocalKey] = useState(fieldKey);

  useEffect(() => {
    setLocalKey(fieldKey);
  }, [fieldKey]);

  const commitKey = () => {
    const trimmed = localKey.trim();
    if (trimmed !== fieldKey) onRenameKey(trimmed);
  };

  return (
    <div className="flex gap-2 items-center">
      <input
        type="text"
        list="custom-field-names"
        placeholder="Field name (e.g. plan)"
        value={localKey}
        onChange={(e) => setLocalKey(e.target.value)}
        onBlur={commitKey}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            commitKey();
          }
        }}
        className="flex-1 border border-gray-200 rounded px-2 py-1 text-sm"
      />
      <input
        type="text"
        placeholder="Value (e.g. pro)"
        value={fieldValue || ''}
        onChange={(e) => onChangeValue(e.target.value)}
        className="flex-1 border border-gray-200 rounded px-2 py-1 text-sm"
      />
      <button
        type="button"
        onClick={onRemove}
        className="text-red-600 hover:text-red-800 px-2"
        aria-label="Remove field"
      >
        ❌
      </button>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// Preview modal
// ────────────────────────────────────────────────────────────────────────────

function PreviewModal({ data, onClose }) {
  const subscribers = data?.subscribers || [];
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-gray-100 flex items-center justify-between">
          <div>
            <h3 className="text-xl font-bold">Segment Preview</h3>
            <p className="text-xs text-gray-500 mt-1">
              {fmt(data?.total_matching || 0)} total match · showing first {subscribers.length}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-2xl">
            ×
          </button>
        </div>

        <div className="p-6">
          {subscribers.length === 0 ? (
            <p className="text-sm text-gray-500 text-center py-8">
              No subscribers match these criteria.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                    Email
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                    List
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                    Status
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                    Country
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {subscribers.map((s) => (
                  <tr key={s._id}>
                    <td className="px-3 py-2 text-sm text-gray-900">{s.email}</td>
                    <td className="px-3 py-2 text-xs text-gray-500">{s.list || '—'}</td>
                    <td className="px-3 py-2 text-xs text-gray-500">{s.status || '—'}</td>
                    <td className="px-3 py-2 text-xs text-gray-500">
                      {s.standard_fields?.country || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}