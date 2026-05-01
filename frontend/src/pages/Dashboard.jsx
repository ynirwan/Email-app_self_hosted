import { useEffect, useState, useCallback } from "react";
import { useNavigate, Link } from "react-router-dom";
import API from "../api";
import { useUser } from "../contexts/UserContext";
import { useSettings } from "../contexts/SettingsContext";

// ─── tiny helpers ────────────────────────────────────────────
const fmt = (n) => Number(n ?? 0).toLocaleString();
const pct = (n) => `${Number(n ?? 0).toFixed(1)}%`;
const timeAgo = (iso) => {
  if (!iso) return null;
  const secs = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  return `${Math.floor(secs / 3600)}h ago`;
};

// ─── StatCard ────────────────────────────────────────────────
function StatCard({
  label,
  value,
  sub,
  subColor = "text-gray-500",
  accent,
  icon,
  pulse,
}) {
  return (
    <div
      className={`bg-white rounded-xl border border-gray-200 p-5 shadow-sm hover:shadow-md transition-shadow`}
    >
      <div className="flex items-start justify-between mb-3">
        <span className="text-sm font-medium text-gray-500">{label}</span>
        <span className={`text-xl ${accent}`}>{icon}</span>
      </div>
      <div className="flex items-end gap-2">
        <span className="text-2xl font-bold text-gray-900 tabular-nums">
          {value}
        </span>
        {pulse && (
          <span className="mb-0.5 flex items-center gap-1 text-xs font-semibold text-blue-600">
            <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse" />
            live
          </span>
        )}
      </div>
      {sub && <p className={`text-xs mt-1 ${subColor}`}>{sub}</p>}
    </div>
  );
}

// ─── StatusPill ──────────────────────────────────────────────
const STATUS_STYLES = {
  draft: { bg: "bg-yellow-100", text: "text-yellow-800", dot: "bg-yellow-400" },
  sending: {
    bg: "bg-blue-100",
    text: "text-blue-800",
    dot: "bg-blue-500",
    pulse: true,
  },
  scheduled: {
    bg: "bg-purple-100",
    text: "text-purple-800",
    dot: "bg-purple-400",
  },
  completed: {
    bg: "bg-green-100",
    text: "text-green-800",
    dot: "bg-green-500",
  },
  failed: { bg: "bg-red-100", text: "text-red-800", dot: "bg-red-500" },
  stopped: { bg: "bg-gray-100", text: "text-gray-700", dot: "bg-gray-400" },
};

function StatusPill({ label, count, status, onClick }) {
  if (!count) return null;
  const s = STATUS_STYLES[status] || STATUS_STYLES.draft;
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold ${s.bg} ${s.text} hover:opacity-80 transition-opacity cursor-pointer`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${s.dot} ${s.pulse ? "animate-pulse" : ""}`}
      />
      {count} {label}
    </button>
  );
}

// ─── BarRow (list breakdown) ─────────────────────────────────
function BarRow({ name, count, total, index }) {
  const pctVal = total > 0 ? (count / total) * 100 : 0;
  const colors = [
    "bg-blue-500",
    "bg-violet-500",
    "bg-emerald-500",
    "bg-amber-500",
    "bg-rose-500",
  ];
  const color = colors[index % colors.length];
  return (
    <div>
      <div className="flex justify-between items-center mb-1">
        <span className="text-sm font-medium text-gray-700 capitalize truncate max-w-[160px]">
          {name || "Unknown"}
        </span>
        <span className="text-sm text-gray-500 tabular-nums ml-2">
          {fmt(count)}
        </span>
      </div>
      <div className="bg-gray-100 rounded-full h-2 overflow-hidden">
        <div
          className={`h-2 rounded-full ${color} transition-all duration-700`}
          style={{ width: `${Math.max(pctVal, 2)}%` }}
        />
      </div>
      <div className="text-xs text-gray-400 mt-0.5">{pct(pctVal)} of total</div>
    </div>
  );
}

// ─── RateBar (open/click visual) ─────────────────────────────
function RateBar({ label, value, color, max = 100 }) {
  const width = Math.min((value / Math.max(max, 1)) * 100, 100);
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-gray-500 w-16 flex-shrink-0">{label}</span>
      <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
        <div
          className={`h-2 rounded-full transition-all duration-700 ${color}`}
          style={{ width: `${width}%` }}
        />
      </div>
      <span
        className={`text-sm font-bold tabular-nums w-12 text-right ${color.replace("bg-", "text-")}`}
      >
        {pct(value)}
      </span>
    </div>
  );
}

