import { useEffect, useState, useCallback } from 'react';
import { useSettings } from "../contexts/SettingsContext";
import API from '../api';

// ─── helpers ────────────────────────────────────────────────
const fmt = (n) => Number(n ?? 0).toLocaleString();


const ACTION_STYLE = {
  create:     'bg-green-100   text-green-800',
  update:     'bg-blue-100    text-blue-800',
  delete:     'bg-red-100     text-red-800',
  upload:     'bg-purple-100  text-purple-800',
  export:     'bg-yellow-100  text-yellow-800',
  send:       'bg-indigo-100  text-indigo-800',
  pause:      'bg-orange-100  text-orange-800',
  resume:     'bg-teal-100    text-teal-800',
  test:       'bg-pink-100    text-pink-800',
  start:      'bg-emerald-100 text-emerald-800',
  stop:       'bg-rose-100    text-rose-800',
  trigger:    'bg-violet-100  text-violet-800',
  reactivate: 'bg-lime-100    text-lime-800',
  refresh:    'bg-cyan-100    text-cyan-800',
};

const ENTITY_ICON = {
  subscriber: '👤', list: '📋', campaign: '📧', segment: '🎯',
  automation: '🤖', template: '📝', suppression: '🚫',
  ab_test: '🧪', bulk_upload: '📤', email: '✉️', smtp: '🔧',
};

const ENTITY_TYPES = [
  { value: 'subscriber',  label: '👤 Subscribers' },
  { value: 'list',        label: '📋 Lists' },
  { value: 'campaign',    label: '📧 Campaigns' },
  { value: 'segment',     label: '🎯 Segments' },
  { value: 'automation',  label: '🤖 Automation' },
  { value: 'template',    label: '📝 Templates' },
  { value: 'suppression', label: '🚫 Suppressions' },
  { value: 'ab_test',     label: '🧪 A/B Tests' },
  { value: 'bulk_upload', label: '📤 Bulk Uploads' },
  { value: 'email',       label: '✉️ Email Settings' },
  { value: 'smtp',        label: '🔧 SMTP Config' },
];

const ACTION_TYPES = [
  'create','update','delete','upload','export',
  'send','pause','resume','test','start','stop',
  'trigger','reactivate','refresh',
];

// Renders before/after changes in a readable diff format
function ChangesDiff({ before, after }) {
  const hasBefore = before && Object.keys(before).length > 0;
  const hasAfter  = after  && Object.keys(after).length  > 0;
  if (!hasBefore && !hasAfter) return <span className="text-gray-300 text-xs">—</span>;

  // Show only keys that changed, not the full object
  const changedKeys = new Set([
    ...(hasBefore ? Object.keys(before) : []),
    ...(hasAfter  ? Object.keys(after)  : []),
  ]);

  const relevant = [...changedKeys].filter(k => {
    const b = JSON.stringify(before?.[k]);
    const a = JSON.stringify(after?.[k]);
    return b !== a;
  }).slice(0, 4); // cap at 4 fields to keep cell readable

  if (relevant.length === 0 && (hasBefore || hasAfter)) {
    return <span className="text-xs text-gray-400 italic">no field changes</span>;
  }

  return (
    <div className="space-y-1 max-w-[200px]">
      {relevant.map(key => {
        const bVal = before?.[key];
        const aVal = after?.[key];
        return (
          <div key={key} className="text-xs">
            <span className="font-medium text-gray-500">{key}: </span>
            {hasBefore && bVal !== undefined && (
              <span className="bg-red-50 text-red-700 px-1 rounded line-through">
                {String(bVal).substring(0, 20)}
              </span>
            )}
            {hasBefore && hasAfter && bVal !== undefined && aVal !== undefined && (
              <span className="text-gray-400 mx-0.5">→</span>
            )}
            {hasAfter && aVal !== undefined && (
              <span className="bg-green-50 text-green-700 px-1 rounded">
                {String(aVal).substring(0, 20)}
              </span>
            )}
          </div>
        );
      })}
      {changedKeys.size > 4 && (
        <span className="text-xs text-gray-400">+{changedKeys.size - 4} more fields</span>
      )}
    </div>
  );
}

