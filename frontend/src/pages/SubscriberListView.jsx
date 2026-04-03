import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import API from "../api";

// ─── helpers ─────────────────────────────────────────────────
const fmt = (n) => Number(n ?? 0).toLocaleString();
const fmtD = (iso) =>
    iso
        ? new Date(iso).toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
              year: "numeric",
          })
        : "—";

// Safely convert any stored field value (bool, number, string) to a
// displayable string.  Returns null when the value is genuinely absent.
function fieldDisplay(value) {
    if (value === undefined || value === null || value === "") return null;
    return String(value);
}

const STATUS_STYLE = {
    active: "bg-green-100 text-green-700",
    inactive: "bg-gray-100  text-gray-600",
    bounced: "bg-red-100   text-red-700",
    unsubscribed: "bg-orange-100 text-orange-700",
};

function useDebounce(value, delay) {
    const [debouncedValue, setDebouncedValue] = useState(value);
    useEffect(() => {
        const t = setTimeout(() => setDebouncedValue(value), delay);
        return () => clearTimeout(t);
    }, [value, delay]);
    return debouncedValue;
}

// ─── Toast ────────────────────────────────────────────────────
function Toast({ message, type, onClose }) {
    useEffect(() => {
        const t = setTimeout(onClose, 3500);
        return () => clearTimeout(t);
    }, []);
    return (
        <div
            onClick={onClose}
            className={`fixed top-4 right-4 z-50 flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg text-sm font-medium cursor-pointer
        ${type === "success" ? "bg-green-600 text-white" : type === "error" ? "bg-red-600 text-white" : "bg-gray-800 text-white"}`}
        >
            {type === "success" ? "✓" : type === "error" ? "✕" : "ℹ"} {message}
        </div>
    );
}

// ─── Pagination ───────────────────────────────────────────────
function Pagination({ page, totalPages, total, onChange }) {
    if (totalPages <= 1) return null;
    const pages = [];
    const max = 5;
    let start = Math.max(1, page - Math.floor(max / 2));
    let end = Math.min(totalPages, start + max - 1);
    if (end - start + 1 < max) start = Math.max(1, end - max + 1);
    for (let i = start; i <= end; i++) pages.push(i);

    return (
        <div className="flex items-center justify-between px-5 py-3 border-t border-gray-100">
            <p className="text-sm text-gray-500">
                Page {page} of {totalPages} · <strong>{fmt(total)}</strong>{" "}
                subscribers
            </p>
            <div className="flex gap-1">
                {[
                    ["«", 1],
                    ["‹", page - 1],
                ].map(([label, target]) => (
                    <button
                        key={label}
                        onClick={() => onChange(target)}
                        disabled={page === 1}
                        className="px-2.5 py-1 text-xs border rounded disabled:opacity-40 hover:bg-gray-50"
                    >
                        {label}
                    </button>
                ))}
                {pages.map((p) => (
                    <button
                        key={p}
                        onClick={() => onChange(p)}
                        className={`px-2.5 py-1 text-xs border rounded ${p === page ? "bg-blue-600 text-white border-blue-600" : "hover:bg-gray-50"}`}
                    >
                        {p}
                    </button>
                ))}
                {[
                    ["›", page + 1],
                    ["»", totalPages],
                ].map(([label, target]) => (
                    <button
                        key={label}
                        onClick={() => onChange(target)}
                        disabled={page === totalPages}
                        className="px-2.5 py-1 text-xs border rounded disabled:opacity-40 hover:bg-gray-50"
                    >
                        {label}
                    </button>
                ))}
            </div>
        </div>
    );
}