// ─── Main Dashboard ──────────────────────────────────────────
export default function Dashboard() {
  const { user, userLoading } = useUser();
  const { t, formatDate, formatRelative } = useSettings();
  const navigate = useNavigate();

  const [stats, setStats] = useState(null);
  const [engagement, setEngagement] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchAll = useCallback(
    async (isRefresh = false) => {
      if (isRefresh) setRefreshing(true);
      try {
        setError(null);
        const [summaryRes, engagementRes] = await Promise.all([
          API.get("/stats/summary"),
          API.get("/stats/engagement"),
        ]);
        setStats(summaryRes.data);
        setEngagement(engagementRes.data);
        setLastUpdated(new Date().toISOString());
      } catch (err) {
        if (err.response?.status === 401) {
          localStorage.removeItem("token");
          navigate("/login", { replace: true });
          return;
        }
        setError("Failed to load dashboard data");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [navigate],
  );

  // initial load
  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  // auto-refresh every 60s when campaigns are actively sending
  useEffect(() => {
    if (!stats?.sending_campaigns) return;
    const id = setInterval(() => fetchAll(true), 60_000);
    return () => clearInterval(id);
  }, [stats?.sending_campaigns, fetchAll]);

  // ── loading state ──
  if (loading || userLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto" />
          <p className="mt-3 text-gray-500 text-sm">Loading dashboard…</p>
        </div>
      </div>
    );
  }

  // ── error state ──
  if (error && !stats) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center max-w-sm">
          <div className="text-4xl mb-3">⚠️</div>
          <p className="font-semibold text-gray-800 mb-1">
            Failed to load dashboard
          </p>
          <p className="text-sm text-gray-500 mb-4">{error}</p>
          <button
            onClick={() => fetchAll()}
            className="px-5 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 transition-colors"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  const s = stats || {};
  const totalSubs = s.total_subscribers || 0;
  const recentCampaigns = s.recent_performance || [];
  const lists = s.lists || [];

  // ── contextual quick actions ──
  const quickActions = [];
  if (s.sending_campaigns > 0)
    quickActions.push({
      label: `View ${s.sending_campaigns} sending`,
      icon: "📤",
      to: "/campaigns",
      color: "bg-blue-600 hover:bg-blue-700",
    });
  if (s.failed_campaigns > 0)
    quickActions.push({
      label: `${s.failed_campaigns} failed`,
      icon: "⚠️",
      to: "/campaigns",
      color: "bg-red-600 hover:bg-red-700",
    });
  if (s.draft_campaigns > 0)
    quickActions.push({
      label: "Continue draft",
      icon: "📝",
      to: "/campaigns",
      color: "bg-yellow-500 hover:bg-yellow-600",
    });
  if (totalSubs === 0)
    quickActions.push({
      label: "Import subscribers",
      icon: "📥",
      to: "/subscribers",
      color: "bg-blue-600 hover:bg-blue-700",
    });
  // always-present fallbacks
  if (quickActions.length < 4)
    quickActions.push({
      label: "Create campaign",
      icon: "📧",
      to: "/campaigns",
      color: "bg-green-600 hover:bg-green-700",
    });
  if (quickActions.length < 4)
    quickActions.push({
      label: "A/B Testing",
      icon: "🧪",
      to: "/ab-testing",
      color: "bg-indigo-600 hover:bg-indigo-700",
    });
  if (quickActions.length < 4)
    quickActions.push({
      label: "Subscribers",
      icon: "👥",
      to: "/subscribers",
      color: "bg-gray-700 hover:bg-gray-800",
    });
  if (quickActions.length < 4)
    quickActions.push({
      label: "Settings",
      icon: "⚙️",
      to: "/settings/email",
      color: "bg-gray-600 hover:bg-gray-700",
    });

  return (
    <div className="space-y-8 pb-10">
      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {user ? `Welcome back, ${user.name} 👋` : "Dashboard"}
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {user?.email}
            {lastUpdated && (
              <span className="ml-3 text-gray-400">
                · Updated {formatRelative(lastUpdated)}
                {s.sending_campaigns > 0 && " · auto-refreshing"}
              </span>
            )}
          </p>
        </div>
        <button
          onClick={() => fetchAll(true)}
          disabled={refreshing}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
        >
          <span className={refreshing ? "animate-spin" : ""}>🔄</span>
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {/* ── 6 stat cards ── */}
      <section>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <StatCard
            label="Total Subscribers"
            value={fmt(totalSubs)}
            sub={`${fmt(s.active_subscribers)} active`}
            subColor="text-green-600"
            icon="👥"
            accent="text-blue-500"
          />
          <StatCard
            label="Active Rate"
            value={pct(s.summary?.active_rate)}
            sub={`${fmt(totalSubs - (s.active_subscribers || 0))} inactive`}
            subColor="text-gray-400"
            icon="💚"
            accent="text-green-500"
          />
          <StatCard
            label="Avg Open Rate"
            value={pct(s.summary?.avg_open_rate)}
            sub={
              engagement
                ? `best ${pct(engagement.best_open_rate)}`
                : "last 5 campaigns"
            }
            subColor="text-blue-500"
            icon="📬"
            accent="text-blue-500"
          />
          <StatCard
            label="Total Campaigns"
            value={fmt(s.total_campaigns)}
            sub={`${fmt(s.completed_campaigns)} completed`}
            subColor="text-green-600"
            icon="📢"
            accent="text-purple-500"
          />
          <StatCard
            label="Sending Now"
            value={fmt(s.sending_campaigns)}
            sub={s.sending_campaigns > 0 ? "active sends" : "none active"}
            subColor={
              s.sending_campaigns > 0 ? "text-blue-600" : "text-gray-400"
            }
            icon="📤"
            accent="text-blue-500"
            pulse={s.sending_campaigns > 0}
          />
          <StatCard
            label="Avg Click Rate"
            value={pct(s.summary?.avg_click_rate)}
            sub={
              engagement
                ? `${fmt(engagement.total_emails_sent)} sent total`
                : "last 5 campaigns"
            }
            subColor="text-purple-500"
            icon="👆"
            accent="text-purple-500"
          />
        </div>
      </section>

      {/* ── Campaign status strip ── */}
      {s.total_campaigns > 0 && (
        <section className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">
            Campaign Status
          </h2>
          <div className="flex flex-wrap gap-2">
            <StatusPill
              label="Draft"
              count={s.draft_campaigns}
              status="draft"
              onClick={() => navigate("/campaigns")}
            />
            <StatusPill
              label="Sending"
              count={s.sending_campaigns}
              status="sending"
              onClick={() => navigate("/campaigns")}
            />
            <StatusPill
              label="Scheduled"
              count={s.scheduled_campaigns}
              status="scheduled"
              onClick={() => navigate("/campaigns")}
            />
            <StatusPill
              label="Completed"
              count={s.completed_campaigns}
              status="completed"
              onClick={() => navigate("/campaigns")}
            />
            <StatusPill
              label="Stopped"
              count={s.stopped_campaigns}
              status="stopped"
              onClick={() => navigate("/campaigns")}
            />
            <StatusPill
              label="Failed"
              count={s.failed_campaigns}
              status="failed"
              onClick={() => navigate("/campaigns")}
            />
          </div>
        </section>
      )}

      {/* ── Two-column: recent campaigns + list breakdown ── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Recent Campaigns — 3 cols */}
        <section className="lg:col-span-3 bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
            <h2 className="text-sm font-semibold text-gray-700">
              {t('dashboard.recentCampaigns')}
            </h2>
            <Link
              to="/campaigns"
              className="text-xs text-blue-600 font-medium hover:underline"
            >
              View all →
            </Link>
          </div>

          {recentCampaigns.length === 0 ? (
            <div className="px-5 py-10 text-center">
              <p className="text-3xl mb-2">📭</p>
              <p className="text-sm text-gray-500">
                {t('dashboard.noData')}
              </p>
              <Link
                to="/campaigns"
                className="inline-block mt-3 text-sm text-blue-600 font-medium hover:underline"
              >
                Create your first campaign →
              </Link>
            </div>
          ) : (
            <div className="divide-y divide-gray-50">
              {/* header row */}
              <div className="grid grid-cols-12 px-5 py-2 text-xs font-medium text-gray-400 uppercase tracking-wider">
                <span className="col-span-5">Campaign</span>
                <span className="col-span-2 text-right">Sent</span>
                <span className="col-span-2 text-right">Open</span>
                <span className="col-span-2 text-right">Click</span>
                <span className="col-span-1" />
              </div>
              {recentCampaigns.map((c, i) => (
                <div
                  key={c._id || i}
                  className="grid grid-cols-12 items-center px-5 py-3 hover:bg-gray-50 transition-colors"
                >
                  <div className="col-span-5 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {c.title || "Untitled"}
                    </p>
                    {c.sent_at && (
                      <p className="text-xs text-gray-400">
                        {formatDate(c.sent_at)}
                      </p>
                    )}
                  </div>
                  <span className="col-span-2 text-sm text-gray-600 tabular-nums text-right">
                    {fmt(c.sent_count)}
                  </span>
                  <span
                    className={`col-span-2 text-sm font-semibold tabular-nums text-right ${
                      (c.open_rate || 0) >= 20
                        ? "text-green-600"
                        : (c.open_rate || 0) >= 10
                          ? "text-yellow-600"
                          : "text-gray-500"
                    }`}
                  >
                    {pct(c.open_rate)}
                  </span>
                  <span
                    className={`col-span-2 text-sm font-semibold tabular-nums text-right ${
                      (c.click_rate || 0) >= 3
                        ? "text-blue-600"
                        : "text-gray-500"
                    }`}
                  >
                    {pct(c.click_rate)}
                  </span>
                  <div className="col-span-1 flex justify-end">
                    <Link
                      to={`/analytics/campaign/${c._id}`}
                      className="text-gray-300 hover:text-blue-500 transition-colors text-xs"
                      title="View report"
                    >
                      📊
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* List breakdown — 2 cols */}
        <section className="lg:col-span-2 bg-white border border-gray-200 rounded-xl shadow-sm">
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
            <h2 className="text-sm font-semibold text-gray-700">
              Subscribers by List
            </h2>
            <Link
              to="/subscribers"
              className="text-xs text-blue-600 font-medium hover:underline"
            >
              Manage →
            </Link>
          </div>
          <div className="p-5">
            {lists.length === 0 ? (
              <div className="py-6 text-center">
                <p className="text-2xl mb-2">📋</p>
                <p className="text-sm text-gray-500">No lists yet</p>
                <Link
                  to="/subscribers"
                  className="text-xs text-blue-600 mt-1 inline-block hover:underline"
                >
                  Import subscribers →
                </Link>
              </div>
            ) : (
              <div className="space-y-4">
                {lists.map((list, i) => (
                  <BarRow
                    key={list._id || i}
                    name={list._id}
                    count={list.count}
                    total={totalSubs}
                    index={i}
                  />
                ))}
              </div>
            )}
          </div>
        </section>
      </div>

      {/* ── Engagement rates visual ── */}
      {(s.summary?.avg_open_rate > 0 || s.summary?.avg_click_rate > 0) && (
        <section className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-gray-700">
              Engagement Performance
            </h2>
            <span className="text-xs text-gray-400">
              {engagement ? "Last 30 days" : "Last 5 campaigns"}
            </span>
          </div>
          <div className="space-y-3 max-w-lg">
            <RateBar
              label="Open rate"
              value={s.summary?.avg_open_rate || 0}
              color="bg-blue-500"
              max={50}
            />
            <RateBar
              label="Click rate"
              value={s.summary?.avg_click_rate || 0}
              color="bg-purple-500"
              max={50}
            />
            {engagement?.best_open_rate > 0 && (
              <RateBar
                label="Best open"
                value={engagement.best_open_rate}
                color="bg-green-500"
                max={50}
              />
            )}
          </div>
          {engagement?.total_emails_sent > 0 && (
            <p className="text-xs text-gray-400 mt-4">
              {fmt(engagement.total_emails_sent)} total emails sent in the last
              30 days
            </p>
          )}
        </section>
      )}

      {/* ── Quick Actions ── */}
      <section>
        <h2 className="text-sm font-semibold text-gray-700 mb-3">
          Quick Actions
        </h2>
        <div className="flex flex-wrap gap-3">
          {quickActions.slice(0, 4).map((action) => (
            <Link
              key={action.label}
              to={action.to}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold text-white transition-colors ${action.color}`}
            >
              <span>{action.icon}</span>
              {action.label}
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
