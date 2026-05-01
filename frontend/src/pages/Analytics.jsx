import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import API from "../api";
import { useSettings } from "../contexts/SettingsContext";

const fmt = (n) => Number(n ?? 0).toLocaleString();
const pct = (n) => `${Number(n ?? 0).toFixed(1)}%`;
const fmtD = (iso) =>
  iso
    ? new Date(iso).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "—";

function StatCard({ label, value, sub, color, icon }) {
  const colors = {
    blue: "bg-blue-50   border-blue-200   text-blue-700",
    green: "bg-green-50  border-green-200  text-green-700",
    purple: "bg-purple-50 border-purple-200 text-purple-700",
    rose: "bg-rose-50   border-rose-200   text-rose-700",
    gray: "bg-gray-50   border-gray-200   text-gray-600",
  };
  return (
    <div className={`rounded-xl border p-5 ${colors[color] || colors.gray}`}>
      <div className="flex items-center justify-between mb-3">
        <span className="text-xl">{icon}</span>
      </div>
      <p className="text-2xl font-bold tabular-nums">{value}</p>
      <p className="text-xs font-semibold mt-0.5 opacity-75">{label}</p>
      {sub && <p className="text-xs mt-1 opacity-60">{sub}</p>}
    </div>
  );
}

function CampaignRow({ campaign, formatDate }) {
  const analytics = campaign.analytics || {};
  const sent = analytics.total_sent || 0;
  const openRate = analytics.open_rate || 0;
  const clickRate = analytics.click_rate || 0;
  const status = campaign.status || "draft";
  const statusStyles = {
    sent: "bg-green-100 text-green-800",
    completed: "bg-green-100 text-green-800",
    sending: "bg-blue-100 text-blue-800",
    draft: "bg-gray-100 text-gray-700",
    paused: "bg-amber-100 text-amber-800",
    failed: "bg-red-100 text-red-700",
    stopped: "bg-gray-100 text-gray-600",
    scheduled: "bg-purple-100 text-purple-800",
  };
  return (
    <tr className="hover:bg-gray-50 transition-colors border-b border-gray-50 last:border-0">
      <td className="px-5 py-3.5">
        <Link to={`/analytics/campaign/${campaign._id}`} className="group">
          <p className="text-sm font-semibold text-gray-900 group-hover:text-blue-600 truncate max-w-[200px]">
            {campaign.title || "Untitled"}
          </p>
          <p className="text-xs text-gray-400 truncate max-w-[200px] mt-0.5">
            {campaign.subject}
          </p>
        </Link>
      </td>
      <td className="px-4 py-3.5">
        <span
          className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${statusStyles[status] || statusStyles.draft}`}
        >
          {status}
        </span>
      </td>
      <td className="px-4 py-3.5 text-right tabular-nums text-sm text-gray-700 font-medium">
        {sent > 0 ? fmt(sent) : <span className="text-gray-300">—</span>}
      </td>
      <td className="px-4 py-3.5 w-40">
        <div className="flex items-center gap-2">
          <div className="flex-1 bg-blue-100 rounded-full h-1.5 overflow-hidden">
            <div
              className="bg-blue-500 h-1.5 rounded-full"
              style={{ width: `${Math.min(openRate, 100)}%` }}
            />
          </div>
          <span className="text-xs font-semibold text-blue-600 w-12 text-right">
            {pct(openRate)}
          </span>
        </div>
      </td>
      <td className="px-4 py-3.5 w-40">
        <div className="flex items-center gap-2">
          <div className="flex-1 bg-purple-100 rounded-full h-1.5 overflow-hidden">
            <div
              className="bg-purple-500 h-1.5 rounded-full"
              style={{ width: `${Math.min(clickRate * 4, 100)}%` }}
            />
          </div>
          <span className="text-xs font-semibold text-purple-600 w-12 text-right">
            {pct(clickRate)}
          </span>
        </div>
      </td>
      <td className="px-4 py-3.5 text-right text-xs text-gray-400 whitespace-nowrap">
        {formatDate(
          campaign.completed_at || campaign.started_at || campaign.created_at,
        )}
      </td>
      <td className="px-4 py-3.5 text-right">
        <Link
          to={`/analytics/campaign/${campaign._id}`}
          className="text-xs font-medium text-blue-600 hover:underline"
        >
          Report →
        </Link>
      </td>
    </tr>
  );
}

function ABStatusBadge({ status }) {
  const cfg = {
    completed: { cls: "bg-green-100 text-green-800", label: "Completed" },
    running: { cls: "bg-blue-100 text-blue-800", label: "Sending" },
    stopped: { cls: "bg-amber-100 text-amber-800", label: "Stopped" },
    not_sent: { cls: "bg-gray-100 text-gray-500", label: "Not sent" },
  }[status || "not_sent"] || {
    cls: "bg-gray-100 text-gray-600",
    label: status || "—",
  };
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full font-semibold ${cfg.cls}`}
    >
      {cfg.label}
    </span>
  );
}

