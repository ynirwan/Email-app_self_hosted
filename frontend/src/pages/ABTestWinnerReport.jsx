// frontend/src/pages/ABTestWinnerReport.jsx
// Detailed analytics page for the A/B test winner send phase.
// Mirrors CampaignAnalytics.jsx — same metric cards, openers, clickers,
// metric detail modal, CSV export — all scoped to is_winner_send=True records.

import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import API from "../api";

// ── Helpers ────────────────────────────────────────────────────────────────────
const fmt = (n) => Number(n ?? 0).toLocaleString();
const pct = (n) => `${Number(n ?? 0).toFixed(1)}%`;
const fmtD = (iso) =>
  iso
    ? new Date(iso).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

const parseDevice = (ua = "") => {
  const u = ua.toLowerCase();
  if (!ua) return "Unknown";
  if (/iphone|android|mobile|blackberry/.test(u)) return "Mobile";
  if (/ipad|tablet/.test(u)) return "Tablet";
  if (/mozilla|chrome|safari|firefox|edge|opera|msie/.test(u)) return "Desktop";
  return "Unknown";
};
const DeviceIcon = ({ d }) =>
  d === "Mobile" ? "📱" : d === "Tablet" ? "📟" : d === "Desktop" ? "🖥️" : "❓";

// ── Metric config (mirrors CampaignAnalytics) ──────────────────────────────────
const METRIC_CFG = {
  opened: {
    label: "Opens",
    icon: "👁️",
    color: "text-green-600",
    bg: "bg-green-50",
    border: "border-green-200",
    totalKey: "total_opened",
    rateKey: "open_rate",
    dlKey: "opened",
  },
  clicked: {
    label: "Clicks",
    icon: "👆",
    color: "text-purple-600",
    bg: "bg-purple-50",
    border: "border-purple-200",
    totalKey: "total_clicked",
    rateKey: "click_rate",
    dlKey: "clicked",
  },
  delivered: {
    label: "Delivered",
    icon: "✅",
    color: "text-teal-600",
    bg: "bg-teal-50",
    border: "border-teal-200",
    totalKey: "total_delivered",
    rateKey: "delivery_rate",
    dlKey: null,
  },
  bounced: {
    label: "Bounces",
    icon: "⚠️",
    color: "text-red-600",
    bg: "bg-red-100",
    border: "border-red-200",
    totalKey: "total_bounced",
    rateKey: "bounce_rate",
    dlKey: "bounced",
  },
  unsubscribed: {
    label: "Unsubscribes",
    icon: "🚫",
    color: "text-orange-600",
    bg: "bg-orange-100",
    border: "border-orange-200",
    totalKey: "total_unsubscribed",
    rateKey: "unsubscribe_rate",
    dlKey: "unsubscribed",
  },
  failed: {
    label: "Failed",
    icon: "❌",
    color: "text-red-700",
    bg: "bg-red-100",
    border: "border-red-200",
    totalKey: "total_failed",
    rateKey: "fail_rate",
    dlKey: null,
  },
};

