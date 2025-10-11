import { useEffect, useState } from 'react';
import API from '../api';

export default function AuditTrail() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    entity_type: '',
    action: '',
    start_date: '',
    end_date: ''
  });
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 50,
    total: 0
  });

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

      const res = await API.get(`/subscribers/audit/logs?${params}`);
      setLogs(res.data.logs);
      setPagination(prev => ({ ...prev, total: res.data.total }));
    } catch (err) {
      console.error("Failed to fetch audit logs", err);
      alert("Failed to load audit logs");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [pagination.page, filters]);

  const formatTimestamp = (timestamp) => {
    return new Date(timestamp).toLocaleString();
  };

  const getActionBadge = (action) => {
    const colors = {
      create: 'bg-green-100 text-green-800',
      update: 'bg-blue-100 text-blue-800',
      delete: 'bg-red-100 text-red-800',
      upload: 'bg-purple-100 text-purple-800',
      export: 'bg-yellow-100 text-yellow-800'
    };
    return colors[action] || 'bg-gray-100 text-gray-800';
  };

  const clearFilters = () => {
    setFilters({
      entity_type: '',
      action: '',
      start_date: '',
      end_date: ''
    });
    setPagination(prev => ({ ...prev, page: 1 }));
  };

  return (
    <div className="max-w-7xl mx-auto mt-10">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold">📋 Audit Trail</h2>
        <div className="flex gap-2">
          <button
            onClick={clearFilters}
            className="bg-gray-600 text-white px-4 py-2 rounded hover:bg-gray-700"
          >
            Clear Filters
          </button>
          <button
            onClick={() => fetchLogs()}
            className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Filters Section */}
      <div className="bg-white p-4 rounded shadow mb-6">
        <h3 className="font-semibold mb-3">🔍 Filter Activities</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">Entity Type</label>
            <select
              value={filters.entity_type}
              onChange={e => setFilters({...filters, entity_type: e.target.value})}
              className="border p-2 rounded w-full"
            >
              <option value="">All Types</option>
              <option value="subscriber">Subscribers</option>
              <option value="list">Lists</option>
              <option value="bulk_upload">Bulk Uploads</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Action</label>
            <select
              value={filters.action}
              onChange={e => setFilters({...filters, action: e.target.value})}
              className="border p-2 rounded w-full"
            >
              <option value="">All Actions</option>
              <option value="create">Create</option>
              <option value="update">Update</option>
              <option value="delete">Delete</option>
              <option value="upload">Upload</option>
              <option value="export">Export</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Start Date</label>
            <input
              type="datetime-local"
              value={filters.start_date}
              onChange={e => setFilters({...filters, start_date: e.target.value})}
              className="border p-2 rounded w-full"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">End Date</label>
            <input
              type="datetime-local"
              value={filters.end_date}
              onChange={e => setFilters({...filters, end_date: e.target.value})}
              className="border p-2 rounded w-full"
            />
          </div>
        </div>
      </div>

      {/* Activity Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-6">
        <div className="bg-green-50 p-4 rounded border border-green-200">
          <h4 className="font-semibold text-green-800">Creates</h4>
          <p className="text-2xl font-bold text-green-600">
            {logs.filter(log => log.action === 'create').length}
          </p>
        </div>
        <div className="bg-blue-50 p-4 rounded border border-blue-200">
          <h4 className="font-semibold text-blue-800">Updates</h4>
          <p className="text-2xl font-bold text-blue-600">
            {logs.filter(log => log.action === 'update').length}
          </p>
        </div>
        <div className="bg-red-50 p-4 rounded border border-red-200">
          <h4 className="font-semibold text-red-800">Deletes</h4>
          <p className="text-2xl font-bold text-red-600">
            {logs.filter(log => log.action === 'delete').length}
          </p>
        </div>
        <div className="bg-purple-50 p-4 rounded border border-purple-200">
          <h4 className="font-semibold text-purple-800">Uploads</h4>
          <p className="text-2xl font-bold text-purple-600">
            {logs.filter(log => log.action === 'upload').length}
          </p>
        </div>
        <div className="bg-yellow-50 p-4 rounded border border-yellow-200">
          <h4 className="font-semibold text-yellow-800">Exports</h4>
          <p className="text-2xl font-bold text-yellow-600">
            {logs.filter(log => log.action === 'export').length}
          </p>
        </div>
      </div>

      {/* Audit Logs Table */}
      <div className="bg-white shadow rounded">
        {loading ? (
          <div className="p-8 text-center">
            <div className="spinner-border animate-spin inline-block w-8 h-8 border-4 rounded-full" role="status">
              <span className="visually-hidden">Loading...</span>
            </div>
            <p className="mt-2">Loading activities...</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full table-auto text-sm">
              <thead className="bg-gray-100">
                <tr>
                  <th className="p-3 text-left">Timestamp</th>
                  <th className="p-3 text-left">Action</th>
                  <th className="p-3 text-left">Entity</th>
                  <th className="p-3 text-left">Description</th>
                  <th className="p-3 text-left">Details</th>
                  <th className="p-3 text-left">Metadata</th>
                </tr>
              </thead>
              <tbody>
                {logs.length === 0 ? (
                  <tr>
                    <td colSpan="6" className="p-8 text-center text-gray-500">
                      No activities found. Try adjusting your filters.
                    </td>
                  </tr>
                ) : (
                  logs.map((log, index) => (
                    <tr key={index} className="border-t hover:bg-gray-50">
                      <td className="p-3 text-xs font-mono">
                        {formatTimestamp(log.timestamp)}
                      </td>
                      <td className="p-3">
                        <span className={`px-2 py-1 rounded text-xs font-semibold ${getActionBadge(log.action)}`}>
                          {log.action.toUpperCase()}
                        </span>
                      </td>
                      <td className="p-3">
                        <span className="text-gray-600 text-xs bg-gray-100 px-2 py-1 rounded">
                          {log.entity_type}
                        </span>
                      </td>
                      <td className="p-3 max-w-xs">
                        <div className="truncate" title={log.user_action}>
                          {log.user_action}
                        </div>
                      </td>
                      <td className="p-3">
                        <div className="text-xs space-y-1">
                          {log.before_data && Object.keys(log.before_data).length > 0 && (
                            <div className="bg-red-50 p-1 rounded">
                              <span className="font-semibold text-red-700">Before: </span>
                              {log.before_data.email || log.before_data.list_name || 'Data changed'}
                            </div>
                          )}
                          {log.after_data && Object.keys(log.after_data).length > 0 && (
                            <div className="bg-green-50 p-1 rounded">
                              <span className="font-semibold text-green-700">After: </span>
                              {log.after_data.email || log.after_data.list_name || 'New data'}
                            </div>
                          )}
                        </div>
                      </td>
                      <td className="p-3">
                        <div className="text-xs space-y-1">
                          {log.metadata?.list_name && (
                            <span className="bg-blue-100 text-blue-800 px-1 py-0.5 rounded">
                              📝 {log.metadata.list_name}
                            </span>
                          )}
                          {log.metadata?.count && (
                            <span className="bg-purple-100 text-purple-800 px-1 py-0.5 rounded block">
                              📊 Count: {log.metadata.count}
                            </span>
                          )}
                          {log.metadata?.ip_address && (
                            <span className="bg-gray-100 text-gray-600 px-1 py-0.5 rounded block">
                              🌐 {log.metadata.ip_address}
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>

            {/* Pagination */}
            {logs.length > 0 && (
              <div className="p-4 border-t flex justify-between items-center bg-gray-50">
                <span className="text-sm text-gray-600">
                  Showing {(pagination.page - 1) * pagination.limit + 1} to{' '}
                  {Math.min(pagination.page * pagination.limit, pagination.total)} of{' '}
                  {pagination.total} activities
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => setPagination(prev => ({ ...prev, page: Math.max(1, prev.page - 1) }))}
                    disabled={pagination.page === 1}
                    className="px-3 py-1 border rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-100"
                  >
                    Previous
                  </button>
                  <span className="px-3 py-1 bg-blue-100 text-blue-800 rounded">
                    Page {pagination.page} of {Math.ceil(pagination.total / pagination.limit)}
                  </span>
                  <button
                    onClick={() => setPagination(prev => ({ ...prev, page: prev.page + 1 }))}
                    disabled={pagination.page >= Math.ceil(pagination.total / pagination.limit)}
                    className="px-3 py-1 border rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-100"
                  >
                    Next
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

