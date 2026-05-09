/**
 * ImportSummaryCard
 *
 * Shown after a CSV import completes (or while it's in progress).
 * Reads from GET /subscribers/jobs/:job_id/summary.
 *
 * Props:
 *   jobId       {string}   — the job_id returned by the /bulk endpoint
 *   listName    {string}   — display name for the list
 *   onDismiss   {function} — called when user closes the card
 *   onViewList  {function} — called when user clicks "View list"
 */

import { useState, useEffect, useRef, useCallback } from "react";
import API from "../api"; // your existing axios instance

// ── helpers ──────────────────────────────────────────────────────────────────

const ACTIVE_STATUSES = new Set(["pending", "processing"]);
const TERMINAL_STATUSES = new Set(["completed", "partially_completed", "failed"]);

function fmt(n) {
    return (n ?? 0).toLocaleString();
}

function fmtRate(n) {
    return `${(n ?? 0).toFixed(1)}%`;
}

function fmtSpeed(n) {
    if (!n) return null;
    return n >= 1000 ? `${(n / 1000).toFixed(1)}k/s` : `${n}/s`;
}

function fmtElapsed(sec) {
    if (!sec) return null;
    if (sec < 60) return `${Math.round(sec)}s`;
    const m = Math.floor(sec / 60);
    const s = Math.round(sec % 60);
    return `${m}m ${s}s`;
}

const COLOR_MAP = {
    green: { bar: "bg-green-500", text: "text-green-700", badge: "bg-green-100 text-green-800" },
    blue: { bar: "bg-blue-500", text: "text-blue-700", badge: "bg-blue-100 text-blue-800" },
    yellow: { bar: "bg-yellow-400", text: "text-yellow-700", badge: "bg-yellow-100 text-yellow-800" },
    red: { bar: "bg-red-500", text: "text-red-700", badge: "bg-red-100 text-red-800" },
    gray: { bar: "bg-gray-300", text: "text-gray-500", badge: "bg-gray-100 text-gray-600" },
};

// ── sub-components ───────────────────────────────────────────────────────────

function BreakdownBar({ breakdown, total }) {
    if (!total) return null;
    return (
        <div className="flex w-full h-2 rounded-full overflow-hidden gap-px bg-gray-100">
            {breakdown.map((seg) => {
                if (!seg.count) return null;
                const pct = (seg.count / total) * 100;
                const c = COLOR_MAP[seg.color] ?? COLOR_MAP.gray;
                return (
                    <div
                        key={seg.label}
                        className={`${c.bar} transition-all duration-500`}
                        style={{ width: `${pct}%` }}
                        title={`${seg.label}: ${fmt(seg.count)}`}
                    />
                );
            })}
        </div>
    );
}

function StatCell({ label, value, color = "gray", large = false }) {
    const c = COLOR_MAP[color] ?? COLOR_MAP.gray;
    return (
        <div className="flex flex-col">
            <span className={`font-semibold ${large ? "text-2xl" : "text-lg"} ${c.text}`}>
                {fmt(value)}
            </span>
            <span className="text-xs text-gray-500 mt-0.5">{label}</span>
        </div>
    );
}