function ABWinnerRow({ test }) {
  // winnerSent / winnerOpenRate / winnerClickRate are pre-computed from winner-analytics
  const sent = test.winnerSent ?? 0;
  const openRate = test.winnerOpenRate ?? 0;
  const clickRate = test.winnerClickRate ?? 0;
  const wsStatus = test.winner_send_status;
  return (
    <tr className="hover:bg-gray-50 transition-colors border-b border-gray-50 last:border-0">
      <td className="px-5 py-3.5">
        <p className="text-sm font-semibold text-gray-900 truncate max-w-[200px]">
          {test.test_name || "Untitled"}
        </p>
        <p className="text-xs text-gray-400 mt-0.5 truncate max-w-[200px]">
          {test.subject}
        </p>
      </td>
      <td className="px-4 py-3.5">
        {test.winner_variant ? (
          <span className="inline-flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">
            🏆 Variant {test.winner_variant}
          </span>
        ) : (
          <span className="text-xs text-gray-400 italic">—</span>
        )}
      </td>
      <td className="px-4 py-3.5">
        <ABStatusBadge status={wsStatus} />
      </td>
      <td className="px-4 py-3.5 text-right tabular-nums text-sm text-gray-700 font-medium">
        {sent > 0 ? fmt(sent) : <span className="text-gray-300">—</span>}
      </td>
      <td className="px-4 py-3.5 w-40">
        {sent > 0 ? (
          <div className="flex items-center gap-2">
            <div className="flex-1 bg-violet-100 rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-violet-500 h-1.5 rounded-full"
                style={{ width: `${Math.min(openRate, 100)}%` }}
              />
            </div>
            <span className="text-xs font-semibold text-violet-600 w-12 text-right">
              {pct(openRate)}
            </span>
          </div>
        ) : (
          <span className="text-xs text-gray-300">—</span>
        )}
      </td>
      <td className="px-4 py-3.5 w-40">
        {sent > 0 ? (
          <div className="flex items-center gap-2">
            <div className="flex-1 bg-pink-100 rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-pink-500 h-1.5 rounded-full"
                style={{ width: `${Math.min(clickRate * 4, 100)}%` }}
              />
            </div>
            <span className="text-xs font-semibold text-pink-600 w-12 text-right">
              {pct(clickRate)}
            </span>
          </div>
        ) : (
          <span className="text-xs text-gray-300">—</span>
        )}
      </td>
      <td className="px-4 py-3.5 text-right">
        <div className="flex items-center justify-end gap-3">
          <Link
            to={`/ab-tests/${test._id}/results`}
            className="text-xs font-medium text-violet-600 hover:underline"
          >
            Results →
          </Link>
          {wsStatus && wsStatus !== "not_sent" && (
            <Link
              to={`/ab-tests/${test._id}/winner-report`}
              className="text-xs font-medium text-green-600 hover:underline"
            >
              Report →
            </Link>
          )}
        </div>
      </td>
    </tr>
  );
}

