import { useState, useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import API from "../api";

// ─── helpers ─────────────────────────────────────────────────
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

const STATUS_STYLE = {
  completed: "bg-green-100 text-green-700",
  sending: "bg-blue-100  text-blue-700",
  scheduled: "bg-purple-100 text-purple-700",
  paused: "bg-orange-100 text-orange-700",
  stopped: "bg-gray-100  text-gray-600",
  failed: "bg-red-100   text-red-700",
  draft: "bg-yellow-100 text-yellow-700",
};

// ─── RateBar ─────────────────────────────────────────────────
function RateBar({ value, max = 60, colorClass = "bg-blue-500" }) {
  const w = Math.min(Math.max((value / max) * 100, 0), 100);
  return (
    <div className="flex items-center gap-2 min-w-[90px]">
      <div className="flex-1 bg-gray-100 rounded-full h-1.5 overflow-hidden">
        <div
          className={`h-1.5 rounded-full ${colorClass}`}
          style={{ width: `${w}%` }}
        />
      </div>
      <span className="text-xs tabular-nums font-medium w-10 text-right">
        {pct(value)}
      </span>
    </div>
  );
}

// ─── SummaryCard ─────────────────────────────────────────────
function SummaryCard({
  label,
  value,
  sub,
  icon,
  valueColor = "text-gray-900",
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-medium text-gray-500">{label}</p>
        <span className="text-xl">{icon}</span>
      </div>
      <p className={`text-2xl font-bold tabular-nums ${valueColor}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

// ─── SortButton ──────────────────────────────────────────────
function SortButton({ col, sortCol, sortDir, onSort, children }) {
  const active = sortCol === col;
  return (
    <button
      onClick={() => onSort(col)}
      className="flex items-center gap-1 text-xs font-medium text-gray-500 uppercase tracking-wider hover:text-gray-800 transition-colors group"
    >
      {children}
      <span
        className={`text-gray-300 group-hover:text-gray-500 ${active ? "text-gray-700" : ""}`}
      >
        {active ? (sortDir === "asc" ? "↑" : "↓") : "↕"}
      </span>
    </button>
  );
}

// ─── Main ────────────────────────────────────────────────────
export default function Analytics() {
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dateRange, setDateRange] = useState(30);
  const [search, setSearch] = useState("");
  const [sortCol, setSortCol] = useState("created_at");
  const [sortDir, setSortDir] = useState("desc");
  const [showAllMetrics, setShowAllMetrics] = useState(false);

  useEffect(() => {
    fetchData();
  }, [dateRange]);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await API.get(`/analytics/dashboard?days=${dateRange}`);
      setDashboardData(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load analytics");
    } finally {
      setLoading(false);
    }
  };

  const handleSort = (col) => {
    if (sortCol === col) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortCol(col);
      setSortDir("desc");
    }
  };

  // ── derived data ──────────────────────────────────────────
  const { summary, campaigns = [], date_range } = dashboardData || {};

  // exclude drafts and failed silently — now we tell the user
  const allCampaigns = campaigns;
  const excludedCount = allCampaigns.filter(
    (c) => c.status === "draft" || c.status === "failed",
  ).length;
  const baseCampaigns = allCampaigns.filter(
    (c) => c.status !== "draft" && c.status !== "failed",
  );

  const filtered = useMemo(() => {
    let list = [...baseCampaigns];

    // search
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (c) =>
          (c.title || "").toLowerCase().includes(q) ||
          (c.subject || "").toLowerCase().includes(q),
      );
    }

    // sort
    list.sort((a, b) => {
      let av, bv;
      switch (sortCol) {
        case "sent":
          av = a.analytics?.total_sent || 0;
          bv = b.analytics?.total_sent || 0;
          break;
        case "open_rate":
          av = a.analytics?.open_rate || 0;
          bv = b.analytics?.open_rate || 0;
          break;
        case "click_rate":
          av = a.analytics?.click_rate || 0;
          bv = b.analytics?.click_rate || 0;
          break;
        case "bounce_rate":
          av = a.analytics?.bounce_rate || 0;
          bv = b.analytics?.bounce_rate || 0;
          break;
        case "unsub_rate":
          av = a.analytics?.unsubscribe_rate || 0;
          bv = b.analytics?.unsubscribe_rate || 0;
          break;
        default:
          av = new Date(a.created_at || 0);
          bv = new Date(b.created_at || 0);
      }
      return sortDir === "asc" ? (av > bv ? 1 : -1) : av < bv ? 1 : -1;
    });

    return list;
  }, [baseCampaigns, search, sortCol, sortDir]);

  // ── loading skeleton ──────────────────────────────────────
  if (loading)
    return (
      <div className="space-y-6 animate-pulse">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-24 bg-gray-200 rounded-xl" />
          ))}
        </div>
        <div className="h-64 bg-gray-200 rounded-xl" />
      </div>
    );

  // ── error state ───────────────────────────────────────────
  if (error)
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <span className="text-4xl">⚠️</span>
        <p className="font-semibold text-gray-800">Failed to load analytics</p>
        <p className="text-sm text-gray-500">{error}</p>
        <button
          onClick={fetchData}
          className="px-5 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700"
        >
          Try Again
        </button>
      </div>
    );

  return (
    <div className="space-y-7">
      {/* ── Controls row ── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <p className="text-sm text-gray-500">
            Showing <strong>{baseCampaigns.length}</strong> campaigns
            {date_range && (
              <span>
                {" "}
                · {fmtD(date_range.start_date)} – {fmtD(date_range.end_date)}
              </span>
            )}
          </p>
          {excludedCount > 0 && (
            <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
              {excludedCount} draft/failed excluded
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <select
            value={dateRange}
            onChange={(e) => setDateRange(Number(e.target.value))}
            className="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white"
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={365}>Last year</option>
          </select>
        </div>
      </div>

      {/* ── 6 summary cards ── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <SummaryCard
          label="Campaigns"
          value={fmt(baseCampaigns.length)}
          sub={`of ${fmt(allCampaigns.length)} total`}
          icon="📢"
        />
        <SummaryCard
          label="Emails Sent"
          value={fmt(summary?.total_emails_sent)}
          icon="📤"
          valueColor="text-blue-700"
        />
        <SummaryCard
          label="Total Opens"
          value={fmt(summary?.total_opens)}
          sub="unique opens tracked"
          icon="👁️"
          valueColor="text-green-700"
        />
        <SummaryCard
          label="Total Clicks"
          value={fmt(summary?.total_clicks)}
          sub="link clicks tracked"
          icon="👆"
          valueColor="text-purple-700"
        />
        <SummaryCard
          label="Avg Open Rate"
          value={pct(summary?.average_open_rate)}
          sub="across all campaigns"
          icon="📬"
          valueColor={
            (summary?.average_open_rate || 0) >= 20
              ? "text-green-600"
              : (summary?.average_open_rate || 0) >= 10
                ? "text-yellow-600"
                : "text-red-600"
          }
        />
        <SummaryCard
          label="Avg Click Rate"
          value={pct(summary?.average_click_rate)}
          sub="across all campaigns"
          icon="🖱️"
          valueColor={
            (summary?.average_click_rate || 0) >= 3
              ? "text-purple-600"
              : (summary?.average_click_rate || 0) >= 1
                ? "text-yellow-600"
                : "text-gray-500"
          }
        />
      </div>

      {/* ── Table card ── */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {/* Table toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700">
            Campaign Performance
            {filtered.length !== baseCampaigns.length && (
              <span className="ml-2 text-xs font-normal text-gray-400">
                ({filtered.length} of {baseCampaigns.length} shown)
              </span>
            )}
          </h2>
          <div className="flex items-center gap-2">
            {/* Search */}
            <div className="relative">
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs">
                🔍
              </span>
              <input
                type="text"
                placeholder="Search campaigns…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-7 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 w-44"
              />
            </div>
            {/* Toggle extra columns */}
            <button
              onClick={() => setShowAllMetrics(!showAllMetrics)}
              className="px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors text-gray-600"
              title="Toggle bounce / unsubscribe / delivery columns"
            >
              {showAllMetrics ? "Fewer columns" : "More metrics"}
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                <th className="px-5 py-3 text-left">
                  <SortButton
                    col="created_at"
                    sortCol={sortCol}
                    sortDir={sortDir}
                    onSort={handleSort}
                  >
                    Campaign
                  </SortButton>
                </th>
                <th className="px-4 py-3 text-left w-24">Status</th>
                <th className="px-4 py-3 text-right">
                  <SortButton
                    col="sent"
                    sortCol={sortCol}
                    sortDir={sortDir}
                    onSort={handleSort}
                  >
                    Sent
                  </SortButton>
                </th>
                <th className="px-4 py-3 text-left min-w-[130px]">
                  <SortButton
                    col="open_rate"
                    sortCol={sortCol}
                    sortDir={sortDir}
                    onSort={handleSort}
                  >
                    Open Rate
                  </SortButton>
                </th>
                <th className="px-4 py-3 text-left min-w-[130px]">
                  <SortButton
                    col="click_rate"
                    sortCol={sortCol}
                    sortDir={sortDir}
                    onSort={handleSort}
                  >
                    Click Rate
                  </SortButton>
                </th>
                {showAllMetrics && (
                  <>
                    <th className="px-4 py-3 text-left min-w-[130px]">
                      <SortButton
                        col="bounce_rate"
                        sortCol={sortCol}
                        sortDir={sortDir}
                        onSort={handleSort}
                      >
                        Bounce
                      </SortButton>
                    </th>
                    <th className="px-4 py-3 text-left min-w-[130px]">
                      <SortButton
                        col="unsub_rate"
                        sortCol={sortCol}
                        sortDir={sortDir}
                        onSort={handleSort}
                      >
                        Unsub
                      </SortButton>
                    </th>
                  </>
                )}
                <th className="px-4 py-3 text-right w-20 text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Date
                </th>
                <th className="px-4 py-3 w-16" />
              </tr>
            </thead>

            <tbody className="divide-y divide-gray-50">
              {filtered.length > 0 ? (
                filtered.map((c) => {
                  const a = c.analytics || {};
                  return (
                    <tr
                      key={c._id}
                      className="hover:bg-gray-50 transition-colors"
                    >
                      {/* Campaign name + subject */}
                      <td className="px-5 py-3.5 max-w-[220px]">
                        <p className="font-medium text-gray-900 truncate">
                          {c.title || "Untitled"}
                        </p>
                        <p className="text-xs text-gray-400 truncate mt-0.5">
                          {c.subject || "—"}
                        </p>
                      </td>

                      {/* Status badge */}
                      <td className="px-4 py-3.5">
                        <span
                          className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLE[c.status] || STATUS_STYLE.draft}`}
                        >
                          {c.status || "draft"}
                        </span>
                      </td>

                      {/* Sent */}
                      <td className="px-4 py-3.5 text-right tabular-nums text-gray-700 font-medium">
                        {fmt(a.total_sent || c.sent_count)}
                      </td>

                      {/* Open rate bar */}
                      <td className="px-4 py-3.5">
                        <RateBar
                          value={a.open_rate || 0}
                          max={60}
                          colorClass={
                            (a.open_rate || 0) >= 20
                              ? "bg-green-500"
                              : (a.open_rate || 0) >= 10
                                ? "bg-yellow-400"
                                : "bg-gray-300"
                          }
                        />
                      </td>

                      {/* Click rate bar */}
                      <td className="px-4 py-3.5">
                        <RateBar
                          value={a.click_rate || 0}
                          max={20}
                          colorClass={
                            (a.click_rate || 0) >= 3
                              ? "bg-purple-500"
                              : (a.click_rate || 0) >= 1
                                ? "bg-blue-400"
                                : "bg-gray-300"
                          }
                        />
                      </td>

                      {/* Optional columns */}
                      {showAllMetrics && (
                        <>
                          <td className="px-4 py-3.5">
                            <RateBar
                              value={a.bounce_rate || 0}
                              max={10}
                              colorClass={
                                (a.bounce_rate || 0) > 2
                                  ? "bg-red-500"
                                  : "bg-gray-300"
                              }
                            />
                          </td>
                          <td className="px-4 py-3.5">
                            <RateBar
                              value={a.unsubscribe_rate || 0}
                              max={5}
                              colorClass={
                                (a.unsubscribe_rate || 0) > 0.5
                                  ? "bg-orange-500"
                                  : "bg-gray-300"
                              }
                            />
                          </td>
                        </>
                      )}

                      {/* Date */}
                      <td className="px-4 py-3.5 text-xs text-gray-400 text-right whitespace-nowrap">
                        {fmtD(c.completed_at || c.started_at || c.created_at)}
                      </td>

                      {/* Action */}
                      <td className="px-4 py-3.5 text-right">
                        <Link
                          to={`/analytics/campaign/${c._id}`}
                          className="text-xs font-medium text-blue-600 hover:text-blue-800 hover:underline whitespace-nowrap"
                        >
                          Report →
                        </Link>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td
                    colSpan={showAllMetrics ? 9 : 7}
                    className="py-16 text-center"
                  >
                    {search ? (
                      <>
                        <p className="text-2xl mb-2">🔍</p>
                        <p className="text-sm font-medium text-gray-700">
                          No campaigns match "{search}"
                        </p>
                        <button
                          onClick={() => setSearch("")}
                          className="text-xs text-blue-600 mt-1 hover:underline"
                        >
                          Clear search
                        </button>
                      </>
                    ) : baseCampaigns.length === 0 &&
                      allCampaigns.length > 0 ? (
                      <>
                        <p className="text-2xl mb-2">📅</p>
                        <p className="text-sm font-medium text-gray-700">
                          No campaigns in this date range
                        </p>
                        <p className="text-xs text-gray-400 mt-1">
                          Try extending the date range
                        </p>
                      </>
                    ) : (
                      <>
                        <p className="text-3xl mb-2">📊</p>
                        <p className="text-sm font-medium text-gray-700">
                          No campaigns yet
                        </p>
                        <p className="text-xs text-gray-400 mt-1 mb-4">
                          Create your first campaign to see analytics here
                        </p>
                        <Link
                          to="/campaigns"
                          className="inline-block px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700"
                        >
                          Go to Campaigns
                        </Link>
                      </>
                    )}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
