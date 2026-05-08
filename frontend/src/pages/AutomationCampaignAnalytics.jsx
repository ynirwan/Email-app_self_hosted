import { useState, useEffect, useCallback, useMemo } from "react";
import {
  ArrowLeft, BarChart3, Mail, Users, Activity,
  RefreshCw, ChevronLeft, ChevronRight, AlertCircle,
  CheckCircle, Clock, XCircle, SkipForward
} from "lucide-react";
import { useParams, useNavigate } from "react-router-dom";
import API from "../api";

// ─── helpers ────────────────────────────────────────────────────────────────

const fmt = (n) => Number(n ?? 0).toLocaleString();

function relTime(iso) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return `${Math.floor(diff / 86_400_000)}d ago`;
}

function fmtDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function Spinner() {
  return (
    <div className="flex items-center justify-center py-20 gap-2 text-gray-400">
      <div className="animate-spin h-5 w-5 border-2 border-gray-300 border-t-blue-500 rounded-full" />
      Loading…
    </div>
  );
}

function EmptyState({ icon: Icon = BarChart3, message }) {
  return (
    <div className="py-16 text-center text-gray-400">
      <Icon size={40} className="mx-auto mb-3 opacity-40" />
      <p className="text-sm">{message}</p>
    </div>
  );
}

