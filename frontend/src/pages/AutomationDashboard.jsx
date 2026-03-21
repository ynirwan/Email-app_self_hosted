import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Plus,
  Play,
  Pause,
  BarChart3,
  Trash2,
  Edit,
  Copy,
  Clock,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import API from "../api";

function useToast() {
  const [toasts, setToasts] = useState([]);
  const show = useCallback((message, type = "info") => {
    const id = Date.now();
    setToasts((p) => [...p, { id, message, type }]);
    setTimeout(() => setToasts((p) => p.filter((t) => t.id !== id)), 4000);
  }, []);
  const dismiss = (id) => setToasts((p) => p.filter((t) => t.id !== id));
  return { toasts, show, dismiss };
}

function ToastContainer({ toasts, dismiss }) {
  return (
    <div className="fixed top-4 right-4 z-50 space-y-2 pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          onClick={() => dismiss(t.id)}
          className={`pointer-events-auto flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg text-sm font-medium cursor-pointer max-w-sm
            ${t.type === "success" ? "bg-green-600 text-white" : t.type === "error" ? "bg-red-600 text-white" : "bg-gray-800 text-white"}`}
        >
          {t.type === "success" ? "✓" : t.type === "error" ? "✕" : "ℹ"}{" "}
          {t.message}
        </div>
      ))}
    </div>
  );
}

const RateBar = ({ value, max = 60, color = "bg-blue-500" }) => (
  <div className="flex items-center gap-2">
    <div className="flex-1 bg-gray-100 rounded-full h-1.5 max-w-[60px]">
      <div
        className={`${color} h-1.5 rounded-full`}
        style={{ width: `${Math.min((value / max) * 100, 100)}%` }}
      />
    </div>
    <span className="text-xs tabular-nums text-gray-700 w-10">
      {value.toFixed(1)}%
    </span>
  </div>
);

const STATUS_STYLE = {
  active: "bg-green-100 text-green-800",
  paused: "bg-yellow-100 text-yellow-800",
  draft: "bg-gray-100  text-gray-700",
};