export default function AuditTrail() {
  const { t, formatDate, formatDateTime, formatTime } = useSettings();

  const fmtTime = (timestamp) => {
    const date = new Date(timestamp);
    const diffMs = Date.now() - date;
    const mins  = Math.floor(diffMs / 60000);
    const hours = Math.floor(diffMs / 3600000);
    const days  = Math.floor(diffMs / 86400000);
    if (mins  < 1)  return 'Just now';
    if (mins  < 60) return `${mins}m ago`;
    if (hours < 24) return `${hours}h ago`;
    if (days  < 7)  return `${days}d ago`;
    return formatDateTime(timestamp);
  };
  const [logs, setLogs]           = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [exporting, setExporting] = useState(false);
  const [totalCount, setTotalCount] = useState(0);

  const [filters, setFilters] = useState({
    entity_type: '', action: '', start_date: '', end_date: '', search: ''
  });
  const [pagination, setPagination] = useState({ page: 1, limit: 50 });

  const setFilter = (key, value) => {
    setFilters(p => ({ ...p, [key]: value }));
    setPagination(p => ({ ...p, page: 1 }));
  };

  const clearFilters = () => {
    setFilters({ entity_type: '', action: '', start_date: '', end_date: '', search: '' });
    setPagination(p => ({ ...p, page: 1 }));
  };

  const activeFilterCount = [
    filters.entity_type, filters.action, filters.start_date,
    filters.end_date, filters.search
  ].filter(Boolean).length;

  const fetchLogs = useCallback(async () => {
    try {
      setLoading(true); setError(null);
      const params = new URLSearchParams();
      params.append('limit', pagination.limit);
      params.append('skip', (pagination.page - 1) * pagination.limit);
      if (filters.entity_type) params.append('entity_type', filters.entity_type);
      if (filters.action)      params.append('action', filters.action);
      if (filters.start_date)  params.append('start_date', filters.start_date);
      if (filters.end_date)    params.append('end_date', filters.end_date);
      if (filters.search)      params.append('search', filters.search);

      const res = await API.get(`/audit/logs?${params}`);
      setLogs(res.data.logs || []);
      setTotalCount(res.data.total_count || 0);
    } catch {
      setError('Failed to load audit logs');
      setLogs([]);
    } finally { setLoading(false); }
  }, [pagination.page, pagination.limit, filters]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  const exportLogs = async () => {
    setExporting(true);
    try {
      const params = new URLSearchParams();
      if (filters.entity_type) params.append('entity_type', filters.entity_type);
      if (filters.action)      params.append('action', filters.action);
      if (filters.start_date)  params.append('start_date', filters.start_date);
      if (filters.end_date)    params.append('end_date', filters.end_date);

      const res = await API.get(`/audit/export?${params}`, { responseType: 'blob' });
      const url  = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `audit-logs-${new Date().toISOString().split('T')[0]}.csv`);
      document.body.appendChild(link); link.click(); link.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      setError('Failed to export audit logs — please try again');
    } finally { setExporting(false); }
  };

  const totalPages = Math.ceil(totalCount / pagination.limit);
  const showFrom   = (pagination.page - 1) * pagination.limit + 1;
  const showTo     = Math.min(pagination.page * pagination.limit, totalCount);

  // Stats derived from current page (honest about scope)
  const pageActionCounts = {};
  logs.forEach(log => {
    const a = log.action || 'unknown';
    pageActionCounts[a] = (pageActionCounts[a] || 0) + 1;
  });

  return (
    <div className="space-y-5">

      {/* ── Action bar ── */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <button onClick={fetchLogs}
            className="px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600">
            🔄 Refresh
          </button>
          {activeFilterCount > 0 && (
            <button onClick={clearFilters}
              className="px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600">
              ✕ Clear filters ({activeFilterCount})
            </button>
          )}
        </div>
        <button onClick={exportLogs} disabled={exporting}
          className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white text-sm font-semibold rounded-lg hover:bg-green-700 disabled:opacity-50">
          {exporting ? '⏳ Exporting…' : '📥 Export CSV'}
        </button>
      </div>

      {/* ── Error ── */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm flex items-center justify-between">
          ⚠️ {error}
          <button onClick={fetchLogs} className="underline ml-3">Retry</button>
        </div>
      )}

      {/* ── Summary stat cards — only Total from API is reliable ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Total Activities',  value: fmt(totalCount),                          color: 'text-blue-700',   bg: 'bg-blue-50   border-blue-200' },
          { label: 'This Page',         value: fmt(logs.length),                         color: 'text-gray-700',   bg: 'bg-gray-50   border-gray-200' },
          { label: 'Entity Types',      value: new Set(logs.map(l => l.entity_type)).size, color: 'text-purple-700', bg: 'bg-purple-50 border-purple-200' },
          { label: 'Action Types',      value: Object.keys(pageActionCounts).length,     color: 'text-orange-700', bg: 'bg-orange-50 border-orange-200' },
        ].map(s => (
          <div key={s.label} className={`rounded-xl border p-4 ${s.bg}`}>
            <p className={`text-2xl font-bold tabular-nums ${s.color}`}>{s.value}</p>
            <p className="text-xs font-medium text-gray-500 mt-0.5">{s.label}</p>
          </div>
        ))}
      </div>

      {/* ── Table with filters in toolbar ── */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">

        {/* Toolbar with all filter controls */}
        <div className="px-5 py-4 border-b border-gray-100 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-700">
              Activity Log
              {totalCount > 0 && (
                <span className="ml-2 text-xs font-normal text-gray-400">
                  {fmt(totalCount)} total
                  {activeFilterCount > 0 && ' (filtered)'}
                </span>
              )}
            </h2>
          </div>

          {/* Filter row */}
          <div className="flex flex-wrap gap-2">
            {/* Entity type */}
            <select value={filters.entity_type} onChange={e => setFilter('entity_type', e.target.value)}
              className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-white text-gray-600 focus:ring-2 focus:ring-blue-500">
              <option value="">All entities</option>
              {ENTITY_TYPES.map(e => (
                <option key={e.value} value={e.value}>{e.label}</option>
              ))}
            </select>

            {/* Action */}
            <select value={filters.action} onChange={e => setFilter('action', e.target.value)}
              className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-white text-gray-600 focus:ring-2 focus:ring-blue-500">
              <option value="">All actions</option>
              {ACTION_TYPES.map(a => (
                <option key={a} value={a} className="capitalize">{a}</option>
              ))}
            </select>

            {/* Date range */}
            <div className="flex items-center gap-1.5">
              <input type="datetime-local" value={filters.start_date}
                onChange={e => setFilter('start_date', e.target.value)}
                className="px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500" />
              <span className="text-gray-400 text-xs">→</span>
              <input type="datetime-local" value={filters.end_date}
                onChange={e => setFilter('end_date', e.target.value)}
                className="px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500" />
            </div>

            {/* Search — sent to API, searches full dataset */}
            <div className="relative flex-1 min-w-[180px]">
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs">🔍</span>
              <input type="text" placeholder={t('audit.search')} value={filters.search}
                onChange={e => setFilter('search', e.target.value)}
                className="pl-7 pr-3 py-1.5 w-full text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500" />
              {filters.search && (
                <button onClick={() => setFilter('search', '')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-300 hover:text-gray-500 text-xs">✕</button>
              )}
            </div>
          </div>

          {/* Action breakdown pills — clickable shortcuts for the action filter */}
          {Object.keys(pageActionCounts).length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(pageActionCounts)
                .sort(([,a],[,b]) => b - a)
                .map(([action, count]) => (
                  <button key={action} onClick={() => setFilter('action', filters.action === action ? '' : action)}
                    className={`px-2.5 py-1 text-xs font-medium rounded-full border transition-colors
                      ${filters.action === action
                        ? (ACTION_STYLE[action] || 'bg-gray-100 text-gray-700') + ' ring-2 ring-offset-1 ring-blue-400'
                        : (ACTION_STYLE[action] || 'bg-gray-100 text-gray-700')
                      }`}>
                    {action} <span className="opacity-70 ml-0.5">({count})</span>
                  </button>
                ))}
            </div>
          )}
        </div>

        {/* Table */}
        {loading ? (
          <div className="flex items-center justify-center py-16 gap-3 text-gray-400">
            <div className="animate-spin h-5 w-5 border-2 border-gray-300 border-t-blue-500 rounded-full" />
            Loading activities…
          </div>
        ) : logs.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-3xl mb-2">🔍</p>
            <p className="text-sm font-medium text-gray-700 mb-1">{t('audit.empty')}</p>
            {activeFilterCount > 0 && (
              <button onClick={clearFilters} className="text-xs text-blue-600 mt-1 hover:underline">
                Clear filters
              </button>
            )}
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-100">
                    <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-32">{t('audit.timestamp')}</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-32">{t('audit.resource')}</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-24">{t('audit.action')}</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Description</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-56">Changes</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-48">Metadata</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {logs.map((log, index) => (
                    <tr key={index} className="hover:bg-gray-50 transition-colors">

                      {/* Time */}
                      <td className="px-5 py-3.5">
                        <p className="text-xs font-medium text-gray-700">{fmtTime(log.timestamp)}</p>
                        <p className="text-xs text-gray-400 font-mono mt-0.5">
                          {formatTime(log.timestamp)}
                        </p>
                      </td>

                      {/* Entity */}
                      <td className="px-4 py-3.5">
                        <div className="flex items-center gap-1.5">
                          <span className="text-base">{ENTITY_ICON[log.entity_type] || '📄'}</span>
                          <span className="text-xs font-medium text-gray-700 capitalize">{log.entity_type}</span>
                        </div>
                        {log.entity_id && (
                          <p className="text-xs text-gray-400 font-mono mt-0.5">
                            {log.entity_id.substring(0, 8)}…
                          </p>
                        )}
                      </td>

                      {/* Action badge */}
                      <td className="px-4 py-3.5">
                        <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wide
                          ${ACTION_STYLE[log.action] || 'bg-gray-100 text-gray-700'}`}>
                          {log.action || '—'}
                        </span>
                      </td>

                      {/* Description */}
                      <td className="px-4 py-3.5 max-w-xs">
                        <p className="text-sm text-gray-700 line-clamp-2" title={log.user_action}>
                          {log.user_action || <span className="text-gray-400 italic">No description</span>}
                        </p>
                      </td>

                      {/* Changes — readable diff, not raw JSON */}
                      <td className="px-4 py-3.5">
                        <ChangesDiff before={log.before_data} after={log.after_data} />
                      </td>

                      {/* Metadata */}
                      <td className="px-4 py-3.5">
                        {log.metadata && Object.keys(log.metadata).length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {Object.entries(log.metadata)
                              .filter(([k, v]) => v && k !== '_id')
                              .slice(0, 3)
                              .map(([key, value]) => (
                                <span key={key}
                                  className="text-xs bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded border border-blue-100"
                                  title={`${key}: ${value}`}>
                                  {key}: {String(value).substring(0, 15)}
                                </span>
                              ))}
                            {Object.keys(log.metadata).filter(k => log.metadata[k] && k !== '_id').length > 3 && (
                              <span className="text-xs text-gray-400">
                                +{Object.keys(log.metadata).filter(k => log.metadata[k] && k !== '_id').length - 3}
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-gray-300 text-xs">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between px-5 py-3.5 border-t border-gray-100 bg-gray-50">
              <p className="text-xs text-gray-500">
                {t('common.showing')} <span className="font-semibold text-gray-700">{formatDate(showFrom)}–{formatDate(showTo)}</span> of{' '}
                <span className="font-semibold text-gray-700">{formatDate(totalCount)}</span> activities
              </p>
              <div className="flex items-center gap-1.5">
                <button onClick={() => setPagination(p => ({ ...p, page: 1 }))}
                  disabled={pagination.page === 1}
                  className="px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg disabled:opacity-40 hover:bg-white transition-colors">
                  First
                </button>
                <button onClick={() => setPagination(p => ({ ...p, page: Math.max(1, p.page - 1) }))}
                  disabled={pagination.page === 1}
                  className="px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg disabled:opacity-40 hover:bg-white transition-colors">
                  ← {t('common.previous')}
                </button>
                <span className="px-3 py-1.5 bg-blue-600 text-white text-xs font-semibold rounded-lg">
                  {pagination.page} / {totalPages}
                </span>
                <button onClick={() => setPagination(p => ({ ...p, page: p.page + 1 }))}
                  disabled={pagination.page >= totalPages}
                  className="px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg disabled:opacity-40 hover:bg-white transition-colors">
                  {t('common.next')} →
                </button>
                <button onClick={() => setPagination(p => ({ ...p, page: totalPages }))}
                  disabled={pagination.page >= totalPages}
                  className="px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg disabled:opacity-40 hover:bg-white transition-colors">
                  Last
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}