const STATUS_CONFIG = {
  sent:        { icon: CheckCircle, color: "text-green-600",  bg: "bg-green-50",  label: "Sent" },
  delivered:   { icon: CheckCircle, color: "text-green-600",  bg: "bg-green-50",  label: "Delivered" },
  failed:      { icon: XCircle,     color: "text-red-600",    bg: "bg-red-50",    label: "Failed" },
  skipped:     { icon: SkipForward, color: "text-yellow-600", bg: "bg-yellow-50", label: "Skipped" },
  in_progress: { icon: Clock,       color: "text-blue-600",   bg: "bg-blue-50",   label: "Active" },
  completed:   { icon: CheckCircle, color: "text-green-600",  bg: "bg-green-50",  label: "Completed" },
  running:     { icon: Activity,    color: "text-blue-600",   bg: "bg-blue-50",   label: "Running" },
};

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || { icon: AlertCircle, color: "text-gray-500", bg: "bg-gray-50", label: status };
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.bg} ${cfg.color}`}>
      <Icon size={10} />
      {cfg.label}
    </span>
  );
}

function Pagination({ page, pages, onPage }) {
  if (pages <= 1) return null;
  return (
    <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-gray-100">
      <button
        onClick={() => onPage(page - 1)} disabled={page <= 1}
        className="p-1.5 rounded border border-gray-200 disabled:opacity-40 hover:bg-gray-50"
      >
        <ChevronLeft size={14} />
      </button>
      <span className="text-xs text-gray-500">Page {page} of {pages}</span>
      <button
        onClick={() => onPage(page + 1)} disabled={page >= pages}
        className="p-1.5 rounded border border-gray-200 disabled:opacity-40 hover:bg-gray-50"
      >
        <ChevronRight size={14} />
      </button>
    </div>
  );
}

// ─── Tab: Overview ──────────────────────────────────────────────────────────

function OverviewTab({ analytics }) {
  if (!analytics) return <EmptyState message="No analytics data available." />;

  const cards = [
    { label: "Emails Sent",          value: fmt(analytics.emails_sent),          color: "text-blue-700",   bg: "bg-blue-50   border-blue-200" },
    { label: "Emails Opened",        value: fmt(analytics.emails_opened),        color: "text-green-700",  bg: "bg-green-50  border-green-200" },
    { label: "Emails Clicked",       value: fmt(analytics.emails_clicked),       color: "text-purple-700", bg: "bg-purple-50 border-purple-200" },
    { label: "Open Rate",            value: `${(analytics.open_rate || 0).toFixed(1)}%`,   color: "text-teal-700",   bg: "bg-teal-50   border-teal-200" },
    { label: "Click Rate",           value: `${(analytics.click_rate || 0).toFixed(1)}%`,  color: "text-orange-700", bg: "bg-orange-50 border-orange-200" },
    { label: "Subscribers Entered",  value: fmt(analytics.subscribers_entered),  color: "text-indigo-700", bg: "bg-indigo-50 border-indigo-200" },
    { label: "Subscribers Completed",value: fmt(analytics.subscribers_completed),color: "text-green-700",  bg: "bg-green-50  border-green-200" },
    { label: "Total Executions",     value: fmt(analytics.total_executions),     color: "text-gray-700",   bg: "bg-gray-50   border-gray-200" },
    { label: "Completed Executions", value: fmt(analytics.completed_executions), color: "text-green-700",  bg: "bg-green-50  border-green-200" },
    { label: "Failed Executions",    value: fmt(analytics.failed_executions),    color: "text-red-700",    bg: "bg-red-50    border-red-200" },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 p-4">
      {cards.map((c) => (
        <div key={c.label} className={`rounded-xl border p-4 ${c.bg}`}>
          <p className={`text-2xl font-bold tabular-nums ${c.color}`}>{c.value}</p>
          <p className="text-xs text-gray-500 mt-0.5 font-medium">{c.label}</p>
        </div>
      ))}
    </div>
  );
}

// ─── Tab: Steps ─────────────────────────────────────────────────────────────

function StepsTab({ ruleId }) {
  const [steps, setSteps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    API.get(`/automation/rules/${ruleId}/step-stats`)
      .then((res) => setSteps(res?.data?.steps || []))
      .catch(() => setError("Failed to load step data."))
      .finally(() => setLoading(false));
  }, [ruleId]);

  if (loading) return <Spinner />;
  if (error) return <div className="p-4 text-red-600 text-sm">{error}</div>;
  if (!steps.length) return <EmptyState icon={Activity} message="No steps configured for this automation." />;

  return (
    <div className="divide-y divide-gray-100">
      {steps.map((step, idx) => {
        const total = step.emails_sent + step.emails_failed + step.emails_skipped;
        const successPct = total > 0 ? (step.emails_sent / total) * 100 : 0;

        return (
          <div key={step.step_id} className="p-4 hover:bg-gray-50 transition-colors">
            <div className="flex items-start gap-4">
              {/* step number */}
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-100 text-blue-700 text-sm font-bold flex items-center justify-center">
                {idx + 1}
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-gray-900 text-sm capitalize">
                    {(step.step_type || "email").replace(/_/g, " ")} step
                  </span>
                  <span className="px-2 py-0.5 text-xs rounded-full bg-gray-100 text-gray-600">
                    {step.delay_label}
                  </span>
                  {step.template_name && step.template_name !== "—" && (
                    <span className="px-2 py-0.5 text-xs rounded-full bg-purple-100 text-purple-700 truncate max-w-[200px]">
                      📄 {step.template_name}
                    </span>
                  )}
                </div>

                {step.subject_line && (
                  <p className="text-xs text-gray-500 mt-1 truncate max-w-md">
                    Subject: {step.subject_line}
                  </p>
                )}

                {/* stats row */}
                <div className="flex items-center gap-4 mt-2 flex-wrap">
                  <span className="flex items-center gap-1 text-xs text-green-700">
                    <CheckCircle size={11} /> {fmt(step.emails_sent)} sent
                  </span>
                  <span className="flex items-center gap-1 text-xs text-red-600">
                    <XCircle size={11} /> {fmt(step.emails_failed)} failed
                  </span>
                  <span className="flex items-center gap-1 text-xs text-yellow-600">
                    <SkipForward size={11} /> {fmt(step.emails_skipped)} skipped
                  </span>
                  {step.exec_running > 0 && (
                    <span className="flex items-center gap-1 text-xs text-blue-600">
                      <Activity size={11} /> {fmt(step.exec_running)} in queue
                    </span>
                  )}
                </div>

                {/* success bar */}
                {total > 0 && (
                  <div className="mt-2 flex items-center gap-2">
                    <div className="flex-1 bg-gray-100 rounded-full h-1.5 max-w-[160px]">
                      <div
                        className="bg-green-500 h-1.5 rounded-full transition-all"
                        style={{ width: `${successPct}%` }}
                      />
                    </div>
                    <span className="text-xs text-gray-500 tabular-nums">
                      {successPct.toFixed(0)}% success
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Tab: Active Workflows ───────────────────────────────────────────────────

function WorkflowsTab({ ruleId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({ page, limit: 25 });
    if (statusFilter) params.set("status", statusFilter);
    API.get(`/automation/rules/${ruleId}/workflows?${params}`)
      .then((res) => setData(res?.data || res))
      .catch(() => setError("Failed to load workflow data."))
      .finally(() => setLoading(false));
  }, [ruleId, page, statusFilter]);

  useEffect(() => { load(); }, [load]);

  const handleStatusFilter = (s) => { setStatusFilter(s); setPage(1); };

  return (
    <div>
      {/* filter bar */}
      <div className="flex items-center gap-2 p-3 border-b border-gray-100 flex-wrap">
        {["", "in_progress", "completed", "failed"].map((s) => (
          <button
            key={s}
            onClick={() => handleStatusFilter(s)}
            className={`px-3 py-1 text-xs rounded-full font-medium transition-colors ${
              statusFilter === s
                ? "bg-blue-600 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {s === "" ? "All" : s === "in_progress" ? "Active" : s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
        {data && (
          <span className="ml-auto text-xs text-gray-400">{fmt(data.total)} total</span>
        )}
      </div>

      {loading ? (
        <Spinner />
      ) : error ? (
        <div className="p-4 text-red-600 text-sm">{error}</div>
      ) : !data?.workflows?.length ? (
        <EmptyState icon={Users} message="No workflows found." />
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wider">
                  <th className="px-4 py-2.5 text-left">Subscriber</th>
                  <th className="px-4 py-2.5 text-left">Status</th>
                  <th className="px-4 py-2.5 text-center">Steps</th>
                  <th className="px-4 py-2.5 text-center">Emails Sent</th>
                  <th className="px-4 py-2.5 text-left">Started</th>
                  <th className="px-4 py-2.5 text-left">Completed</th>
                  <th className="px-4 py-2.5 text-left">Error</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {data.workflows.map((w) => (
                  <tr key={w.workflow_instance_id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-900 text-xs">{w.subscriber_email}</p>
                      {w.subscriber_name && (
                        <p className="text-xs text-gray-400">{w.subscriber_name}</p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={w.status} />
                    </td>
                    <td className="px-4 py-3 text-center text-xs tabular-nums text-gray-600">
                      {w.completed_steps} / {w.total_steps}
                    </td>
                    <td className="px-4 py-3 text-center text-xs tabular-nums text-gray-600">
                      {w.emails_sent}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500" title={fmtDate(w.started_at)}>
                      {relTime(w.started_at)}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500" title={fmtDate(w.completed_at)}>
                      {w.completed_at ? relTime(w.completed_at) : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-red-600 max-w-[160px]">
                      {w.error ? (
                        <span className="truncate block" title={w.error}>{w.error}</span>
                      ) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={data.page} pages={data.pages} onPage={setPage} />
        </>
      )}
    </div>
  );
}

// ─── Tab: Email Logs ─────────────────────────────────────────────────────────

function EmailLogsTab({ ruleId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({ page, limit: 50 });
    if (statusFilter) params.set("status", statusFilter);
    API.get(`/automation/rules/${ruleId}/email-logs?${params}`)
      .then((res) => setData(res?.data || res))
      .catch(() => setError("Failed to load email logs."))
      .finally(() => setLoading(false));
  }, [ruleId, page, statusFilter]);

  useEffect(() => { load(); }, [load]);

  const handleStatusFilter = (s) => { setStatusFilter(s); setPage(1); };

  const breakdown = data?.breakdown || {};
  const totalSent = (breakdown.sent || 0) + (breakdown.delivered || 0);
  const totalFailed = breakdown.failed || 0;
  const totalSkipped = breakdown.skipped || 0;

  return (
    <div>
      {/* breakdown bar */}
      {data && (
        <div className="flex items-center gap-3 p-3 border-b border-gray-100 flex-wrap">
          <span className="flex items-center gap-1.5 text-xs text-green-700 font-medium">
            <CheckCircle size={12} /> {fmt(totalSent)} sent
          </span>
          <span className="flex items-center gap-1.5 text-xs text-red-600 font-medium">
            <XCircle size={12} /> {fmt(totalFailed)} failed
          </span>
          <span className="flex items-center gap-1.5 text-xs text-yellow-600 font-medium">
            <SkipForward size={12} /> {fmt(totalSkipped)} skipped
          </span>
          <div className="ml-2 flex items-center gap-1 border-l border-gray-200 pl-2">
            {["", "sent", "failed", "skipped"].map((s) => (
              <button
                key={s}
                onClick={() => handleStatusFilter(s)}
                className={`px-2.5 py-1 text-xs rounded-full font-medium transition-colors ${
                  statusFilter === s
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
              >
                {s === "" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)}
              </button>
            ))}
          </div>
          <span className="ml-auto text-xs text-gray-400">{fmt(data.total)} total</span>
        </div>
      )}

      {loading ? (
        <Spinner />
      ) : error ? (
        <div className="p-4 text-red-600 text-sm">{error}</div>
      ) : !data?.logs?.length ? (
        <EmptyState icon={Mail} message="No email logs found." />
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wider">
                  <th className="px-4 py-2.5 text-left">Recipient</th>
                  <th className="px-4 py-2.5 text-left">Subject</th>
                  <th className="px-4 py-2.5 text-left">Status</th>
                  <th className="px-4 py-2.5 text-left">Provider</th>
                  <th className="px-4 py-2.5 text-left">Sent</th>
                  <th className="px-4 py-2.5 text-left">Error</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {data.logs.map((log) => (
                  <>
                    <tr
                      key={log.log_id}
                      className="hover:bg-gray-50 cursor-pointer"
                      onClick={() => setExpanded(expanded === log.log_id ? null : log.log_id)}
                    >
                      <td className="px-4 py-3">
                        <p className="text-xs font-medium text-gray-900">{log.subscriber_email}</p>
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-600 max-w-[180px]">
                        <span className="truncate block">{log.subject || "—"}</span>
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={log.latest_status || log.status} />
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-500">
                        {log.provider || "—"}
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-500" title={fmtDate(log.sent_at)}>
                        {log.sent_at ? relTime(log.sent_at) : relTime(log.created_at)}
                      </td>
                      <td className="px-4 py-3 text-xs text-red-600 max-w-[200px]">
                        {log.error_message ? (
                          <span className="truncate block" title={log.error_message}>
                            {log.error_message}
                          </span>
                        ) : "—"}
                      </td>
                    </tr>
                    {expanded === log.log_id && (
                      <tr key={`${log.log_id}-detail`} className="bg-gray-50">
                        <td colSpan={6} className="px-6 py-3">
                          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
                            <div>
                              <span className="text-gray-400 uppercase tracking-wide text-[10px]">Message ID</span>
                              <p className="font-mono text-gray-700 break-all mt-0.5">
                                {log.message_id || "—"}
                              </p>
                            </div>
                            <div>
                              <span className="text-gray-400 uppercase tracking-wide text-[10px]">Workflow</span>
                              <p className="font-mono text-gray-700 break-all mt-0.5">
                                {log.workflow_instance_id || "—"}
                              </p>
                            </div>
                            <div>
                              <span className="text-gray-400 uppercase tracking-wide text-[10px]">Step</span>
                              <p className="font-mono text-gray-700 break-all mt-0.5">
                                {log.step_id || "—"}
                              </p>
                            </div>
                            {log.error_message && (
                              <div className="col-span-full">
                                <span className="text-red-400 uppercase tracking-wide text-[10px]">Full Error</span>
                                <p className="text-red-700 mt-0.5 whitespace-pre-wrap break-words">
                                  {log.error_message}
                                </p>
                              </div>
                            )}
                            <div>
                              <span className="text-gray-400 uppercase tracking-wide text-[10px]">Created</span>
                              <p className="text-gray-700 mt-0.5">{fmtDate(log.created_at)}</p>
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
          <Pagination page={data.page} pages={data.pages} onPage={setPage} />
        </>
      )}
    </div>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

const TABS = [
  { id: "overview",   label: "Overview",        icon: BarChart3 },
  { id: "steps",      label: "Steps",           icon: Activity },
  { id: "workflows",  label: "Subscriber Runs", icon: Users },
  { id: "email_logs", label: "Email Logs",       icon: Mail },
];

export default function AutomationCampaignAnalytics() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [analytics, setAnalytics] = useState(null);
  const [ruleName, setRuleName] = useState("");
  const [ruleStatus, setRuleStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [refreshKey, setRefreshKey] = useState(0);

  const fetchOverview = useCallback(async () => {
    if (!id) return;
    try {
      setLoading(true); setError(null);
      const [analyticsRes, ruleRes] = await Promise.allSettled([
        API.get(`/automation/rules/${id}/analytics`),
        API.get(`/automation/rules/${id}`),
      ]);
      if (analyticsRes.status === "fulfilled") {
        const d = analyticsRes.value?.data || analyticsRes.value;
        setAnalytics(d);
        setRuleName(d.rule_name || "Automation");
      }
      if (ruleRes.status === "fulfilled") {
        const r = ruleRes.value?.data || ruleRes.value;
        setRuleStatus(r.status || "");
        if (!ruleName) setRuleName(r.name || "Automation");
      }
    } catch {
      setError("Failed to load automation details.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { fetchOverview(); }, [fetchOverview, refreshKey]);

  const handleRefresh = () => setRefreshKey((k) => k + 1);

  if (loading) return <Spinner />;

  if (error) return (
    <div className="space-y-4 p-4">
      <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm flex items-center justify-between">
        <span>⚠️ {error}</span>
        <button onClick={fetchOverview} className="underline ml-3">Retry</button>
      </div>
      <button onClick={() => navigate("/automation")}
        className="flex items-center gap-2 px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600">
        <ArrowLeft size={14} /> Back to Automations
      </button>
    </div>
  );

  return (
    <div className="space-y-5">
      {/* header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate("/automation")}
            className="p-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500"
          >
            <ArrowLeft size={16} />
          </button>
          <div>
            <h1 className="text-lg font-semibold text-gray-900 leading-tight">
              {ruleName || "Automation Analytics"}
            </h1>
            <div className="flex items-center gap-2 mt-0.5">
              {ruleStatus && (
                <span className={`px-2 py-0.5 text-xs rounded-full font-medium
                  ${ruleStatus === "active" ? "bg-green-100 text-green-700" :
                    ruleStatus === "paused" ? "bg-yellow-100 text-yellow-700" :
                    "bg-gray-100 text-gray-600"}`}>
                  {ruleStatus}
                </span>
              )}
              <span className="text-xs text-gray-400">Automation ID: {id}</span>
            </div>
          </div>
        </div>
        <button
          onClick={handleRefresh}
          className="flex items-center gap-2 px-3 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600"
        >
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {/* tabs */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="flex border-b border-gray-100 overflow-x-auto">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-5 py-3.5 text-sm font-medium whitespace-nowrap transition-colors border-b-2
                  ${activeTab === tab.id
                    ? "border-blue-600 text-blue-600 bg-blue-50/40"
                    : "border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50"}`}
              >
                <Icon size={14} />
                {tab.label}
              </button>
            );
          })}
        </div>

        <div className="min-h-[300px]">
          {activeTab === "overview"   && <OverviewTab  analytics={analytics} />}
          {activeTab === "steps"      && <StepsTab     ruleId={id} key={refreshKey} />}
          {activeTab === "workflows"  && <WorkflowsTab ruleId={id} key={refreshKey} />}
          {activeTab === "email_logs" && <EmailLogsTab ruleId={id} key={refreshKey} />}
        </div>
      </div>
    </div>
  );
}
