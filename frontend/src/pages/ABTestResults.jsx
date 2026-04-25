import { useState, useEffect, useRef, useCallback } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
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

// ── Helper: time remaining until auto-declare ──────────────
const getTimeRemaining = (startDate, durationHours) => {
  if (!startDate || !durationHours) return null;
  const endMs = new Date(startDate).getTime() + durationHours * 3600 * 1000;
  const diffMs = endMs - Date.now();
  if (diffMs <= 0)
    return { label: "Expired — winner declaration pending", expired: true };
  const h = Math.floor(diffMs / 3600000);
  const m = Math.floor((diffMs % 3600000) / 60000);
  return { label: `${h}h ${m}m remaining`, expired: false };
};

const _fmt = (n) => Number(n ?? 0).toLocaleString();

function StatBox({ label, value, icon, color, bg }) {
  return (
    <div
      className={`${bg} border border-gray-100 rounded-xl p-4 text-center shadow-sm`}
    >
      <p className="text-lg mb-1">{icon}</p>
      <p className="text-xs text-gray-400 mb-1">{label}</p>
      <p className={`text-xl font-bold tabular-nums ${color}`}>{value}</p>
    </div>
  );
}

// ── WinnerSendSection ──────────────────────────────────────
export function WinnerSendSection({ testId, results, onReload }) {
  const wsStatus = results?.winner_send_status;
  const wsVariant = results?.winner_variant;
  const wsTotal = results?.winner_send_total;
  const wsCount = results?.winner_send_count;

  const [progress, setProgress] = useState(null);
  const [stopping, setStopping] = useState(false);
  const [stopConfirm, setStopConfirm] = useState(false);
  const [stopError, setStopError] = useState(null);
  const pollRef = useRef(null);

  const fetchProgress = useCallback(async () => {
    try {
      const res = await API.get(`/ab-tests/${testId}/winner-send-progress`);
      setProgress(res.data);
      // Stop polling once no longer running
      if (res.data?.status && res.data.status !== "running") {
        clearInterval(pollRef.current);
        onReload?.();
      }
    } catch {
      // ignore transient polling failures
    }
  }, [testId, onReload]);

  useEffect(() => {
    // FIX: Poll whenever winner send is running, not only if wsStatus is "running"
    // wsStatus comes from the test doc; progress endpoint is the live source
    if (wsStatus === "running") {
      fetchProgress();
      pollRef.current = setInterval(fetchProgress, 5000);
    }
    return () => clearInterval(pollRef.current);
  }, [wsStatus, fetchProgress]);

  const handleStop = async () => {
    if (!stopConfirm) {
      setStopConfirm(true);
      return;
    }
    setStopping(true);
    setStopError(null);
    setStopConfirm(false);
    try {
      await API.post(`/ab-tests/${testId}/stop-winner-send`);
      clearInterval(pollRef.current);
      await onReload?.();
    } catch (e) {
      setStopError(e.response?.data?.detail || "Failed to stop winner send.");
    } finally {
      setStopping(false);
    }
  };

  // Only render if there's a winner variant assigned
  if (!wsVariant) return null;

  const displaySent =
    (wsStatus === "running" ? progress?.sent : null) ??
    wsCount ??
    results?.winner_send_sent ??
    0;
  const displayFailed =
    (wsStatus === "running" ? progress?.failed : null) ??
    results?.winner_send_failed ??
    0;
  const displayTotal =
    (wsStatus === "running" ? progress?.total : null) ?? wsTotal ?? null;
  const displayPct =
    (wsStatus === "running" ? progress?.progress_pct : null) ??
    (displayTotal && displayTotal > 0
      ? Math.min(100, Math.round((displaySent / displayTotal) * 100))
      : null);

  const statusColor =
    {
      completed: "border-green-200 bg-green-50",
      running: "border-blue-200 bg-blue-50",
      stopped: "border-orange-200 bg-orange-50",
    }[wsStatus] || "border-gray-200 bg-gray-50";

  const headerColor =
    {
      completed: "bg-green-100/60",
      running: "bg-blue-100/60",
      stopped: "bg-orange-100/60",
    }[wsStatus] || "bg-gray-100/60";

  const badgeColor =
    {
      completed: "bg-green-200 text-green-800",
      running: "bg-blue-200 text-blue-800 animate-pulse",
      stopped: "bg-orange-200 text-orange-800",
    }[wsStatus] || "bg-gray-200 text-gray-700";

  const statusIcon =
    {
      completed: "🏆",
      running: "📤",
      stopped: "⏹️",
    }[wsStatus] || "📬";

  const statusLabel =
    {
      completed: "Send completed successfully",
      running: "Sending in progress...",
      stopped: "Send was stopped",
    }[wsStatus] || "Pending";

  return (
    <div
      className={`rounded-xl border shadow-sm overflow-hidden mt-6 ${statusColor}`}
    >
      <div
        className={`flex items-center justify-between px-5 py-4 ${headerColor}`}
      >
        <div className="flex items-center gap-3">
          <span className="text-xl">{statusIcon}</span>
          <div>
            <h3 className="font-semibold text-gray-900 text-sm">
              Winner Send — Variant {wsVariant}
            </h3>
            <p className="text-xs text-gray-500">{statusLabel}</p>
          </div>
        </div>
        <span
          className={`text-xs font-bold px-3 py-1 rounded-full ${badgeColor}`}
        >
          {wsStatus?.toUpperCase() ?? "PENDING"}
        </span>
      </div>

      <div className="px-5 py-4 space-y-4">
        {/* Progress bar — visible while running */}
        {wsStatus === "running" && (
          <div>
            <div className="flex justify-between text-xs text-gray-500 mb-1">
              <span>Progress</span>
              <span>
                {displayPct != null ? `${displayPct}%` : "Calculating..."}
                {displayTotal
                  ? ` — ${_fmt(displaySent)} / ${_fmt(displayTotal)}`
                  : ""}
              </span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2.5 overflow-hidden">
              <div
                className="bg-blue-500 h-2.5 rounded-full transition-all duration-500"
                style={{ width: `${displayPct ?? 0}%` }}
              />
            </div>
          </div>
        )}

        {/* Stat boxes */}
        <div className="grid grid-cols-3 gap-4">
          <StatBox
            label="Sent"
            value={_fmt(displaySent)}
            icon="✅"
            color="text-green-600"
            bg="bg-white"
          />
          <StatBox
            label="Failed"
            value={_fmt(displayFailed)}
            icon="❌"
            color="text-red-500"
            bg="bg-white"
          />
          <StatBox
            label={wsStatus === "completed" ? "Total" : "Remaining"}
            value={
              displayTotal
                ? _fmt(Math.max(0, displayTotal - displaySent - displayFailed))
                : "—"
            }
            icon={wsStatus === "completed" ? "📊" : "⏳"}
            color="text-gray-600"
            bg="bg-white"
          />
        </div>

        {stopError && (
          <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            ⚠️ {stopError}
          </div>
        )}

        <div className="flex flex-wrap gap-2 pt-1">
          {/* Stop controls — only when running */}
          {wsStatus === "running" && (
            <>
              {stopConfirm ? (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-orange-600 font-medium">
                    Confirm stop?
                  </span>
                  <button
                    onClick={handleStop}
                    disabled={stopping}
                    className="px-3 py-1.5 bg-orange-600 text-white text-xs font-semibold rounded-lg hover:bg-orange-700 disabled:opacity-50"
                  >
                    {stopping ? "Stopping..." : "Yes, Stop"}
                  </button>
                  <button
                    onClick={() => setStopConfirm(false)}
                    className="px-3 py-1.5 text-xs border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-500"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setStopConfirm(true)}
                  disabled={stopping}
                  className="px-4 py-2 border border-orange-300 text-orange-700 text-sm font-medium rounded-lg hover:bg-orange-50 disabled:opacity-50 transition-colors"
                >
                  ⏹ Stop Winner Send
                </button>
              )}
              <button
                onClick={fetchProgress}
                className="px-3 py-2 text-xs text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-50"
              >
                🔄 Refresh
              </button>
            </>
          )}

          {/* FIX: Show View Report link for both running AND completed */}
          {(wsStatus === "running" || wsStatus === "completed") && (
            <Link
              to={`/ab-tests/${testId}/winner-report`}
              className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 transition-colors shadow-sm"
            >
              📊 {wsStatus === "running" ? "Live Report" : "View Winner Report"}
            </Link>
          )}

          {wsStatus === "stopped" && (
            <div className="flex items-center gap-2 text-xs text-orange-600 bg-orange-100 border border-orange-200 rounded-lg px-3 py-2 w-full">
              <span>⚠️</span>
              <span>
                The winner send was stopped manually. In-flight emails may still
                have been delivered.
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main ABTestResults ─────────────────────────────────────
const ABTestResults = () => {
  const { testId } = useParams();
  const navigate = useNavigate();

  const { toasts, show: toast, dismiss } = useToast();
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [completing, setCompleting] = useState(false);
  const [timeLeft, setTimeLeft] = useState(null);

  const fetchResults = useCallback(async () => {
    try {
      const response = await API.get(`/ab-tests/${testId}/results`);
      setResults(response.data);
      setError("");
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load results");
    } finally {
      setLoading(false);
    }
  }, [testId]);

  // Auto-refresh every 30 s while running
  useEffect(() => {
    fetchResults();
    const interval = setInterval(fetchResults, 30000);
    return () => clearInterval(interval);
  }, [fetchResults]);

  // Countdown ticker
  useEffect(() => {
    if (!results) return;
    const tick = () => {
      setTimeLeft(
        getTimeRemaining(results.start_date, results.test_duration_hours),
      );
    };
    tick();
    const id = setInterval(tick, 60000);
    return () => clearInterval(id);
  }, [results]);

  // ── Actions ────────────────────────────────────────────────
  const handleCompleteTest = async (applyWinner) => {
    const msg = applyWinner
      ? `Complete test and apply Variant ${results.winner?.winner} to campaign?`
      : "Complete test without applying winner to campaign?";
    if (!window.confirm(msg)) return;

    setCompleting(true);
    try {
      const res = await API.post(`/ab-tests/${testId}/complete`, {
        apply_to_campaign: applyWinner,
      });
      toast(res.data.message || "Test completed.", "success");
      fetchResults();
    } catch (err) {
      toast(err.response?.data?.detail || "Failed to complete test", "error");
    } finally {
      setCompleting(false);
    }
  };

  // ── Render guards ──────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 gap-3 text-gray-400">
        <div className="animate-spin h-5 w-5 border-2 border-gray-300 border-t-blue-500 rounded-full" />
        Loading results…
      </div>
    );
  }

  if (error) {
    return (
      <div className="py-6">
        <div className="bg-red-50 border border-red-200 rounded p-4">
          <p className="text-red-800">{error}</p>
          <button
            onClick={() => navigate("/ab-testing")}
            className="text-red-600 underline mt-2"
          >
            ← Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  if (!results) return null;

  // ── Derived values ─────────────────────────────────────────
  const isRunning = results.status === "running";
  const isCompleted = results.status === "completed";
  const varA = results.results?.variant_a || {};
  const varB = results.results?.variant_b || {};
  const winner = results.winner || {};
  const winnerInfo = results.winner_info || winner;
  const sig = results.statistical_significance || {};

  const calcDiff = (a, b) => {
    if (!b) return a > 0 ? "+100" : "0";
    const diff = (((a - b) / b) * 100).toFixed(1);
    return diff > 0 ? `+${diff}` : String(diff);
  };

  const statusColors = {
    running: "bg-blue-100 text-blue-800",
    completed: "bg-green-100 text-green-800",
    draft: "bg-gray-100 text-gray-700",
    paused: "bg-yellow-100 text-yellow-800",
    stopped: "bg-orange-100 text-orange-800",
  };

  const sigColors = {
    high: "bg-green-100 text-green-800",
    medium: "bg-yellow-100 text-yellow-800",
    low: "bg-red-100 text-red-800",
  };

  return (
    <div className="space-y-6">
      <ToastContainer toasts={toasts} dismiss={dismiss} />

      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-base font-semibold text-gray-900">
            {results.test_name}
          </p>
          <p className="text-xs text-gray-400 mt-0.5">
            {results.test_type?.replace("_", " ")} test
          </p>
        </div>
        <button
          onClick={() => navigate("/ab-testing")}
          className="px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600"
        >
          ← Back
        </button>
      </div>

      {/* ── Meta info card ── */}
      <div className="bg-white shadow rounded-lg p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-sm flex-1">
            <div>
              <p className="text-gray-500">Status</p>
              <span
                className={`mt-1 inline-block px-2 py-0.5 rounded font-medium ${statusColors[results.status] || "bg-gray-100 text-gray-700"}`}
              >
                {results.status?.toUpperCase()}
              </span>
            </div>
            <div>
              <p className="text-gray-500">Test Type</p>
              <p className="font-semibold capitalize">
                {results.test_type?.replace("_", " ")}
              </p>
            </div>
            <div>
              <p className="text-gray-500">Sample Size</p>
              <p className="font-semibold">
                {results.sample_size?.toLocaleString()}
              </p>
            </div>
            <div>
              <p className="text-gray-500">Split</p>
              <p className="font-semibold">
                {results.split_percentage}% /{" "}
                {100 - (results.split_percentage || 50)}%
              </p>
            </div>
            <div>
              <p className="text-gray-500">Winner Criteria</p>
              <p className="font-semibold capitalize">
                {results.winner_criteria?.replace("_", " ")}
              </p>
            </div>
            <div>
              <p className="text-gray-500">Duration</p>
              <p className="font-semibold">
                {results.test_duration_hours
                  ? `${results.test_duration_hours}h`
                  : "—"}
              </p>
            </div>
            <div>
              <p className="text-gray-500">Started</p>
              <p className="font-semibold">
                {results.start_date
                  ? new Date(results.start_date).toLocaleString()
                  : "—"}
              </p>
            </div>
            <div>
              <p className="text-gray-500">Ended</p>
              <p className="font-semibold">
                {results.end_date
                  ? new Date(results.end_date).toLocaleString()
                  : "—"}
              </p>
            </div>
          </div>
        </div>

        {/* Countdown + auto-send badges */}
        {isRunning && (
          <div className="mt-4 flex flex-wrap gap-3">
            {timeLeft && (
              <div
                className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-sm border ${timeLeft.expired ? "bg-red-50 border-red-200 text-red-700" : "bg-amber-50 border-amber-200 text-amber-800"}`}
              >
                <span>⏱</span>
                <span className="font-medium">{timeLeft.label}</span>
              </div>
            )}
            {results.auto_send_winner && (
              <div className="flex items-center gap-1.5 bg-green-50 border border-green-200 rounded-full px-3 py-1 text-sm">
                <span>🚀</span>
                <span className="font-medium text-green-800">
                  Auto-send winner enabled
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Winner announcement ── */}
      {winner.winner && winner.winner !== "TIE" && (
        <div className="bg-green-50 border-2 border-green-300 rounded-lg p-6">
          <div className="flex items-center gap-3">
            <span className="text-4xl">🏆</span>
            <div>
              <p className="text-2xl font-bold text-green-800">
                Variant {winner.winner} is the winner
              </p>
              <p className="text-green-700 mt-1">
                {Number(winner.improvement ?? 0).toFixed(2)}% better on{" "}
                <span className="font-semibold capitalize">
                  {results.winner_criteria?.replace("_", " ")}
                </span>
              </p>
              {isCompleted && results.winner_variant_applied && (
                <p className="text-green-600 text-sm mt-1">
                  ✓ Applied to campaign — remaining subscribers will receive
                  Variant {winner.winner}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {winner.winner === "TIE" && (
        <div className="bg-yellow-50 border-2 border-yellow-300 rounded-lg p-6">
          <p className="text-xl font-bold text-yellow-800">
            🤝 Both variants are performing equally
          </p>
          <p className="text-yellow-700 text-sm mt-1">
            Consider running the test longer for more conclusive results.
          </p>
        </div>
      )}

      {/* ── Metrics comparison ── */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Variant A */}
        <div
          className={`border-2 rounded-lg p-5 ${winnerInfo.winner === "A" ? "border-green-400 bg-green-50" : "border-blue-200 bg-blue-50"}`}
        >
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-bold text-gray-800">
              Variant A (Control)
            </h3>
            {winnerInfo.winner === "A" && (
              <span className="bg-green-500 text-white px-2 py-1 rounded text-sm font-bold">
                🏆 WINNER
              </span>
            )}
          </div>
          <div className="space-y-3 text-sm">
            {[
              { label: "Sent", value: varA.sent?.toLocaleString() },
              { label: "Opened", value: varA.opened?.toLocaleString() },
              { label: "Clicked", value: varA.clicked?.toLocaleString() },
              {
                label: "Open Rate",
                value: `${varA.open_rate ?? 0}%`,
                color: "text-blue-700",
              },
              {
                label: "Click Rate",
                value: `${varA.click_rate ?? 0}%`,
                color: "text-purple-700",
              },
            ].map(({ label, value, color }) => (
              <div key={label} className="flex justify-between">
                <span className="text-gray-600">{label}</span>
                <span className={`font-semibold ${color || "text-gray-900"}`}>
                  {value ?? "—"}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Variant B */}
        <div
          className={`border-2 rounded-lg p-5 ${winnerInfo.winner === "B" ? "border-green-400 bg-green-50" : "border-orange-200 bg-orange-50"}`}
        >
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-bold text-gray-800">
              Variant B (Test)
            </h3>
            {winnerInfo.winner === "B" && (
              <span className="bg-green-500 text-white px-2 py-1 rounded text-sm font-bold">
                🏆 WINNER
              </span>
            )}
          </div>
          <div className="space-y-3 text-sm">
            {[
              { label: "Sent", value: varB.sent?.toLocaleString() },
              { label: "Opened", value: varB.opened?.toLocaleString() },
              { label: "Clicked", value: varB.clicked?.toLocaleString() },
              {
                label: "Open Rate",
                value: `${varB.open_rate ?? 0}%`,
                color: "text-blue-700",
              },
              {
                label: "Click Rate",
                value: `${varB.click_rate ?? 0}%`,
                color: "text-purple-700",
              },
            ].map(({ label, value, color }) => (
              <div key={label} className="flex justify-between">
                <span className="text-gray-600">{label}</span>
                <span className={`font-semibold ${color || "text-gray-900"}`}>
                  {value ?? "—"}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Winner Send Section */}
      <WinnerSendSection
        testId={testId}
        results={results}
        onReload={fetchResults}
      />

      {/* Performance summary strip */}
      {winnerInfo.winner && winnerInfo.winner !== "TIE" && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <p className="text-sm">
            <strong>Variant {winnerInfo.winner}</strong> performed{" "}
            <strong>
              {Number(
                winnerInfo.improvement_percentage ?? winner.improvement ?? 0,
              ).toFixed(2)}
              %
            </strong>{" "}
            better based on{" "}
            <strong className="capitalize">
              {(winnerInfo.criteria || results.winner_criteria)?.replace(
                "_",
                " ",
              )}
            </strong>
          </p>
        </div>
      )}

      {/* Full comparison table */}
      <div className="bg-white shadow rounded-lg overflow-hidden">
        <div className="p-4 border-b bg-gray-50">
          <h3 className="text-lg font-semibold">Performance Comparison</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-100 text-gray-600 uppercase text-xs">
              <tr>
                <th className="px-6 py-3 text-left">Variant</th>
                <th className="px-6 py-3 text-right">Sent</th>
                <th className="px-6 py-3 text-right">Opened</th>
                <th className="px-6 py-3 text-right">Clicked</th>
                <th className="px-6 py-3 text-right">Open Rate</th>
                <th className="px-6 py-3 text-right">Click Rate</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-t hover:bg-gray-50">
                <td className="px-6 py-4 font-semibold text-blue-700">
                  Variant A (Control)
                </td>
                <td className="px-6 py-4 text-right">{varA.sent ?? "—"}</td>
                <td className="px-6 py-4 text-right">{varA.opened ?? "—"}</td>
                <td className="px-6 py-4 text-right">{varA.clicked ?? "—"}</td>
                <td className="px-6 py-4 text-right font-medium">
                  {varA.open_rate ?? "—"}%
                </td>
                <td className="px-6 py-4 text-right font-medium">
                  {varA.click_rate ?? "—"}%
                </td>
              </tr>
              <tr className="border-t hover:bg-gray-50">
                <td className="px-6 py-4 font-semibold text-orange-700">
                  Variant B (Test)
                </td>
                <td className="px-6 py-4 text-right">{varB.sent ?? "—"}</td>
                <td className="px-6 py-4 text-right">{varB.opened ?? "—"}</td>
                <td className="px-6 py-4 text-right">{varB.clicked ?? "—"}</td>
                <td className="px-6 py-4 text-right font-medium">
                  {varB.open_rate ?? "—"}%
                </td>
                <td className="px-6 py-4 text-right font-medium">
                  {varB.click_rate ?? "—"}%
                </td>
              </tr>
              {/* Difference row */}
              <tr className="border-t bg-gray-50 text-xs text-gray-500">
                <td className="px-6 py-2 italic">B vs A difference</td>
                <td className="px-6 py-2 text-right">—</td>
                <td className="px-6 py-2 text-right">—</td>
                <td className="px-6 py-2 text-right">—</td>
                <td
                  className={`px-6 py-2 text-right font-semibold ${varB.open_rate > varA.open_rate ? "text-green-600" : varB.open_rate < varA.open_rate ? "text-red-600" : "text-gray-500"}`}
                >
                  {calcDiff(varB.open_rate ?? 0, varA.open_rate ?? 0)}%
                </td>
                <td
                  className={`px-6 py-2 text-right font-semibold ${varB.click_rate > varA.click_rate ? "text-green-600" : varB.click_rate < varA.click_rate ? "text-red-600" : "text-gray-500"}`}
                >
                  {calcDiff(varB.click_rate ?? 0, varA.click_rate ?? 0)}%
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Statistical significance */}
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">
          📈 Statistical Significance
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <p className="text-sm text-gray-500">Confidence Level</p>
            <span
              className={`mt-1 inline-block px-3 py-1 rounded font-bold text-lg uppercase ${sigColors[sig.confidence_level] || "bg-gray-100 text-gray-700"}`}
            >
              {sig.confidence_level ?? "—"}
            </span>
          </div>
          <div>
            <p className="text-sm text-gray-500">Total Samples</p>
            <p className="text-2xl font-bold">
              {sig.total_samples?.toLocaleString() ?? "—"}
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-500">Statistically Significant</p>
            <p className="text-2xl font-bold">
              {sig.is_significant === true && (
                <span className="text-green-600">✓ Yes</span>
              )}
              {sig.is_significant === false && (
                <span className="text-red-600">✗ No</span>
              )}
              {sig.is_significant == null && "—"}
            </p>
          </div>
        </div>
        {sig.is_significant === false && (
          <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded text-sm text-yellow-800">
            ⚠️ Sample size is too small for reliable conclusions. Consider
            running the test longer or increasing the sample size.
          </div>
        )}
      </div>

      {/* Visual bar chart */}
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-5">📊 Visual Comparison</h3>
        <div className="space-y-6">
          <div>
            <div className="flex justify-between mb-2 text-sm">
              <span className="font-medium">Open Rate</span>
              <span className="text-gray-500">
                A: {varA.open_rate ?? 0}% | B: {varB.open_rate ?? 0}%
              </span>
            </div>
            <div className="flex gap-2">
              <div className="flex-1">
                <div className="bg-blue-200 rounded h-8 overflow-hidden relative">
                  <div
                    className="bg-blue-600 h-full rounded transition-all duration-700"
                    style={{ width: `${Math.min(varA.open_rate ?? 0, 100)}%` }}
                  >
                    <span className="absolute inset-0 flex items-center justify-center text-white text-xs font-bold">
                      A — {varA.open_rate ?? 0}%
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex-1">
                <div className="bg-orange-200 rounded h-8 overflow-hidden relative">
                  <div
                    className="bg-orange-500 h-full rounded transition-all duration-700"
                    style={{ width: `${Math.min(varB.open_rate ?? 0, 100)}%` }}
                  >
                    <span className="absolute inset-0 flex items-center justify-center text-white text-xs font-bold">
                      B — {varB.open_rate ?? 0}%
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div>
            <div className="flex justify-between mb-2 text-sm">
              <span className="font-medium">Click Rate</span>
              <span className="text-gray-500">
                A: {varA.click_rate ?? 0}% | B: {varB.click_rate ?? 0}%
              </span>
            </div>
            <div className="flex gap-2">
              <div className="flex-1">
                <div className="bg-purple-200 rounded h-8 overflow-hidden relative">
                  <div
                    className="bg-purple-600 h-full rounded transition-all duration-700"
                    style={{ width: `${Math.min(varA.click_rate ?? 0, 100)}%` }}
                  >
                    <span className="absolute inset-0 flex items-center justify-center text-white text-xs font-bold">
                      A — {varA.click_rate ?? 0}%
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex-1">
                <div className="bg-pink-200 rounded h-8 overflow-hidden relative">
                  <div
                    className="bg-pink-500 h-full rounded transition-all duration-700"
                    style={{ width: `${Math.min(varB.click_rate ?? 0, 100)}%` }}
                  >
                    <span className="absolute inset-0 flex items-center justify-center text-white text-xs font-bold">
                      B — {varB.click_rate ?? 0}%
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">Actions</h3>

        {/* Running test */}
        {isRunning && (
          <div className="space-y-3">
            <div className="flex flex-col sm:flex-row gap-3">
              <button
                onClick={() => handleCompleteTest(true)}
                disabled={
                  completing || !winner.winner || winner.winner === "TIE"
                }
                className="flex-1 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white py-3 px-6 rounded-lg font-semibold transition-colors"
              >
                {completing
                  ? "Completing..."
                  : "✅ Complete Test & Send Winner"}
              </button>
              <button
                onClick={() => handleCompleteTest(false)}
                disabled={completing}
                className="flex-1 bg-gray-600 hover:bg-gray-700 disabled:opacity-50 text-white py-3 px-6 rounded-lg font-semibold transition-colors"
              >
                Complete Without Sending
              </button>
            </div>
            {(!winner.winner || winner.winner === "TIE") && (
              <p className="text-xs text-amber-600">
                ⚠️ A clear winner is needed to send the variant. You can still
                complete without sending.
              </p>
            )}
          </div>
        )}

        {/* Stopped test */}
        {results.status === "stopped" && (
          <div className="space-y-3">
            <div className="flex items-center gap-3 bg-orange-50 border border-orange-200 rounded-lg px-4 py-3 mb-3">
              <span className="text-orange-600 text-lg">🛑</span>
              <p className="text-sm text-orange-800">
                Test is stopped. You can still complete it to declare a winner
                and send to remaining subscribers.
              </p>
            </div>
            <div className="flex flex-col sm:flex-row gap-3">
              <button
                onClick={() => handleCompleteTest(true)}
                disabled={
                  completing || !winner.winner || winner.winner === "TIE"
                }
                className="flex-1 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white py-3 px-6 rounded-lg font-semibold transition-colors"
              >
                {completing ? "Completing..." : "✅ Complete & Send Winner"}
              </button>
              <button
                onClick={() => handleCompleteTest(false)}
                disabled={completing}
                className="flex-1 bg-gray-600 hover:bg-gray-700 disabled:opacity-50 text-white py-3 px-6 rounded-lg font-semibold transition-colors"
              >
                Complete Without Sending
              </button>
            </div>
          </div>
        )}

        {isCompleted && (
          <p className="text-sm text-gray-500">
            ✓ Test completed on{" "}
            {results.end_date
              ? new Date(results.end_date).toLocaleString()
              : "—"}
          </p>
        )}
      </div>

      {/* Info notice */}
      <div className="p-3 bg-gray-50 border border-gray-200 rounded text-sm text-gray-500">
        🔄 Results refresh automatically every 30 seconds.{" "}
        {isRunning && results.test_duration_hours && (
          <>
            Winner will be auto-declared after{" "}
            <strong>{results.test_duration_hours}h</strong> via scheduled task.
          </>
        )}
      </div>
    </div>
  );
};

export default ABTestResults;
