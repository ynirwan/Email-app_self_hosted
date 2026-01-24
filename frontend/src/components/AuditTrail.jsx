import { useEffect, useState } from 'react';
import API from '../api';

export default function AuditTrail() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    entity_type: '',
    action: '',
    start_date: '',
    end_date: '',
    search: ''
  });
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 50,
    total: 0
  });
  const [stats, setStats] = useState({
    total: 0,
    byAction: {},
    byEntity: {},
    recent24h: 0
  });

  // Enhanced entity types covering all features
  const entityTypes = [
    { value: 'subscriber', label: '👤 Subscribers', icon: '👤' },
    { value: 'list', label: '📋 Lists', icon: '📋' },
    { value: 'campaign', label: '📧 Campaigns', icon: '📧' },
    { value: 'segment', label: '🎯 Segments', icon: '🎯' },
    { value: 'automation', label: '🤖 Automation', icon: '🤖' },
    { value: 'template', label: '📝 Templates', icon: '📝' },
    { value: 'suppression', label: '🚫 Suppressions', icon: '🚫' },
    { value: 'ab_test', label: '🧪 A/B Tests', icon: '🧪' },
    { value: 'bulk_upload', label: '📤 Bulk Uploads', icon: '📤' },
    { value: 'email', label: '✉️ Email Settings', icon: '✉️' },
    { value: 'smtp', label: '🔧 SMTP Config', icon: '🔧' }
  ];

  // Enhanced action types
  const actionTypes = [
    { value: 'create', label: 'Create', color: 'green' },
    { value: 'update', label: 'Update', color: 'blue' },
    { value: 'delete', label: 'Delete', color: 'red' },
    { value: 'upload', label: 'Upload', color: 'purple' },
    { value: 'export', label: 'Export', color: 'yellow' },
    { value: 'send', label: 'Send', color: 'indigo' },
    { value: 'pause', label: 'Pause', color: 'orange' },
    { value: 'resume', label: 'Resume', color: 'teal' },
    { value: 'test', label: 'Test', color: 'pink' },
    { value: 'refresh', label: 'Refresh', color: 'cyan' },
    { value: 'reactivate', label: 'Reactivate', color: 'lime' },
    { value: 'start', label: 'Start', color: 'emerald' },
    { value: 'stop', label: 'Stop', color: 'rose' },
    { value: 'trigger', label: 'Trigger', color: 'violet' }
  ];

  const fetchLogs = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      params.append('limit', pagination.limit);
      params.append('skip', (pagination.page - 1) * pagination.limit);

      if (filters.entity_type) params.append('entity_type', filters.entity_type);
      if (filters.action) params.append('action', filters.action);
      if (filters.start_date) params.append('start_date', filters.start_date);
      if (filters.end_date) params.append('end_date', filters.end_date);

      const res = await API.get(`/audit/logs?${params}`);
      setLogs(res.data.logs);
      setPagination(prev => ({ ...prev, total: res.data.total_count }));

      // Calculate statistics
      calculateStats(res.data.logs, res.data.total_count);
    } catch (err) {
      console.error("Failed to fetch audit logs", err);
      alert("Failed to load audit logs");
    } finally {
      setLoading(false);
    }
  };

  const calculateStats = (logsData, total) => {
    const byAction = {};
    const byEntity = {};
    const twentyFourHoursAgo = new Date(Date.now() - 24 * 60 * 60 * 1000);
    let recent24h = 0;

    logsData.forEach(log => {
      // Count by action
      byAction[log.action] = (byAction[log.action] || 0) + 1;

      // Count by entity
      byEntity[log.entity_type] = (byEntity[log.entity_type] || 0) + 1;

      // Count recent activities
      if (new Date(log.timestamp) > twentyFourHoursAgo) {
        recent24h++;
      }
    });

    setStats({ total, byAction, byEntity, recent24h });
  };

  useEffect(() => {
    fetchLogs();
  }, [pagination.page, filters.entity_type, filters.action, filters.start_date, filters.end_date]);

  const formatTimestamp = (timestamp) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getActionBadge = (action) => {
    const actionConfig = actionTypes.find(a => a.value === action);
    const color = actionConfig?.color || 'gray';

    const colorClasses = {
      green: 'bg-green-100 text-green-800 border-green-200',
      blue: 'bg-blue-100 text-blue-800 border-blue-200',
      red: 'bg-red-100 text-red-800 border-red-200',
      purple: 'bg-purple-100 text-purple-800 border-purple-200',
      yellow: 'bg-yellow-100 text-yellow-800 border-yellow-200',
      indigo: 'bg-indigo-100 text-indigo-800 border-indigo-200',
      orange: 'bg-orange-100 text-orange-800 border-orange-200',
      teal: 'bg-teal-100 text-teal-800 border-teal-200',
      pink: 'bg-pink-100 text-pink-800 border-pink-200',
      cyan: 'bg-cyan-100 text-cyan-800 border-cyan-200',
      lime: 'bg-lime-100 text-lime-800 border-lime-200',
      emerald: 'bg-emerald-100 text-emerald-800 border-emerald-200',
      rose: 'bg-rose-100 text-rose-800 border-rose-200',
      violet: 'bg-violet-100 text-violet-800 border-violet-200',
      gray: 'bg-gray-100 text-gray-800 border-gray-200'
    };

    return colorClasses[color];
  };

  const getEntityIcon = (entityType) => {
    const entity = entityTypes.find(e => e.value === entityType);
    return entity?.icon || '📄';
  };

  const clearFilters = () => {
    setFilters({
      entity_type: '',
      action: '',
      start_date: '',
      end_date: '',
      search: ''
    });
    setPagination(prev => ({ ...prev, page: 1 }));
  };

  const exportLogs = async () => {
    try {
      const params = new URLSearchParams();
      if (filters.entity_type) params.append('entity_type', filters.entity_type);
      if (filters.action) params.append('action', filters.action);
      if (filters.start_date) params.append('start_date', filters.start_date);
      if (filters.end_date) params.append('end_date', filters.end_date);

      const response = await API.get(`/audit/export?${params}`, {
        responseType: 'blob'
      });

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `audit-logs-${new Date().toISOString()}.csv`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      console.error("Failed to export logs", err);
      alert("Failed to export audit logs");
    }
  };

  const filteredLogs = logs.filter(log => {
    if (!filters.search) return true;
    const searchLower = filters.search.toLowerCase();
    return (
      log.user_action?.toLowerCase().includes(searchLower) ||
      log.entity_type?.toLowerCase().includes(searchLower) ||
      log.action?.toLowerCase().includes(searchLower) ||
      log.entity_id?.toLowerCase().includes(searchLower)
    );
  });

  return (
    <div className="max-w-8xl mx-auto mt-10 px-4">
      {/* Header */}
      <div className="flex justify-between items-center mb-1">
        <div>
          <h2 className="text-3xl font-bold text-gray-800">📋 Audit Trail</h2>
          <p className="text-gray-600 mt-1">Complete activity log across all system features</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={exportLogs}
            className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 flex items-center gap-2"
            title="Export audit logs"
          >
            <span>📥</span> Export
          </button>
          <button
            onClick={clearFilters}
            className="bg-gray-600 text-white px-4 py-2 rounded hover:bg-gray-700"
          >
            Clear Filters
          </button>
          <button
            onClick={fetchLogs}
            className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 flex items-center gap-2"
          >
            <span>🔄</span> Refresh
          </button>
        </div>
      </div>

      {/* Statistics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-1">
        <div className="bg-gradient-to-br from-blue-50 to-blue-100 p-4 rounded-lg border border-blue-200 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-blue-600 font-medium">Total Activities</p>
              <p className="text-3xl font-bold text-blue-800">{stats.total.toLocaleString()}</p>
            </div>
            <span className="text-4xl">📊</span>
          </div>
        </div>

        <div className="bg-gradient-to-br from-green-50 to-green-100 p-4 rounded-lg border border-green-200 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-green-600 font-medium">Last 24 Hours</p>
              <p className="text-3xl font-bold text-green-800">{stats.recent24h}</p>
            </div>
            <span className="text-4xl">⏱️</span>
          </div>
        </div>

        <div className="bg-gradient-to-br from-purple-50 to-purple-100 p-4 rounded-lg border border-purple-200 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-purple-600 font-medium">Entity Types</p>
              <p className="text-3xl font-bold text-purple-800">{Object.keys(stats.byEntity).length}</p>
            </div>
            <span className="text-4xl">🗂️</span>
          </div>
        </div>

        <div className="bg-gradient-to-br from-orange-50 to-orange-100 p-4 rounded-lg border border-orange-200 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-orange-600 font-medium">Action Types</p>
              <p className="text-3xl font-bold text-orange-800">{Object.keys(stats.byAction).length}</p>
            </div>
            <span className="text-4xl">⚡</span>
          </div>
        </div>
      </div>

      {/* Filters Section */}
      <div className="bg-white p-6 rounded-lg shadow-md mb-1 border border-gray-200">
        <h3 className="font-semibold mb-4 text-lg flex items-center gap-2">
          <span>🔍</span> Filter Activities
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          <div>
            <label className="block text-sm font-medium mb-2 text-gray-700">Entity Type</label>
            <select
              value={filters.entity_type}
              onChange={e => setFilters({ ...filters, entity_type: e.target.value })}
              className="border border-gray-300 p-2 rounded w-full focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="">All Types</option>
              {entityTypes.map(entity => (
                <option key={entity.value} value={entity.value}>
                  {entity.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2 text-gray-700">Action</label>
            <select
              value={filters.action}
              onChange={e => setFilters({ ...filters, action: e.target.value })}
              className="border border-gray-300 p-2 rounded w-full focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="">All Actions</option>
              {actionTypes.map(action => (
                <option key={action.value} value={action.value}>
                  {action.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2 text-gray-700">Start Date</label>
            <input
              type="datetime-local"
              value={filters.start_date}
              onChange={e => setFilters({ ...filters, start_date: e.target.value })}
              className="border border-gray-300 p-2 rounded w-full focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-2 text-gray-700">End Date</label>
            <input
              type="datetime-local"
              value={filters.end_date}
              onChange={e => setFilters({ ...filters, end_date: e.target.value })}
              className="border border-gray-300 p-2 rounded w-full focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-2 text-gray-700">Search</label>
            <input
              type="text"
              placeholder="Search activities..."
              value={filters.search}
              onChange={e => setFilters({ ...filters, search: e.target.value })}
              className="border border-gray-300 p-2 rounded w-full focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
        </div>
      </div>

      {/* Quick Stats by Action */}
      <div className="bg-white p-4 rounded-lg shadow-md mb-1 border border-gray-200">
        <h3 className="font-semibold mb-1 text-gray-800">Activity Breakdown</h3>
        <div className="flex flex-wrap gap-3">
          {actionTypes.map(actionType => {
            const count = stats.byAction[actionType.value] || 0;
            if (count === 0) return null;
            return (
              <div
                key={actionType.value}
                className={`px-3 py-2 rounded-lg border ${getActionBadge(actionType.value)} cursor-pointer hover:shadow-md transition-shadow`}
                onClick={() => setFilters({ ...filters, action: actionType.value })}
              >
                <span className="font-semibold">{actionType.label}</span>
                <span className="ml-2 text-sm">({count})</span>
              </div>
            );
          })}
        </div>
      </div>
       
      {/* Activity Timeline View (Optional) */}
      {filteredLogs.length > 0 && (
        <div className="mt-6 bg-white p-6 rounded-lg shadow-md border border-gray-200">
          <h3 className="font-semibold mb-4 text-lg flex items-center gap-2">
            <span>📅</span> Recent Activity Timeline
          </h3>
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {filteredLogs.slice(0, 10).map((log, index) => (
              <div key={index} className="flex items-start gap-3 p-3 hover:bg-gray-50 rounded transition-colors">
                <div className="flex-shrink-0">
                  <span className="text-2xl">{getEntityIcon(log.entity_type)}</span>
                </div>
                <div className="flex-grow">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${getActionBadge(log.action)}`}>
                      {log.action}
                    </span>
                    <span className="text-xs text-gray-500">{formatTimestamp(log.timestamp)}</span>
                  </div>
                  <p className="text-sm text-gray-700">{log.user_action}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
         
      {/* Audit Logs Table */}
      <div className="bg-white shadow-lg rounded-lg border border-gray-200">
        {loading ? (
          <div className="p-12 text-center">
            <div className="inline-block w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-4"></div>
            <p className="text-gray-600 font-medium">Loading activities...</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full table-auto text-sm">
              <thead className="bg-gradient-to-r from-gray-50 to-gray-100 border-b-2 border-gray-200">
                <tr>
                  <th className="p-4 text-left font-semibold text-gray-700">Time</th>
                  <th className="p-4 text-left font-semibold text-gray-700">Entity</th>
                  <th className="p-4 text-left font-semibold text-gray-700">Action</th>
                  <th className="p-4 text-left font-semibold text-gray-700">Description</th>
                  <th className="p-4 text-left font-semibold text-gray-700">Changes</th>
                  <th className="p-4 text-left font-semibold text-gray-700">Metadata</th>
                </tr>
              </thead>
              <tbody>
                {filteredLogs.length === 0 ? (
                  <tr>
                    <td colSpan="6" className="p-12 text-center">
                      <div className="text-gray-400 text-6xl mb-4">🔍</div>
                      <p className="text-gray-500 font-medium text-lg">No activities found</p>
                      <p className="text-gray-400 text-sm mt-2">Try adjusting your filters or search criteria</p>
                    </td>
                  </tr>
                ) : (
                  filteredLogs.map((log, index) => (
                    <tr
                      key={index}
                      className="border-t border-gray-100 hover:bg-blue-50 transition-colors"
                    >
                      <td className="p-4">
                        <div className="flex flex-col">
                          <span className="text-xs font-medium text-gray-600">
                            {formatTimestamp(log.timestamp)}
                          </span>
                          <span className="text-xs text-gray-400 font-mono">
                            {new Date(log.timestamp).toLocaleTimeString()}
                          </span>
                        </div>
                      </td>

                      <td className="p-4">
                        <div className="flex items-center gap-2">
                          <span className="text-xl">{getEntityIcon(log.entity_type)}</span>
                          <span className="text-xs font-medium bg-gray-100 px-2 py-1 rounded border border-gray-200">
                            {log.entity_type}
                          </span>
                        </div>
                      </td>

                      <td className="p-4">
                        <span className={`px-3 py-1 rounded-full text-xs font-bold border ${getActionBadge(log.action)}`}>
                          {log.action?.toUpperCase() || 'UNKNOWN'}
                        </span>
                      </td>

                      <td className="p-4 max-w-md">
                        <div className="text-sm text-gray-700 line-clamp-2" title={log.user_action}>
                          {log.user_action}
                        </div>
                        {log.entity_id && (
                          <div className="text-xs text-gray-400 mt-1 font-mono">
                            ID: {log.entity_id.substring(0, 8)}...
                          </div>
                        )}
                      </td>

                      <td className="p-4">
                        <div className="space-y-1 max-w-xs">
                          {log.before_data && Object.keys(log.before_data).length > 0 && (
                            <div className="bg-red-50 p-2 rounded border border-red-200">
                              <span className="font-semibold text-red-700 text-xs">Before:</span>
                              <div className="text-xs text-red-600 mt-1 max-h-20 overflow-auto">
                                {JSON.stringify(log.before_data, null, 2)}
                              </div>
                            </div>
                          )}
                          {log.after_data && Object.keys(log.after_data).length > 0 && (
                            <div className="bg-green-50 p-2 rounded border border-green-200">
                              <span className="font-semibold text-green-700 text-xs">After:</span>
                              <div className="text-xs text-green-600 mt-1 max-h-20 overflow-auto">
                                {JSON.stringify(log.after_data, null, 2)}
                              </div>
                            </div>
                          )}
                        </div>
                      </td>

                      <td className="p-4">
                        <div className="flex flex-wrap gap-1 max-w-xs">
                          {log.metadata && Object.entries(log.metadata).map(([key, value]) => {
                            if (!value || key === '_id') return null;
                            return (
                              <span
                                key={key}
                                className="text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded border border-blue-200"
                                title={`${key}: ${value}`}
                              >
                                {key}: {typeof value === 'object' ? JSON.stringify(value).substring(0, 20) + '...' : String(value).substring(0, 20)}
                              </span>
                            );
                          })}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>

            {/* Pagination */}
            {filteredLogs.length > 0 && (
              <div className="p-4 border-t border-gray-200 flex justify-between items-center bg-gray-50">
                <span className="text-sm text-gray-600">
                  Showing <span className="font-semibold">{(pagination.page - 1) * pagination.limit + 1}</span> to{' '}
                  <span className="font-semibold">{Math.min(pagination.page * pagination.limit, pagination.total)}</span> of{' '}
                  <span className="font-semibold">{pagination.total.toLocaleString()}</span> activities
                </span>
                <div className="flex gap-2 items-center">
                  <button
                    onClick={() => setPagination(prev => ({ ...prev, page: 1 }))}
                    disabled={pagination.page === 1}
                    className="px-3 py-1 border border-gray-300 rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-100 text-sm"
                  >
                    First
                  </button>
                  <button
                    onClick={() => setPagination(prev => ({ ...prev, page: Math.max(1, prev.page - 1) }))}
                    disabled={pagination.page === 1}
                    className="px-3 py-1 border border-gray-300 rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-100 text-sm"
                  >
                    ← Previous
                  </button>
                  <span className="px-4 py-1 bg-blue-100 text-blue-800 rounded font-semibold text-sm">
                    Page {pagination.page} of {Math.ceil(pagination.total / pagination.limit)}
                  </span>
                  <button
                    onClick={() => setPagination(prev => ({ ...prev, page: prev.page + 1 }))}
                    disabled={pagination.page >= Math.ceil(pagination.total / pagination.limit)}
                    className="px-3 py-1 border border-gray-300 rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-100 text-sm"
                  >
                    Next →
                  </button>
                  <button
                    onClick={() => setPagination(prev => ({ ...prev, page: Math.ceil(pagination.total / pagination.limit) }))}
                    disabled={pagination.page >= Math.ceil(pagination.total / pagination.limit)}
                    className="px-3 py-1 border border-gray-300 rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-100 text-sm"
                  >
                    Last
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
