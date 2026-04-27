import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import API from "../api";
import ProviderErrorBanner from "../components/ProviderErrorBanner";

// ── Helpers ───────────────────────────────────────────────────────────────────
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

// ── Metric detail config ─────────────────────────────────────────────────────
const METRIC_CFG = {
  opened: {
    label: "Opens",
    icon: "👁️",
    color: "text-green-600",
    bg: "bg-green-50",
    border: "border-green-200",
    rateKey: "open_rate",
    totalKey: "total_opened",
    dlKey: "opened",
  },
  clicked: {
    label: "Clicks",
    icon: "👆",
    color: "text-purple-600",
    bg: "bg-purple-50",
    border: "border-purple-200",
    rateKey: "click_rate",
    totalKey: "total_clicked",
    dlKey: "clicked",
  },
  delivered: {
    label: "Delivered",
    icon: "✅",
    color: "text-teal-600",
    bg: "bg-teal-50",
    border: "border-teal-200",
    rateKey: "delivery_rate",
    totalKey: "total_delivered",
    dlKey: "delivered",
  },
  bounced: {
    label: "Bounces",
    icon: "⚠️",
    color: "text-red-600",
    bg: "bg-red-100",
    border: "border-red-200",
    rateKey: "bounce_rate",
    totalKey: "total_bounced",
    dlKey: "bounced",
  },
  unsubscribed: {
    label: "Unsubscribes",
    icon: "🚫",
    color: "text-orange-600",
    bg: "bg-orange-100",
    border: "border-orange-200",
    rateKey: "unsubscribe_rate",
    totalKey: "total_unsubscribed",
    dlKey: "unsubscribed",
  },
  spam_report: {
    label: "Spam Reports",
    icon: "🚨",
    color: "text-red-700",
    bg: "bg-red-100",
    border: "border-red-200",
    rateKey: null,
    totalKey: "total_spam_reports",
    dlKey: "spam_report",
  },
};