function ErrorTable({ errors, total, hasMore }) {
    const [expanded, setExpanded] = useState(false);
    if (!errors?.length) return null;

    const shown = expanded ? errors : errors.slice(0, 5);

    return (
        <div className="mt-3">
            <button
                onClick={() => setExpanded((v) => !v)}
                className="flex items-center gap-1.5 text-xs font-medium text-red-700 hover:text-red-900"
            >
                <span>{expanded ? "▲" : "▼"}</span>
                {expanded ? "Hide" : "Show"} failed rows ({fmt(total)} total
                {hasMore ? ", showing first 200" : ""})
            </button>
            {expanded && (
                <div className="mt-2 rounded border border-red-100 overflow-hidden text-xs">
                    <table className="w-full">
                        <thead className="bg-red-50">
                            <tr>
                                <th className="px-3 py-1.5 text-left text-red-700 font-medium w-16">Row</th>
                                <th className="px-3 py-1.5 text-left text-red-700 font-medium">Email</th>
                                <th className="px-3 py-1.5 text-left text-red-700 font-medium">Reason</th>
                            </tr>
                        </thead>
                        <tbody>
                            {shown.map((err, i) => (
                                <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-red-50/40"}>
                                    <td className="px-3 py-1.5 text-gray-500">{err.row ?? "—"}</td>
                                    <td className="px-3 py-1.5 font-mono text-gray-700 break-all">{err.email || "—"}</td>
                                    <td className="px-3 py-1.5 text-red-600">{err.reason}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {!expanded && errors.length > 5 && (
                        <div className="px-3 py-1.5 bg-red-50 text-red-600 text-center">
                            +{errors.length - 5} more rows
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

// ── main component ───────────────────────────────────────────────────────────

export default function ImportSummaryCard({ jobId, listName, onDismiss, onViewList }) {
    const [summary, setSummary] = useState(null);
    const [error, setError] = useState(null);
    const intervalRef = useRef(null);

    const fetchSummary = useCallback(async () => {
        try {
            const res = await API.get(`/subscribers/jobs/${jobId}/summary`);
            const data = res.data;
            setSummary(data);

            // Stop polling once the job reaches a terminal state
            if (TERMINAL_STATUSES.has(data.status)) {
                clearInterval(intervalRef.current);
                intervalRef.current = null;
            }
        } catch (err) {
            setError("Could not load import summary.");
            clearInterval(intervalRef.current);
        }
    }, [jobId]);

    useEffect(() => {
        fetchSummary();
        // Poll every 2s while the job is running
        intervalRef.current = setInterval(fetchSummary, 2000);
        return () => clearInterval(intervalRef.current);
    }, [fetchSummary]);

    // ── render states ──────────────────────────────────────────────────────────

    if (error) {
        return (
            <div className="rounded-xl border border-red-200 bg-red-50 p-4 flex justify-between items-center">
                <span className="text-sm text-red-700">{error}</span>
                <button onClick={onDismiss} className="text-xs text-red-500 hover:text-red-700 ml-4">Dismiss</button>
            </div>
        );
    }

    if (!summary) {
        return (
            <div className="rounded-xl border border-gray-200 bg-white p-4 flex items-center gap-3 animate-pulse">
                <div className="h-4 w-4 rounded-full bg-blue-300" />
                <span className="text-sm text-gray-500">Loading import summary…</span>
            </div>
        );
    }

    const isRunning = ACTIVE_STATUSES.has(summary.status);
    const isFailed = summary.status === "failed";
    const isPartial = summary.status === "partially_completed";
    const isComplete = summary.status === "completed";

    const statusMeta = isRunning ? { icon: "⏳", label: "Processing", color: "blue" }
        : isComplete ? { icon: "✅", label: "Import complete", color: "green" }
            : isPartial ? { icon: "⚠️", label: "Partially imported", color: "yellow" }
                : { icon: "❌", label: "Import failed", color: "red" };

    const c = COLOR_MAP[statusMeta.color];

    return (
        <div className={`rounded-xl border bg-white shadow-sm overflow-hidden`}>
            {/* Header */}
            <div className={`px-4 py-3 flex items-center justify-between ${isRunning ? "bg-blue-50 border-b border-blue-100" :
                    isComplete ? "bg-green-50 border-b border-green-100" :
                        isPartial ? "bg-yellow-50 border-b border-yellow-100" :
                            "bg-red-50 border-b border-red-100"
                }`}>
                <div className="flex items-center gap-2">
                    <span className="text-base">{statusMeta.icon}</span>
                    <div>
                        <p className={`text-sm font-semibold ${c.text}`}>{statusMeta.label}</p>
                        <p className="text-xs text-gray-500">
                            {summary.list_name ?? listName}
                            {summary.elapsed_seconds && !isRunning && (
                                <span className="ml-2 text-gray-400">· {fmtElapsed(summary.elapsed_seconds)}</span>
                            )}
                        </p>
                    </div>
                </div>
                <button
                    onClick={onDismiss}
                    className="text-gray-400 hover:text-gray-600 text-lg leading-none"
                    title="Dismiss"
                >
                    ✕
                </button>
            </div>

            {/* Live progress bar (only while running) */}
            {isRunning && (
                <div className="px-4 pt-3 pb-1">
                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                        <span>
                            {fmt(summary.processed)} / {fmt(summary.total_input)} rows
                        </span>
                        <span>{summary.progress}%</span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-2">
                        <div
                            className="bg-blue-500 h-2 rounded-full transition-all duration-500"
                            style={{ width: `${summary.progress}%` }}
                        />
                    </div>
                    {summary.records_per_second > 0 && (
                        <p className="text-xs text-gray-400 mt-1">
                            ⚡ {fmtSpeed(summary.records_per_second)} · est.{" "}
                            {fmtElapsed(
                                (summary.total_input - summary.processed) / summary.records_per_second
                            )}{" "}
                            remaining
                        </p>
                    )}
                </div>
            )}

            {/* Breakdown bar (always) */}
            {summary.total_input > 0 && (
                <div className="px-4 pt-3">
                    <BreakdownBar breakdown={summary.breakdown} total={summary.total_input} />
                    {/* Legend */}
                    <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1.5">
                        {summary.breakdown
                            .filter((s) => s.count > 0)
                            .map((seg) => {
                                const sc = COLOR_MAP[seg.color] ?? COLOR_MAP.gray;
                                return (
                                    <span key={seg.label} className="flex items-center gap-1 text-xs">
                                        <span className={`inline-block w-2 h-2 rounded-full ${sc.bar}`} />
                                        <span className="text-gray-600">
                                            {seg.label}: <strong>{fmt(seg.count)}</strong>
                                        </span>
                                    </span>
                                );
                            })}
                    </div>
                </div>
            )}

            {/* Stat grid */}
            <div className="px-4 py-3 grid grid-cols-4 gap-3 border-t border-gray-50 mt-3">
                <StatCell label="Total input" value={summary.total_input} color="gray" />
                <StatCell label="New" value={summary.new_records} color="green" />
                <StatCell label="Updated" value={summary.updated} color="blue" />
                <StatCell label="Duplicates" value={summary.duplicates} color="yellow" />
            </div>

            {/* Rates row */}
            {!isRunning && summary.total_input > 0 && (
                <div className="px-4 pb-3 flex gap-4 text-xs text-gray-500">
                    <span>
                        Success rate:{" "}
                        <strong className="text-gray-700">{fmtRate(summary.success_rate)}</strong>
                    </span>
                    {summary.duplicate_rate > 0 && (
                        <span>
                            Duplicate rate:{" "}
                            <strong className="text-gray-700">{fmtRate(summary.duplicate_rate)}</strong>
                        </span>
                    )}
                    {summary.failure_rate > 0 && (
                        <span>
                            Failure rate:{" "}
                            <strong className="text-red-600">{fmtRate(summary.failure_rate)}</strong>
                        </span>
                    )}
                    {summary.records_per_second > 0 && (
                        <span>
                            Speed:{" "}
                            <strong className="text-gray-700">{fmtSpeed(summary.records_per_second)}</strong>
                        </span>
                    )}
                </div>
            )}

            {/* Per-row errors */}
            {summary.failed > 0 && (
                <div className="px-4 pb-3 border-t border-gray-50 pt-2">
                    <ErrorTable
                        errors={summary.import_errors}
                        total={summary.failed}
                        hasMore={summary.has_more_errors}
                    />
                </div>
            )}

            {/* Footer actions */}
            {!isRunning && (
                <div className="px-4 py-3 bg-gray-50 border-t border-gray-100 flex gap-2 justify-end">
                    {(isComplete || isPartial) && onViewList && (
                        <button
                            onClick={() => onViewList(summary.list_name)}
                            className="text-xs px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                        >
                            View list
                        </button>
                    )}
                    <button
                        onClick={onDismiss}
                        className="text-xs px-3 py-1.5 border border-gray-200 rounded-lg hover:bg-gray-100 text-gray-600"
                    >
                        Dismiss
                    </button>
                </div>
            )}
        </div>
    );
}