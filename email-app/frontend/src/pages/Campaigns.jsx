// src/pages/Campaigns.jsx
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import API from '../api';

export default function Campaigns() {
  /* ───────── state ───────── */
  const [campaigns, setCampaigns] = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);

  /* send modal */
  const [showSendModal, setShowSendModal] = useState(false);
  const [selectedCampaign, setSelectedCampaign] = useState(null);
  const [sending, setSending] = useState(false);

  /* test-modal */
  const [showTestModal, setShowTestModal] = useState(false);
  const [testEmail,     setTestEmail]     = useState('');
  const [testing,       setTesting]       = useState(false);

  /* stop flag */
  const [stopping, setStopping] = useState(false);

  /* schedule modal */
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [scheduleDate, setScheduleDate] = useState('');
  const [scheduleTime, setScheduleTime] = useState('');
  const [scheduling, setScheduling] = useState(false);

  const navigate = useNavigate();

  /* ───────── fetch list ───────── */
  const fetchCampaigns = async () => {
    try {
      setLoading(true); setError(null);
      const res = await API.get('/campaigns');
      const data = res.data.campaigns || res.data;
      setCampaigns(Array.isArray(data) ? data : []);
    } catch (e) {
      setError('Failed to load campaigns'); setCampaigns([]);
    } finally { setLoading(false); }
  };
  useEffect(() => { fetchCampaigns(); }, []);

  /* ───────── helpers ───────── */
  const openSendModal = (c) => { setSelectedCampaign(c); setShowSendModal(true); };
  const openTestModal = (c) => { setSelectedCampaign(c); setShowTestModal(true); };
  const openScheduleModal = (c) => { setSelectedCampaign(c); setShowScheduleModal(true); };
  const closeModals   = () => {
    setShowSendModal(false); setShowTestModal(false); setShowScheduleModal(false);
    setSelectedCampaign(null); setSending(false); setTesting(false);
    setTestEmail(''); setScheduleDate(''); setScheduleTime(''); setScheduling(false);
  };

  /* ───────── actions ───────── */
  const confirmSend = async () => {
    if (!selectedCampaign) return;
    try {
      setSending(true);
      await API.post(`/campaigns/${selectedCampaign._id}/send`);
      alert('Campaign sending started!');
      closeModals(); await fetchCampaigns();
    } catch (e) {
      alert(e.response?.data?.detail || 'Send failed'); setSending(false);
    }
  };

  const confirmTest = async () => {
    if (!testEmail.trim()) return;
    try {
      setTesting(true);
      await API.post(`/campaigns/${selectedCampaign._id}/test-email`, {
        test_email: testEmail.trim(),
        use_custom_data: false
      });
      alert('Test email sent!');
      closeModals();
    } catch (e) {
      alert(e.response?.data?.detail || 'Test failed'); setTesting(false);
    }
  };

  const confirmSchedule = async () => {
    if (!selectedCampaign || !scheduleDate || !scheduleTime) return;
    try {
      setScheduling(true);
      const scheduledTime = new Date(`${scheduleDate}T${scheduleTime}`).toISOString();
      await API.post(`/campaigns/${selectedCampaign._id}/schedule`, { scheduled_time: scheduledTime });
      alert('Campaign scheduled successfully!');
      closeModals(); await fetchCampaigns();
    } catch (e) {
      alert(e.response?.data?.detail || 'Schedule failed'); setScheduling(false);
    }
  };

  const handleCancelSchedule = async (id) => {
    if (!window.confirm('Cancel the scheduled send and revert to draft?')) return;
    try {
      await API.post(`/campaigns/${id}/cancel-schedule`);
      alert('Schedule cancelled.');
      await fetchCampaigns();
    } catch (e) {
      alert(e.response?.data?.detail || 'Cancel schedule failed');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this campaign? This cannot be undone.')) return;
    try {
      await API.delete(`/campaigns/${id}`);
      alert('Campaign deleted.');
      await fetchCampaigns();
    } catch (e) {
      alert(e.response?.data?.detail || 'Delete failed');
    }
  };

  const handleStop = async (id) => {
    const c = campaigns.find(x => x._id === id);
    if (!c) return;
    if (!window.confirm(`Stop campaign “${c.title}”? This halts remaining batches.`)) return;
    try {
      setStopping(true);
      await API.post(`/campaigns/${id}/stop`);
      alert('Campaign stopped.');
      await fetchCampaigns();
    } catch (e) {
      alert(e.response?.data?.detail || 'Stop failed');
    } finally { setStopping(false); }
  };

  /* ───────── stats ───────── */
  const total      = campaigns.length;
  const drafts     = campaigns.filter(c => (c.status || 'draft') === 'draft').length;
  const sentNum    = campaigns.filter(c => c.status === 'sent').length;
  const scheduled  = campaigns.filter(c => c.status === 'scheduled').length;

  /* ───────── render ───────── */
  if (loading) return <p className="text-center mt-10">Loading campaigns…</p>;

  return (
    <div className="space-y-6">
      {/* header */}
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold">📢 Campaigns</h2>
        <button onClick={() => navigate('/campaigns/create')}
                className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700">
          ✨ Create Campaign
        </button>
      </div>

      {/* error */}
      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-6">
          {error}
          <button onClick={fetchCampaigns} className="ml-2 underline">Try Again</button>
        </div>
      )}

      {/* counters */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-6 mb-6">
        <StatCard color="blue"   label="Total Campaigns"     value={total}     icon="📊" />
        <StatCard color="yellow" label="Draft Campaigns"     value={drafts}    icon="📝" />
        <StatCard color="purple" label="Scheduled Campaigns" value={scheduled} icon="🕐" />
        <StatCard color="green"  label="Sent Campaigns"      value={sentNum}   icon="📧" />
      </div>

      {/* table */}
      <div className="bg-white shadow rounded">
        <div className="p-4 border-b">
          <h3 className="text-lg font-semibold">📋 Your Campaigns ({total})</h3>
        </div>
        {total === 0 ? (
          <div className="p-8 text-center text-gray-500">
            <p className="text-lg mb-2">📭 No campaigns yet</p>
            <p>Click “Create Campaign” to get started!</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full table-auto text-sm">
              <thead>
                <tr className="bg-gray-100 text-left">
                  <Th>Campaign Name</Th><Th>Subject</Th><Th>Status</Th>
                  <Th>Created</Th><Th>Actions</Th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map(c => (
                  <tr key={c._id} className="border-t hover:bg-gray-50">
                    <Td bold>{c.title}</Td>
                    <Td>{c.subject}</Td>
                    <Td>
                      <span className={`px-2 py-1 rounded text-xs font-medium ${
                        c.status === 'sent'      ? 'bg-green-100 text-green-800' :
                        c.status === 'sending'   ? 'bg-blue-100  text-blue-800'  :
                        c.status === 'scheduled' ? 'bg-purple-100 text-purple-800' :
                        c.status === 'stopped'   ? 'bg-gray-200 text-gray-700'  :
                        c.status === 'failed'    ? 'bg-red-200 text-red-700'  :                  
                                                    'bg-yellow-100 text-yellow-800'
                      }`}>{c.status || 'draft'}</span>
                      {c.status === 'scheduled' && c.scheduled_time && (
                        <span className="block text-xs text-purple-600 mt-1">
                          {new Date(c.scheduled_time).toLocaleString()}
                        </span>
                      )}
                    </Td>
                    <Td>{c.created_at ? new Date(c.created_at).toLocaleDateString() : '-'}</Td>
                    <Td>
                      <div className="flex flex-wrap gap-3">
                        {c.status === 'draft'
                          ? <Link to={`/campaigns/${c._id}/edit`}
                                  className="text-blue-600 hover:text-blue-800 hover:underline">📝 Edit</Link>
                          : <span className="text-gray-400">📝 Edit</span>}

                        {c.status === 'draft' &&
                          <button onClick={() => openSendModal(c)}
                                  className="text-green-600 hover:text-green-800 hover:underline">📧 Send</button>}

                        {c.status === 'draft' &&
                          <button onClick={() => openScheduleModal(c)}
                                  className="text-purple-600 hover:text-purple-800 hover:underline">🕐 Schedule</button>}

                        {c.status === 'scheduled' &&
                          <button onClick={() => handleCancelSchedule(c._id)}
                                  className="text-orange-600 hover:text-orange-800 hover:underline">❌ Cancel Schedule</button>}

                        {c.status === 'sending' &&
                          <button onClick={() => handleStop(c._id)}
                                  disabled={stopping}
                                  className="text-red-600 hover:text-red-800 hover:underline">
                            {stopping ? '⏳' : '🛑 Stop'}
                          </button>}

                        <button onClick={() => openTestModal(c)}
                                className="text-indigo-600 hover:text-indigo-800 hover:underline">
                          📨 Test
                        </button>

                        <Link to={`/analytics/campaign/${c._id}`}
                              className="text-purple-600 hover:text-purple-800 hover:underline">📊 Report</Link>

                        {c.status === 'draft' &&
                        <button onClick={() => handleDelete(c._id)}
                                className="text-red-600 hover:text-red-800 hover:underline">🗑️ Delete</button>}
                      </div>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ───────── Send modal ───────── */}
      {showSendModal && selectedCampaign && (
        <Modal title="📤 Send Campaign" onClose={closeModals}>
          <p className="mb-4 text-sm">
            You are about to send <strong>{selectedCampaign.title}</strong>.
            Once sent, it cannot be undone.
          </p>
          <div className="flex justify-end gap-3">
            <BtnSecondary onClick={closeModals}>Cancel</BtnSecondary>
            <BtnPrimary onClick={confirmSend} disabled={sending}>
              {sending ? 'Sending…' : 'Confirm & Send'}
            </BtnPrimary>
          </div>
        </Modal>
      )}

      {/* ───────── Test modal ───────── */}
      {showTestModal && selectedCampaign && (
        <Modal title="📨 Send Test Email" onClose={closeModals}>
          <p className="text-sm mb-3">
            Campaign: <strong>{selectedCampaign.title}</strong>
          </p>
          <input type="email" placeholder="recipient@example.com"
                 value={testEmail}
                 onChange={e => setTestEmail(e.target.value)}
                 className="w-full px-3 py-2 border rounded mb-4"/>
          <div className="flex justify-end gap-3">
            <BtnSecondary onClick={closeModals}>Cancel</BtnSecondary>
            <BtnPrimary onClick={confirmTest}
                        disabled={testing || !testEmail.trim()}>
              {testing ? 'Sending…' : 'Send Test'}
            </BtnPrimary>
          </div>
        </Modal>
      )}

      {/* ───────── Schedule modal ───────── */}
      {showScheduleModal && selectedCampaign && (
        <Modal title="🕐 Schedule Campaign" onClose={closeModals}>
          <p className="text-sm mb-4">
            Schedule <strong>{selectedCampaign.title}</strong> to send at a future date and time.
          </p>
          <div className="space-y-3 mb-4">
            <div>
              <label className="block text-sm font-medium mb-1">Date</label>
              <input type="date"
                     value={scheduleDate}
                     min={new Date().toISOString().split('T')[0]}
                     onChange={e => setScheduleDate(e.target.value)}
                     className="w-full px-3 py-2 border rounded"/>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Time</label>
              <input type="time"
                     value={scheduleTime}
                     onChange={e => setScheduleTime(e.target.value)}
                     className="w-full px-3 py-2 border rounded"/>
            </div>
            {scheduleDate && scheduleTime && (
              <p className="text-sm text-purple-600 bg-purple-50 p-2 rounded">
                Will send on: {new Date(`${scheduleDate}T${scheduleTime}`).toLocaleString()}
              </p>
            )}
          </div>
          <div className="flex justify-end gap-3">
            <BtnSecondary onClick={closeModals}>Cancel</BtnSecondary>
            <BtnPrimary onClick={confirmSchedule}
                        disabled={scheduling || !scheduleDate || !scheduleTime}>
              {scheduling ? 'Scheduling…' : 'Confirm Schedule'}
            </BtnPrimary>
          </div>
        </Modal>
      )}
    </div>
  );
}

/* ───────── tiny helpers ───────── */
const Th = ({children}) => <th className="p-3 font-semibold">{children}</th>;
const Td = ({children,bold}) => (
  <td className={`p-3 ${bold?'font-medium':''}`}>{children}</td>
);

const StatCard = ({color,label,value,icon}) => (
  <div className={`bg-${color}-50 p-6 rounded-lg border`}>
    <div className="flex items-center justify-between">
      <div>
        <p className={`text-sm text-${color}-600 font-medium`}>{label}</p>
        <p className={`text-3xl font-bold text-${color}-800`}>{value}</p>
      </div>
      <span className="text-4xl">{icon}</span>
    </div>
  </div>
);

const Modal = ({title,children,onClose}) => (
  <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
    <div className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4">
      <div className="px-6 py-4 border-b flex justify-between">
        <h3 className="text-lg font-semibold">{title}</h3>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600">✕</button>
      </div>
      <div className="px-6 py-4">{children}</div>
    </div>
  </div>
);

const BtnPrimary = ({children,disabled,onClick}) => (
  <button onClick={onClick} disabled={disabled}
          className={`px-6 py-2 rounded-lg text-white ${
            disabled ? 'bg-gray-400' : 'bg-green-600 hover:bg-green-700'}`}>
    {children}
  </button>
);

const BtnSecondary = ({children,onClick}) => (
  <button onClick={onClick}
          className="px-4 py-2 bg-gray-100 rounded-lg hover:bg-gray-200">
    {children}
  </button>
);