// ── Main component ─────────────────────────────────────────────────────────────
export default function ABTestWinnerReport() {
  const { testId } = useParams();
  const navigate = useNavigate();

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [downloading, setDl] = useState(null);

  const [panel, setPanel] = useState("recipients"); // recipients | openers | clickers
  const [panelRows, setPanelRows] = useState([]);
  const [panelTotal, setPanelTotal] = useState(0);
  const [panelLoading, setPL] = useState(false);

  const [modal, setModal] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await API.get(`/ab-tests/${testId}/winner-analytics`);
      setData(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load winner analytics");
    } finally {
      setLoading(false);
    }
  }, [testId]);

  useEffect(() => {
    load();
  }, [load]);

  // ── Panel loader ─────────────────────────────────────────────────────────────
  const loadPanel = useCallback(
    async (tab) => {
      setPanel(tab);
      setPanelRows([]);
      setPanelTotal(0);
      setPL(true);
      try {
        let res;
        if (tab === "openers") {
          res = await API.get(`/ab-tests/${testId}/winner-openers?limit=10`);
        } else if (tab === "clickers") {
          res = await API.get(`/ab-tests/${testId}/winner-clickers?limit=10`);
        } else {
          res = await API.get(`/ab-tests/${testId}/winner-recipients?limit=10`);
        }
        setPanelRows(res.data.rows || []);
        setPanelTotal(res.data.total || 0);
      } catch {
        setPanelRows([]);
      } finally {
        setPL(false);
      }
    },
    [testId],
  );

  useEffect(() => {
    loadPanel("recipients");
  }, [loadPanel]);

  // ── Metric detail modal ──────────────────────────────────────────────────────
  const openModal = async (metric) => {
    setModal({
      metric,
      rows: [],
      total_all: 0,
      total_unique: 0,
      total_duplicate: 0,
      loading: true,
    });
    try {
      const res = await API.get(
        `/ab-tests/${testId}/winner-detail?metric=${metric}&limit=200`,
      );
      setModal({ metric, ...res.data, loading: false });
    } catch {
      setModal((m) => ({ ...m, loading: false, error: true }));
    }
  };
  const closeModal = () => setModal(null);

  // ── Download ─────────────────────────────────────────────────────────────────
  const download = async (eventType = "all") => {
    setDl(eventType);
    try {
      const res = await API.get(
        `/ab-tests/${testId}/winner-export?event_type=${eventType}`,
        { responseType: "blob" },
      );
      const name = (data?.test_name || "ab_test")
        .replace(/[^a-z0-9]/gi, "_")
        .toLowerCase();
      const filename =
        eventType === "all"
          ? `${name}_winner_report.csv`
          : `${name}_winner_${eventType}.csv`;
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      alert("Download failed.");
    } finally {
      setDl(null);
    }
  };

  if (loading) return <Skeleton />;
  if (error) return <ErrState msg={error} retry={load} />;

  const { analytics } = data || {};

  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-6 py-5">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-lg font-bold text-gray-900">
                {data?.test_name}
              </h1>
              <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-green-100 text-green-800">
                🏆 Winner: Variant {data?.winner_variant}
              </span>
              <span
                className={`text-xs px-2.5 py-0.5 rounded-full font-semibold ${
                  data?.winner_send_status === "completed"
                    ? "bg-green-100 text-green-800"
                    : data?.winner_send_status === "running"
                      ? "bg-blue-100 text-blue-800"
                      : data?.winner_send_status === "stopped"
                        ? "bg-orange-100 text-orange-800"
                        : "bg-gray-100 text-gray-700"
                }`}
              >
                {data?.winner_send_status || "—"}
              </span>
            </div>
            <p className="text-sm text-gray-500 mt-0.5">
              Winner Send Analytics
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={load}
              className="px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600"
            >
              🔄 Refresh
            </button>
            <button
              onClick={() => download("all")}
              disabled={downloading === "all"}
              className="px-4 py-2 bg-green-600 text-white text-sm font-semibold rounded-lg hover:bg-green-700 disabled:opacity-60"
            >
              {downloading === "all" ? "⏳ Downloading…" : "⬇️ Full Report"}
            </button>
            <button
              onClick={() => download("recipients")}
              disabled={!!downloading}
              className="px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600 disabled:opacity-50"
            >
              ⬇️ Recipients CSV
            </button>
            <Link
              to={`/ab-tests/${testId}/results`}
              className="px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600"
            >
              ← Back to Test
            </Link>
          </div>
        </div>
        {/* Send window */}
        {(data?.winner_send_started_at || data?.winner_send_completed_at) && (
          <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm border-t border-gray-100 pt-4">
            <div>
              <p className="text-xs text-gray-400">Started</p>
              <p className="font-medium">{fmtD(data.winner_send_started_at)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Completed</p>
              <p className="font-medium">
                {fmtD(data.winner_send_completed_at)}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Total Sent</p>
              <p className="font-bold text-blue-700">
                {fmt(analytics?.total_sent)}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Failed</p>
              <p className="font-bold text-red-600">
                {fmt(analytics?.total_failed)}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* ── Engagement metrics ── */}
      <div>
        <h2 className="text-sm font-semibold text-gray-700 mb-3">
          Engagement Metrics
          <span className="text-xs text-gray-400 font-normal ml-2">
            Click a card for full detail
          </span>
        </h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          {["opened", "clicked", "delivered"].map((metric) => {
            const cfg = METRIC_CFG[metric];
            const total = analytics?.[cfg.totalKey] || 0;
            const rate = analytics?.[cfg.rateKey] || 0;
            const clickable = metric !== "delivered";
            return (
              <button
                key={metric}
                onClick={clickable ? () => openModal(metric) : undefined}
                className={`${cfg.bg} border ${cfg.border} rounded-xl p-5 text-center transition-all relative group
                  ${clickable ? "hover:shadow-md cursor-pointer" : "cursor-default"}`}
              >
                {clickable && (
                  <div className="absolute top-2 right-2 text-gray-300 group-hover:text-gray-500 text-xs">
                    ↗
                  </div>
                )}
                <p className="text-2xl mb-2">{cfg.icon}</p>
                <p className="text-xs font-medium text-gray-500 mb-1">
                  {cfg.label}
                </p>
                <p className={`text-3xl font-bold tabular-nums ${cfg.color}`}>
                  {fmt(total)}
                </p>
                <p className="text-xs text-gray-400 mt-1">{pct(rate)}</p>
              </button>
            );
          })}
          <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 text-center">
            <p className="text-2xl mb-2">📧</p>
            <p className="text-xs font-medium text-gray-500 mb-1">Sent</p>
            <p className="text-3xl font-bold tabular-nums text-blue-600">
              {fmt(analytics?.total_sent)}
            </p>
            <p className="text-xs text-gray-400 mt-1">Total dispatched</p>
          </div>
        </div>

        {/* Issues strip */}
        <div className="bg-red-50 border border-red-100 rounded-xl p-5">
          <h3 className="text-xs font-semibold text-red-700 mb-3 uppercase tracking-wide">
            ⚠️ Issues
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {["bounced", "unsubscribed", "failed"].map((metric) => {
              const cfg = METRIC_CFG[metric];
              const total = analytics?.[cfg.totalKey] || 0;
              const rate = cfg.rateKey ? analytics?.[cfg.rateKey] || 0 : null;
              const clickable = cfg.dlKey != null;
              return (
                <button
                  key={metric}
                  onClick={clickable ? () => openModal(metric) : undefined}
                  className={`bg-white border border-red-100 rounded-xl p-4 text-center relative group
                    ${clickable ? "hover:shadow-md cursor-pointer transition-all" : "cursor-default"}`}
                >
                  {clickable && (
                    <div className="absolute top-2 right-2 text-gray-300 group-hover:text-gray-500 text-xs">
                      ↗
                    </div>
                  )}
                  <p className="text-xl mb-1">{cfg.icon}</p>
                  <p className="text-xs font-medium text-gray-500">
                    {cfg.label}
                  </p>
                  <p className={`text-2xl font-bold tabular-nums ${cfg.color}`}>
                    {fmt(total)}
                  </p>
                  {rate !== null && (
                    <p className="text-xs text-gray-400">{pct(rate)}</p>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── Panel tabs ── */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="flex border-b border-gray-100 overflow-x-auto">
          {[
            { key: "recipients", label: "📋 All Recipients" },
            { key: "openers", label: "👁️ Who Opened" },
            { key: "clickers", label: "👆 Who Clicked" },
          ].map(({ key, label }) => (
            <button
              key={key}
              onClick={() => loadPanel(key)}
              className={`px-5 py-3 text-sm font-medium whitespace-nowrap border-b-2 -mb-px transition-colors
                ${
                  panel === key
                    ? "border-indigo-600 text-indigo-700 bg-indigo-50"
                    : "border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-50"
                }`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="p-5">
          {panelLoading ? (
            <Spinner />
          ) : panel === "recipients" ? (
            <RecipientsTable
              rows={panelRows}
              total={panelTotal}
              onViewAll={() => download("recipients")}
            />
          ) : (
            <MiniEventTable
              rows={panelRows}
              total={panelTotal}
              type={panel}
              onViewAll={() =>
                openModal(panel === "openers" ? "opened" : "clicked")
              }
            />
          )}
        </div>
      </div>

      {/* ── Metric detail modal ── */}
      {modal && (
        <MetricDetailModal
          modal={modal}
          onClose={closeModal}
          onDownload={download}
          downloading={downloading}
        />
      )}
    </div>
  );
}

// ── RecipientsTable ────────────────────────────────────────────────────────────
function RecipientsTable({ rows, total, onViewAll }) {
  if (!rows.length)
    return (
      <div className="text-center py-12">
        <p className="text-3xl mb-2">📋</p>
        <p className="text-sm text-gray-400">No recipients yet</p>
      </div>
    );
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-gray-400">
          Showing {rows.length} of {fmt(total)}
        </p>
        {total > 10 && (
          <button
            onClick={onViewAll}
            className="text-xs text-indigo-600 hover:underline font-medium"
          >
            Download all {fmt(total)} as CSV →
          </button>
        )}
      </div>
      <div className="overflow-x-auto rounded-lg border border-gray-100">
        <table className="w-full text-xs text-left">
          <thead className="bg-gray-50 text-gray-400 uppercase border-b border-gray-100">
            <tr>
              <th className="px-3 py-2 font-semibold">Email</th>
              <th className="px-3 py-2 font-semibold">Sent</th>
              <th className="px-3 py-2 font-semibold">Opened</th>
              <th className="px-3 py-2 font-semibold">Clicked</th>
              <th className="px-3 py-2 font-semibold">Sent At</th>
              <th className="px-3 py-2 font-semibold">Error / Note</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {rows.map((row, i) => (
              <tr key={i} className="hover:bg-gray-50">
                <td className="px-3 py-2 font-medium text-gray-700">
                  {row.subscriber_email || "—"}
                </td>
                <td className="px-3 py-2">
                  <span
                    className={`px-1.5 py-0.5 rounded text-xs font-medium ${row.email_sent ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}
                  >
                    {row.email_sent ? "Yes" : "No"}
                  </span>
                </td>
                <td className="px-3 py-2 text-gray-500">
                  {row.email_opened ? "✓" : "—"}
                </td>
                <td className="px-3 py-2 text-gray-500">
                  {row.email_clicked ? "✓" : "—"}
                </td>
                <td className="px-3 py-2 text-gray-400 whitespace-nowrap">
                  {fmtD(row.sent_at)}
                </td>
                <td className="px-3 py-2 text-red-500 text-xs truncate max-w-[180px]">
                  {row.error || row.skipped_reason || ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── MiniEventTable ─────────────────────────────────────────────────────────────
function MiniEventTable({ rows, total, type, onViewAll }) {
  if (!rows.length)
    return (
      <div className="text-center py-12">
        <p className="text-2xl mb-2">{type === "openers" ? "👁️" : "👆"}</p>
        <p className="text-sm text-gray-400">
          {type === "openers" ? "No opens yet" : "No clicks yet"}
        </p>
      </div>
    );
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-gray-400">
          Showing {rows.length} of {fmt(total)}
        </p>
        {total > 10 && (
          <button
            onClick={onViewAll}
            className="text-xs text-indigo-600 hover:underline font-medium"
          >
            View all {fmt(total)} →
          </button>
        )}
      </div>
      <div className="overflow-x-auto rounded-lg border border-gray-100">
        <table className="w-full text-xs text-left">
          <thead className="bg-gray-50 text-gray-400 uppercase border-b border-gray-100">
            <tr>
              <th className="px-3 py-2 font-semibold">Email</th>
              {type === "clickers" && (
                <th className="px-3 py-2 font-semibold">URL</th>
              )}
              <th className="px-3 py-2 font-semibold">Device</th>
              <th className="px-3 py-2 font-semibold">IP</th>
              <th className="px-3 py-2 font-semibold">Time</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {rows.map((row, i) => {
              const device = parseDevice(row.user_agent || "");
              return (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="px-3 py-2 font-medium text-gray-700">
                    {row.email || "—"}
                  </td>
                  {type === "clickers" && (
                    <td className="px-3 py-2 max-w-[180px]">
                      <a
                        href={row.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-blue-600 hover:underline truncate block"
                        title={row.url}
                      >
                        {row.url
                          ? row.url.length > 30
                            ? row.url.slice(0, 30) + "…"
                            : row.url
                          : "—"}
                      </a>
                    </td>
                  )}
                  <td className="px-3 py-2 text-gray-500">
                    <DeviceIcon d={device} /> {device}
                  </td>
                  <td className="px-3 py-2 text-gray-400 font-mono">
                    {row.ip_address || "—"}
                  </td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">
                    {fmtD(row.timestamp)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── MetricDetailModal (same as CampaignAnalytics) ──────────────────────────────
function MetricDetailModal({ modal, onClose, onDownload, downloading }) {
  const cfg = METRIC_CFG[modal.metric] || {};
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");

  const rows = (modal.rows || []).filter((r) => {
    const matchFilter =
      filter === "all" || (filter === "unique" ? r.is_unique : !r.is_unique);
    const matchSearch =
      !search ||
      (r.email || "").toLowerCase().includes(search.toLowerCase()) ||
      (r.url || "").toLowerCase().includes(search.toLowerCase());
    return matchFilter && matchSearch;
  });

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl my-8">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <span className="text-2xl">{cfg.icon}</span>
            <div>
              <h2 className="text-base font-bold text-gray-900">
                {cfg.label} Detail — Winner Send
              </h2>
              {!modal.loading && (
                <p className="text-xs text-gray-400">
                  {fmt(modal.total_all)} total · {fmt(modal.total_unique)}{" "}
                  unique · {fmt(modal.total_duplicate)} duplicate
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {cfg.dlKey && (
              <button
                onClick={() => onDownload(cfg.dlKey)}
                disabled={downloading === cfg.dlKey}
                className="px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600 disabled:opacity-50"
              >
                {downloading === cfg.dlKey ? "⏳" : "⬇️ CSV"}
              </button>
            )}
            <button
              onClick={onClose}
              className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-gray-100 text-gray-500 text-lg"
            >
              ×
            </button>
          </div>
        </div>

        {modal.loading ? (
          <div className="flex justify-center py-16">
            <Spinner />
          </div>
        ) : modal.error ? (
          <div className="py-16 text-center text-sm text-red-500">
            Failed to load data.
          </div>
        ) : (
          <>
            <div className="flex items-center gap-3 px-6 py-4 bg-gray-50 border-b border-gray-100">
              <StatPill
                label="Total"
                value={modal.total_all}
                color="bg-gray-200 text-gray-700"
              />
              <StatPill
                label="Unique"
                value={modal.total_unique}
                color="bg-green-100 text-green-700"
              />
              <StatPill
                label="Duplicate"
                value={modal.total_duplicate}
                color="bg-amber-100 text-amber-700"
              />
            </div>
            <div className="flex items-center gap-3 px-6 py-3 border-b border-gray-100">
              <div className="flex rounded-lg border border-gray-200 overflow-hidden text-xs">
                {["all", "unique", "duplicate"].map((f) => (
                  <button
                    key={f}
                    onClick={() => setFilter(f)}
                    className={`px-3 py-1.5 capitalize font-medium transition-colors
                      ${filter === f ? "bg-indigo-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}`}
                  >
                    {f}
                  </button>
                ))}
              </div>
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search email or URL…"
                className="flex-1 text-sm px-3 py-1.5 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
              <span className="text-xs text-gray-400 whitespace-nowrap">
                {fmt(rows.length)} shown
              </span>
            </div>

            <div className="overflow-x-auto max-h-[55vh] overflow-y-auto">
              {rows.length === 0 ? (
                <div className="py-16 text-center text-sm text-gray-400">
                  No records match your filter.
                </div>
              ) : (
                <table className="w-full text-sm text-left">
                  <thead className="bg-gray-50 text-xs text-gray-500 uppercase sticky top-0">
                    <tr>
                      <th className="px-4 py-3 font-semibold">Type</th>
                      <th className="px-4 py-3 font-semibold">Email</th>
                      {modal.metric === "clicked" && (
                        <th className="px-4 py-3 font-semibold">URL</th>
                      )}
                      <th className="px-4 py-3 font-semibold">Device</th>
                      <th className="px-4 py-3 font-semibold">IP</th>
                      <th className="px-4 py-3 font-semibold">Time</th>
                      <th className="px-4 py-3 font-semibold">Count</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {rows.map((row, i) => {
                      const device = parseDevice(row.user_agent || "");
                      return (
                        <tr key={i} className="hover:bg-gray-50">
                          <td className="px-4 py-3">
                            <span
                              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold
                              ${row.is_unique ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}
                            >
                              {row.is_unique ? "✓ Unique" : "↻ Repeat"}
                            </span>
                          </td>
                          <td className="px-4 py-3 font-medium text-gray-800 text-xs">
                            {row.email || "—"}
                          </td>
                          {modal.metric === "clicked" && (
                            <td className="px-4 py-3 max-w-xs">
                              <a
                                href={row.url}
                                target="_blank"
                                rel="noreferrer"
                                className="text-blue-600 hover:underline text-xs truncate block"
                                title={row.url}
                              >
                                {row.url
                                  ? row.url.length > 45
                                    ? row.url.slice(0, 45) + "…"
                                    : row.url
                                  : "—"}
                              </a>
                            </td>
                          )}
                          <td className="px-4 py-3 text-xs text-gray-500">
                            <DeviceIcon d={device} /> {device}
                          </td>
                          <td className="px-4 py-3 text-xs font-mono text-gray-400">
                            {row.ip_address || "—"}
                          </td>
                          <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                            {fmtD(row.timestamp)}
                          </td>
                          <td className="px-4 py-3 text-xs text-gray-500">
                            {row.total_count || 1}×
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
            <div className="px-6 py-3 border-t border-gray-100 text-xs text-gray-400 flex justify-between">
              <span>
                Showing up to 200 records. Download CSV for full export.
              </span>
              <button
                onClick={onClose}
                className="text-indigo-600 hover:underline font-medium"
              >
                Close
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function StatPill({ label, value, color }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold ${color}`}
    >
      {label}: {fmt(value)}
    </span>
  );
}

const Spinner = () => (
  <div className="flex justify-center py-12">
    <div className="w-6 h-6 border-2 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
  </div>
);

const Skeleton = () => (
  <div className="space-y-6 animate-pulse">
    <div className="h-24 bg-gray-200 rounded-xl" />
    <div className="grid grid-cols-4 gap-4">
      {[...Array(4)].map((_, i) => (
        <div key={i} className="h-32 bg-gray-200 rounded-xl" />
      ))}
    </div>
    <div className="h-64 bg-gray-200 rounded-xl" />
  </div>
);

const ErrState = ({ msg, retry }) => (
  <div className="flex items-center justify-center min-h-[60vh]">
    <div className="text-center max-w-sm">
      <p className="text-4xl mb-3">⚠️</p>
      <p className="font-semibold text-gray-800 mb-1">
        Failed to load analytics
      </p>
      <p className="text-sm text-gray-500 mb-4">{msg}</p>
      <button
        onClick={retry}
        className="px-5 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700"
      >
        Try Again
      </button>
    </div>
  </div>
);