// ─── Main ─────────────────────────────────────────────────────
export default function SubscriberListView() {
    const { listName } = useParams();
    const navigate = useNavigate();

    const [subscribers, setSubscribers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [currentPage, setCurrentPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);
    const [totalCount, setTotalCount] = useState(0);
    const [searchTerm, setSearchTerm] = useState("");
    const [statusFilter, setStatusFilter] = useState("");
    const [customFieldKeys, setCustomFieldKeys] = useState([]);
    const [showAllCustomFields, setShowAllCustomFields] = useState(false);

    // edit modal
    const [editModalOpen, setEditModalOpen] = useState(false);
    const [editSubscriber, setEditSubscriber] = useState(null);
    const [saving, setSaving] = useState(false);

    // toast
    const [toast, setToast] = useState(null);
    const showToast = useCallback(
        (message, type = "info") => setToast({ message, type }),
        [],
    );

    const ITEMS_PER_PAGE = 50;
    const debouncedSearch = useDebounce(searchTerm, 400);

    const fetchSubscribers = useCallback(
        async (page = 1, search = "", status = "") => {
            setLoading(true);
            try {
                const params = { page, limit: ITEMS_PER_PAGE };
                if (search) params.search = search;
                if (status) params.status = status;
                const res = await API.get(`/subscribers/list/${listName}`, {
                    params,
                });
                const data = res.data;
                if (data.success && data.subscribers) {
                    setSubscribers(data.subscribers);
                    setTotalPages(data.pagination?.total_pages || 1);
                    setTotalCount(data.pagination?.total || 0);
                    setCurrentPage(page);
                    const keys = new Set();
                    data.subscribers.forEach((sub) => {
                        if (sub.custom_fields)
                            Object.keys(sub.custom_fields).forEach((k) =>
                                keys.add(k),
                            );
                    });
                    setCustomFieldKeys(Array.from(keys));
                } else {
                    setSubscribers([]);
                    setTotalPages(1);
                    setTotalCount(0);
                    setCustomFieldKeys([]);
                }
            } catch (e) {
                console.error(e);
                showToast("Failed to fetch subscribers", "error");
                setSubscribers([]);
                setTotalPages(1);
                setTotalCount(0);
            } finally {
                setLoading(false);
            }
        },
        [listName, showToast],
    );

    useEffect(() => {
        if (listName) fetchSubscribers(1, "", "");
    }, [listName]);
    useEffect(() => {
        fetchSubscribers(1, debouncedSearch, statusFilter);
    }, [debouncedSearch, statusFilter]);

    const handleDelete = async (id) => {
        if (!confirm("Delete this subscriber?")) return;
        try {
            await API.delete(`/subscribers/${id}`);
            showToast("Subscriber deleted", "success");
            fetchSubscribers(currentPage, searchTerm, statusFilter);
        } catch {
            showToast("Delete failed", "error");
        }
    };

    const handleSaveEdit = async () => {
        if (!editSubscriber) return;
        setSaving(true);
        try {
            await API.put(`/subscribers/${editSubscriber._id}`, {
                email: editSubscriber.email,
                list: listName,
                status: editSubscriber.status,
                standard_fields: editSubscriber.standard_fields,
                custom_fields: editSubscriber.custom_fields,
            });
            showToast("Subscriber updated", "success");
            setEditModalOpen(false);
            setEditSubscriber(null);
            fetchSubscribers(currentPage, searchTerm, statusFilter);
        } catch (err) {
            showToast(err.response?.data?.detail || "Update failed", "error");
        } finally {
            setSaving(false);
        }
    };

    const handleExport = async () => {
        try {
            const res = await API.get(`/subscribers/lists/${listName}/export`, {
                responseType: "blob",
            });
            const url = window.URL.createObjectURL(
                new Blob([res.data], { type: "text/csv" }),
            );
            const a = document.createElement("a");
            a.href = url;
            a.download = `${listName}_subscribers.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            showToast("Export started", "success");
        } catch {
            showToast("Export failed", "error");
        }
    };

    // limit visible custom field columns to avoid unusable wide tables
    const visibleCustomKeys = showAllCustomFields
        ? customFieldKeys
        : customFieldKeys.slice(0, 3);

    return (
        <div className="space-y-5">
            {toast && (
                <Toast
                    message={toast.message}
                    type={toast.type}
                    onClose={() => setToast(null)}
                />
            )}

            {/* ── Header ── */}
            <div className="flex items-center justify-between gap-4 flex-wrap">
                <div className="flex items-center gap-3">
                    <button
                        onClick={() => navigate("/subscribers")}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600 transition-colors"
                    >
                        ← Back
                    </button>
                    <div>
                        <h1 className="text-lg font-semibold text-gray-900 capitalize">
                            {listName}
                        </h1>
                        {!loading && (
                            <p className="text-xs text-gray-400">
                                {fmt(totalCount)} subscribers
                            </p>
                        )}
                    </div>
                </div>
                <button
                    onClick={handleExport}
                    className="flex items-center gap-2 px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600 transition-colors"
                >
                    📥 Export CSV
                </button>
            </div>

            {/* ── Table card ── */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                {/* Toolbar */}
                <div className="flex flex-wrap items-center gap-3 px-5 py-4 border-b border-gray-100">
                    <div className="relative flex-1 min-w-[180px] max-w-xs">
                        <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs">
                            🔍
                        </span>
                        <input
                            type="text"
                            placeholder="Search by email or name…"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="pl-7 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 w-full"
                        />
                        {searchTerm && (
                            <button
                                onClick={() => setSearchTerm("")}
                                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-300 hover:text-gray-500 text-xs"
                            >
                                ✕
                            </button>
                        )}
                    </div>

                    <select
                        value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                        className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 bg-white text-gray-600"
                    >
                        <option value="">All statuses</option>
                        <option value="active">Active</option>
                        <option value="inactive">Inactive</option>
                        <option value="bounced">Bounced</option>
                        <option value="unsubscribed">Unsubscribed</option>
                    </select>

                    {(searchTerm || statusFilter) && (
                        <button
                            onClick={() => {
                                setSearchTerm("");
                                setStatusFilter("");
                            }}
                            className="text-xs text-gray-400 hover:text-gray-600 hover:underline"
                        >
                            Clear filters
                        </button>
                    )}

                    {customFieldKeys.length > 3 && (
                        <button
                            onClick={() =>
                                setShowAllCustomFields(!showAllCustomFields)
                            }
                            className="ml-auto text-xs text-blue-600 hover:underline"
                        >
                            {showAllCustomFields
                                ? "Fewer columns"
                                : `+${customFieldKeys.length - 3} more fields`}
                        </button>
                    )}
                </div>

                {loading ? (
                    <div className="flex items-center justify-center py-16 gap-2 text-gray-400 text-sm">
                        <div className="animate-spin h-4 w-4 border-2 border-gray-300 border-t-blue-500 rounded-full" />
                        Loading…
                    </div>
                ) : subscribers.length === 0 ? (
                    <div className="py-16 text-center">
                        <p className="text-3xl mb-2">
                            {searchTerm || statusFilter ? "🔍" : "👥"}
                        </p>
                        <p className="text-sm font-medium text-gray-700">
                            {searchTerm || statusFilter
                                ? "No subscribers match your filters"
                                : "No subscribers in this list"}
                        </p>
                        {(searchTerm || statusFilter) && (
                            <button
                                onClick={() => {
                                    setSearchTerm("");
                                    setStatusFilter("");
                                }}
                                className="text-xs text-blue-600 mt-2 hover:underline"
                            >
                                Clear filters
                            </button>
                        )}
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="bg-gray-50 border-b border-gray-100">
                                    <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                        Email
                                    </th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                        Name
                                    </th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                        Status
                                    </th>
                                    {visibleCustomKeys.map((k) => (
                                        <th
                                            key={k}
                                            className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider whitespace-nowrap max-w-[120px]"
                                        >
                                            {k.replace(/_/g, " ")}
                                        </th>
                                    ))}
                                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider whitespace-nowrap">
                                        Joined
                                    </th>
                                    <th className="px-4 py-3 w-20" />
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-50">
                                {subscribers.map((sub) => (
                                    <tr
                                        key={sub._id}
                                        className="hover:bg-gray-50 transition-colors"
                                    >
                                        <td className="px-5 py-3 font-medium text-gray-900 whitespace-nowrap">
                                            {sub.email}
                                        </td>
                                        <td className="px-4 py-3 text-gray-600 whitespace-nowrap">
                                            {[
                                                sub.standard_fields?.first_name,
                                                sub.standard_fields?.last_name,
                                            ]
                                                .filter(Boolean)
                                                .join(" ") || (
                                                <span className="text-gray-300">
                                                    —
                                                </span>
                                            )}
                                        </td>
                                        <td className="px-4 py-3">
                                            <span
                                                className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap ${STATUS_STYLE[sub.status] || STATUS_STYLE.inactive}`}
                                            >
                                                {sub.status}
                                            </span>
                                        </td>
                                        {visibleCustomKeys.map((k) => {
                                            const display = fieldDisplay(
                                                sub.custom_fields?.[k],
                                            );
                                            return (
                                                <td
                                                    key={k}
                                                    className="px-4 py-3 text-gray-500 max-w-[120px] truncate"
                                                    title={display ?? ""}
                                                >
                                                    {display ?? (
                                                        <span className="text-gray-300">
                                                            —
                                                        </span>
                                                    )}
                                                </td>
                                            );
                                        })}
                                        <td className="px-4 py-3 text-xs text-gray-400 text-right whitespace-nowrap">
                                            {fmtD(sub.created_at)}
                                        </td>
                                        <td className="px-4 py-3 text-right">
                                            <div className="flex items-center justify-end gap-2">
                                                <button
                                                    onClick={() => {
                                                        setEditSubscriber({
                                                            ...sub,
                                                            standard_fields: {
                                                                ...sub.standard_fields,
                                                            },
                                                            custom_fields: {
                                                                ...sub.custom_fields,
                                                            },
                                                        });
                                                        setEditModalOpen(true);
                                                    }}
                                                    className="text-xs text-blue-600 hover:underline font-medium"
                                                >
                                                    Edit
                                                </button>
                                                <button
                                                    onClick={() =>
                                                        handleDelete(sub._id)
                                                    }
                                                    className="text-xs text-red-500 hover:underline font-medium"
                                                >
                                                    Delete
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                <Pagination
                    page={currentPage}
                    totalPages={totalPages}
                    total={totalCount}
                    onChange={(p) =>
                        fetchSubscribers(p, searchTerm, statusFilter)
                    }
                />
            </div>

            {/* ── Edit Modal ── */}
            {editModalOpen && editSubscriber && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
                        <div className="flex items-center justify-between px-6 py-4 border-b">
                            <h2 className="text-base font-semibold">
                                Edit Subscriber
                            </h2>
                            <button
                                onClick={() => {
                                    setEditModalOpen(false);
                                    setEditSubscriber(null);
                                }}
                                className="text-gray-400 hover:text-gray-600 text-xl"
                            >
                                ✕
                            </button>
                        </div>

                        <div className="px-6 py-4 space-y-4">
                            <div>
                                <label className="block text-sm font-medium mb-1">
                                    Email
                                </label>
                                <input
                                    type="email"
                                    value={editSubscriber.email}
                                    onChange={(e) =>
                                        setEditSubscriber((p) => ({
                                            ...p,
                                            email: e.target.value,
                                        }))
                                    }
                                    className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium mb-1">
                                    Status
                                </label>
                                <select
                                    value={editSubscriber.status}
                                    onChange={(e) =>
                                        setEditSubscriber((p) => ({
                                            ...p,
                                            status: e.target.value,
                                        }))
                                    }
                                    className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
                                >
                                    <option value="active">Active</option>
                                    <option value="inactive">Inactive</option>
                                    <option value="bounced">Bounced</option>
                                    <option value="unsubscribed">
                                        Unsubscribed
                                    </option>
                                </select>
                            </div>

                            {Object.keys(
                                editSubscriber.standard_fields || {},
                            ).map((field) => (
                                <div key={field}>
                                    <label className="block text-sm font-medium mb-1 capitalize">
                                        {field.replace(/_/g, " ")}
                                    </label>
                                    <input
                                        type="text"
                                        value={
                                            editSubscriber.standard_fields[
                                                field
                                            ] || ""
                                        }
                                        onChange={(e) =>
                                            setEditSubscriber((p) => ({
                                                ...p,
                                                standard_fields: {
                                                    ...p.standard_fields,
                                                    [field]: e.target.value,
                                                },
                                            }))
                                        }
                                        className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
                                    />
                                </div>
                            ))}

                            {Object.keys(editSubscriber.custom_fields || {})
                                .length > 0 && (
                                <div className="border-t pt-3">
                                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
                                        Custom Fields
                                    </p>
                                    {Object.keys(
                                        editSubscriber.custom_fields,
                                    ).map((field) => (
                                        <div key={field} className="mb-3">
                                            <label className="block text-sm font-medium mb-1 capitalize">
                                                {field.replace(/_/g, " ")}
                                            </label>
                                            <input
                                                type="text"
                                                value={String(
                                                    editSubscriber
                                                        .custom_fields[field] ??
                                                        "",
                                                )}
                                                onChange={(e) =>
                                                    setEditSubscriber((p) => ({
                                                        ...p,
                                                        custom_fields: {
                                                            ...p.custom_fields,
                                                            [field]:
                                                                e.target.value,
                                                        },
                                                    }))
                                                }
                                                className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
                                            />
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        <div className="flex gap-3 px-6 py-4 border-t bg-gray-50 rounded-b-xl">
                            <button
                                onClick={handleSaveEdit}
                                disabled={saving}
                                className="flex-1 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50"
                            >
                                {saving ? "Saving…" : "Save Changes"}
                            </button>
                            <button
                                onClick={() => {
                                    setEditModalOpen(false);
                                    setEditSubscriber(null);
                                }}
                                className="px-4 py-2 border text-sm font-medium rounded-lg hover:bg-gray-100"
                            >
                                Cancel
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
