import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import API from "../api";
import axios from "axios";

const fmt  = (n) => Number(n ?? 0).toLocaleString();
const fmtD = (iso) =>
  iso ? new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  }) : "—";

const DeviceIcon = ({ device }) => {
  if (device === "Mobile")  return <span title="Mobile">📱</span>;
  if (device === "Tablet")  return <span title="Tablet">📟</span>;
  if (device === "Desktop") return <span title="Desktop">🖥️</span>;
  return <span title="Unknown">❓</span>;
};

// ─────────────────────────────────────────────────────────────────────────────
export default function CampaignAnalytics() {
  const { campaignId } = useParams();
  const navigate       = useNavigate();

  const [analyticsData, setAnalyticsData] = useState(null);
  const [loading, setLoading]             = useState(true);
  const [error, setError]                 = useState(null);
  const [downloading, setDownloading]     = useState(null);

  const [detailTab, setDetailTab] = useState("activity");
  const [openers,   setOpeners]   = useState(null);
  const [clickers,  setClickers]  = useState(null);
  const [detailLoading, setDL]    = useState(false);

  useEffect(() => { fetchCampaignAnalytics(); }, [campaignId]);

  const fetchCampaignAnalytics = async () => {
    try {
      setLoading(true); setError(null);
      const res = await API.get(`/analytics/campaigns/${campaignId}`);
      setAnalyticsData(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load analytics");
    } finally { setLoading(false); }
  };

  const loadOpeners = async () => {
    if (openers) return;
    setDL(true);
    try {
      const res = await API.get(`/analytics/campaigns/${campaignId}/openers?limit=100`);
      setOpeners(res.data);
    } catch { setOpeners({ rows: [], total: 0 }); }
    finally { setDL(false); }
  };

  const loadClickers = async () => {
    if (clickers) return;
    setDL(true);
    try {
      const res = await API.get(`/analytics/campaigns/${campaignId}/clickers?limit=100`);
      setClickers(res.data);
    } catch { setClickers({ rows: [], total: 0 }); }
    finally { setDL(false); }
  };

  const handleTab = (tab) => {
    setDetailTab(tab);
    if (tab === "openers")  loadOpeners();
    if (tab === "clickers") loadClickers();
  };

  const downloadReport = async (eventType = "all") => {
    setDownloading(eventType);
    try {
      const token = localStorage.getItem("token");
      const response = await axios.get(
        `/api/analytics/campaigns/${campaignId}/export?event_type=${eventType}`,
        { responseType: "blob", headers: { Authorization: `Bearer ${token}` } },
      );
      const title = (analyticsData?.campaign?.title || "campaign")
        .replace(/[^a-z0-9]/gi, "_").replace(/_+/g, "_").toLowerCase();
      const filename = eventType === "all"
        ? `${title}_full_report.csv`
        : `${title}_${eventType}.csv`;
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch { alert("Download failed. Please try again."); }
    finally { setDownloading(null); }
  };

  if (loading) return <LoadingSkeleton />;
  if (error)   return <ErrorState error={error} onRetry={fetchCampaignAnalytics} />;

  const { campaign, analytics, recent_events, top_links } = analyticsData || {};
  const progress = campaign?.target_list_count > 0
    ? Math.round((campaign.sent_count / campaign.target_list_count) * 100) : 0;

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
              <CampaignStatusBadge status={campaign?.status} />
            </div>
            <p className="text-sm text-gray-500 mt-0.5">{campaign?.subject}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={fetchCampaignAnalytics}
              className="flex items-center gap-2 px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600">
              🔄 Refresh
            </button>
            <button onClick={() => downloadReport("all")} disabled={downloading === "all"}
              className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white text-sm font-semibold rounded-lg hover:bg-green-700 disabled:opacity-60">
              {downloading === "all" ? "⏳ Downloading…" : "⬇️ Full Report"}
            </button>
            <button onClick={() => navigate(-1)}
              className="flex items-center gap-2 px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600">
              ← Back
            </button>
          </div>
        </div>
      </div>

      {/* Progress bar — only while sending/paused */}
      {["sending", "paused"].includes(campaign?.status) && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-5">Campaign Progress</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <ProgressCard title="Target"    value={campaign?.target_list_count || 0} subtitle="Total to send"  icon="🎯" color="bg-blue-50   text-blue-700   border-blue-200" />
            <ProgressCard title="Processed" value={campaign?.processed_count    || 0} subtitle="Processed"      icon="⚙️" color="bg-green-50  text-green-700  border-green-200" />
            <ProgressCard title="Sent"      value={campaign?.sent_count         || 0} subtitle="Successfully"   icon="✅" color="bg-purple-50 text-purple-700 border-purple-200" />
            <ProgressCard title="Queued"    value={campaign?.queued_count       || 0} subtitle="Waiting"        icon="⏳" color="bg-orange-50 text-orange-700 border-orange-200" />
          </div>
          <div className="mb-1 flex justify-between text-xs text-gray-500">
            <span>Progress</span><span>{progress}%</span>
          </div>
          <div className="bg-gray-100 rounded-full h-2 mb-5">
            <div className="bg-blue-600 h-2 rounded-full transition-all duration-500" style={{ width: `${progress}%` }} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4 border-t border-gray-100">
            <TimelineItem label="Started"    value={fmtD(campaign?.started_at)} />
            <TimelineItem label="Last Batch" value={fmtD(campaign?.last_batch_at)} />
            <TimelineItem label="Completed"  value={campaign?.completed_at ? fmtD(campaign.completed_at) : "In progress"} />
          </div>
        </div>
      )}

      {/* Engagement metrics */}
      <div>
        <h2 className="text-sm font-semibold text-gray-700 mb-4">Engagement Metrics</h2>
        <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          <MetricCard title="Sent"      value={analytics?.total_sent    || 0} subtitle="Emails dispatched"                         icon="📧" color="text-blue-600"   bg="bg-blue-50" />
          <MetricCard title="Opens"     value={analytics?.total_opened  || 0} subtitle={`${analytics?.open_rate  || 0}% open rate`}  icon="👁️" color="text-green-600"  bg="bg-green-50"  onDownload={() => downloadReport("opened")}      downloading={downloading === "opened"} />
          <MetricCard title="Clicks"    value={analytics?.total_clicked || 0} subtitle={`${analytics?.click_rate || 0}% click rate`} icon="👆" color="text-purple-600" bg="bg-purple-50" onDownload={() => downloadReport("clicked")}     downloading={downloading === "clicked"} />
          <MetricCard title="Delivered" value={analytics?.total_delivered || Math.max(0, (analytics?.total_sent || 0) - (analytics?.total_bounced || 0))} subtitle={`${analytics?.delivery_rate || 0}% delivery`} icon="✅" color="text-teal-600" bg="bg-teal-50" onDownload={() => downloadReport("delivered")} downloading={downloading === "delivered"} />
        </div>
        <div className="bg-red-50 border border-red-100 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-red-800 mb-4">⚠️ Issues & Failures</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <MetricCard title="Bounces"      value={analytics?.total_bounced      || 0} subtitle={`${analytics?.bounce_rate      || 0}% bounce`} icon="⚠️" color="text-red-600"    bg="bg-red-100"    onDownload={() => downloadReport("bounced")}     downloading={downloading === "bounced"} />
            <MetricCard title="Unsubscribes" value={analytics?.total_unsubscribed || 0} subtitle={`${analytics?.unsubscribe_rate || 0}% unsub`}  icon="🚫" color="text-orange-600" bg="bg-orange-100" onDownload={() => downloadReport("unsubscribed")} downloading={downloading === "unsubscribed"} />
            <MetricCard title="Spam Reports" value={analytics?.total_spam_reports || 0} subtitle="Marked as spam"                                 icon="🚨" color="text-red-700"    bg="bg-red-100"    onDownload={() => downloadReport("spam_report")} downloading={downloading === "spam_report"} />
          </div>
        </div>
      </div>

      {/* Activity / Openers / Clickers / Links tabs */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="flex border-b border-gray-100 overflow-x-auto">
          {[
            { key: "activity", label: "📈 Recent Activity" },
            { key: "openers",  label: `👁️ Who Opened (${fmt(analytics?.total_opened || 0)})` },
            { key: "clickers", label: `👆 Who Clicked (${fmt(analytics?.total_clicked || 0)})` },
            { key: "links",    label: "🔗 Top Links" },
          ].map(({ key, label }) => (
            <button key={key} onClick={() => handleTab(key)}
              className={`px-5 py-3 text-sm font-medium whitespace-nowrap transition-colors border-b-2 -mb-px
                ${detailTab === key
                  ? "border-indigo-600 text-indigo-700 bg-indigo-50"
                  : "border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-50"}`}>
              {label}
            </button>
          ))}
        </div>
        <div className="p-5">
          {detailTab === "activity" && <ActivityFeed events={recent_events} />}
          {detailTab === "openers"  && (detailLoading ? <TabSpinner /> : <ContactTable rows={openers?.rows  || []} total={openers?.total  || 0} type="open"  />)}
          {detailTab === "clickers" && (detailLoading ? <TabSpinner /> : <ContactTable rows={clickers?.rows || []} total={clickers?.total || 0} type="click" />)}
          {detailTab === "links"    && <TopClickedLinks links={top_links} />}
        </div>
      </div>

      <EmailContentPreview campaign={campaign} />
      <CampaignDetails campaign={campaign} />
    </div>
  );
}

// ── ContactTable (openers / clickers) ─────────────────────────────────────────
function ContactTable({ rows, total, type }) {
  const [expanded, setExpanded] = useState(null);
  if (!rows.length) return (
    <div className="text-center py-12">
      <p className="text-3xl mb-2">{type === "open" ? "👁️" : "👆"}</p>
      <p className="text-sm text-gray-400">{type === "open" ? "No opens recorded yet" : "No clicks recorded yet"}</p>
    </div>
  );
  return (
    <div>
      <p className="text-xs text-gray-400 mb-3">
        Showing {rows.length} of {total.toLocaleString()} {type === "open" ? "opens" : "clicks"}
      </p>
      <div className="overflow-x-auto rounded-lg border border-gray-100">
        <table className="w-full text-sm text-left">
          <thead className="bg-gray-50 text-xs text-gray-500 uppercase border-b border-gray-100">
            <tr>
              <th className="px-4 py-3 font-semibold">Email</th>
              {type === "click" && <th className="px-4 py-3 font-semibold">URL</th>}
              <th className="px-4 py-3 font-semibold">Device</th>
              <th className="px-4 py-3 font-semibold">IP</th>
              <th className="px-4 py-3 font-semibold">Time</th>
              <th className="px-4 py-3 w-6"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {rows.map((row, i) => (
              <>
                <tr key={i} onClick={() => setExpanded(expanded === i ? null : i)}
                  className="hover:bg-gray-50 cursor-pointer transition-colors">
                  <td className="px-4 py-3 font-medium text-gray-800 text-sm">{row.email || "—"}</td>
                  {type === "click" && (
                    <td className="px-4 py-3 max-w-xs">
                      <span className="text-blue-600 truncate block text-xs" title={row.url}>
                        {row.url ? (row.url.length > 50 ? row.url.slice(0, 50) + "…" : row.url) : "—"}
                      </span>
                    </td>
                  )}
                  <td className="px-4 py-3">
                    <span className="flex items-center gap-1.5 text-gray-600 text-xs">
                      <DeviceIcon device={row.device} />{row.device || "Unknown"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs font-mono">{row.ip_address || "—"}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">{fmtD(row.timestamp)}</td>
                  <td className="px-4 py-3 text-gray-300 text-xs">{expanded === i ? "▲" : "▼"}</td>
                </tr>
                {expanded === i && (
                  <tr key={`${i}-d`} className="bg-indigo-50">
                    <td colSpan={type === "click" ? 6 : 5} className="px-4 py-3">
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                        <div>
                          <p className="font-semibold text-gray-600 mb-1">User Agent</p>
                          <p className="text-gray-500 break-all font-mono leading-relaxed">{row.user_agent || "Not captured"}</p>
                        </div>
                        <div className="space-y-1.5">
                          <p><span className="font-semibold text-gray-600">IP: </span><span className="font-mono text-gray-500">{row.ip_address || "—"}</span></p>
                          <p><span className="font-semibold text-gray-600">Device: </span><span className="text-gray-500">{row.device || "Unknown"}</span></p>
                          <p><span className="font-semibold text-gray-600">Time: </span><span className="text-gray-500">{fmtD(row.timestamp)}</span></p>
                          {type === "click" && row.url && (
                            <p><span className="font-semibold text-gray-600">URL: </span>
                              <a href={row.url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline break-all">{row.url}</a>
                            </p>
                          )}
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── ActivityFeed ───────────────────────────────────────────────────────────────
const EVENT_CFG = {
  opened:       { icon: "👁️", bg: "bg-green-100",  color: "text-green-700",  label: "Opened" },
  clicked:      { icon: "👆", bg: "bg-purple-100", color: "text-purple-700", label: "Clicked" },
  bounced:      { icon: "⚠️", bg: "bg-red-100",    color: "text-red-700",    label: "Bounced" },
  delivered:    { icon: "✅", bg: "bg-green-100",  color: "text-green-700",  label: "Delivered" },
  unsubscribed: { icon: "🚫", bg: "bg-orange-100", color: "text-orange-700", label: "Unsubscribed" },
  spam_report:  { icon: "🚨", bg: "bg-red-100",    color: "text-red-700",    label: "Spam Report" },
};

function ActivityFeed({ events }) {
  if (!events?.length) return (
    <div className="text-center py-12">
      <p className="text-3xl text-gray-200 mb-2">📊</p>
      <p className="text-sm text-gray-400">No activity recorded yet</p>
    </div>
  );
  return (
    <div className="space-y-1 max-h-80 overflow-y-auto pr-1">
      {events.slice(0, 20).map((event, i) => {
        const cfg = EVENT_CFG[event.event_type] || { icon: "📧", bg: "bg-gray-100", color: "text-gray-600", label: event.event_type };
        // Support both field names: our new docs use "email", legacy use "subscriber_email"
        const emailAddr = event.email || event.subscriber_email || "";
        return (
          <div key={i} className="flex items-start gap-3 p-2.5 hover:bg-gray-50 rounded-lg transition-colors">
            <div className={`w-7 h-7 ${cfg.bg} rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5`}>
              <span className="text-xs">{cfg.icon}</span>
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`text-xs font-semibold ${cfg.color}`}>{cfg.label}</span>
                {emailAddr && <span className="text-xs text-gray-600">{emailAddr}</span>}
                {event.device && (
                  <span className="text-xs text-gray-400 flex items-center gap-0.5">
                    <DeviceIcon device={event.device} />{event.device}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3 mt-0.5">
                <p className="text-xs text-gray-400">{fmtD(event.timestamp)}</p>
                {event.ip_address && <p className="text-xs text-gray-300 font-mono">{event.ip_address}</p>}
              </div>
              {event.url && event.event_type === "clicked" && (
                <p className="text-xs text-blue-500 truncate mt-0.5">{event.url}</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Shared sub-components ──────────────────────────────────────────────────────
const TabSpinner = () => (
  <div className="flex justify-center py-12">
    <div className="w-6 h-6 border-2 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
  </div>
);

const ProgressCard = ({ title, value, subtitle, icon, color }) => (
  <div className={`${color} border rounded-xl p-4 text-center`}>
    <p className="text-2xl mb-1">{icon}</p>
    <p className="text-xs font-medium mb-0.5">{title}</p>
    <p className="text-2xl font-bold tabular-nums">{fmt(value)}</p>
    <p className="text-xs opacity-70 mt-0.5">{subtitle}</p>
  </div>
);

const TimelineItem = ({ label, value }) => (
  <div>
    <p className="text-xs font-medium text-gray-500 mb-0.5">{label}</p>
    <p className="text-sm text-gray-800">{value}</p>
  </div>
);

const MetricCard = ({ title, value, subtitle, icon, color, bg, onDownload, downloading }) => (
  <div className={`bg-white ${bg} rounded-xl p-5 border hover:shadow-sm transition-shadow relative`}>
    {onDownload && (
      <button onClick={onDownload} disabled={downloading} title={`Download ${title} list`}
        className="absolute top-3 right-3 p-1.5 bg-white rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-50 shadow-sm text-xs">
        {downloading ? "⏳" : "⬇️"}
      </button>
    )}
    <div className="text-center">
      <p className="text-2xl mb-2">{icon}</p>
      <p className="text-xs font-medium text-gray-500 mb-1">{title}</p>
      <p className={`text-3xl font-bold tabular-nums ${color} mb-1`}>{fmt(value)}</p>
      {subtitle && <p className="text-xs text-gray-400">{subtitle}</p>}
    </div>
  </div>
);

const TopClickedLinks = ({ links }) =>
  links?.length > 0 ? (
    <div className="space-y-2">
      {links.map((link, i) => (
        <div key={i} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className="w-6 h-6 bg-blue-600 text-white rounded-md flex items-center justify-center text-xs font-bold flex-shrink-0">{i + 1}</div>
            <a href={link.url} target="_blank" rel="noreferrer" className="text-sm text-blue-600 hover:underline truncate">{link.url || "Unknown URL"}</a>
          </div>
          <span className="px-2.5 py-1 bg-blue-100 text-blue-800 text-xs font-semibold rounded-full ml-3 flex-shrink-0">{fmt(link.clicks)} clicks</span>
        </div>
      ))}
    </div>
  ) : (
    <div className="text-center py-12">
      <p className="text-3xl text-gray-200 mb-2">🔗</p>
      <p className="text-sm text-gray-400">No link clicks recorded yet</p>
    </div>
  );

const CampaignStatusBadge = ({ status }) => {
  const cfg = {
    sent:      { bg: "bg-green-100",  text: "text-green-800",  label: "✅ Sent" },
    completed: { bg: "bg-green-100",  text: "text-green-800",  label: "✅ Completed" },
    draft:     { bg: "bg-yellow-100", text: "text-yellow-800", label: "📝 Draft" },
    sending:   { bg: "bg-blue-100",   text: "text-blue-800",   label: "📤 Sending" },
    paused:    { bg: "bg-orange-100", text: "text-orange-800", label: "⏸️ Paused" },
    stopped:   { bg: "bg-gray-100",   text: "text-gray-700",   label: "🛑 Stopped" },
    failed:    { bg: "bg-red-100",    text: "text-red-800",    label: "❌ Failed" },
  }[status] || { bg: "bg-gray-100", text: "text-gray-700", label: status || "Unknown" };
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${cfg.bg} ${cfg.text}`}>
      {cfg.label}
    </span>
  );
};

const CampaignDetails = ({ campaign }) => (
  <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
    <div className="px-5 py-4 border-b border-gray-100">
      <h3 className="text-sm font-semibold text-gray-700">📧 Campaign Details</h3>
    </div>
    <div className="p-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
      {[
        { label: "Title",     value: campaign?.title },
        { label: "Subject",   value: campaign?.subject },
        { label: "Sender",    value: campaign?.sender_name },
        { label: "From",      value: campaign?.sender_email },
        { label: "Reply To",  value: campaign?.reply_to || campaign?.sender_email },
        { label: "Lists",     value: campaign?.target_lists?.join(", ") || "None" },
        { label: "Target",    value: fmt(campaign?.target_list_count) },
        { label: "Sent",      value: fmt(campaign?.sent_count) },
        { label: "Created",   value: fmtD(campaign?.created_at) },
        { label: "Started",   value: fmtD(campaign?.started_at) },
        { label: "Completed", value: campaign?.completed_at ? fmtD(campaign.completed_at) : "In progress" },
      ].map(({ label, value }) => (
        <div key={label}>
          <p className="text-xs font-medium text-gray-400 mb-1">{label}</p>
          <div className="text-sm text-gray-800 font-medium">{value || "—"}</div>
        </div>
      ))}
      <div>
        <p className="text-xs font-medium text-gray-400 mb-1">Status</p>
        <CampaignStatusBadge status={campaign?.status} />
      </div>
    </div>
  </div>
);

const EmailContentPreview = ({ campaign }) => {
  const [expanded, setExpanded] = useState(false);
  const html = campaign?.content_snapshot?.html_content;
  if (!html) return null;
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">📩 Email Content</h3>
        <button onClick={() => setExpanded(v => !v)} className="text-xs px-3 py-1.5 border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600 font-medium">
          {expanded ? "Collapse" : "Expand"}
        </button>
      </div>
      <div className="overflow-hidden transition-all duration-300" style={{ maxHeight: expanded ? "none" : "480px" }}>
        <iframe srcDoc={html} title="Email Preview" sandbox="allow-same-origin" className="w-full border-0" style={{ height: expanded ? "800px" : "480px" }} />
      </div>
      {!expanded && (
        <div className="px-5 py-3 border-t border-gray-100 text-center">
          <button onClick={() => setExpanded(true)} className="text-xs text-blue-600 hover:text-blue-700 font-medium">Show full email ↓</button>
        </div>
      )}
    </div>
  );
};

const LoadingSkeleton = () => (
  <div className="space-y-6 animate-pulse">
    <div className="h-24 bg-gray-200 rounded-xl" />
    <div className="h-48 bg-gray-200 rounded-xl" />
    <div className="grid grid-cols-4 gap-4">
      {[...Array(4)].map((_, i) => <div key={i} className="h-32 bg-gray-200 rounded-xl" />)}
    </div>
  </div>
);

const ErrorState = ({ error, onRetry }) => (
  <div className="flex items-center justify-center min-h-[60vh]">
    <div className="text-center max-w-sm">
      <p className="text-4xl mb-3">⚠️</p>
      <p className="font-semibold text-gray-800 mb-1">Failed to load analytics</p>
      <p className="text-sm text-gray-500 mb-4">{error}</p>
      <button onClick={onRetry} className="px-5 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700">Try Again</button>
    </div>
  </div>
);