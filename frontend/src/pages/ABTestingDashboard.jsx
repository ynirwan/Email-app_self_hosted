import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import API from '../api';

const fmt = (n) => Number(n ?? 0).toLocaleString();

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

const STATUS_STYLE = {
  running:   'bg-blue-100  text-blue-800',
  completed: 'bg-green-100 text-green-800',
  stopped:   'bg-gray-100  text-gray-700',
  failed:    'bg-red-100   text-red-800',
  draft:     'bg-yellow-100 text-yellow-800',
};

export default function ABTestingDashboard() {
  const [abTests, setAbTests]             = useState([]);
  const [loading, setLoading]             = useState(true);
  const [actionLoading, setActionLoading] = useState({});
  const [resultsModal, setResultsModal]   = useState(null);
  const [error, setError]                 = useState('');
  const [search, setSearch]               = useState('');
  const [statusFilter, setStatusFilter]   = useState('');
  const { toasts, show: toast, dismiss }  = useToast();
  const navigate = useNavigate();

  const setRowLoading = (id, v) => setActionLoading(p => ({ ...p, [id]: v }));

  const fetchData = useCallback(async () => {
    try {
      setLoading(true); setError('');
      const res = await API.get('/ab-tests');
      setAbTests(res.data.tests || res.data || []);
    } catch {
      setError('Failed to load A/B tests');
      setAbTests([]);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const startTest = async (testId, testName) => {
    setRowLoading(testId, 'starting');
    try {
      await API.post(`/ab-tests/${testId}/start`);
      toast(`"${testName}" started!`, 'success');
      fetchData();
    } catch (err) {
      toast(err.response?.data?.detail || 'Failed to start test', 'error');
    } finally { setRowLoading(testId, null); }
  };

  const stopTest = async (testId, testName) => {
    if (!confirm(`Stop "${testName}"?`)) return;
    setRowLoading(testId, 'stopping');
    try {
      await API.post(`/ab-tests/${testId}/stop`);
      toast(`"${testName}" stopped`, 'success');
      fetchData();
    } catch (err) {
      toast(err.response?.data?.detail || 'Failed to stop test', 'error');
    } finally { setRowLoading(testId, null); }
  };

  const deleteTest = async (testId, testName) => {
    if (!confirm(`Delete "${testName}"? This cannot be undone.`)) return;
    setRowLoading(testId, 'deleting');
    try {
      await API.delete(`/ab-tests/${testId}`);
      toast(`"${testName}" deleted`, 'success');
      fetchData();
    } catch (err) {
      toast(err.response?.data?.detail || 'Failed to delete test', 'error');
    } finally { setRowLoading(testId, null); }
  };

  const viewResults = async (testId) => {
    setRowLoading(testId, 'loading');
    try {
      const res = await API.get(`/ab-tests/${testId}/results`);
      setResultsModal(res.data);
    } catch (err) {
      toast(err.response?.data?.detail || 'Failed to load results', 'error');
    } finally { setRowLoading(testId, null); }
  };

  const counts = useMemo(() => ({
    total:     abTests.length,
    running:   abTests.filter(t => t.status === 'running').length,
    draft:     abTests.filter(t => t.status === 'draft').length,
    completed: abTests.filter(t => t.status === 'completed').length,
    stopped:   abTests.filter(t => t.status === 'stopped').length,
  }), [abTests]);

  const filtered = useMemo(() => {
    let list = abTests;
    if (statusFilter) list = list.filter(t => t.status === statusFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(t =>
        (t.test_name || '').toLowerCase().includes(q) ||
        (t.test_type || '').toLowerCase().includes(q)
      );
    }
    return list;
  }, [abTests, statusFilter, search]);

  if (loading) return (
    <div className="flex items-center justify-center py-24 gap-3 text-gray-400">
      <div className="animate-spin h-5 w-5 border-2 border-gray-300 border-t-blue-500 rounded-full" />
      Loading A/B tests…
    </div>
  );

  return (
    <div className="space-y-6">
      <ToastContainer toasts={toasts} dismiss={dismiss} />

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <button onClick={() => navigate('/ab-testing/create')}
          className="px-5 py-2.5 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700">
          + Create A/B Test
        </button>
        <button onClick={fetchData}
          className="px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600">
          🔄 Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
          {error} <button onClick={fetchData} className="underline ml-2">Retry</button>
        </div>
      )}

      {/* stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {[
          { label: 'Total',     value: counts.total,     bg: 'bg-blue-50   border-blue-200',   color: 'text-blue-700' },
          { label: 'Running',   value: counts.running,   bg: 'bg-blue-50   border-blue-200',   color: 'text-blue-700',   pulse: counts.running > 0 },
          { label: 'Draft',     value: counts.draft,     bg: 'bg-yellow-50 border-yellow-200', color: 'text-yellow-700' },
          { label: 'Completed', value: counts.completed, bg: 'bg-green-50  border-green-200',  color: 'text-green-700' },
          { label: 'Stopped',   value: counts.stopped,   bg: 'bg-gray-50   border-gray-200',   color: 'text-gray-600' },
        ].map(s => (
          <div key={s.label} className={`rounded-xl border p-4 ${s.bg}`}>
            <p className={`text-2xl font-bold tabular-nums flex items-center gap-2 ${s.color}`}>
              {s.value}
              {s.pulse && <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />}
            </p>
            <p className="text-xs font-medium text-gray-500 mt-0.5">{s.label}</p>
          </div>
        ))}
      </div>

      {/* table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700">
            A/B Tests
            {filtered.length !== abTests.length && (
              <span className="ml-2 text-xs font-normal text-gray-400">({filtered.length} of {abTests.length})</span>
            )}
          </h2>
          <div className="flex items-center gap-2">
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
              className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-white text-gray-600">
              <option value="">All statuses</option>
              <option value="draft">Draft</option>
              <option value="running">Running</option>
              <option value="completed">Completed</option>
              <option value="stopped">Stopped</option>
            </select>
            <div className="relative">
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs">🔍</span>
              <input type="text" placeholder="Search tests…" value={search}
                onChange={e => setSearch(e.target.value)}
                className="pl-7 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 w-44" />
              {search && (
                <button onClick={() => setSearch('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-300 hover:text-gray-500 text-xs">✕</button>
              )}
            </div>
          </div>
        </div>

        {abTests.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-3xl mb-2">🧪</p>
            <p className="text-sm font-medium text-gray-700 mb-1">No A/B tests yet</p>
            <p className="text-xs text-gray-400 mb-4">Create your first test to start optimising campaigns</p>
            <button onClick={() => navigate('/ab-testing/create')}
              className="px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700">
              Create A/B Test
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-sm text-gray-500">No tests match your filters</p>
            <button onClick={() => { setSearch(''); setStatusFilter(''); }}
              className="text-xs text-blue-600 mt-2 hover:underline">Clear filters</button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Test Name</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Lists</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-28">Status</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-20">Sample</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map(test => {
                  const busy = actionLoading[test._id];
                  return (
                    <tr key={test._id} className="hover:bg-gray-50 transition-colors">
                      <td className="px-5 py-3.5 font-medium text-gray-900">{test.test_name}</td>
                      <td className="px-4 py-3.5">
                        <span className="px-2 py-0.5 bg-gray-100 text-gray-700 rounded text-xs capitalize">
                          {(test.test_type || '').replace('_', ' ')}
                        </span>
                      </td>
                      <td className="px-4 py-3.5 text-xs text-gray-500 max-w-[120px] truncate">
                        {(test.target_lists || []).join(', ') || '—'}
                      </td>
                      <td className="px-4 py-3.5">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLE[test.status] || STATUS_STYLE.draft}`}>
                          {test.status === 'running' && <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse" />}
                          {test.status}
                        </span>
                      </td>
                      <td className="px-4 py-3.5 text-right tabular-nums text-xs text-gray-600">
                        {fmt(test.sample_size)}
                      </td>
                      <td className="px-4 py-3.5">
                        <div className="flex items-center justify-end gap-1.5 flex-wrap">
                          {test.status === 'draft' && (
                            <button onClick={() => startTest(test._id, test.test_name)} disabled={!!busy}
                              className="px-2.5 py-1.5 text-xs font-medium border border-green-200 rounded-lg hover:bg-green-50 text-green-700 disabled:opacity-50">
                              {busy === 'starting' ? '⏳' : 'Start'}
                            </button>
                          )}
                          {test.status === 'running' && (
                            <button onClick={() => stopTest(test._id, test.test_name)} disabled={!!busy}
                              className="px-2.5 py-1.5 text-xs font-medium border border-orange-200 rounded-lg hover:bg-orange-50 text-orange-700 disabled:opacity-50">
                              {busy === 'stopping' ? '⏳' : 'Stop'}
                            </button>
                          )}
                          {(test.status === 'running' || test.status === 'completed') && (
                            <button onClick={() => viewResults(test._id)} disabled={!!busy}
                              className="px-2.5 py-1.5 text-xs font-medium border border-purple-200 rounded-lg hover:bg-purple-50 text-purple-700 disabled:opacity-50">
                              {busy === 'loading' ? '⏳' : 'Quick View'}
                            </button>
                          )}
                          <Link to={`/ab-tests/${test._id}/results`}
                            className="px-2.5 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600">
                            Full Report
                          </Link>
                          <button onClick={() => deleteTest(test._id, test.test_name)} disabled={!!busy}
                            className="px-2.5 py-1.5 text-xs font-medium border border-red-200 rounded-lg hover:bg-red-50 text-red-600 disabled:opacity-50">
                            {busy === 'deleting' ? '⏳' : 'Delete'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Quick-view results modal */}
      {resultsModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-3xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b">
              <div>
                <h3 className="text-base font-semibold">{resultsModal.test_name}</h3>
                <p className="text-xs text-gray-400">Quick Results Summary</p>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => { setResultsModal(null); navigate(`/ab-tests/${resultsModal.test_id}/results`); }}
                  className="px-3 py-1.5 bg-purple-600 text-white text-xs font-semibold rounded-lg hover:bg-purple-700">
                  Full Report →
                </button>
                <button onClick={() => setResultsModal(null)} className="text-gray-400 hover:text-gray-600 text-xl">✕</button>
              </div>
            </div>
            <div className="p-6 space-y-4">
              {/* meta */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 bg-gray-50 rounded-xl p-4 text-sm">
                {[
                  { label: 'Status',      value: resultsModal.status },
                  { label: 'Type',        value: (resultsModal.test_type || '').replace('_', ' ') },
                  { label: 'Sample Size', value: fmt(resultsModal.sample_size) },
                  { label: 'Lists',       value: (resultsModal.target_lists || []).join(', ') || '—' },
                ].map(({ label, value }) => (
                  <div key={label}>
                    <p className="text-xs text-gray-400 mb-0.5">{label}</p>
                    <p className="font-semibold text-gray-800 capitalize">{value}</p>
                  </div>
                ))}
              </div>

              {/* winner */}
              {resultsModal.winner?.winner && resultsModal.winner.winner !== 'TIE' && (
                <div className="bg-green-50 border border-green-200 rounded-xl p-4">
                  <p className="font-bold text-green-800">
                    🏆 Variant {resultsModal.winner.winner} is winning by {Number(resultsModal.winner.improvement ?? 0).toFixed(2)}%
                  </p>
                </div>
              )}
              {resultsModal.winner?.winner === 'TIE' && (
                <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4">
                  <p className="font-bold text-yellow-800">🤝 Both variants equal — test inconclusive</p>
                </div>
              )}

              {/* comparison */}
              {resultsModal.results && (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-50 border-b border-gray-100">
                        {['Variant', 'Sent', 'Opened', 'Open Rate', 'Clicked', 'Click Rate'].map(h => (
                          <th key={h} className={`px-4 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wider ${h === 'Variant' ? 'text-left' : 'text-right'}`}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {[
                        { label: 'Variant A', data: resultsModal.results.variant_a, color: 'text-blue-700' },
                        { label: 'Variant B', data: resultsModal.results.variant_b, color: 'text-orange-700' },
                      ].map(({ label, data, color }) => (
                        <tr key={label} className="hover:bg-gray-50">
                          <td className={`px-4 py-3 font-semibold ${color}`}>{label}</td>
                          <td className="px-4 py-3 text-right tabular-nums">{fmt(data?.sent)}</td>
                          <td className="px-4 py-3 text-right tabular-nums">{fmt(data?.opened)}</td>
                          <td className="px-4 py-3 text-right font-medium">{Number(data?.open_rate ?? 0).toFixed(2)}%</td>
                          <td className="px-4 py-3 text-right tabular-nums">{fmt(data?.clicked)}</td>
                          <td className="px-4 py-3 text-right font-medium">{Number(data?.click_rate ?? 0).toFixed(2)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* significance */}
              {resultsModal.statistical_significance && (
                <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-sm">
                  <p className="font-semibold text-blue-800 mb-1">Statistical Significance</p>
                  <p className="text-blue-700">
                    Confidence: <strong className="uppercase">{resultsModal.statistical_significance.confidence_level}</strong>
                    {' · '}Total samples: <strong>{fmt(resultsModal.statistical_significance.total_samples)}</strong>
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}