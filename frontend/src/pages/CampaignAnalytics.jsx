import { useState, useEffect } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import API from "../api";
import axios from "axios";

const fmt = (n) => Number(n ?? 0).toLocaleString();
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

export default function CampaignAnalytics() {
  const { campaignId } = useParams();
  const navigate = useNavigate();
  const [analyticsData, setAnalyticsData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [downloading, setDownloading] = useState(null);

  useEffect(() => {
    fetchCampaignAnalytics();
  }, [campaignId]);

  const fetchCampaignAnalytics = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await API.get(`/analytics/campaigns/${campaignId}`);
      setAnalyticsData(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load analytics");
    } finally {
      setLoading(false);
    }
  };

  const downloadReport = async (eventType = "all") => {
    setDownloading(eventType);
    try {
      const token = localStorage.getItem("token");
      const response = await axios.get(
        `/api/analytics/campaigns/${campaignId}/export?event_type=${eventType}`,
        {
          responseType: "blob",
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      const title = (analyticsData?.campaign?.title || "campaign")
        .replace(/[^a-z0-9]/gi, "_")
        .replace(/_+/g, "_")
        .toLowerCase();
      const filename =
        eventType === "all"
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
    } catch (err) {
      alert("Download failed. Please try again.");
    } finally {
      setDownloading(null);
    }
  };

  if (loading) return <LoadingSkeleton />;
  if (error)
    return <ErrorState error={error} onRetry={fetchCampaignAnalytics} />;

  const { campaign, analytics, recent_events, top_links } = analyticsData || {};
  const progress =
    campaign?.target_list_count > 0
      ? Math.round((campaign.sent_count / campaign.target_list_count) * 100)
      : 0;

  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-6 py-5">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div className="flex items-center gap-3">
            <div>
              <div className="flex items-center gap-3 flex-wrap">
                <h1 className="text-lg font-bold text-gray-900">
                  {campaign?.title || "Campaign Analytics"}
                </h1>
                <CampaignStatusBadge status={campaign?.status} />
              </div>
              <p className="text-sm text-gray-500 mt-0.5">
                {campaign?.subject}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={fetchCampaignAnalytics}
              className="flex items-center gap-2 px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600"
            >
              🔄 Refresh
            </button>
            <button
              onClick={() => downloadReport("all")}
              disabled={downloading === "all"}
              className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white text-sm font-semibold rounded-lg hover:bg-green-700 disabled:opacity-60"
            >
              {downloading === "all" ? "⏳ Downloading…" : "⬇️ Full Report"}
            </button>
            <button
              onClick={() => navigate(-1)}
              className="flex items-center gap-2 px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600"
            >
              ← Back
            </button>
          </div>
        </div>
      </div>

      {/* ── Progress — only while actively sending or paused ── */}
      {["sending", "paused"].includes(campaign?.status) && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-5">
            Campaign Progress
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <ProgressCard
              title="Target"
              value={campaign?.target_list_count || 0}
              subtitle="Total to send"
              icon="🎯"
              color="bg-blue-50   text-blue-700   border-blue-200"
            />
            <ProgressCard
              title="Processed"
              value={campaign?.processed_count || 0}
              subtitle="Processed"
              icon="⚙️"
              color="bg-green-50  text-green-700  border-green-200"
            />
            <ProgressCard
              title="Sent"
              value={campaign?.sent_count || 0}
              subtitle="Successfully"
              icon="✅"
              color="bg-purple-50 text-purple-700 border-purple-200"
            />
            <ProgressCard
              title="Queued"
              value={campaign?.queued_count || 0}
              subtitle="Waiting"
              icon="⏳"
              color="bg-orange-50 text-orange-700 border-orange-200"
            />
          </div>
          <div className="mb-1 flex justify-between text-xs text-gray-500">
            <span>Progress</span>
            <span>{progress}%</span>
          </div>
          <div className="bg-gray-100 rounded-full h-2 mb-5">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4 border-t border-gray-100">
            <TimelineItem label="Started" value={fmtD(campaign?.started_at)} />
            <TimelineItem
              label="Last Batch"
              value={fmtD(campaign?.last_batch_at)}
            />
            <TimelineItem
              label="Completed"
              value={
                campaign?.completed_at
                  ? fmtD(campaign.completed_at)
                  : "In progress"
              }
            />
          </div>
        </div>
      )}

      {/* ── Engagement metrics ── */}
      <div>
        <h2 className="text-sm font-semibold text-gray-700 mb-4">
          Engagement Metrics
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          <MetricCard
            title="Sent"
            value={analytics?.total_sent || 0}
            subtitle="From campaign"
            icon="📧"
            color="text-blue-600"
            bg="bg-blue-50"
          />
          <MetricCard
            title="Opens"
            value={analytics?.total_opened || 0}
            subtitle={`${analytics?.open_rate || 0}% open rate`}
            icon="👁️"
            color="text-green-600"
            bg="bg-green-50"
            onDownload={() => downloadReport("opened")}
            downloading={downloading === "opened"}
          />
          <MetricCard
            title="Clicks"
            value={analytics?.total_clicked || 0}
            subtitle={`${analytics?.click_rate || 0}% click rate`}
            icon="👆"
            color="text-purple-600"
            bg="bg-purple-50"
            onDownload={() => downloadReport("clicked")}
            downloading={downloading === "clicked"}
          />
          <MetricCard
            title="Delivered"
            value={
              analytics?.total_delivered ||
              analytics?.total_sent - analytics?.total_bounced ||
              0
            }
            subtitle={`${analytics?.delivery_rate || 0}% delivery`}
            icon="✅"
            color="text-teal-600"
            bg="bg-teal-50"
            onDownload={() => downloadReport("delivered")}
            downloading={downloading === "delivered"}
          />
        </div>
        <div className="bg-red-50 border border-red-100 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-red-800 mb-4">
            ⚠️ Issues & Failures
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <MetricCard
              title="Bounces"
              value={analytics?.total_bounced || 0}
              subtitle={`${analytics?.bounce_rate || 0}% bounce`}
              icon="⚠️"
              color="text-red-600"
              bg="bg-red-100"
              onDownload={() => downloadReport("bounced")}
              downloading={downloading === "bounced"}
            />
            <MetricCard
              title="Unsubscribes"
              value={analytics?.total_unsubscribed || 0}
              subtitle={`${analytics?.unsubscribe_rate || 0}% unsub`}
              icon="🚫"
              color="text-orange-600"
              bg="bg-orange-100"
              onDownload={() => downloadReport("unsubscribed")}
              downloading={downloading === "unsubscribed"}
            />
            <MetricCard
              title="Spam Reports"
              value={analytics?.total_spam_reports || 0}
              subtitle="Marked as spam"
              icon="🚨"
              color="text-red-700"
              bg="bg-red-100"
              onDownload={() => downloadReport("spam_report")}
              downloading={downloading === "spam_report"}
            />
          </div>
        </div>
      </div>

      {/* ── Links + Activity ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <TopClickedLinks links={top_links} />
        <RecentActivity events={recent_events} />
      </div>

      {/* ── Email Content Preview ── */}
      <EmailContentPreview campaign={campaign} />

      {/* ── Campaign details ── */}
      <CampaignDetails campaign={campaign} />
    </div>
  );
}

