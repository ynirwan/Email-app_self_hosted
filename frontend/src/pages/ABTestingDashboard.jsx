// frontend/src/pages/ABTestingDashboard.jsx
import { useState, useEffect, useCallback, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useSettings } from "../contexts/SettingsContext";
import API from "../api";

// ── Toast ─────────────────────────────────────────────────────────────────────
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

function ToastStack({ toasts, dismiss }) {
  return (
    <div className="fixed bottom-4 right-4 z-50 space-y-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          onClick={() => dismiss(t.id)}
          className={`cursor-pointer px-4 py-3 rounded-xl text-sm font-medium shadow-lg ${
            t.type === "success"
              ? "bg-green-600 text-white"
              : t.type === "error"
                ? "bg-red-600 text-white"
                : "bg-gray-800 text-white"
          }`}
        >
          {t.type === "success" ? "✓" : t.type === "error" ? "✕" : "ℹ"}{" "}
          {t.message}
        </div>
      ))}
    </div>
  );
}

// ── Status style map ──────────────────────────────────────────────────────────
const STATUS_STYLE = {
  running: "bg-blue-100  text-blue-800",
  completed: "bg-green-100 text-green-800",
  stopped: "bg-gray-100  text-gray-700",
  failed: "bg-red-100   text-red-800",
  draft: "bg-yellow-100 text-yellow-800",
};