export default function Analytics() {
  const { t, formatDate } = useSettings();
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [abTests, setAbTests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingAB, setLoadingAB] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("campaigns");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await API.get(`/analytics/dashboard?days=${days}`);
      setData(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load analytics");
    } finally {
      setLoading(false);
    }
  }, [days]);

  const loadABTests = useCallback(async () => {
    setLoadingAB(true);
    try {
      const res = await API.get("/ab-tests");
      const allTests = res.data.tests || res.data || [];
      const relevant = allTests.filter(
        (t) => t.status === "completed" || t.winner_send_status === "running",
      );

      // Fetch winner analytics for all in parallel
      const results = await Promise.allSettled(
        relevant.map((t) =>
          API.get(`/ab-tests/${t._id}/winner-analytics`)
            .then((r) => ({
              id: t._id,
              analytics: r.data?.analytics || {},
              winner_send_status: r.data?.winner_send_status,
            }))
            .catch(() => ({
              id: t._id,
              analytics: {},
              winner_send_status: null,
            })),
        ),
      );

      const enriched = relevant.map((t) => {
        const found = results.find(
          (r) => r.status === "fulfilled" && r.value.id === t._id,
        );
        const wd = found?.value || {};
        const a = wd.analytics || {};
        const totalSent = a.total_sent || 0;
        return {
          ...t,
          winnerSent: totalSent,
          winnerOpenRate:
            totalSent > 0 ? ((a.total_opened || 0) / totalSent) * 100 : 0,
          winnerClickRate:
            totalSent > 0 ? ((a.total_clicked || 0) / totalSent) * 100 : 0,
          winner_send_status:
            wd.winner_send_status || t.winner_send_status || null,
        };
      });
      setAbTests(enriched);
    } catch {
      setAbTests([]);
    } finally {
      setLoadingAB(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (activeTab === "ab_tests") loadABTests();
  }, [activeTab, loadABTests]);

  const summary = data?.summary || {};
  const campaigns = data?.campaigns || [];

  // AB aggregates (only tests with actual sends)
  const abWithSends = abTests.filter((t) => t.winnerSent > 0);
  const abTotalSent = abWithSends.reduce((s, t) => s + t.winnerSent, 0);
  const abTotalOpened = abWithSends.reduce(
    (s, t) => s + Math.round((t.winnerOpenRate / 100) * t.winnerSent),
    0,
  );
  const abTotalClicked = abWithSends.reduce(
    (s, t) => s + Math.round((t.winnerClickRate / 100) * t.winnerSent),
    0,
  );
  const abAvgOpen = abTotalSent > 0 ? (abTotalOpened / abTotalSent) * 100 : 0;
  const abAvgClick = abTotalSent > 0 ? (abTotalClicked / abTotalSent) * 100 : 0;

  if (loading && !data) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-28 bg-gray-200 rounded-xl" />
          ))}
        </div>
        <div className="h-72 bg-gray-200 rounded-xl" />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-center">
          <p className="text-3xl mb-2">⚠️</p>
          <p className="text-gray-700 font-semibold mb-2">
            Failed to load analytics
          </p>
          <p className="text-sm text-gray-500 mb-4">{error}</p>
          <button
            onClick={load}
            className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Performance overview across campaigns & A/B tests
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:ring-2 focus:ring-blue-400"
          >
            <option value={7}>{t('analytics.last7Days')}</option>
            <option value={30}>{t('analytics.last30Days')}</option>
            <option value={90}>Last 90 days</option>
            <option value={365}>Last year</option>
          </select>
          <button
            onClick={load}
            className="px-4 py-2 text-sm font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600"
          >
            🔄 Refresh
          </button>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Total Campaigns"
          value={fmt(summary.total_campaigns)}
          icon="📢"
          color="blue"
          sub={`Last ${days} days`}
        />
        <StatCard
          label={t('analytics.totalSent')}
          value={fmt(summary.total_emails_sent)}
          icon="📧"
          color="green"
          sub="Across all campaigns"
        />
        <StatCard
          label={t('analytics.openRate')}
          value={pct(summary.average_open_rate)}
          icon="👁️"
          color="purple"
          sub={`${fmt(summary.total_opens)} ${t('analytics.opens')}`}
        />
        <StatCard
          label={t('analytics.clickRate')}
          value={pct(summary.average_click_rate)}
          icon="👆"
          color="rose"
          sub={`${fmt(summary.total_clicks)} ${t('analytics.clicks')}`}
        />
      </div>

      {/* Engagement rates — ONE section only, for campaigns */}
      {(summary.average_open_rate > 0 || summary.average_click_rate > 0) && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">
            Campaign Engagement Rates
          </h2>
          <div className="space-y-3 max-w-lg">
            <div className="flex items-center gap-3">
              <span className="text-xs text-gray-500 w-24 flex-shrink-0">
                {t('analytics.openRate')}
              </span>
              <div className="flex-1 bg-blue-100 rounded-full h-2 overflow-hidden">
                <div
                  className="bg-blue-500 h-2 rounded-full transition-all duration-700"
                  style={{
                    width: `${Math.min(summary.average_open_rate || 0, 100)}%`,
                  }}
                />
              </div>
              <span className="text-sm font-bold text-blue-600 w-14 text-right">
                {pct(summary.average_open_rate)}
              </span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-gray-500 w-24 flex-shrink-0">
                {t('analytics.clickRate')}
              </span>
              <div className="flex-1 bg-purple-100 rounded-full h-2 overflow-hidden">
                <div
                  className="bg-purple-500 h-2 rounded-full transition-all duration-700"
                  style={{
                    width: `${Math.min(summary.average_click_rate || 0, 100)}%`,
                  }}
                />
              </div>
              <span className="text-sm font-bold text-purple-600 w-14 text-right">
                {pct(summary.average_click_rate)}
              </span>
            </div>
          </div>
          <p className="text-xs text-gray-400 mt-3">
            Based on {fmt(summary.total_campaigns)} campaign
            {summary.total_campaigns !== 1 ? "s" : ""} in the last {days} days.
          </p>
        </div>
      )}

      {/* Tab card */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="flex border-b border-gray-200">
          {[
            {
              key: "campaigns",
              label: "📢 Campaigns",
              count: campaigns.length,
            },
            {
              key: "ab_tests",
              label: "🧪 A/B Winner Sends",
              count: abTests.length,
            },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-6 py-3.5 text-sm font-semibold border-b-2 -mb-px transition-colors ${
                activeTab === tab.key
                  ? "border-blue-600 text-blue-700 bg-blue-50"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50"
              }`}
            >
              {tab.label}
              {tab.count > 0 && (
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-bold ${
                    activeTab === tab.key
                      ? "bg-blue-100 text-blue-700"
                      : "bg-gray-100 text-gray-500"
                  }`}
                >
                  {tab.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Campaigns tab */}
        {activeTab === "campaigns" &&
          (campaigns.length === 0 ? (
            <div className="py-16 text-center">
              <p className="text-3xl mb-2">📭</p>
              <p className="text-sm text-gray-500 mb-1">
                No campaigns in the last {days} days
              </p>
              <Link
                to="/campaigns/create"
                className="text-sm text-blue-600 hover:underline"
              >
                Create your first campaign →
              </Link>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-100">
                    <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Campaign
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      {t('analytics.totalSent')}
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-40">
                      {t('analytics.openRate')}
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-40">
                      {t('analytics.clickRate')}
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Date
                    </th>
                    <th className="px-4 py-3 w-16" />
                  </tr>
                </thead>
                <tbody>
                  {campaigns.map((c) => (
                    <CampaignRow key={c._id} campaign={c} formatDate={formatDate} />
                  ))}
                </tbody>
              </table>
            </div>
          ))}

        {/* AB Winner Sends tab */}
        {activeTab === "ab_tests" &&
          (loadingAB ? (
            <div className="py-12 text-center">
              <div className="inline-flex items-center gap-2 text-gray-400 text-sm">
                <div className="animate-spin h-4 w-4 border-2 border-gray-300 border-t-violet-500 rounded-full" />
                Loading A/B test analytics…
              </div>
            </div>
          ) : abTests.length === 0 ? (
            <div className="py-16 text-center">
              <p className="text-3xl mb-2">🧪</p>
              <p className="text-sm text-gray-500 mb-1">
                No completed A/B tests yet
              </p>
              <Link
                to="/ab-testing"
                className="text-sm text-violet-600 hover:underline"
              >
                Go to A/B Testing →
              </Link>
            </div>
          ) : (
            <>
              {/* AB aggregate mini-stats */}
              <div className="px-5 py-4 border-b border-gray-100 grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="text-center">
                  <p className="text-xl font-bold text-violet-700">
                    {fmt(abTests.length)}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    Completed Tests
                  </p>
                </div>
                <div className="text-center">
                  <p className="text-xl font-bold text-green-700">
                    {fmt(abTotalSent)}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    Winner Emails Sent
                  </p>
                </div>
                <div className="text-center">
                  <p className="text-xl font-bold text-blue-700">
                    {pct(abAvgOpen)}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">{t('analytics.openRate')}</p>
                </div>
                <div className="text-center">
                  <p className="text-xl font-bold text-pink-700">
                    {pct(abAvgClick)}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">{t('analytics.clickRate')}</p>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-100">
                      <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Test Name
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Winner
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Send Status
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Sent
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-40">
                        Open Rate
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-40">
                        Click Rate
                      </th>
                      <th className="px-4 py-3 w-24" />
                    </tr>
                  </thead>
                  <tbody>
                    {abTests.map((t) => (
                      <ABWinnerRow key={t._id} test={t} />
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="px-5 py-3 border-t border-gray-100 bg-gray-50 flex items-center justify-between">
                <p className="text-xs text-gray-400">
                  Open/click rates reflect winner send phase only — A/B sample
                  emails excluded.
                </p>
                <Link
                  to="/ab-testing"
                  className="text-xs text-violet-600 font-medium hover:underline"
                >
                  Manage A/B Tests →
                </Link>
              </div>
            </>
          ))}
      </div>
    </div>
  );
}