// ─── sub-components ──────────────────────────────────────────
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

const MetricCard = ({
  title,
  value,
  subtitle,
  icon,
  color,
  bg,
  onDownload,
  downloading,
}) => (
  <div
    className={`bg-white ${bg} rounded-xl p-5 border hover:shadow-sm transition-shadow relative`}
  >
    {onDownload && (
      <button
        onClick={onDownload}
        disabled={downloading}
        title={`Download ${title} list`}
        className="absolute top-3 right-3 p-1.5 bg-white rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-50 shadow-sm text-xs"
      >
        {downloading ? "⏳" : "⬇️"}
      </button>
    )}
    <div className="text-center">
      <p className="text-2xl mb-2">{icon}</p>
      <p className="text-xs font-medium text-gray-500 mb-1">{title}</p>
      <p className={`text-3xl font-bold tabular-nums ${color} mb-1`}>
        {fmt(value)}
      </p>
      {subtitle && <p className="text-xs text-gray-400">{subtitle}</p>}
    </div>
  </div>
);

const TopClickedLinks = ({ links }) => (
  <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
    <div className="px-5 py-4 border-b border-gray-100">
      <h3 className="text-sm font-semibold text-gray-700">
        🔗 Top Clicked Links
      </h3>
    </div>
    <div className="p-5">
      {links?.length > 0 ? (
        <div className="space-y-2">
          {links.map((link, i) => (
            <div
              key={i}
              className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
            >
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <div className="w-6 h-6 bg-blue-600 text-white rounded-md flex items-center justify-center text-xs font-bold flex-shrink-0">
                  {i + 1}
                </div>
                <p className="text-sm text-gray-800 truncate">
                  {link.url || "Unknown URL"}
                </p>
              </div>
              <span className="px-2.5 py-1 bg-blue-100 text-blue-800 text-xs font-semibold rounded-full ml-3 flex-shrink-0">
                {fmt(link.clicks)}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-8">
          <p className="text-3xl text-gray-200 mb-2">🔗</p>
          <p className="text-sm text-gray-400">No link clicks recorded yet</p>
        </div>
      )}
    </div>
  </div>
);

const EVENT_ICONS = {
  opened: { icon: "👁️", bg: "bg-green-100", color: "text-green-600" },
  clicked: { icon: "👆", bg: "bg-purple-100", color: "text-purple-600" },
  bounced: { icon: "⚠️", bg: "bg-red-100", color: "text-red-600" },
  delivered: { icon: "✅", bg: "bg-green-100", color: "text-green-600" },
  unsubscribed: { icon: "🚫", bg: "bg-orange-100", color: "text-orange-600" },
  spam_report: { icon: "🚨", bg: "bg-red-100", color: "text-red-600" },
};

const RecentActivity = ({ events }) => (
  <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
    <div className="px-5 py-4 border-b border-gray-100">
      <h3 className="text-sm font-semibold text-gray-700">
        📈 Recent Activity
      </h3>
    </div>
    <div className="p-5">
      {events?.length > 0 ? (
        <div className="space-y-2 max-h-72 overflow-y-auto">
          {events.slice(0, 15).map((event, i) => {
            const cfg = EVENT_ICONS[event.event_type] || {
              icon: "📧",
              bg: "bg-gray-100",
              color: "text-gray-600",
            };
            return (
              <div
                key={i}
                className="flex items-center gap-3 p-2 hover:bg-gray-50 rounded-lg"
              >
                <div
                  className={`w-7 h-7 ${cfg.bg} rounded-lg flex items-center justify-center flex-shrink-0`}
                >
                  <span className="text-xs">{cfg.icon}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-gray-800 capitalize">
                    {event.event_type}
                    {event.subscriber_email && (
                      <span className="text-gray-400 font-normal ml-1">
                        · {event.subscriber_email}
                      </span>
                    )}
                  </p>
                  <p className="text-xs text-gray-400">
                    {fmtD(event.timestamp)}
                  </p>
                  {event.url && event.event_type === "clicked" && (
                    <p className="text-xs text-blue-500 truncate mt-0.5">
                      {event.url}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-center py-8">
          <p className="text-3xl text-gray-200 mb-2">📊</p>
          <p className="text-sm text-gray-400">No recent activity</p>
        </div>
      )}
    </div>
  </div>
);

const CampaignDetails = ({ campaign }) => (
  <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
    <div className="px-5 py-4 border-b border-gray-100">
      <h3 className="text-sm font-semibold text-gray-700">
        📧 Campaign Details
      </h3>
    </div>
    <div className="p-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
      {[
        { label: "Title", value: campaign?.title },
        { label: "Subject", value: campaign?.subject },
        { label: "Sender", value: campaign?.sender_name },
        { label: "From", value: campaign?.sender_email },
        {
          label: "Reply To",
          value: campaign?.reply_to || campaign?.sender_email,
        },
        { label: "Lists", value: campaign?.target_lists?.join(", ") || "None" },
        { label: "Target", value: fmt(campaign?.target_list_count) },
        { label: "Sent", value: fmt(campaign?.sent_count) },
        { label: "Created", value: fmtD(campaign?.created_at) },
        { label: "Started", value: fmtD(campaign?.started_at) },
        {
          label: "Completed",
          value: campaign?.completed_at
            ? fmtD(campaign.completed_at)
            : "In progress",
        },
      ].map(({ label, value }) => (
        <div key={label}>
          <p className="text-xs font-medium text-gray-400 mb-1">{label}</p>
          <div className="text-sm text-gray-800 font-medium">
            {value || "—"}
          </div>
        </div>
      ))}
      <div>
        <p className="text-xs font-medium text-gray-400 mb-1">Status</p>
        <CampaignStatusBadge status={campaign?.status} />
      </div>
    </div>
  </div>
);

const CampaignStatusBadge = ({ status }) => {
  const cfg = {
    sent: { bg: "bg-green-100", text: "text-green-800", label: "✅ Sent" },
    completed: {
      bg: "bg-green-100",
      text: "text-green-800",
      label: "✅ Completed",
    },
    draft: { bg: "bg-yellow-100", text: "text-yellow-800", label: "📝 Draft" },
    sending: { bg: "bg-blue-100", text: "text-blue-800", label: "📤 Sending" },
    paused: {
      bg: "bg-orange-100",
      text: "text-orange-800",
      label: "⏸️ Paused",
    },
    stopped: { bg: "bg-gray-100", text: "text-gray-700", label: "🛑 Stopped" },
    failed: { bg: "bg-red-100", text: "text-red-800", label: "❌ Failed" },
  }[status] || {
    bg: "bg-gray-100",
    text: "text-gray-700",
    label: status || "Unknown",
  };
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${cfg.bg} ${cfg.text}`}
    >
      {cfg.label}
    </span>
  );
};

const EmailContentPreview = ({ campaign }) => {
  const [expanded, setExpanded] = useState(false);
  const html = campaign?.content_snapshot?.html_content;

  if (!html) return null;

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">📩 Email Content</h3>
        <button
          onClick={() => setExpanded((v) => !v)}
          className="text-xs px-3 py-1.5 border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600 font-medium"
        >
          {expanded ? "Collapse" : "Expand"}
        </button>
      </div>
      <div
        className="overflow-hidden transition-all duration-300"
        style={{ maxHeight: expanded ? "none" : "480px" }}
      >
        <iframe
          srcDoc={html}
          title="Email Preview"
          sandbox="allow-same-origin"
          className="w-full border-0"
          style={{ height: expanded ? "800px" : "480px" }}
        />
      </div>
      {!expanded && (
        <div className="px-5 py-3 border-t border-gray-100 text-center">
          <button
            onClick={() => setExpanded(true)}
            className="text-xs text-blue-600 hover:text-blue-700 font-medium"
          >
            Show full email ↓
          </button>
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
      {[...Array(4)].map((_, i) => (
        <div key={i} className="h-32 bg-gray-200 rounded-xl" />
      ))}
    </div>
  </div>
);

const ErrorState = ({ error, onRetry }) => (
  <div className="flex items-center justify-center min-h-[60vh]">
    <div className="text-center max-w-sm">
      <p className="text-4xl mb-3">⚠️</p>
      <p className="font-semibold text-gray-800 mb-1">
        Failed to load analytics
      </p>
      <p className="text-sm text-gray-500 mb-4">{error}</p>
      <button
        onClick={onRetry}
        className="px-5 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700"
      >
        Try Again
      </button>
    </div>
  </div>
);
