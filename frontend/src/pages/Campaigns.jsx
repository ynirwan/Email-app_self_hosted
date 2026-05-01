// frontend/src/pages/Campaigns.jsx
// Changes vs previous version:
//   - Action buttons are now per-status (CampaignActions component)
//   - Error-paused campaigns show "⚠️ Fix Error" button → analytics page
//   - Campaign title cell shows inline "⚠️ Provider Error" pill badge
//   - StatusBadge distinguishes error-pause from manual pause
//   - All existing modals, handlers, and state are preserved

import { useEffect, useState, useCallback, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import API from "../api";
import { useSettings } from "../contexts/SettingsContext";

// ── Status badge ──────────────────────────────────────────────────────────────
function StatusBadge({ status, pauseReason, t }) {
  const isPausedByError =
    status === "paused" && pauseReason === "provider_error_auto_pause";

  const MAP = {
    draft: { cls: "bg-yellow-100 text-yellow-800", label: `📝 ${t('campaigns.draft')}` },
    scheduled: { cls: "bg-purple-100 text-purple-800", label: `🕐 ${t('campaigns.scheduled')}` },
    sending: { cls: "bg-blue-100   text-blue-800", label: `📤 ${t('campaigns.sending')}` },
    queued: { cls: "bg-blue-100   text-blue-800", label: "⏳ Queued" },
    completed: { cls: "bg-green-100  text-green-800", label: `✅ ${t('campaigns.completed')}` },
    sent: { cls: "bg-green-100  text-green-800", label: `✅ ${t('campaigns.completed')}` },
    stopped: { cls: "bg-gray-100   text-gray-700", label: "🛑 Stopped" },
    cancelled: { cls: "bg-gray-100   text-gray-700", label: "✕ Cancelled" },
    failed: { cls: "bg-red-100    text-red-800", label: `❌ ${t('campaigns.failed')}` },
    paused: isPausedByError
      ? { cls: "bg-red-100 text-red-800", label: "⚠️ Paused — Error" }
      : { cls: "bg-orange-100 text-orange-800", label: "⏸ Paused" },
  };
  const cfg = MAP[status] || MAP.draft;
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${cfg.cls}`}
    >
      {cfg.label}
    </span>
  );
}

// ── Campaign title cell with inline error badge ───────────────────────────────
function CampaignTitleCell({ c }) {
  const hasError =
    c.status === "paused" && c.pause_reason === "provider_error_auto_pause";
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="font-medium text-gray-900 text-sm">{c.title}</span>
      {hasError && (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-red-100 text-red-700 border border-red-300 rounded-full text-xs font-semibold">
          ⚠️ Provider Error
        </span>
      )}
    </div>
  );
}

// ── Per-status action buttons ─────────────────────────────────────────────────
function CampaignActions({
  c,
  onSend,
  onSchedule,
  onCancelSchedule,
  onPause,
  onResume,
  onStop,
  onDelete,
  onTest,
}) {
  const navigate = useNavigate();
  const isPausedByError =
    c.status === "paused" && c.pause_reason === "provider_error_auto_pause";
  const isPausedManual = c.status === "paused" && !isPausedByError;
  const isDraft = c.status === "draft";
  const isScheduled = c.status === "scheduled";
  const isSending = c.status === "sending";
  const isFinished = [
    "completed",
    "sent",
    "stopped",
    "cancelled",
    "failed",
  ].includes(c.status);

  const lnk = (label, to, cls = "text-blue-600 hover:text-blue-800") => (
    <Link to={to} className={`hover:underline text-sm ${cls}`}>
      {label}
    </Link>
  );
  const btn = (
    label,
    onClick,
    cls = "text-gray-600 hover:text-gray-800",
    disabled = false,
  ) => (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`hover:underline text-sm disabled:opacity-40 ${cls}`}
    >
      {label}
    </button>
  );

  return (
    <div className="flex flex-wrap gap-3 items-center">
      {/* Draft actions */}
      {isDraft && lnk("📝 Edit", `/campaigns/${c._id}/edit`)}
      {isDraft &&
        btn("📧 Send", () => onSend(c), "text-green-600 hover:text-green-800")}
      {isDraft &&
        btn(
          "🕐 Schedule",
          () => onSchedule(c),
          "text-purple-600 hover:text-purple-800",
        )}
      {isDraft &&
        btn(
          "🗑️ Delete",
          () => onDelete(c._id),
          "text-red-600 hover:text-red-800",
        )}

      {/* Scheduled actions */}
      {isScheduled && lnk("📝 Edit", `/campaigns/${c._id}/edit`)}
      {isScheduled &&
        btn(
          "❌ Cancel Schedule",
          () => onCancelSchedule(c._id),
          "text-orange-600 hover:text-orange-800",
        )}

      {/* Sending actions */}
      {isSending &&
        btn(
          "⏸ Pause",
          () => onPause(c._id),
          "text-orange-600 hover:text-orange-800",
        )}

      {isSending &&
        btn("🛑 Stop", () => onStop(c._id), "text-red-600 hover:text-red-800")}

      {/* Error-paused: only show Fix Error (no edit here — EditCampaign handles it) */}
      {isPausedByError && (
        <button
          onClick={() => navigate(`/analytics/campaign/${c._id}`)}
          className="text-sm font-semibold text-red-600 hover:text-red-800 hover:underline"
        >
          ⚠️ Fix Error
        </button>
      )}

      {/* Manual pause: allow limited edit */}
      {isPausedManual &&
        btn(
          "▶ Resume",
          () => onResume(c._id),
          "text-green-600 hover:text-green-800",
        )}

      {/* Test email — always available */}
      {btn("📨 Test", () => onTest(c), "text-indigo-600 hover:text-indigo-800")}

      {/* Report — always available for non-draft */}
      {!isDraft &&
        lnk(
          "📊 Report",
          `/analytics/campaign/${c._id}`,
          "text-purple-600 hover:text-purple-800",
        )}
    </div>
  );
}

// ── UI primitives ─────────────────────────────────────────────────────────────
const Th = ({ children }) => (
  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
    {children}
  </th>
);
const Td = ({ children, bold }) => (
  <td className={`px-4 py-3 ${bold ? "font-medium" : ""}`}>{children}</td>
);
const StatCard = ({ color, label, value, icon }) => {
  const colors = {
    blue: "bg-blue-50   border-blue-200   text-blue-800",
    yellow: "bg-yellow-50 border-yellow-200 text-yellow-800",
    purple: "bg-purple-50 border-purple-200 text-purple-800",
    green: "bg-green-50  border-green-200  text-green-800",
    red: "bg-red-50    border-red-200    text-red-800",
    gray: "bg-gray-50   border-gray-200   text-gray-700",
  };
  return (
    <div className={`rounded-xl border p-4 ${colors[color] || colors.gray}`}>
      <p className="text-2xl font-bold tabular-nums">{value}</p>
      <p className="text-xs font-medium mt-0.5 opacity-75">
        {icon} {label}
      </p>
    </div>
  );
};
const Modal = ({ title, children, onClose }) => (
  <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
    <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
      <div className="px-6 py-4 border-b flex justify-between items-center">
        <h3 className="text-lg font-semibold">{title}</h3>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 text-xl leading-none"
        >
          ✕
        </button>
      </div>
      <div className="px-6 py-5">{children}</div>
    </div>
  </div>
);
const BtnPrimary = ({ children, disabled, onClick }) => (
  <button
    onClick={onClick}
    disabled={disabled}
    className="px-5 py-2 rounded-lg text-white bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-semibold"
  >
    {children}
  </button>
);
const BtnSecondary = ({ children, onClick }) => (
  <button
    onClick={onClick}
    className="px-4 py-2 bg-gray-100 rounded-lg hover:bg-gray-200 text-sm"
  >
    {children}
  </button>
);

// ── Main ──────────────────────────────────────────────────────────────────────
export default function Campaigns() {
  const { t, formatDate, formatDateTime } = useSettings();
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showSendModal, setShowSendModal] = useState(false);
  const [showTestModal, setShowTestModal] = useState(false);
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [selectedCampaign, setSelectedCampaign] = useState(null);
  const [sending, setSending] = useState(false);
  const [testing, setTesting] = useState(false);
  const [scheduling, setScheduling] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [testEmail, setTestEmail] = useState("");
  const [scheduleDate, setScheduleDate] = useState("");
  const [scheduleTime, setScheduleTime] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const navigate = useNavigate();

  const fetchCampaigns = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await API.get("/campaigns");
      const data = res.data.campaigns || res.data;
      setCampaigns(Array.isArray(data) ? data : []);
    } catch {
      setError("Failed to load campaigns");
      setCampaigns([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCampaigns();
  }, [fetchCampaigns]);

  const closeModals = () => {
    setShowSendModal(false);
    setShowTestModal(false);
    setShowScheduleModal(false);
    setSelectedCampaign(null);
    setSending(false);
    setTesting(false);
    setScheduling(false);
    setTestEmail("");
    setScheduleDate("");
    setScheduleTime("");
  };

  // ── Handlers ──────────────────────────────────────────────────────────────
  const openSendModal = (c) => {
    setSelectedCampaign(c);
    setShowSendModal(true);
  };
  const openTestModal = (c) => {
    setSelectedCampaign(c);
    setShowTestModal(true);
  };
  const openScheduleModal = (c) => {
    setSelectedCampaign(c);
    setShowScheduleModal(true);
  };

  const confirmSend = async () => {
    if (!selectedCampaign) return;
    try {
      setSending(true);
      await API.post(`/campaigns/${selectedCampaign._id}/send`);
      alert("Campaign sending started!");
      closeModals();
      await fetchCampaigns();
    } catch (e) {
      alert(e.response?.data?.detail || "Send failed");
      setSending(false);
    }
  };

  const confirmTest = async () => {
    if (!testEmail.trim()) return;
    try {
      setTesting(true);
      await API.post(`/campaigns/${selectedCampaign._id}/test-email`, {
        test_email: testEmail.trim(),
        use_custom_data: false,
      });
      alert("Test email sent!");
      closeModals();
    } catch (e) {
      alert(e.response?.data?.detail || "Test failed");
      setTesting(false);
    }
  };

  const confirmSchedule = async () => {
    if (!selectedCampaign || !scheduleDate || !scheduleTime) return;
    try {
      setScheduling(true);
      const scheduledTime = new Date(
        `${scheduleDate}T${scheduleTime}`,
      ).toISOString();
      await API.post(`/campaigns/${selectedCampaign._id}/schedule`, {
        scheduled_time: scheduledTime,
      });
      alert("Campaign scheduled!");
      closeModals();
      await fetchCampaigns();
    } catch (e) {
      alert(e.response?.data?.detail || "Schedule failed");
      setScheduling(false);
    }
  };

  const handleCancelSchedule = async (id) => {
    if (!window.confirm("Cancel the scheduled send and revert to draft?"))
      return;
    try {
      await API.post(`/campaigns/${id}/cancel-schedule`);
      alert("Schedule cancelled.");
      await fetchCampaigns();
    } catch (e) {
      alert(e.response?.data?.detail || "Cancel failed");
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm(t('campaigns.deleteConfirm'))) return;
    try {
      await API.delete(`/campaigns/${id}`);
      alert("Campaign deleted.");
      await fetchCampaigns();
    } catch (e) {
      alert(e.response?.data?.detail || "Delete failed");
    }
  };

  const handlePause = async (id) => {
    const c = campaigns.find((x) => x._id === id);
    if (
      !c ||
      !window.confirm(`Pause campaign "${c.title}"? You can resume it later.`)
    )
      return;
    try {
      await API.post(`/campaigns/${id}/pause`);
      alert("Campaign paused.");
      await fetchCampaigns();
    } catch (e) {
      alert(e.response?.data?.detail || "Pause failed");
    }
  };

  const handleResume = async (id) => {
    const c = campaigns.find((x) => x._id === id);
    if (!c || !window.confirm(`Resume "${c.title}"?`)) return;
    try {
      await API.post(`/campaigns/${id}/resume`);
      await fetchCampaigns();
    } catch (e) {
      alert(e.response?.data?.detail || "Resume failed");
    }
  };

  const handleStop = async (id) => {
    const c = campaigns.find((x) => x._id === id);
    if (
      !c ||
      !window.confirm(`Stop "${c.title}"? This halts remaining batches.`)
    )
      return;
    try {
      setStopping(true);
      await API.post(`/campaigns/${id}/stop`);
      alert("Campaign stopped.");
      await fetchCampaigns();
    } catch (e) {
      alert(e.response?.data?.detail || "Stop failed");
    } finally {
      setStopping(false);
    }
  };

  // ── Derived stats ─────────────────────────────────────────────────────────
  const total = campaigns.length;
  const drafts = campaigns.filter(
    (c) => (c.status || "draft") === "draft",
  ).length;
  const sentNum = campaigns.filter(
    (c) => c.status === "sent" || c.status === "completed",
  ).length;
  const scheduled = campaigns.filter((c) => c.status === "scheduled").length;
  const errors = campaigns.filter(
    (c) =>
      c.status === "paused" && c.pause_reason === "provider_error_auto_pause",
  ).length;

  // ── Filtered list ─────────────────────────────────────────────────────────
  const filtered = useMemo(() => {
    let list = campaigns;
    if (statusFilter) list = list.filter((c) => c.status === statusFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (c) =>
          (c.title || "").toLowerCase().includes(q) ||
          (c.subject || "").toLowerCase().includes(q),
      );
    }
    return list;
  }, [campaigns, statusFilter, search]);

  if (loading)
    return (
      <p className="text-center mt-10 text-gray-500">Loading campaigns…</p>
    );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-gray-900">📢 {t('campaigns.title')}</h2>
        <button
          onClick={() => navigate("/campaigns/create")}
          className="bg-blue-600 text-white px-5 py-2 rounded-lg hover:bg-blue-700 text-sm font-semibold"
        >
          ✨ {t('campaigns.create')}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-300 text-red-700 px-4 py-3 rounded-lg">
          {error}
          <button onClick={fetchCampaigns} className="ml-2 underline text-sm">
            Retry
          </button>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
        <StatCard color="blue" label="Total" value={total} icon="📊" />
        <StatCard color="yellow" label="Drafts" value={drafts} icon="📝" />
        <StatCard
          color="purple"
          label="Scheduled"
          value={scheduled}
          icon="🕐"
        />
        <StatCard color="green" label="Sent" value={sentNum} icon="✅" />
        {errors > 0 && (
          <StatCard
            color="red"
            label="Provider Errors"
            value={errors}
            icon="⚠️"
          />
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t('campaigns.search')}
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 w-56"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none"
        >
          <option value="">{t('campaigns.all')}</option>
          {[
            "draft",
            "scheduled",
            "sending",
            "paused",
            "completed",
            "sent",
            "stopped",
            "failed",
          ].map((s) => (
            <option key={s} value={s}>
              {t(`campaigns.${s}`)}
            </option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="bg-white shadow-sm rounded-xl border border-gray-200">
        <div className="px-5 py-4 border-b border-gray-100">
          <h3 className="text-base font-semibold text-gray-800">
            📋 Your Campaigns ({filtered.length})
          </h3>
        </div>

        {filtered.length === 0 ? (
          <div className="py-16 text-center text-gray-400">
            <p className="text-lg mb-2">{t('campaigns.empty')}</p>
            <p className="text-sm">
              {campaigns.length === 0
                ? "Create your first campaign to get started."
                : "Try adjusting your filters."}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  <Th>Campaign</Th>
                  <Th>Status</Th>
                  <Th>Subscribers</Th>
                  <Th>Sent</Th>
                  <Th>Created</Th>
                  <Th>Actions</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map((c) => (
                  <tr
                    key={c._id}
                    className="hover:bg-gray-50 transition-colors"
                  >
                    <Td bold>
                      <CampaignTitleCell c={c} />
                      <p className="text-xs text-gray-400 mt-0.5 truncate max-w-xs">
                        {c.subject}
                      </p>
                    </Td>
                    <Td>
                      <StatusBadge
                        status={c.status}
                        pauseReason={c.pause_reason}
                        t={t}
                      />
                    </Td>
                    <Td>{(c.target_list_count || 0).toLocaleString()}</Td>
                    <Td>{(c.sent_count || 0).toLocaleString()}</Td>
                    <Td>
                      {c.created_at
                        ? formatDate(c.created_at)
                        : "—"}
                    </Td>
                    <Td>
                      <CampaignActions
                        c={c}
                        onSend={openSendModal}
                        onSchedule={openScheduleModal}
                        onCancelSchedule={handleCancelSchedule}
                        onPause={handlePause}
                        onResume={handleResume}
                        onStop={handleStop}
                        onDelete={handleDelete}
                        onTest={openTestModal}
                      />
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Send modal ── */}
      {showSendModal && selectedCampaign && (
        <Modal title="📤 Send Campaign" onClose={closeModals}>
          <p className="text-sm text-gray-700 mb-4">
            You are about to send <strong>{selectedCampaign.title}</strong> to{" "}
            <strong>
              {(selectedCampaign.target_list_count || 0).toLocaleString()}
            </strong>{" "}
            subscribers. Once started, this cannot be undone.
          </p>
          <div className="flex justify-end gap-3">
            <BtnSecondary onClick={closeModals}>Cancel</BtnSecondary>
            <BtnPrimary onClick={confirmSend} disabled={sending}>
              {sending ? "⏳ Sending…" : "📧 Send Now"}
            </BtnPrimary>
          </div>
        </Modal>
      )}

      {/* ── Test email modal ── */}
      {showTestModal && selectedCampaign && (
        <Modal title="📨 Send Test Email" onClose={closeModals}>
          <p className="text-sm text-gray-600 mb-4">
            Send a test of <strong>{selectedCampaign.title}</strong>:
          </p>
          <input
            type="email"
            value={testEmail}
            onChange={(e) => setTestEmail(e.target.value)}
            placeholder="test@example.com"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          <div className="flex justify-end gap-3">
            <BtnSecondary onClick={closeModals}>Cancel</BtnSecondary>
            <BtnPrimary
              onClick={confirmTest}
              disabled={testing || !testEmail.trim()}
            >
              {testing ? "⏳ Sending…" : "Send Test"}
            </BtnPrimary>
          </div>
        </Modal>
      )}

      {/* ── Schedule modal ── */}
      {showScheduleModal && selectedCampaign && (
        <Modal title="🕐 Schedule Campaign" onClose={closeModals}>
          <p className="text-sm text-gray-600 mb-4">
            Schedule <strong>{selectedCampaign.title}</strong> for a future
            send:
          </p>
          <div className="space-y-3 mb-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Date
              </label>
              <input
                type="date"
                value={scheduleDate}
                min={new Date().toISOString().split("T")[0]}
                onChange={(e) => setScheduleDate(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
              {scheduleDate && scheduleTime && (
                <p className="text-sm text-purple-600 bg-purple-50 p-2 rounded">
                  Will send on:{" "}
                  {formatDateTime(`${scheduleDate}T${scheduleTime}`)}
                </p>
              )}
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Time (UTC)
              </label>
              <input
                type="time"
                value={scheduleTime}
                onChange={(e) => setScheduleTime(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            </div>
          </div>
          <div className="flex justify-end gap-3">
            <BtnSecondary onClick={closeModals}>Cancel</BtnSecondary>
            <BtnPrimary
              onClick={confirmSchedule}
              disabled={scheduling || !scheduleDate || !scheduleTime}
            >
              {scheduling ? "⏳ Scheduling…" : "✅ Confirm Schedule"}
            </BtnPrimary>
          </div>
        </Modal>
      )}
    </div>
  );
}
