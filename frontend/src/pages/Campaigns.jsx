import { useEffect, useState, useCallback, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import API from '../api';

// ─── helpers ────────────────────────────────────────────────
const fmt  = (n) => Number(n ?? 0).toLocaleString();
const fmtD = (iso) => iso ? new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '—';

const STATUS_STYLE = {
  draft:     'bg-yellow-100 text-yellow-800',
  sending:   'bg-blue-100   text-blue-800',
  paused:    'bg-orange-100 text-orange-800',
  scheduled: 'bg-purple-100 text-purple-800',
  completed: 'bg-green-100  text-green-800',
  sent:      'bg-green-100  text-green-800',
  stopped:   'bg-gray-100   text-gray-700',
  failed:    'bg-red-100    text-red-700',
};

// ─── Toast ───────────────────────────────────────────────────
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

// ─── Modal ───────────────────────────────────────────────────
function Modal({ title, children, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h3 className="text-base font-semibold">{title}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">✕</button>
        </div>
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  );
}

// ─── StatCard ────────────────────────────────────────────────
function StatCard({ label, value, color, pulse }) {
  const colors = {
    blue:   'bg-blue-50   border-blue-200   text-blue-700',
    yellow: 'bg-yellow-50 border-yellow-200 text-yellow-700',
    purple: 'bg-purple-50 border-purple-200 text-purple-700',
    green:  'bg-green-50  border-green-200  text-green-700',
    orange: 'bg-orange-50 border-orange-200 text-orange-700',
    gray:   'bg-gray-50   border-gray-200   text-gray-600',
    red:    'bg-red-50    border-red-200    text-red-700',
  };
  return (
    <div className={`rounded-xl border p-4 ${colors[color] || colors.gray}`}>
      <p className="text-2xl font-bold tabular-nums flex items-center gap-2">
        {value}
        {pulse && <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />}
      </p>
      <p className="text-xs font-medium mt-0.5 opacity-75">{label}</p>
    </div>
  );
}

// ─── Main ────────────────────────────────────────────────────
export default function Campaigns() {
  const [campaigns, setCampaigns] = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);
  const { toasts, show: toast, dismiss } = useToast();

  // filters
  const [search,       setSearch]       = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  // send modal
  const [showSendModal, setShowSendModal]         = useState(false);
  const [selectedCampaign, setSelectedCampaign]   = useState(null);
  const [sending, setSending]                     = useState(false);

  // test modal
  const [showTestModal, setShowTestModal] = useState(false);
  const [testEmail,     setTestEmail]     = useState('');
  const [testing,       setTesting]       = useState(false);

  // schedule modal
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [scheduleDate,      setScheduleDate]      = useState('');
  const [scheduleTime,      setScheduleTime]      = useState('');
  const [scheduling,        setScheduling]        = useState(false);

  // per-row action loading
  const [actionLoading, setActionLoading] = useState({});
  const setRowLoading = (id, v) => setActionLoading(p => ({ ...p, [id]: v }));

  const navigate = useNavigate();

  const fetchCampaigns = useCallback(async () => {
    try {
      setLoading(true); setError(null);
      const res = await API.get('/campaigns');
      const data = res.data.campaigns || res.data;
      setCampaigns(Array.isArray(data) ? data : []);
    } catch { setError('Failed to load campaigns'); setCampaigns([]);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchCampaigns(); }, [fetchCampaigns]);

  const closeModals = () => {
    setShowSendModal(false); setShowTestModal(false); setShowScheduleModal(false);
    setSelectedCampaign(null); setSending(false); setTesting(false);
    setTestEmail(''); setScheduleDate(''); setScheduleTime(''); setScheduling(false);
  };

  // ── actions ─────────────────────────────────────────────
  const confirmSend = async () => {
    try {
      setSending(true);
      await API.post(`/campaigns/${selectedCampaign._id}/send`);
      toast('Campaign sending started!', 'success');
      closeModals(); fetchCampaigns();
    } catch (e) { toast(e.response?.data?.detail || 'Send failed', 'error'); setSending(false); }
  };

  const confirmTest = async () => {
    if (!testEmail.trim()) return;
    try {
      setTesting(true);
      await API.post(`/campaigns/${selectedCampaign._id}/test-email`, { test_email: testEmail.trim(), use_custom_data: false });
      toast(`Test email sent to ${testEmail}`, 'success');
      closeModals();
    } catch (e) { toast(e.response?.data?.detail || 'Test failed', 'error'); setTesting(false); }
  };

  const confirmSchedule = async () => {
    if (!selectedCampaign || !scheduleDate || !scheduleTime) return;
    try {
      setScheduling(true);
      const scheduledTime = new Date(`${scheduleDate}T${scheduleTime}`).toISOString();
      await API.post(`/campaigns/${selectedCampaign._id}/schedule`, { scheduled_time: scheduledTime });
      toast('Campaign scheduled!', 'success');
      closeModals(); fetchCampaigns();
    } catch (e) { toast(e.response?.data?.detail || 'Schedule failed', 'error'); setScheduling(false); }
  };

  const handleCancelSchedule = async (c) => {
    if (!confirm(`Cancel scheduled send for "${c.title}" and revert to draft?`)) return;
    setRowLoading(c._id, 'cancel');
    try {
      await API.post(`/campaigns/${c._id}/cancel-schedule`);
      toast('Schedule cancelled', 'success'); fetchCampaigns();
    } catch (e) { toast(e.response?.data?.detail || 'Cancel failed', 'error');
    } finally { setRowLoading(c._id, null); }
  };

  const handleDelete = async (c) => {
    if (!confirm(`Delete "${c.title}"? This cannot be undone.`)) return;
    setRowLoading(c._id, 'delete');
    try {
      await API.delete(`/campaigns/${c._id}`);
      toast('Campaign deleted', 'success'); fetchCampaigns();
    } catch (e) { toast(e.response?.data?.detail || 'Delete failed', 'error');
    } finally { setRowLoading(c._id, null); }
  };

  const handleStop = async (c) => {
    if (!confirm(`Stop "${c.title}"? Remaining batches will be halted.`)) return;
    setRowLoading(c._id, 'stop');
    try {
      await API.post(`/campaigns/${c._id}/stop`);
      toast('Campaign stopped', 'success'); fetchCampaigns();
    } catch (e) { toast(e.response?.data?.detail || 'Stop failed', 'error');
    } finally { setRowLoading(c._id, null); }
  };

  const handlePause = async (c) => {
    setRowLoading(c._id, 'pause');
    try {
      await API.post(`/campaigns/${c._id}/pause`);
      toast('Campaign paused', 'success'); fetchCampaigns();
    } catch (e) { toast(e.response?.data?.detail || 'Pause failed', 'error');
    } finally { setRowLoading(c._id, null); }
  };

  const handleResume = async (c) => {
    setRowLoading(c._id, 'resume');
    try {
      await API.post(`/campaigns/${c._id}/resume`);
      toast('Campaign resumed', 'success'); fetchCampaigns();
    } catch (e) { toast(e.response?.data?.detail || 'Resume failed', 'error');
    } finally { setRowLoading(c._id, null); }
  };

  const handleDuplicate = async (c) => {
    setRowLoading(c._id, 'dup');
    try {
      await API.post(`/campaigns/${c._id}/duplicate`);
      toast(`"${c.title}" duplicated as draft`, 'success'); fetchCampaigns();
    } catch (e) { toast(e.response?.data?.detail || 'Duplicate failed', 'error');
    } finally { setRowLoading(c._id, null); }
  };

  // ── derived ─────────────────────────────────────────────
  const counts = useMemo(() => {
    const c = { total: campaigns.length, draft: 0, sending: 0, scheduled: 0, completed: 0, paused: 0, stopped: 0, failed: 0 };
    campaigns.forEach(x => {
      const s = x.status || 'draft';
      if (s === 'sent') c.completed++;
      else if (c[s] !== undefined) c[s]++;
    });
    return c;
  }, [campaigns]);

  const filtered = useMemo(() => {
    let list = campaigns;
    if (statusFilter) list = list.filter(c => (c.status || 'draft') === statusFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(c => (c.title || '').toLowerCase().includes(q) || (c.subject || '').toLowerCase().includes(q));
    }
    return list;
  }, [campaigns, statusFilter, search]);

  // ── render ───────────────────────────────────────────────
  if (loading) return (
    <div className="space-y-6 animate-pulse">
      <div className="grid grid-cols-4 gap-4">{[...Array(4)].map((_, i) => <div key={i} className="h-20 bg-gray-200 rounded-xl" />)}</div>
      <div className="h-64 bg-gray-200 rounded-xl" />
    </div>
  );

  return (
    <div className="space-y-6">
      <ToastContainer toasts={toasts} dismiss={dismiss} />

      {/* ── action bar ── */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <button onClick={() => navigate('/campaigns/create')}
          className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 transition-colors">
          ✨ Create Campaign
        </button>
        <button onClick={fetchCampaigns}
          className="flex items-center gap-2 px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600">
          🔄 Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm flex items-center justify-between">
          {error}
          <button onClick={fetchCampaigns} className="underline ml-2">Try Again</button>
        </div>
      )}

      {/* ── stat cards ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        <StatCard label="Total"     value={counts.total}     color="blue" />
        <StatCard label="Draft"     value={counts.draft}     color="yellow" />
        <StatCard label="Sending"   value={counts.sending}   color="blue"   pulse={counts.sending > 0} />
        <StatCard label="Scheduled" value={counts.scheduled} color="purple" />
        <StatCard label="Completed" value={counts.completed} color="green" />
        <StatCard label="Paused"    value={counts.paused}    color="orange" />
        <StatCard label="Failed"    value={counts.failed}    color="red" />
      </div>

      {/* ── table card ── */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {/* toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700">
            Campaigns
            {filtered.length !== campaigns.length && (
              <span className="ml-2 text-xs font-normal text-gray-400">({filtered.length} of {campaigns.length})</span>
            )}
          </h2>
          <div className="flex items-center gap-2">
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
              className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-white text-gray-600 focus:ring-2 focus:ring-blue-500">
              <option value="">All statuses</option>
              <option value="draft">Draft</option>
              <option value="sending">Sending</option>
              <option value="paused">Paused</option>
              <option value="scheduled">Scheduled</option>
              <option value="completed">Completed</option>
              <option value="stopped">Stopped</option>
              <option value="failed">Failed</option>
            </select>
            <div className="relative">
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs">🔍</span>
              <input type="text" placeholder="Search campaigns…" value={search}
                onChange={e => setSearch(e.target.value)}
                className="pl-7 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 w-48" />
              {search && (
                <button onClick={() => setSearch('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-300 hover:text-gray-500 text-xs">✕</button>
              )}
            </div>
          </div>
        </div>

        {campaigns.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-3xl mb-2">📭</p>
            <p className="text-sm font-medium text-gray-700 mb-1">No campaigns yet</p>
            <p className="text-xs text-gray-400 mb-4">Create your first campaign to get started</p>
            <button onClick={() => navigate('/campaigns/create')}
              className="px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700">
              Create Campaign
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-2xl mb-2">🔍</p>
            <p className="text-sm font-medium text-gray-700">No campaigns match your filters</p>
            <button onClick={() => { setSearch(''); setStatusFilter(''); }}
              className="text-xs text-blue-600 mt-2 hover:underline">Clear filters</button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Campaign</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-28">Status</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-24">Sent</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-24">Date</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-72">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map(c => {
                  const busy = actionLoading[c._id];
                  const status = c.status || 'draft';
                  return (
                    <tr key={c._id} className="hover:bg-gray-50 transition-colors">
                      <td className="px-5 py-3.5">
                        <p className="font-medium text-gray-900 truncate max-w-xs">{c.title}</p>
                        <p className="text-xs text-gray-400 truncate mt-0.5">{c.subject}</p>
                      </td>
                      <td className="px-4 py-3.5">
                        <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLE[status] || STATUS_STYLE.draft}`}>
                          {status}
                        </span>
                        {status === 'scheduled' && c.scheduled_time && (
                          <p className="text-xs text-purple-600 mt-0.5">{fmtD(c.scheduled_time)}</p>
                        )}
                      </td>
                      <td className="px-4 py-3.5 text-right tabular-nums text-gray-600 font-medium">
                        {c.sent_count ? fmt(c.sent_count) : <span className="text-gray-300">—</span>}
                      </td>
                      <td className="px-4 py-3.5 text-right text-xs text-gray-400 whitespace-nowrap">
                        {fmtD(c.completed_at || c.started_at || c.created_at)}
                      </td>
                      <td className="px-4 py-3.5">
                        <div className="flex items-center justify-end gap-1.5 flex-wrap">
                          {status === 'draft' && (
                            <Link to={`/campaigns/${c._id}/edit`}
                              className="px-2.5 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600">
                              Edit
                            </Link>
                          )}
                          {status === 'draft' && (
                            <button onClick={() => { setSelectedCampaign(c); setShowSendModal(true); }}
                              className="px-2.5 py-1.5 text-xs font-medium border border-green-200 rounded-lg hover:bg-green-50 text-green-700">
                              Send
                            </button>
                          )}
                          {status === 'draft' && (
                            <button onClick={() => { setSelectedCampaign(c); setShowScheduleModal(true); }}
                              className="px-2.5 py-1.5 text-xs font-medium border border-purple-200 rounded-lg hover:bg-purple-50 text-purple-700">
                              Schedule
                            </button>
                          )}
                          {status === 'scheduled' && (
                            <button onClick={() => handleCancelSchedule(c)} disabled={!!busy}
                              className="px-2.5 py-1.5 text-xs font-medium border border-orange-200 rounded-lg hover:bg-orange-50 text-orange-700 disabled:opacity-50">
                              {busy === 'cancel' ? '⏳' : 'Cancel'}
                            </button>
                          )}
                          {status === 'sending' && (
                            <button onClick={() => handlePause(c)} disabled={!!busy}
                              className="px-2.5 py-1.5 text-xs font-medium border border-orange-200 rounded-lg hover:bg-orange-50 text-orange-700 disabled:opacity-50">
                              {busy === 'pause' ? '⏳' : 'Pause'}
                            </button>
                          )}
                          {status === 'paused' && (
                            <button onClick={() => handleResume(c)} disabled={!!busy}
                              className="px-2.5 py-1.5 text-xs font-medium border border-green-200 rounded-lg hover:bg-green-50 text-green-700 disabled:opacity-50">
                              {busy === 'resume' ? '⏳' : 'Resume'}
                            </button>
                          )}
                          {status === 'sending' && (
                            <button onClick={() => handleStop(c)} disabled={!!busy}
                              className="px-2.5 py-1.5 text-xs font-medium border border-red-200 rounded-lg hover:bg-red-50 text-red-700 disabled:opacity-50">
                              {busy === 'stop' ? '⏳' : 'Stop'}
                            </button>
                          )}
                          <button onClick={() => { setSelectedCampaign(c); setShowTestModal(true); }}
                            className="px-2.5 py-1.5 text-xs font-medium border border-indigo-200 rounded-lg hover:bg-indigo-50 text-indigo-700">
                            Test
                          </button>
                          <button onClick={() => handleDuplicate(c)} disabled={!!busy}
                            className="px-2.5 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600 disabled:opacity-50">
                            {busy === 'dup' ? '⏳' : 'Clone'}
                          </button>
                          <Link to={`/analytics/campaign/${c._id}`}
                            className="px-2.5 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600">
                            Report
                          </Link>
                          {status === 'draft' && (
                            <button onClick={() => handleDelete(c)} disabled={!!busy}
                              className="px-2.5 py-1.5 text-xs font-medium border border-red-200 rounded-lg hover:bg-red-50 text-red-600 disabled:opacity-50">
                              {busy === 'delete' ? '⏳' : 'Delete'}
                            </button>
                          )}
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

      {/* ── Send modal ── */}
      {showSendModal && selectedCampaign && (
        <Modal title="Send Campaign" onClose={closeModals}>
          <p className="text-sm text-gray-600 mb-4">
            You are about to send <strong>{selectedCampaign.title}</strong>.
            Once started, all eligible subscribers will receive this email.
          </p>
          <div className="flex justify-end gap-3">
            <button onClick={closeModals} className="px-4 py-2 border text-sm font-medium rounded-lg hover:bg-gray-50">Cancel</button>
            <button onClick={confirmSend} disabled={sending}
              className="px-5 py-2 bg-green-600 text-white text-sm font-semibold rounded-lg hover:bg-green-700 disabled:opacity-50">
              {sending ? 'Sending…' : 'Confirm & Send'}
            </button>
          </div>
        </Modal>
      )}

      {/* ── Test modal ── */}
      {showTestModal && selectedCampaign && (
        <Modal title="Send Test Email" onClose={closeModals}>
          <p className="text-xs text-gray-500 mb-3"><strong>{selectedCampaign.title}</strong></p>
          <label className="block text-sm font-medium mb-1.5">Recipient email</label>
          <input type="email" placeholder="you@example.com" value={testEmail}
            onChange={e => setTestEmail(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && confirmTest()}
            className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 mb-4" autoFocus />
          <div className="flex justify-end gap-3">
            <button onClick={closeModals} className="px-4 py-2 border text-sm font-medium rounded-lg hover:bg-gray-50">Cancel</button>
            <button onClick={confirmTest} disabled={testing || !testEmail.trim()}
              className="px-5 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 disabled:opacity-50">
              {testing ? 'Sending…' : 'Send Test'}
            </button>
          </div>
        </Modal>
      )}

      {/* ── Schedule modal ── */}
      {showScheduleModal && selectedCampaign && (
        <Modal title="Schedule Campaign" onClose={closeModals}>
          <p className="text-xs text-gray-500 mb-4"><strong>{selectedCampaign.title}</strong></p>
          <div className="space-y-3 mb-4">
            <div>
              <label className="block text-sm font-medium mb-1">Date</label>
              <input type="date" value={scheduleDate} min={new Date().toISOString().split('T')[0]}
                onChange={e => setScheduleDate(e.target.value)}
                className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Time</label>
              <input type="time" value={scheduleTime}
                onChange={e => setScheduleTime(e.target.value)}
                className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
            </div>
            {scheduleDate && scheduleTime && (
              <p className="text-sm text-purple-700 bg-purple-50 border border-purple-200 px-3 py-2 rounded-lg">
                Will send: {new Date(`${scheduleDate}T${scheduleTime}`).toLocaleString()}
              </p>
            )}
          </div>
          <div className="flex justify-end gap-3">
            <button onClick={closeModals} className="px-4 py-2 border text-sm font-medium rounded-lg hover:bg-gray-50">Cancel</button>
            <button onClick={confirmSchedule} disabled={scheduling || !scheduleDate || !scheduleTime}
              className="px-5 py-2 bg-purple-600 text-white text-sm font-semibold rounded-lg hover:bg-purple-700 disabled:opacity-50">
              {scheduling ? 'Scheduling…' : 'Confirm Schedule'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}