// ── Main component ────────────────────────────────────────────────────────────
export default function CampaignAnalytics() {
  const { campaignId } = useParams();
  const navigate = useNavigate();

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [downloading, setDl] = useState(null);

  const [panel, setPanel] = useState("activity"); // activity | openers | clickers | links
  const [panelRows, setPanelRows] = useState([]);
  const [panelTotal, setPanelTotal] = useState(0);
  const [panelLoading, setPL] = useState(false);

  const [modal, setModal] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await API.get(`/analytics/campaigns/${campaignId}`);
      setData(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load analytics");
    } finally {
      setLoading(false);
    }
  }, [campaignId]);

  useEffect(() => {
    load();
  }, [load]);

  // ── Panel loader ────────────────────────────────────────────────────────────
  const loadPanel = useCallback(
    async (tab) => {
      setPanel(tab);

      if (tab === "activity" || tab === "links") return;

      const eventType = tab === "openers" ? "opened" : "clicked";
      setPL(true);
      setPanelRows([]);
      setPanelTotal(0);

      try {
        const res = await API.get(
          `/analytics/campaigns/${campaignId}/detail?metric=${eventType}&limit=10`
        );
        setPanelRows(res.data.rows || []);
        setPanelTotal(res.data.total_all || 0);
      } catch {
        setPanelRows([]);
        setPanelTotal(0);
      } finally {
        setPL(false);
      }
    },
    [campaignId]
  );

  // ── Metric modal opener ─────────────────────────────────────────────────────
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
        `/analytics/campaigns/${campaignId}/detail?metric=${metric}&limit=200`
      );
      setModal({ metric, ...res.data, loading: false });
    } catch {
      setModal((m) => ({ ...m, loading: false, error: true }));
    }
  };

  const closeModal = () => setModal(null);

  // ── Download ────────────────────────────────────────────────────────────────
  const download = async (eventType = "all") => {
    setDl(eventType);
    try {
      const res = await API.get(
        `/analytics/campaigns/${campaignId}/export?event_type=${eventType}`,
        { responseType: "blob" }
      );

      const title = (data?.campaign?.title || "campaign")
        .replace(/[^a-z0-9]/gi, "_")
        .replace(/_+/g, "_")
        .toLowerCase();

      const filename =
        eventType === "all"
          ? `${title}_full_report.csv`
          : `${title}_${eventType}.csv`;

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

  const { campaign, analytics, recent_events, top_links } = data || {};
  const progress =
    campaign?.target_list_count > 0
      ? Math.round(((campaign.sent_count || 0) / campaign.target_list_count) * 100)
      : 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-6 py-5">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-lg font-bold text-gray-900">
                {campaign?.title || "Campaign Analytics"}
              </h1>
            <StatusBadge status={campaign?.status} pauseReason={campaign?.pause_reason} />
            </div>
            <ProviderErrorBanner
              providerError={campaign?.provider_error}
              isCampaign={true}
              campaignId={campaignId}
              onFixed={load}       // re-fetch data so banner updates
              onResumed={load}
            />
            <p className="text-sm text-gray-500 mt-0.5">{campaign?.subject}</p>
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
              onClick={() => navigate(-1)}
              className="px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600"
            >
              ← Back
            </button>
          </div>
        </div>
      </div>

      {/* Progress */}
      {["sending", "paused"].includes(campaign?.status) && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-5">
            Campaign Progress
          </h2>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            {[
              {
                title: "Target",
                val: campaign?.target_list_count,
                icon: "🎯",
                cls: "bg-blue-50 text-blue-700 border-blue-200",
              },
              {
                title: "Processed",
                val: campaign?.processed_count,
                icon: "⚙️",
                cls: "bg-green-50 text-green-700 border-green-200",
              },
              {
                title: "Sent",
                val: campaign?.sent_count,
                icon: "✅",
                cls: "bg-purple-50 text-purple-700 border-purple-200",
              },
              {
                title: "Queued",
                val: campaign?.queued_count,
                icon: "⏳",
                cls: "bg-orange-50 text-orange-700 border-orange-200",
              },
            ].map(({ title, val, icon, cls }) => (
              <div key={title} className={`${cls} border rounded-xl p-4 text-center`}>
                <p className="text-2xl mb-1">{icon}</p>
                <p className="text-xs font-medium">{title}</p>
                <p className="text-2xl font-bold tabular-nums">{fmt(val)}</p>
              </div>
            ))}
          </div>

          <div className="mb-1 flex justify-between text-xs text-gray-500">
            <span>Progress</span>
            <span>{progress}%</span>
          </div>

          <div className="bg-gray-100 rounded-full h-2 mb-5">
            <div className="bg-blue-600 h-2 rounded-full" style={{ width: `${progress}%` }} />
          </div>

          <div className="grid grid-cols-3 gap-4 pt-4 border-t border-gray-100 text-sm">
            {[
              ["Started", campaign?.started_at],
              ["Last Batch", campaign?.last_batch_at],
              ["Completed", campaign?.completed_at],
            ].map(([l, v]) => (
              <div key={l}>
                <p className="text-xs text-gray-500 mb-0.5">{l}</p>
                <p className="text-gray-800">{fmtD(v)}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Metrics */}
      <div>
        <h2 className="text-sm font-semibold text-gray-700 mb-3">
          Engagement Metrics
          <span className="text-xs text-gray-400 font-normal ml-2">
            Click any card to see full detail
          </span>
        </h2>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          {[
            {
              metric: "opened",
              total: analytics?.total_opened || 0,
              rate: analytics?.open_rate || 0,
              rateLabel: "open rate",
            },
            {
              metric: "clicked",
              total: analytics?.total_clicked || 0,
              rate: analytics?.click_rate || 0,
              rateLabel: "click rate",
            },
            {
              metric: "delivered",
              total:
                analytics?.total_delivered ||
                Math.max(0, (analytics?.total_sent || 0) - (analytics?.total_bounced || 0)),
              rate: analytics?.delivery_rate || 0,
              rateLabel: "delivery",
            },
          ].map(({ metric, total, rate, rateLabel }) => {
            const cfg = METRIC_CFG[metric];
            return (
              <button
                key={metric}
                onClick={() => openModal(metric)}
                className={`${cfg.bg} border ${cfg.border} rounded-xl p-5 text-center hover:shadow-md transition-all cursor-pointer group relative`}
              >
                <div className="absolute top-2 right-2 text-gray-300 group-hover:text-gray-500 text-xs">
                  ↗
                </div>
                <p className="text-2xl mb-2">{cfg.icon}</p>
                <p className="text-xs font-medium text-gray-500 mb-1">{cfg.label}</p>
                <p className={`text-3xl font-bold tabular-nums ${cfg.color}`}>{fmt(total)}</p>
                <p className="text-xs text-gray-400 mt-1">
                  {pct(rate)} {rateLabel}
                </p>
              </button>
            );
          })}

          <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 text-center">
            <p className="text-2xl mb-2">📧</p>
            <p className="text-xs font-medium text-gray-500 mb-1">Sent</p>
            <p className="text-3xl font-bold tabular-nums text-blue-600">
              {fmt(analytics?.total_sent || 0)}
            </p>
            <p className="text-xs text-gray-400 mt-1">Total dispatched</p>
          </div>
        </div>

        <div className="bg-red-50 border border-red-100 rounded-xl p-5">
          <h3 className="text-xs font-semibold text-red-700 mb-3 uppercase tracking-wide">
            ⚠️ Issues
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {["bounced", "unsubscribed", "spam_report"].map((metric) => {
              const cfg = METRIC_CFG[metric];
              const total = analytics?.[cfg.totalKey] || 0;
              const rate = cfg.rateKey ? analytics?.[cfg.rateKey] || 0 : null;

              return (
                <button
                  key={metric}
                  onClick={() => openModal(metric)}
                  className="bg-white border border-red-100 rounded-xl p-4 text-center hover:shadow-md transition-all cursor-pointer group relative"
                >
                  <div className="absolute top-2 right-2 text-gray-300 group-hover:text-gray-500 text-xs">
                    ↗
                  </div>
                  <p className="text-xl mb-1">{cfg.icon}</p>
                  <p className="text-xs font-medium text-gray-500">{cfg.label}</p>
                  <p className={`text-2xl font-bold tabular-nums ${cfg.color}`}>{fmt(total)}</p>
                  {rate !== null && <p className="text-xs text-gray-400">{pct(rate)}</p>}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Panel */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="flex border-b border-gray-100 overflow-x-auto">
          {[
            { key: "activity", label: "📈 Recent Activity" },
            { key: "openers", label: "👁️ Who Opened" },
            { key: "clickers", label: "👆 Who Clicked" },
            { key: "links", label: "🔗 Top Links" },
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
          {panel === "activity" && <ActivityFeed events={recent_events} limit={10} />}
          {panel === "links" && <LinkList links={top_links} limit={10} />}
          {(panel === "openers" || panel === "clickers") &&
            (panelLoading ? (
              <Spinner />
            ) : (
              <MiniTable
                rows={panelRows}
                total={panelTotal}
                type={panel === "openers" ? "open" : "click"}
                onViewAll={() => openModal(panel === "openers" ? "opened" : "clicked")}
              />
            ))}
        </div>
      </div>

      <EmailPreview campaign={campaign} />
      <CampaignDetails campaign={campaign} />

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

// ── MetricDetailModal ─────────────────────────────────────────────────────────
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
              <h2 className="text-base font-bold text-gray-900">{cfg.label} Detail</h2>
              {!modal.loading && (
                <p className="text-xs text-gray-400">
                  {fmt(modal.total_all)} total · {fmt(modal.total_unique)} unique ·{" "}
                  {fmt(modal.total_duplicate)} duplicate
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
          <div className="py-16 text-center text-sm text-red-500">Failed to load data.</div>
        ) : (
          <>
            <div className="flex items-center gap-3 px-6 py-4 bg-gray-50 border-b border-gray-100">
              <StatPill label="Total" value={modal.total_all} color="bg-gray-200 text-gray-700" />
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
                      ${
                        filter === f
                          ? "bg-indigo-600 text-white"
                          : "bg-white text-gray-500 hover:bg-gray-50"
                      }`}
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
                    {rows.map((row, i) => (
                      <DetailRow key={i} row={row} metric={modal.metric} />
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="px-6 py-3 border-t border-gray-100 text-xs text-gray-400 flex justify-between">
              <span>Showing up to 200 records. Download CSV for full export.</span>
              <button onClick={onClose} className="text-indigo-600 hover:underline font-medium">
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
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold ${color}`}>
      {label}: {fmt(value)}
    </span>
  );
}

function DetailRow({ row, metric }) {
  const [exp, setExp] = useState(false);
  const device = row.device || parseDevice(row.user_agent || "");
  const colSpan = metric === "clicked" ? 7 : 6;

  return (
    <>
      <tr
        onClick={() => setExp((v) => !v)}
        className="hover:bg-gray-50 cursor-pointer transition-colors"
      >
        <td className="px-4 py-3">
          <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold
            ${row.is_unique ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}
          >
            {row.is_unique ? "✓ Unique" : "↻ Repeat"}
          </span>
        </td>

        <td className="px-4 py-3 font-medium text-gray-800 text-xs">{row.email || "—"}</td>

        {metric === "clicked" && (
          <td className="px-4 py-3 max-w-xs">
            <a
              href={row.url}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="text-blue-600 hover:underline text-xs truncate block"
              title={row.url}
            >
              {row.url ? (row.url.length > 45 ? row.url.slice(0, 45) + "…" : row.url) : "—"}
            </a>
          </td>
        )}

        <td className="px-4 py-3 text-xs text-gray-500">
          <span className="flex items-center gap-1">
            <DeviceIcon d={device} /> {device}
          </span>
        </td>

        <td className="px-4 py-3 text-xs font-mono text-gray-400">{row.ip_address || "—"}</td>
        <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">{fmtD(row.timestamp)}</td>
        <td className="px-4 py-3">
          <span className="text-xs text-gray-500">{row.total_count || 1}×</span>
        </td>
      </tr>

      {exp && (
        <tr className="bg-indigo-50">
          <td colSpan={colSpan} className="px-4 py-3">
            <div className="text-xs text-gray-500 space-y-1">
              <p>
                <span className="font-semibold text-gray-600">User Agent: </span>
                <span className="font-mono break-all">{row.user_agent || "Not captured"}</span>
              </p>
              {metric === "clicked" && row.url && (
                <p>
                  <span className="font-semibold text-gray-600">Full URL: </span>
                  <span className="break-all text-blue-600">{row.url}</span>
                </p>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ── MiniTable ─────────────────────────────────────────────────────────────────
function MiniTable({ rows, total, type, onViewAll }) {
  if (!rows.length) {
    return (
      <div className="text-center py-12">
        <p className="text-3xl mb-2">{type === "open" ? "👁️" : "👆"}</p>
        <p className="text-sm text-gray-400">{type === "open" ? "No opens yet" : "No clicks yet"}</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-gray-400">
          Showing {rows.length} of {fmt(total)}
        </p>
        {total > 10 && (
          <button onClick={onViewAll} className="text-xs text-indigo-600 hover:underline font-medium">
            View all {fmt(total)} →
          </button>
        )}
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-100">
        <table className="w-full text-xs text-left">
          <thead className="bg-gray-50 text-gray-400 uppercase border-b border-gray-100">
            <tr>
              <th className="px-3 py-2 font-semibold">Email</th>
              {type === "click" && <th className="px-3 py-2 font-semibold">URL</th>}
              <th className="px-3 py-2 font-semibold">Device</th>
              <th className="px-3 py-2 font-semibold">IP</th>
              <th className="px-3 py-2 font-semibold">Time</th>
              <th className="px-3 py-2 font-semibold">Type</th>
            </tr>
          </thead>

          <tbody className="divide-y divide-gray-50">
            {rows.map((row, i) => {
              const device = row.device || parseDevice(row.user_agent || "");
              return (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="px-3 py-2 font-medium text-gray-700">{row.email || "—"}</td>

                  {type === "click" && (
                    <td className="px-3 py-2 max-w-[180px]">
                      <span className="text-blue-600 truncate block" title={row.url}>
                        {row.url ? (row.url.length > 30 ? row.url.slice(0, 30) + "…" : row.url) : "—"}
                      </span>
                    </td>
                  )}

                  <td className="px-3 py-2 text-gray-500">
                    <DeviceIcon d={device} /> {device}
                  </td>
                  <td className="px-3 py-2 text-gray-400 font-mono">{row.ip_address || "—"}</td>
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{fmtD(row.timestamp)}</td>
                  <td className="px-3 py-2">
                    <span
                      className={`px-1.5 py-0.5 rounded text-xs font-medium
                      ${row.is_unique ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}
                    >
                      {row.is_unique ? "Unique" : "Repeat"}
                    </span>
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

// ── ActivityFeed ──────────────────────────────────────────────────────────────
const EV_CFG = {
  opened: { icon: "👁️", bg: "bg-green-100", color: "text-green-700", label: "Opened" },
  clicked: { icon: "👆", bg: "bg-purple-100", color: "text-purple-700", label: "Clicked" },
  bounced: { icon: "⚠️", bg: "bg-red-100", color: "text-red-700", label: "Bounced" },
  delivered: { icon: "✅", bg: "bg-green-100", color: "text-green-700", label: "Delivered" },
  unsubscribed: { icon: "🚫", bg: "bg-orange-100", color: "text-orange-700", label: "Unsubscribed" },
  spam_report: { icon: "🚨", bg: "bg-red-100", color: "text-red-700", label: "Spam Report" },
};

function ActivityFeed({ events, limit = 10 }) {
  const items = (events || []).slice(0, limit);

  if (!items.length) {
    return (
      <div className="text-center py-12">
        <p className="text-3xl text-gray-200 mb-2">📊</p>
        <p className="text-sm text-gray-400">No activity yet</p>
      </div>
    );
  }

  return (
    <div className="space-y-1 max-h-80 overflow-y-auto pr-1">
      {items.map((ev, i) => {
        const cfg = EV_CFG[ev.event_type] || {
          icon: "📧",
          bg: "bg-gray-100",
          color: "text-gray-600",
          label: ev.event_type,
        };

        const email = ev.email || ev.subscriber_email || "";
        const device = ev.device || parseDevice(ev.user_agent || "");

        return (
          <div key={i} className="flex items-start gap-3 p-2.5 hover:bg-gray-50 rounded-lg">
            <div className={`w-7 h-7 ${cfg.bg} rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5 text-xs`}>
              {cfg.icon}
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`text-xs font-semibold ${cfg.color}`}>{cfg.label}</span>
                {email && <span className="text-xs text-gray-600">{email}</span>}
                <span className="text-xs text-gray-400">
                  {device !== "Unknown" && (
                    <>
                      <DeviceIcon d={device} /> {device}
                    </>
                  )}
                </span>
              </div>

              <div className="flex gap-3 mt-0.5">
                <p className="text-xs text-gray-400">{fmtD(ev.timestamp)}</p>
                {ev.ip_address && <p className="text-xs text-gray-300 font-mono">{ev.ip_address}</p>}
              </div>

              {ev.url && ev.event_type === "clicked" && (
                <p className="text-xs text-blue-500 truncate">{ev.url}</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── LinkList ──────────────────────────────────────────────────────────────────
function LinkList({ links, limit = 10 }) {
  const items = (links || []).slice(0, limit);

  if (!items.length) {
    return (
      <div className="text-center py-12">
        <p className="text-3xl text-gray-200 mb-2">🔗</p>
        <p className="text-sm text-gray-400">No link clicks yet</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {items.map((link, i) => (
        <div key={i} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className="w-6 h-6 bg-blue-600 text-white rounded-md flex items-center justify-center text-xs font-bold flex-shrink-0">
              {i + 1}
            </div>
            <a
              href={link.url}
              target="_blank"
              rel="noreferrer"
              className="text-sm text-blue-600 hover:underline truncate"
            >
              {link.url || "Unknown URL"}
            </a>
          </div>
          <span className="px-2.5 py-1 bg-blue-100 text-blue-800 text-xs font-semibold rounded-full ml-3 flex-shrink-0">
            {fmt(link.clicks)} clicks
          </span>
        </div>
      ))}
    </div>
  );
}

// ── Misc ──────────────────────────────────────────────────────────────────────
const Spinner = () => (
  <div className="flex justify-center py-12">
    <div className="w-6 h-6 border-2 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
  </div>
);

function StatusBadge({ status, pauseReason }) {
  const isPausedByError = pauseReason === "provider_error_auto_pause";

  const map = {
    sent:      { cls: "bg-green-100 text-green-800",   label: "✅ Sent" },
    completed: { cls: "bg-green-100 text-green-800",   label: "✅ Completed" },
    sending:   { cls: "bg-blue-100  text-blue-800",    label: "📤 Sending" },
    queued:    { cls: "bg-blue-100  text-blue-800",    label: "⏳ Queued" },
    scheduled: { cls: "bg-purple-100 text-purple-800", label: "🕐 Scheduled" },
    draft:     { cls: "bg-yellow-100 text-yellow-800", label: "📝 Draft" },
    stopped:   { cls: "bg-gray-100  text-gray-700",    label: "🛑 Stopped" },
    cancelled: { cls: "bg-gray-100  text-gray-700",    label: "✕ Cancelled" },
    failed:    { cls: "bg-red-100   text-red-800",     label: "❌ Failed" },
    paused: isPausedByError
      ? { cls: "bg-red-100 text-red-800",   label: "⚠️ Paused — Provider Error" }
      : { cls: "bg-orange-100 text-orange-800", label: "⏸ Paused" },
  };

  const cfg = map[status] || map.draft;
  return (
    <span className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold ${cfg.cls}`}>
      {cfg.label}
    </span>
  );
}

 

const EmailPreview = ({ campaign }) => {
  const [exp, setExp] = useState(false);
  const html = campaign?.content_snapshot?.html_content;

  if (!html) return null;

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">📩 Email Content</h3>
        <button
          onClick={() => setExp((v) => !v)}
          className="text-xs px-3 py-1.5 border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600"
        >
          {exp ? "Collapse" : "Expand"}
        </button>
      </div>

      <div style={{ maxHeight: exp ? "none" : "480px", overflow: "hidden" }}>
        <iframe
          srcDoc={html}
          title="Email Preview"
          sandbox="allow-same-origin"
          className="w-full border-0"
          style={{ height: exp ? "800px" : "480px" }}
        />
      </div>

      {!exp && (
        <div className="px-5 py-3 border-t border-gray-100 text-center">
          <button onClick={() => setExp(true)} className="text-xs text-blue-600 hover:text-blue-700 font-medium">
            Show full email ↓
          </button>
        </div>
      )}
    </div>
  );
};

const CampaignDetails = ({ campaign }) => (
  <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
    <div className="px-5 py-4 border-b border-gray-100">
      <h3 className="text-sm font-semibold text-gray-700">📧 Campaign Details</h3>
    </div>

    <div className="p-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
      {[
        ["Title", campaign?.title],
        ["Subject", campaign?.subject],
        ["Sender", campaign?.sender_name],
        ["From", campaign?.sender_email],
        ["Reply To", campaign?.reply_to || campaign?.sender_email],
        ["Lists", campaign?.target_lists?.join(", ") || "None"],
        ["Target", fmt(campaign?.target_list_count)],
        ["Sent", fmt(campaign?.sent_count)],
        ["Created", fmtD(campaign?.created_at)],
        ["Started", fmtD(campaign?.started_at)],
        ["Completed", campaign?.completed_at ? fmtD(campaign.completed_at) : "In progress"],
      ].map(([label, value]) => (
        <div key={label}>
          <p className="text-xs font-medium text-gray-400 mb-1">{label}</p>
          <p className="text-sm text-gray-800 font-medium">{value || "—"}</p>
        </div>
      ))}

      <div>
        <p className="text-xs font-medium text-gray-400 mb-1">Status</p>
        <StatusBadge status={campaign?.status} />
      </div>
    </div>
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
      <p className="font-semibold text-gray-800 mb-1">Failed to load analytics</p>
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