export default function AutomationDashboard() {
  const navigate = useNavigate();
  const [automations, setAutomations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState({});
  const [filterStatus, setFilterStatus] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const { toasts, show: toast, dismiss } = useToast();

  const setRowBusy = (id, v) => setActionLoading((p) => ({ ...p, [id]: v }));

  const fetchAutomations = useCallback(async () => {
    try {
      setLoading(true);
      const response = await API.get("/automation/rules");
      const data = response?.data?.rules || response?.data || [];
      setAutomations(Array.isArray(data) ? data : []);
    } catch {
      toast("Failed to load automations", "error");
      setAutomations([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAutomations();
  }, [fetchAutomations]);

  const toggleAutomation = async (id, name, currentStatus) => {
    const newStatus = currentStatus === "active" ? "paused" : "active";
    setRowBusy(id, "toggle");
    try {
      await API.post(`/automation/rules/${id}/status`, { status: newStatus });
      toast(
        `"${name}" ${newStatus === "active" ? "activated" : "paused"}`,
        "success",
      );
      fetchAutomations();
    } catch (err) {
      toast(err.response?.data?.detail || "Failed to update status", "error");
    } finally {
      setRowBusy(id, null);
    }
  };

  const duplicateAutomation = async (automation) => {
    setRowBusy(automation.id, "dup");
    try {
      const payload = {
        ...automation,
        name: `${automation.name} (Copy)`,
        active: false,
        status: "draft",
      };
      [
        "id",
        "_id",
        "created_at",
        "updated_at",
        "emails_sent",
        "open_rate",
        "click_rate",
      ].forEach((k) => delete payload[k]);
      await API.post("/automation/rules", payload);
      toast(`"${automation.name}" duplicated as draft`, "success");
      fetchAutomations();
    } catch {
      toast("Failed to duplicate automation", "error");
    } finally {
      setRowBusy(automation.id, null);
    }
  };

  const deleteAutomation = async (id, name) => {
    if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
    setRowBusy(id, "delete");
    try {
      await API.delete(`/automation/rules/${id}`);
      toast(`"${name}" deleted`, "success");
      fetchAutomations();
    } catch {
      toast("Failed to delete automation", "error");
    } finally {
      setRowBusy(id, null);
    }
  };

  const stats = useMemo(
    () => ({
      total: automations.length,
      active: automations.filter((a) => a.status === "active").length,
      paused: automations.filter((a) => a.status === "paused").length,
      draft: automations.filter((a) => a.status === "draft").length,
      totalSent: automations.reduce((s, a) => s + (a.emails_sent || 0), 0),
      avgOpen:
        automations.length > 0
          ? automations.reduce((s, a) => s + (a.open_rate || 0), 0) /
            automations.length
          : 0,
      avgClick:
        automations.length > 0
          ? automations.reduce((s, a) => s + (a.click_rate || 0), 0) /
            automations.length
          : 0,
    }),
    [automations],
  );

  const filtered = useMemo(() => {
    let list = automations;
    if (filterStatus !== "all")
      list = list.filter((a) => a.status === filterStatus);
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(
        (a) =>
          (a.name || "").toLowerCase().includes(q) ||
          (a.trigger || "").toLowerCase().includes(q),
      );
    }
    return list;
  }, [automations, filterStatus, searchQuery]);

  if (loading)
    return (
      <div className="flex items-center justify-center py-24 gap-3 text-gray-400">
        <div className="animate-spin h-5 w-5 border-2 border-gray-300 border-t-blue-500 rounded-full" />
        Loading automations…
      </div>
    );

  return (
    <div className="space-y-6">
      <ToastContainer toasts={toasts} dismiss={dismiss} />

      {/* action bar */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <button
          onClick={() => navigate("/automation/create")}
          className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus size={16} /> Create Automation
        </button>
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate("/automation/analytics")}
            className="flex items-center gap-2 px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600"
          >
            <BarChart3 size={14} /> Analytics
          </button>
          <button
            onClick={fetchAutomations}
            className="px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600"
          >
            🔄 Refresh
          </button>
        </div>
      </div>

      {/* stat cards — consistent style with rest of app */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        {[
          {
            label: "Total",
            value: stats.total,
            bg: "bg-blue-50   border-blue-200",
            color: "text-blue-700",
          },
          {
            label: "Active",
            value: stats.active,
            bg: "bg-green-50  border-green-200",
            color: "text-green-700",
            pulse: stats.active > 0,
          },
          {
            label: "Paused",
            value: stats.paused,
            bg: "bg-yellow-50 border-yellow-200",
            color: "text-yellow-700",
          },
          {
            label: "Draft",
            value: stats.draft,
            bg: "bg-gray-50   border-gray-200",
            color: "text-gray-600",
          },
          {
            label: "Emails Sent",
            value: stats.totalSent.toLocaleString(),
            bg: "bg-purple-50 border-purple-200",
            color: "text-purple-700",
          },
          {
            label: "Avg Open",
            value: `${stats.avgOpen.toFixed(1)}%`,
            bg: "bg-teal-50   border-teal-200",
            color: "text-teal-700",
          },
          {
            label: "Avg Click",
            value: `${stats.avgClick.toFixed(1)}%`,
            bg: "bg-orange-50 border-orange-200",
            color: "text-orange-700",
          },
        ].map((s) => (
          <div key={s.label} className={`rounded-xl border p-4 ${s.bg}`}>
            <p
              className={`text-2xl font-bold tabular-nums flex items-center gap-1.5 ${s.color}`}
            >
              {s.value}
              {s.pulse && (
                <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
              )}
            </p>
            <p className="text-xs font-medium text-gray-500 mt-0.5">
              {s.label}
            </p>
          </div>
        ))}
      </div>

      {/* table — filters merged into toolbar */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700">
            Automations
            {filtered.length !== automations.length && (
              <span className="ml-2 text-xs font-normal text-gray-400">
                ({filtered.length} of {automations.length})
              </span>
            )}
          </h2>
          <div className="flex items-center gap-2 flex-wrap">
            {/* status filter tabs */}
            <div className="flex border border-gray-200 rounded-lg overflow-hidden text-xs font-medium">
              {[
                { value: "all", label: `All (${stats.total})` },
                { value: "active", label: `Active (${stats.active})` },
                { value: "paused", label: `Paused (${stats.paused})` },
                { value: "draft", label: `Draft (${stats.draft})` },
              ].map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setFilterStatus(opt.value)}
                  className={`px-3 py-1.5 transition-colors ${filterStatus === opt.value ? "bg-blue-600 text-white" : "text-gray-600 hover:bg-gray-50"}`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            {/* search */}
            <div className="relative">
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs">
                🔍
              </span>
              <input
                type="text"
                placeholder="Search…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-7 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 w-44"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-300 hover:text-gray-500 text-xs"
                >
                  ✕
                </button>
              )}
            </div>
          </div>
        </div>

        {automations.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-3xl mb-2">⚡</p>
            <p className="text-sm font-medium text-gray-700 mb-1">
              No automations yet
            </p>
            <p className="text-xs text-gray-400 mb-4">
              Create your first automation to engage subscribers automatically
            </p>
            <button
              onClick={() => navigate("/automation/create")}
              className="px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700"
            >
              Create Automation
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-sm text-gray-500">
              No automations match your filters
            </p>
            <button
              onClick={() => {
                setSearchQuery("");
                setFilterStatus("all");
              }}
              className="text-xs text-blue-600 mt-2 hover:underline"
            >
              Clear filters
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Name
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Trigger
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-24">
                    Status
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-16">
                    Steps
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-20">
                    Sent
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-40">
                    <span className="text-green-600">Open</span> /{" "}
                    <span className="text-purple-600">Click</span>
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map((a) => {
                  const busy = actionLoading[a.id];
                  return (
                    <tr
                      key={a.id}
                      className="hover:bg-gray-50 transition-colors"
                    >
                      <td className="px-5 py-3.5">
                        <p className="font-medium text-gray-900 truncate max-w-[180px]">
                          {a.name}
                        </p>
                        <p className="text-xs text-gray-400 flex items-center gap-1 mt-0.5">
                          <Clock size={10} />
                          {new Date(a.created_at).toLocaleDateString()}
                        </p>
                      </td>
                      <td className="px-4 py-3.5">
                        <span className="px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-800 capitalize whitespace-nowrap">
                          {(a.trigger || "unknown").replace(/_/g, " ")}
                        </span>
                      </td>
                      <td className="px-4 py-3.5">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLE[a.status] || STATUS_STYLE.draft}`}
                        >
                          {a.status === "active" && (
                            <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
                          )}
                          {a.status}
                        </span>
                      </td>
                      <td className="px-4 py-3.5 text-right text-xs tabular-nums text-gray-600">
                        {a.steps?.length || 0}
                      </td>
                      <td className="px-4 py-3.5 text-right text-xs tabular-nums font-medium text-gray-700">
                        {(a.emails_sent || 0).toLocaleString()}
                      </td>
                      <td className="px-4 py-3.5 space-y-1.5">
                        <RateBar
                          value={a.open_rate || 0}
                          color="bg-green-500"
                        />
                        <RateBar
                          value={a.click_rate || 0}
                          color="bg-purple-500"
                        />
                      </td>
                      <td className="px-4 py-3.5">
                        <div className="flex items-center justify-end gap-1.5 flex-wrap">
                          <button
                            onClick={() =>
                              toggleAutomation(a.id, a.name, a.status)
                            }
                            disabled={!!busy}
                            className={`px-2.5 py-1.5 text-xs font-medium border rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1
                              ${a.status === "active" ? "border-yellow-200 hover:bg-yellow-50 text-yellow-700" : "border-green-200 hover:bg-green-50 text-green-700"}`}
                          >
                            {busy === "toggle" ? (
                              "⏳"
                            ) : a.status === "active" ? (
                              <>
                                <Pause size={11} />
                                Pause
                              </>
                            ) : (
                              <>
                                <Play size={11} />
                                Activate
                              </>
                            )}
                          </button>
                          <button
                            onClick={() => navigate(`/automation/edit/${a.id}`)}
                            className="px-2.5 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600 flex items-center gap-1"
                          >
                            <Edit size={11} />
                            Edit
                          </button>
                          <button
                            onClick={() =>
                              navigate(`/automation/analytics/${a.id}`)
                            }
                            className="px-2.5 py-1.5 text-xs font-medium border border-purple-200 rounded-lg hover:bg-purple-50 text-purple-700 flex items-center gap-1"
                          >
                            <BarChart3 size={11} />
                            Stats
                          </button>
                          <button
                            onClick={() => duplicateAutomation(a)}
                            disabled={!!busy}
                            className="px-2.5 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600 disabled:opacity-50 flex items-center gap-1"
                          >
                            {busy === "dup" ? (
                              "⏳"
                            ) : (
                              <>
                                <Copy size={11} />
                                Clone
                              </>
                            )}
                          </button>
                          <button
                            onClick={() => deleteAutomation(a.id, a.name)}
                            disabled={!!busy}
                            className="px-2.5 py-1.5 text-xs font-medium border border-red-200 rounded-lg hover:bg-red-50 text-red-600 disabled:opacity-50 flex items-center gap-1"
                          >
                            {busy === "delete" ? (
                              "⏳"
                            ) : (
                              <>
                                <Trash2 size={11} />
                                Delete
                              </>
                            )}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