// ── Main component ────────────────────────────────────────────────────────────
export default function ABTestingDashboard() {
  const { t, formatDate } = useSettings();
  const [abTests, setAbTests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState({});
  const [resultsModal, setResultsModal] = useState(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const { toasts, show: toast, dismiss } = useToast();
  const navigate = useNavigate();

  const setRowLoading = (id, v) => setActionLoading((p) => ({ ...p, [id]: v }));

  // ── Data fetch ────────────────────────────────────────────────────────────
  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const res = await API.get("/ab-tests");
      setAbTests(res.data.tests || res.data || []);
    } catch {
      setError("Failed to load A/B tests");
      setAbTests([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // ── Actions ───────────────────────────────────────────────────────────────
  const startTest = async (testId, testName) => {
    setRowLoading(testId, "starting");
    try {
      await API.post(`/ab-tests/${testId}/start`);
      toast(`"${testName}" started!`, "success");
      fetchData();
    } catch (err) {
      toast(err.response?.data?.detail || "Failed to start test", "error");
    } finally {
      setRowLoading(testId, null);
    }
  };

  const stopTest = async (testId, testName) => {
    if (!confirm(`Stop "${testName}"?`)) return;
    setRowLoading(testId, "stopping");
    try {
      await API.post(`/ab-tests/${testId}/stop`);
      toast(`"${testName}" stopped`, "success");
      fetchData();
    } catch (err) {
      toast(err.response?.data?.detail || "Failed to stop test", "error");
    } finally {
      setRowLoading(testId, null);
    }
  };

  const deleteTest = async (testId, testName) => {
    if (!confirm(`Delete "${testName}"? This cannot be undone.`)) return;
    setRowLoading(testId, "deleting");
    try {
      await API.delete(`/ab-tests/${testId}`);
      toast(`"${testName}" deleted`, "success");
      fetchData();
    } catch (err) {
      toast(err.response?.data?.detail || "Failed to delete test", "error");
    } finally {
      setRowLoading(testId, null);
    }
  };

  const viewResults = async (testId) => {
    setRowLoading(testId, "loading");
    try {
      const res = await API.get(`/ab-tests/${testId}/results`);
      setResultsModal(res.data);
    } catch (err) {
      toast(err.response?.data?.detail || "Failed to load results", "error");
    } finally {
      setRowLoading(testId, null);
    }
  };

  // ── Derived counts ────────────────────────────────────────────────────────
  const counts = useMemo(
    () => ({
      total: abTests.length,
      running: abTests.filter((t) => t.status === "running").length,
      draft: abTests.filter((t) => t.status === "draft").length,
      completed: abTests.filter((t) => t.status === "completed").length,
      stopped: abTests.filter((t) => t.status === "stopped").length,
    }),
    [abTests],
  );

  // ── Filtered list ─────────────────────────────────────────────────────────
  const filtered = useMemo(() => {
    let list = abTests;
    if (statusFilter) list = list.filter((t) => t.status === statusFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (t) =>
          (t.test_name || "").toLowerCase().includes(q) ||
          (t.test_type || "").toLowerCase().includes(q),
      );
    }
    return list;
  }, [abTests, statusFilter, search]);

  // ── Loading state ─────────────────────────────────────────────────────────
  if (loading)
    return (
      <div className="flex items-center justify-center py-24 gap-3 text-gray-400">
        <div className="animate-spin h-5 w-5 border-2 border-gray-300 border-t-blue-500 rounded-full" />
        Loading A/B tests…
      </div>
    );

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-6">
      <ToastStack toasts={toasts} dismiss={dismiss} />

      {/* Header */}
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-gray-900">🧪 A/B Testing</h2>
        <button
          onClick={() => navigate("/ab-testing/create")}
          className="bg-violet-600 text-white px-5 py-2 rounded-lg hover:bg-violet-700 text-sm font-semibold"
        >
          ✨ {t('abtest.create')}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
          <button onClick={fetchData} className="ml-2 underline text-sm">
            Retry
          </button>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
        {[
          {
            label: "Total",
            value: counts.total,
            bg: "bg-gray-50   border-gray-200",
            color: "text-gray-800",
            pulse: false,
          },
          {
            label: "Running",
            value: counts.running,
            bg: "bg-blue-50   border-blue-200",
            color: "text-blue-800",
            pulse: counts.running > 0,
          },
          {
            label: "Draft",
            value: counts.draft,
            bg: "bg-yellow-50 border-yellow-200",
            color: "text-yellow-700",
            pulse: false,
          },
          {
            label: "Completed",
            value: counts.completed,
            bg: "bg-green-50  border-green-200",
            color: "text-green-700",
            pulse: false,
          },
          {
            label: "Stopped",
            value: counts.stopped,
            bg: "bg-gray-50   border-gray-200",
            color: "text-gray-600",
            pulse: false,
          },
        ].map((s) => (
          <div key={s.label} className={`rounded-xl border p-4 ${s.bg}`}>
            <p
              className={`text-2xl font-bold tabular-nums flex items-center gap-2 ${s.color}`}
            >
              {s.value}
              {s.pulse && (
                <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
              )}
            </p>
            <p className="text-xs font-medium text-gray-500 mt-0.5">
              {t('abtest.variants')}
            </p>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search tests…"
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm w-52 focus:outline-none focus:ring-2 focus:ring-violet-400"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none"
        >
          <option value="">All statuses</option>
          {["draft", "running", "completed", "stopped", "failed"].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700">
            A/B Tests
            {filtered.length !== abTests.length && (
              <span className="ml-2 text-xs font-normal text-gray-400">
                ({filtered.length} of {abTests.length})
              </span>
            )}
          </h2>
        </div>

        {filtered.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-sm text-gray-500">{t('abtest.empty')}</p>
            <button
              onClick={() => {
                setSearch("");
                setStatusFilter("");
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
                    Test Name
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Type
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Lists
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-36">
                    Status
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-20">
                    Sample
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map((test) => {
                  const busy = actionLoading[test._id];

                  // ── NEW: detect provider-error failure ────────────────────
                  const isFailedByError =
                    test.status === "failed" &&
                    test.fail_reason === "provider_error_auto_fail";

                  return (
                    <tr
                      key={test._id}
                      className="hover:bg-gray-50 transition-colors"
                    >
                      {/* Test name */}
                      <td className="px-5 py-3.5 font-medium text-gray-900">
                        {test.test_name}
                      </td>

                      {/* Type */}
                      <td className="px-4 py-3.5">
                        <span className="px-2 py-0.5 bg-gray-100 text-gray-700 rounded text-xs capitalize">
                          {(test.test_type || "").replace("_", " ")}
                        </span>
                      </td>

                      {/* Lists */}
                      <td className="px-4 py-3.5 text-xs text-gray-500 max-w-[120px] truncate">
                        {(test.target_lists || []).join(", ") || "—"}
                      </td>

                      {/* Status — error-aware (CHANGED) */}
                      <td className="px-4 py-3.5">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                            STATUS_STYLE[test.status] || STATUS_STYLE.draft
                          }`}
                        >
                          {test.status === "running" && (
                            <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse" />
                          )}
                          {isFailedByError
                            ? "✕ Failed — Provider Error"
                            : t(`abtest.${test.status}`) || test.status}
                        </span>
                      </td>

                      {/* Sample */}
                      <td className="px-4 py-3.5 text-right tabular-nums text-xs text-gray-600">
                        {formatDate(test.sample_size)}
                      </td>

                      {/* Actions */}
                      <td className="px-4 py-3.5">
                        <div className="flex items-center justify-end gap-1.5 flex-wrap">
                          {/* Edit — draft only */}
                          {test.status === "draft" && (
                            <button
                              onClick={() =>
                                navigate(`/ab-testing/edit/${test._id}`)
                              }
                              className="px-3 py-1.5 text-xs font-medium text-indigo-600 bg-indigo-50 border border-indigo-200 rounded-lg hover:bg-indigo-100"
                            >
                              ✏️ Edit
                            </button>
                          )}

                          {/* Start — draft only */}
                          {test.status === "draft" && (
                            <button
                              onClick={() =>
                                startTest(test._id, test.test_name)
                              }
                              disabled={!!busy}
                              className="px-2.5 py-1.5 text-xs font-medium border border-green-200 rounded-lg hover:bg-green-50 text-green-700 disabled:opacity-50"
                            >
                              {busy === "starting" ? "⏳" : t('abtest.sendWinner')}
                            </button>
                          )}

                          {/* Stop — running only */}
                          {test.status === "running" && (
                            <button
                              onClick={() => stopTest(test._id, test.test_name)}
                              disabled={!!busy}
                              className="px-2.5 py-1.5 text-xs font-medium border border-orange-200 rounded-lg hover:bg-orange-50 text-orange-700 disabled:opacity-50"
                            >
                              {busy === "stopping" ? "⏳" : "Stop"}
                            </button>
                          )}

                          {/* Quick view results — running | completed */}
                          {(test.status === "running" ||
                            test.status === "completed") && (
                            <button
                              onClick={() => viewResults(test._id)}
                              disabled={!!busy}
                              className="px-2.5 py-1.5 text-xs font-medium border border-purple-200 rounded-lg hover:bg-purple-50 text-purple-700 disabled:opacity-50"
                            >
                              {busy === "loading" ? "⏳" : "Quick View"}
                            </button>
                          )}

                          {/* Full report — running | completed | failed (CHANGED: added failed) */}
                          {(test.status === "running" ||
                            test.status === "completed" ||
                            test.status === "failed") && (
                            <Link
                              to={`/ab-tests/${test._id}/results`}
                              className="px-2.5 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600"
                            >
                              {isFailedByError
                                ? "⚠️ View Error"
                                : "Full Report"}
                            </Link>
                          )}

                          {/* Delete */}
                          <button
                            onClick={() => deleteTest(test._id, test.test_name)}
                            disabled={!!busy}
                            className="px-2.5 py-1.5 text-xs font-medium border border-red-200 rounded-lg hover:bg-red-50 text-red-600 disabled:opacity-50"
                          >
                            {busy === "deleting" ? "⏳" : "Delete"}
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

      {/* Quick-view results modal */}
      {resultsModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-3xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b">
              <div>
                <h3 className="text-base font-semibold">
                  {resultsModal.test_name}
                </h3>
                <p className="text-xs text-gray-400">Quick Results Summary</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    const id = resultsModal.test_id;
                    setResultsModal(null);
                    navigate(`/ab-tests/${id}/results`);
                  }}
                  className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 text-sm font-medium"
                >
                  Open Full Report
                </button>
                <button
                  onClick={() => setResultsModal(null)}
                  className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-gray-100 text-gray-500 text-xl"
                >
                  ×
                </button>
              </div>
            </div>

            <div className="p-6 space-y-6">
              {/* Test info */}
              <div className="bg-gray-50 rounded-xl p-4">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  {[
                    ["Status", resultsModal.status],
                    [
                      "Test Type",
                      (resultsModal.test_type || "").replace("_", " "),
                    ],
                    [
                      "Sample",
                      Number(resultsModal.sample_size || 0).toLocaleString(),
                    ],
                    [
                      "Split",
                      `${resultsModal.split_percentage}% / ${100 - resultsModal.split_percentage}%`,
                    ],
                  ].map(([l, v]) => (
                    <div key={l}>
                      <p className="text-gray-500 text-xs">{l}</p>
                      <p className="font-semibold capitalize">{v}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Variant comparison */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {["variant_a", "variant_b"].map((key, i) => {
                  const v = resultsModal.results?.[key] || {};
                  const label =
                    i === 0 ? "Variant A (Control)" : "Variant B (Test)";
                  const isWinner =
                    resultsModal.winner?.winner === (i === 0 ? "A" : "B");
                  return (
                    <div
                      key={key}
                      className={`rounded-xl border-2 p-4 ${isWinner ? "border-green-400 bg-green-50" : "border-gray-200"}`}
                    >
                      <div className="flex items-center justify-between mb-3">
                        <p className="text-sm font-bold text-gray-800">
                          {label}
                        </p>
                        {isWinner && (
                          <span className="bg-green-100 text-green-700 text-xs font-bold px-2 py-0.5 rounded-full">
                            🏆 Winner
                          </span>
                        )}
                      </div>
                      <div className="space-y-1 text-sm">
                        {[
                          ["Sent", v.sent],
                          ["Opened", v.opened],
                          [
                            "Open Rate",
                            v.open_rate != null ? `${v.open_rate}%` : "—",
                          ],
                          ["Clicked", v.clicked],
                          [
                            "Click Rate",
                            v.click_rate != null ? `${v.click_rate}%` : "—",
                          ],
                        ].map(([lbl, val]) => (
                          <div key={lbl} className="flex justify-between">
                            <span className="text-gray-500">{lbl}</span>
                            <span className="font-semibold">{val ?? "—"}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Winner */}
              {resultsModal.winner?.winner && (
                <div className="bg-green-50 border border-green-200 rounded-xl p-4">
                  <p className="font-semibold text-green-800">
                    🏆 Variant {resultsModal.winner.winner} wins
                    {resultsModal.winner.improvement != null && (
                      <span className="ml-2 font-normal text-green-600 text-sm">
                        (+{resultsModal.winner.improvement}% improvement)
                      </span>
                    )}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
