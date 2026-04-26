import { useEffect, useState, useRef, useCallback } from "react";
import { v4 as uuidv4 } from "uuid";
import API from "../api";
import Papa from "papaparse";
import { useNavigate } from "react-router-dom";

function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value);
  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);
  return debouncedValue;
}

const fmt = (n) => Number(n ?? 0).toLocaleString();
const validateEmail = (email) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

const STATUS_STYLE = {
  active: "bg-green-100 text-green-700",
  inactive: "bg-gray-100  text-gray-600",
  bounced: "bg-red-100   text-red-700",
  unsubscribed: "bg-orange-100 text-orange-700",
};

function ListHealthBar({ total, active }) {
  const rate = total > 0 ? (active / total) * 100 : 0;
  const color =
    rate >= 80 ? "bg-green-500" : rate >= 60 ? "bg-yellow-400" : "bg-red-400";
  return (
    <div className="flex items-center gap-2 min-w-[110px]">
      <div className="flex-1 bg-gray-100 rounded-full h-1.5 overflow-hidden">
        <div
          className={`h-1.5 rounded-full ${color}`}
          style={{ width: `${Math.max(rate, 2)}%` }}
        />
      </div>
      <span className="text-xs text-gray-500 tabular-nums w-10 text-right">
        {rate.toFixed(0)}%
      </span>
    </div>
  );
}

function Pagination({ page, totalPages, total, onChange }) {
  if (totalPages <= 1) return null;
  const max = 5;
  let start = Math.max(1, page - Math.floor(max / 2));
  let end = Math.min(totalPages, start + max - 1);
  if (end - start + 1 < max) start = Math.max(1, end - max + 1);
  const pages = [];
  for (let i = start; i <= end; i++) pages.push(i);
  return (
    <div className="flex items-center justify-between mt-4 px-1">
      <p className="text-sm text-gray-500">
        Page {page} of {totalPages} · <strong>{fmt(total)}</strong> subscribers
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

function ToastContainer({ notifications, onDismiss }) {
  return (
    <div className="fixed top-4 right-4 z-50 space-y-2 pointer-events-none">
      {notifications.map((n) => (
        <div
          key={n.id}
          onClick={() => onDismiss(n.id)}
          className={`pointer-events-auto flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg text-sm font-medium cursor-pointer
            ${n.type === "success" ? "bg-green-600 text-white" : n.type === "error" ? "bg-red-600 text-white" : "bg-gray-800 text-white"}`}
        >
          {n.type === "success" ? "✓" : n.type === "error" ? "✕" : "ℹ"}{" "}
          {n.message}
        </div>
      ))}
    </div>
  );
}

function ProcessingBanner({
  processingJobs,
  showBanner,
  onHide,
  onClearFailed,
  onCleanupStuck,
  showToast,
}) {
  if (!showBanner) return null;
  const activeJobs = Array.from(processingJobs.values()).filter((j) =>
    ["pending", "processing"].includes(j.status),
  );
  const failedJobs = Array.from(processingJobs.values()).filter(
    (j) => j.status === "failed",
  );
  if (!activeJobs.length && !failedJobs.length) return null;

  return (
    <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h4 className="font-semibold text-blue-800 text-sm">
          🚀 Background Processing — {activeJobs.length} active
          {failedJobs.length > 0 ? `, ${failedJobs.length} failed` : ""}
        </h4>
        <div className="flex gap-2">
          {failedJobs.length > 0 && (
            <button
              onClick={onClearFailed}
              className="text-xs bg-red-600 text-white px-2.5 py-1 rounded hover:bg-red-700"
            >
              Clear {failedJobs.length} failed
            </button>
          )}
          {activeJobs.some((j) => j.is_really_stuck) && (
            <button
              onClick={onCleanupStuck}
              className="text-xs bg-orange-600 text-white px-2.5 py-1 rounded hover:bg-orange-700"
            >
              Fix stuck
            </button>
          )}
          <button
            onClick={onHide}
            className="text-xs text-blue-600 hover:text-blue-800"
          >
            Hide
          </button>
        </div>
      </div>
      <div className="space-y-2">
        {activeJobs.map((job) => {
          const processed = job.processed_records || job.processed || 0;
          const total = job.total_records || job.total || 1;
          const progress = Math.min((processed / total) * 100, 100);
          const speed = job.records_per_second || 0;
          const etaMin =
            speed > 0
              ? Math.ceil(Math.max(0, total - processed) / speed / 60)
              : 0;
          const stuck = job.is_really_stuck && progress === 0;
          return (
            <div
              key={job.list_name}
              className={`rounded-lg p-3 border ${stuck ? "bg-orange-50 border-orange-200" : "bg-white border-gray-100"}`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2">
                  <div
                    className={`w-3 h-3 rounded-full ${stuck ? "bg-orange-400 animate-pulse" : "border-2 border-blue-500 border-t-transparent rounded-full animate-spin"}`}
                  />
                  <span className="text-sm font-medium">{job.list_name}</span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full ${stuck ? "bg-orange-100 text-orange-700" : job.status === "pending" ? "bg-yellow-100 text-yellow-700" : "bg-blue-100 text-blue-700"}`}
                  >
                    {stuck
                      ? "May be stuck"
                      : job.status === "pending"
                        ? "Queued"
                        : "Processing"}
                  </span>
                </div>
                <div className="text-right text-xs text-gray-500">
                  {fmt(processed)} / {fmt(total)}
                  {speed > 0 && (
                    <span className="ml-2 text-green-600">
                      ⚡{fmt(speed)}/s
                    </span>
                  )}
                  {etaMin > 0 && <span className="ml-1">· ~{etaMin}m</span>}
                </div>
              </div>
              <div className="bg-gray-100 rounded-full h-2 overflow-hidden">
                <div
                  className={`h-2 rounded-full transition-all duration-700 ${stuck ? "bg-orange-400" : "bg-blue-500"}`}
                  style={{ width: `${Math.max(progress, 2)}%` }}
                />
              </div>
            </div>
          );
        })}
        {failedJobs.map((job) => (
          <div
            key={`failed-${job.list_name}`}
            className="bg-red-50 border border-red-200 rounded-lg p-3 flex items-center justify-between"
          >
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 bg-red-500 rounded-full" />
              <span className="text-sm font-medium text-red-800">
                {job.list_name}
              </span>
              {job.error_message && (
                <span className="text-xs text-red-600 truncate max-w-xs">
                  {job.error_message}
                </span>
              )}
            </div>
            <div className="flex gap-2">
              <button
                onClick={async () => {
                  try {
                    await API.post(
                      `/subscribers/jobs/${job.job_id}/force-retry`,
                    );
                    showToast(
                      `Retry initiated for ${job.list_name}`,
                      "success",
                    );
                    setTimeout(() => window.location.reload(), 1500);
                  } catch (e) {
                    showToast(`Retry failed: ${e.message}`, "error");
                  }
                }}
                className="text-xs bg-orange-600 text-white px-2.5 py-1 rounded hover:bg-orange-700"
              >
                Retry
              </button>
              <button
                onClick={async () => {
                  try {
                    await API.delete(`/subscribers/jobs/${job.job_id}`);
                    showToast(`Cleared: ${job.list_name}`, "success");
                    setTimeout(() => window.location.reload(), 1000);
                  } catch {
                    showToast("Clear failed", "error");
                  }
                }}
                className="text-xs bg-gray-500 text-white px-2.5 py-1 rounded hover:bg-gray-600"
              >
                Clear
              </button>
            </div>
          </div>
        ))}
      </div>
      <p className="text-xs text-blue-500 mt-2">
        💡 Jobs run in background — safe to navigate away
      </p>
    </div>
  );
}

function AddSubscriberModal({
  editingSubscriber,
  subscriberForm,
  setSubscriberForm,
  lists,
  listFields,
  loadingFields,
  isNewList,
  setIsNewList,
  emptyForm,
  handleListSelectForAdd,
  handleAddSubscriber,
  handleEditSubscriber,
  onClose,
}) {
  const isEditing = !!editingSubscriber;
  const stdFields = isEditing
    ? Object.keys(editingSubscriber?.standard_fields || {})
    : listFields.standard.length > 0
      ? listFields.standard
      : ["first_name", "last_name"];
  const custFields = isEditing
    ? Object.keys(editingSubscriber?.custom_fields || {})
    : listFields.custom;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2 className="text-base font-semibold">
            {isEditing ? "Edit Subscriber" : "Add Subscriber"}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl"
          >
            ✕
          </button>
        </div>
        <div className="px-6 py-4 space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Email *</label>
            <input
              type="email"
              value={subscriberForm.email}
              onChange={(e) =>
                setSubscriberForm((p) => ({ ...p, email: e.target.value }))
              }
              className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">List *</label>
            {isEditing ? (
              <input
                value={subscriberForm.list}
                disabled
                className="w-full px-3 py-2 border rounded-lg text-sm bg-gray-50 text-gray-500"
              />
            ) : !isNewList ? (
              <select
                value={subscriberForm.list}
                onChange={(e) => handleListSelectForAdd(e.target.value)}
                className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Select a list…</option>
                {lists.map((l) => (
                  <option key={l._id} value={l._id}>
                    {l._id} ({fmt(l.total_count || l.count)} subs)
                  </option>
                ))}
                <option value="__new__">+ Create new list</option>
              </select>
            ) : (
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="New list name…"
                  autoFocus
                  value={subscriberForm.list}
                  onChange={(e) =>
                    setSubscriberForm((p) => ({ ...p, list: e.target.value }))
                  }
                  className="flex-1 px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
                />
                <button
                  onClick={() => {
                    setIsNewList(false);
                    setSubscriberForm((p) => ({ ...p, list: "" }));
                  }}
                  className="px-3 py-2 text-sm border rounded-lg hover:bg-gray-50"
                >
                  Cancel
                </button>
              </div>
            )}
            {loadingFields && (
              <p className="text-xs text-blue-500 mt-1">Loading list fields…</p>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Status</label>
            <select
              value={subscriberForm.status}
              onChange={(e) =>
                setSubscriberForm((p) => ({ ...p, status: e.target.value }))
              }
              className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
            >
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="bounced">Bounced</option>
              <option value="unsubscribed">Unsubscribed</option>
            </select>
          </div>
          {stdFields.map((field) => (
            <div key={field}>
              <label className="block text-sm font-medium mb-1 capitalize">
                {field.replace(/_/g, " ")}
              </label>
              <input
                type="text"
                value={subscriberForm.standard_fields?.[field] || ""}
                onChange={(e) =>
                  setSubscriberForm((p) => ({
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
          {custFields.length > 0 && (
            <div className="border-t pt-3">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                Custom Fields
              </p>
              {custFields.map((field) => (
                <div key={field} className="mb-3">
                  <label className="block text-sm mb-1 capitalize">
                    {field.replace(/_/g, " ")}
                  </label>
                  <input
                    type="text"
                    value={subscriberForm.custom_fields?.[field] || ""}
                    onChange={(e) =>
                      setSubscriberForm((p) => ({
                        ...p,
                        custom_fields: {
                          ...p.custom_fields,
                          [field]: e.target.value,
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
            onClick={isEditing ? handleEditSubscriber : handleAddSubscriber}
            className="flex-1 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700"
          >
            {isEditing ? "Update" : "Add"} Subscriber
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 border text-sm font-medium rounded-lg hover:bg-gray-100"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────
export default function Subscribers() {
  const navigate = useNavigate();

  const [subscribers, setSubscribers] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [isSearchMode, setIsSearchMode] = useState(false);
  const [currentSearchTerm, setCurrentSearchTerm] = useState("");
  const [searchStats, setSearchStats] = useState(null);
  const [searchWarning, setSearchWarning] = useState("");
  const [searchStrategy] = useState("smart");
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [csvHeaders, setCsvHeaders] = useState([]);
  const [csvData, setCsvData] = useState([]);
  const [listName, setListName] = useState("");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatus, setUploadStatus] = useState("");
  const [uploadStats, setUploadStats] = useState({
    total: 0,
    processed: 0,
    speed: 0,
    method: "",
  });
  const [subscriberPage, setSubscriberPage] = useState(1);
  const [subscriberTotalPages, setSubscriberTotalPages] = useState(1);
  const [subscriberTotal, setSubscriberTotal] = useState(0);
  const [fieldMap, setFieldMap] = useState({ rows: [] });
  const [lists, setLists] = useState([]);
  const [selectedListName, setSelectedListName] = useState("");
  const [selectedSubscribers, setSelectedSubscribers] = useState([]);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingSubscriber, setEditingSubscriber] = useState(null);
  const [processingJobs, setProcessingJobs] = useState(new Map());
  const [showProcessingBanner, setShowProcessingBanner] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [listFields, setListFields] = useState({ standard: [], custom: [] });
  const [loadingFields, setLoadingFields] = useState(false);
  const [isNewList, setIsNewList] = useState(false);
  const [error, setError] = useState("");

  const pollingIntervalRef = useRef(null);

  const emptyForm = {
    email: "",
    list: "",
    status: "active",
    standard_fields: { first_name: "", last_name: "" },
    custom_fields: {},
  };
  const [subscriberForm, setSubscriberForm] = useState(emptyForm);

  const debouncedSearchTerm = useDebounce(searchTerm, 300);

  // ── toast ───────────────────────────────────────────────────────────────────
  const showToast = useCallback((message, type = "info") => {
    const id = uuidv4();
    setNotifications((prev) => [...prev, { id, message, type }]);
    setTimeout(
      () => setNotifications((prev) => prev.filter((n) => n.id !== id)),
      4000,
    );
  }, []);

  const dismissToast = useCallback(
    (id) => setNotifications((prev) => prev.filter((n) => n.id !== id)),
    [],
  );

  // ── polling ─────────────────────────────────────────────────────────────────
  const stopPollingJobs = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
  }, []);

  const startPollingJobs = useCallback(() => {
    stopPollingJobs();
    pollingIntervalRef.current = setInterval(async () => {
      try {
        const response = await API.get("/subscribers/jobs/status");
        const jobs = response.data.jobs || [];
        const updatedJobs = new Map();
        let hasActive = false;
        jobs.forEach((job) => {
          if (job.status === "completed") return;
          updatedJobs.set(job.list_name, job);
          if (["pending", "processing", "failed"].includes(job.status))
            hasActive = true;
        });
        setProcessingJobs(updatedJobs);
        setShowProcessingBanner(hasActive || updatedJobs.size > 0);
        if (!hasActive) {
          stopPollingJobs();
          fetchLists();
        }
      } catch (e) {
        console.error("Polling error:", e);
      }
    }, 3000);
  }, [stopPollingJobs]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const check = async () => {
      try {
        const response = await API.get("/subscribers/jobs/status");
        const jobs = response.data.jobs || [];
        const updatedJobs = new Map();
        let hasActive = false;
        jobs.forEach((job) => {
          if (job.status === "completed") return;
          updatedJobs.set(job.list_name, job);
          if (["pending", "processing", "failed"].includes(job.status))
            hasActive = true;
        });
        setProcessingJobs(updatedJobs);
        setShowProcessingBanner(hasActive);
        if (hasActive) startPollingJobs();
      } catch (e) {
        console.error("Initial job check failed:", e);
      }
    };
    check();
    return () => stopPollingJobs();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── auto-search ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (debouncedSearchTerm.length >= 2 || debouncedSearchTerm.length === 0)
      fetchAllSubscribers(1, debouncedSearchTerm, statusFilter);
  }, [debouncedSearchTerm, statusFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── fetchers ─────────────────────────────────────────────────────────────────
  const fetchAllSubscribers = async (page = 1, search = "", status = "") => {
    try {
      setLoading(true);
      setIsSearchMode(search.trim().length > 0);
      setCurrentSearchTerm(search);
      const params = { page, limit: 50, search_mode: searchStrategy };
      if (search) params.search = search;
      if (status) params.status = status;
      const res = await API.get("/subscribers/search", { params });
      setSubscribers(res.data.subscribers || []);
      const { pagination, performance } = res.data;
      setSubscriberPage(page);
      setSubscriberTotalPages(pagination?.total_pages || 1);
      setSubscriberTotal(pagination?.total || 0);
      setSearchStats(performance);
      setSearchWarning(
        search && pagination?.total > 10000
          ? "Large result set — try a more specific search"
          : "",
      );
    } catch {
      setSearchWarning("Search failed. Please try again.");
      setError("Search failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const fetchLists = async () => {
    try {
      const res = await API.get("/subscribers/lists");
      setLists(res.data || []);
    } catch {
      setLists([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLists();
    fetchAllSubscribers(1, "", "");
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── CSV auto-mapping ─────────────────────────────────────────────────────────
  const ALL_STANDARD_FIELDS = [
    "first_name",
    "last_name",
    "phone",
    "company",
    "country",
    "city",
    "state",
    "zip_code",
    "language",
    "timezone",
    "gender",
    "date_of_birth",
    "website",
    "job_title",
  ];

  const norm = (s) => (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");

  const autoMapHeaders = (headers, data) => {
    const sample = data.slice(0, 5);
    const aliases = {
      fname: "first_name",
      firstname: "first_name",
      forename: "first_name",
      lname: "last_name",
      lastname: "last_name",
      surname: "last_name",
      mob: "phone",
      mobile: "phone",
      cell: "phone",
      telephone: "phone",
      org: "company",
      organisation: "company",
      organization: "company",
      zip: "zip_code",
      postal: "zip_code",
      postcode: "zip_code",
      dob: "date_of_birth",
      birthday: "date_of_birth",
      birthdate: "date_of_birth",
      lang: "language",
      locale: "language",
      jobtitle: "job_title",
      title: "job_title",
      role: "job_title",
      position: "job_title",
      web: "website",
      url: "website",
      site: "website",
    };
    return headers.map((header, colIdx) => {
      const n = norm(header);
      const sampleValue =
        sample.map((r) => r[colIdx]).find((v) => v?.trim()) || "";
      if (["email", "emailaddress", "e_mail", "mail"].includes(n))
        return {
          csvHeader: header,
          sampleValue,
          mappedTo: "email",
          fieldType: "string",
        };
      for (const sf of ALL_STANDARD_FIELDS)
        if (norm(sf) === n || norm(sf.replace(/_/g, "")) === n)
          return {
            csvHeader: header,
            sampleValue,
            mappedTo: `standard.${sf}`,
            fieldType: "string",
          };
      if (aliases[n])
        return {
          csvHeader: header,
          sampleValue,
          mappedTo: `standard.${aliases[n]}`,
          fieldType: "string",
        };
      let guessedType = "string";
      if (sampleValue) {
        if (/^\d{4}-\d{2}-\d{2}|\d{2}[\/\-]\d{2}[\/\-]\d{4}/.test(sampleValue))
          guessedType = "date";
        else if (/^(true|false|yes|no|1|0)$/i.test(sampleValue.trim()))
          guessedType = "boolean";
        else if (/^-?\d+(\.\d+)?$/.test(sampleValue.trim()))
          guessedType = "number";
      }
      return {
        csvHeader: header,
        sampleValue,
        mappedTo: `custom.${header.trim().toLowerCase().replace(/\s+/g, "_")}`,
        fieldType: guessedType,
      };
    });
  };

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    Papa.parse(file, {
      complete: (results) => {
        if (results.data?.length > 0) {
          const headers = results.data[0];
          const data = results.data
            .slice(1)
            .filter((r) => r.some((c) => c?.trim()));
          setCsvHeaders(headers);
          setCsvData(data);
          setFieldMap({ rows: autoMapHeaders(headers, data) });
          setUploadStatus("ready");
        } else {
          showToast("CSV file appears to be empty or invalid", "error");
          setUploadStatus("");
        }
      },
      error: () => {
        showToast("Failed to parse CSV file", "error");
        setUploadStatus("");
      },
    });
  };

  const resetUploadModal = () => {
    setCsvHeaders([]);
    setCsvData([]);
    setListName("");
    setUploadProgress(0);
    setUploadStatus("");
    setFieldMap({ rows: [] });
  };

  // ── Upload — chunked ─────────────────────────────────────────────────────────
  // Each chunk is ~5 000 rows ≈ 2 MB JSON, well within the 50 MB Nginx limit.
  // Chunk 0 creates the job and sends field_registry.
  // Chunks 1-N send job_id so the backend appends to the same job on disk.
  // After all chunks are uploaded, /background-upload/start/{job_id} triggers processing.
  const UPLOAD_CHUNK_SIZE = 25_000;

  const handleUploadList = async () => {
    if (!listName.trim()) {
      showToast("List name is required", "error");
      return;
    }

    const emailRow = fieldMap.rows.find((r) => r.mappedTo === "email");
    const emailColIdx = csvHeaders.indexOf(emailRow?.csvHeader ?? "");
    if (emailColIdx === -1) {
      showToast("Map a column to email before uploading", "error");
      return;
    }

    // Build field registry
    const standardFields = [];
    const customFields = {};
    fieldMap.rows.forEach((row) => {
      if (row.mappedTo === "email" || row.mappedTo === "skip") return;
      if (row.mappedTo.startsWith("standard."))
        standardFields.push(row.mappedTo.replace("standard.", ""));
      else if (row.mappedTo.startsWith("custom."))
        customFields[row.mappedTo.replace("custom.", "")] = {
          type: row.fieldType || "string",
        };
    });

    // Build subscriber rows
    const subscribers = csvData
      .map((row) => {
        const email = String(row[emailColIdx] ?? "")
          .trim()
          .toLowerCase();
        if (!email || !validateEmail(email)) return null;
        const fields = {};
        fieldMap.rows.forEach((mapRow) => {
          if (mapRow.mappedTo === "email" || mapRow.mappedTo === "skip") return;
          const val = row[csvHeaders.indexOf(mapRow.csvHeader)];
          if (val !== undefined && val !== "") {
            const key = mapRow.mappedTo.startsWith("standard.")
              ? mapRow.mappedTo.replace("standard.", "")
              : mapRow.mappedTo.replace("custom.", "");
            fields[key] = val;
          }
        });
        return { email, status: "active", fields };
      })
      .filter(Boolean);

    if (subscribers.length === 0) {
      showToast("No valid email addresses found in the CSV", "error");
      return;
    }

    const uploadingFor = listName.trim();
    const uploadingCount = subscribers.length;

    // Close modal immediately
    setShowUploadModal(false);
    resetUploadModal();

    setProcessingJobs((prev) =>
      new Map(prev).set(uploadingFor, {
        list_name: uploadingFor,
        status: "pending",
        processed: 0,
        total: uploadingCount,
      }),
    );
    setShowProcessingBanner(true);

    // Split into chunks
    const chunks = [];
    for (let i = 0; i < subscribers.length; i += UPLOAD_CHUNK_SIZE)
      chunks.push(subscribers.slice(i, i + UPLOAD_CHUNK_SIZE));

    let jobId = null;

    try {
      for (let i = 0; i < chunks.length; i++) {
        const isFirst = i === 0;
        const body = {
          list_name: uploadingFor,
          subscribers: chunks[i],
          processing_mode: "background",
          ...(isFirst
            ? {
                field_registry: {
                  list_name: uploadingFor,
                  standard: standardFields,
                  custom: customFields,
                },
              }
            : { job_id: jobId }),
        };

        const response = await API.post("/subscribers/background-upload", body);

        if (isFirst) {
          jobId = response.data?.job_id;
          setProcessingJobs((prev) => {
            const next = new Map(prev);
            next.set(uploadingFor, {
              list_name: uploadingFor,
              status: "pending",
              job_id: jobId,
              processed: 0,
              total: uploadingCount,
            });
            return next;
          });
        }
      }

      // All chunks on disk — trigger background processing
      await API.post(`/subscribers/background-upload/start/${jobId}`, null, {
        params: { total_records: uploadingCount },
      });

      startPollingJobs();
      showToast(
        `Upload started for "${uploadingFor}" — ${fmt(uploadingCount)} rows processing`,
        "success",
      );
      fetchLists();
    } catch (err) {
      setProcessingJobs((prev) => {
        const next = new Map(prev);
        next.delete(uploadingFor);
        return next;
      });
      showToast(
        err.response?.data?.detail?.message ||
          err.response?.data?.detail ||
          "Upload failed — please try again",
        "error",
      );
    }
  };

  // ── subscriber CRUD ───────────────────────────────────────────────────────────
  const handleAddSubscriber = async () => {
    if (!subscriberForm.email || !validateEmail(subscriberForm.email)) {
      showToast("Valid email is required", "error");
      return;
    }
    if (!subscriberForm.list) {
      showToast("List is required", "error");
      return;
    }
    try {
      await API.post("/subscribers/", subscriberForm);
      showToast("Subscriber added", "success");
      setShowAddModal(false);
      setSubscriberForm(emptyForm);
      fetchLists();
      fetchAllSubscribers(subscriberPage, currentSearchTerm, statusFilter);
    } catch (err) {
      showToast(
        err.response?.data?.detail || "Failed to add subscriber",
        "error",
      );
    }
  };

  const handleEditSubscriber = async () => {
    try {
      await API.put(`/subscribers/${editingSubscriber._id}`, subscriberForm);
      showToast("Subscriber updated", "success");
      setShowAddModal(false);
      setEditingSubscriber(null);
      setSubscriberForm(emptyForm);
      fetchAllSubscribers(subscriberPage, currentSearchTerm, statusFilter);
    } catch (err) {
      showToast(err.response?.data?.detail || "Update failed", "error");
    }
  };

  const handleDeleteSubscriber = async (id) => {
    if (!confirm("Delete this subscriber?")) return;
    try {
      await API.delete(`/subscribers/${id}`);
      showToast("Subscriber deleted", "success");
      fetchLists();
      fetchAllSubscribers(subscriberPage, currentSearchTerm, statusFilter);
    } catch {
      showToast("Delete failed", "error");
    }
  };

  const openEditModal = (sub) => {
    setEditingSubscriber(sub);
    setSubscriberForm({
      email: sub.email,
      list: sub.list,
      status: sub.status,
      standard_fields: sub.standard_fields || {},
      custom_fields: sub.custom_fields || {},
    });
    setShowAddModal(true);
  };

  const handleListSelectForAdd = async (val) => {
    if (val === "__new__") {
      setIsNewList(true);
      setSubscriberForm((p) => ({ ...p, list: "" }));
      return;
    }
    setSubscriberForm((p) => ({ ...p, list: val }));
    if (val) {
      setLoadingFields(true);
      try {
        const res = await API.get(`/subscribers/lists/${val}/fields`);
        setListFields({
          standard: res.data.standard || [],
          custom: res.data.custom || [],
        });
      } catch {
        setListFields({ standard: [], custom: [] });
      } finally {
        setLoadingFields(false);
      }
    }
  };

  const handleExportList = async (name) => {
    try {
      const response = await API.get(`/subscribers/lists/${name}/export`, {
        responseType: "blob",
      });
      const url = window.URL.createObjectURL(
        new Blob([response.data], { type: "text/csv" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `${name}_subscribers.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch {
      showToast("Export failed", "error");
    }
  };

  const handleDeleteList = async (name) => {
    const list = lists.find((l) => l._id === name);
    const count = list?.total_count || list?.count || 0;
    const job = processingJobs.get(name);
    const msg = job
      ? `⚠️ "${name}" is currently being processed.\n\nDeleting will stop the upload and remove all ${fmt(count)} existing subscribers.\n\nContinue?`
      : `Delete "${name}" and all ${fmt(count)} subscribers?\n\nThis cannot be undone.`;
    if (!confirm(msg)) return;
    try {
      await API.delete(`/subscribers/lists/${name}?force=true`);
      showToast(`List "${name}" deleted`, "success");
      fetchLists();
    } catch (err) {
      showToast(err.response?.data?.detail || "Delete failed", "error");
    }
  };

  const handleClearFailed = async () => {
    try {
      await API.delete("/subscribers/jobs/clear-all");
      showToast("Failed jobs cleared", "success");
      setProcessingJobs(new Map());
      setShowProcessingBanner(false);
    } catch {
      showToast("Clear failed", "error");
    }
  };

  const handleCleanupStuck = async () => {
    if (!confirm("Force cleanup stuck jobs? They will be marked as failed."))
      return;
    try {
      await API.post("/subscribers/jobs/cleanup-stuck");
      showToast("Cleanup initiated", "success");
      setTimeout(() => window.location.reload(), 1500);
    } catch {
      showToast("Cleanup failed", "error");
    }
  };

  const totalAcrossLists = lists.reduce(
    (s, l) => s + (l.total_count || l.count || 0),
    0,
  );
  const totalActive = lists.reduce((s, l) => s + (l.active_count || 0), 0);

  return (
    <div className="space-y-6">
      <ToastContainer notifications={notifications} onDismiss={dismissToast} />
      <ProcessingBanner
        processingJobs={processingJobs}
        showBanner={showProcessingBanner}
        onHide={() => setShowProcessingBanner(false)}
        onClearFailed={handleClearFailed}
        onCleanupStuck={handleCleanupStuck}
        showToast={showToast}
      />

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm flex items-center justify-between">
          {error}
          <button
            onClick={() => setError("")}
            className="text-red-400 hover:text-red-600"
          >
            ✕
          </button>
        </div>
      )}

      <div className="flex flex-wrap gap-3">
        <button
          onClick={() => setShowUploadModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 transition-colors"
        >
          📤 Upload CSV
        </button>
        <button
          onClick={() => {
            setShowAddModal(true);
            setEditingSubscriber(null);
            setSubscriberForm(emptyForm);
          }}
          className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white text-sm font-semibold rounded-lg hover:bg-green-700 transition-colors"
        >
          ➕ Add Subscriber
        </button>
        <button
          onClick={fetchLists}
          className="flex items-center gap-2 px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 transition-colors text-gray-600"
        >
          🔄 Refresh
        </button>
      </div>

      {/* Lists */}
      <section className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div>
            <h2 className="text-sm font-semibold text-gray-700">
              Subscriber Lists
            </h2>
            {lists.length > 0 && (
              <p className="text-xs text-gray-400 mt-0.5">
                {lists.length} lists · {fmt(totalAcrossLists)} total ·{" "}
                {fmt(totalActive)} active (
                {totalAcrossLists > 0
                  ? ((totalActive / totalAcrossLists) * 100).toFixed(0)
                  : 0}
                % health)
              </p>
            )}
          </div>
        </div>
        {loading && lists.length === 0 ? (
          <div className="flex items-center justify-center py-12 gap-2 text-gray-400 text-sm">
            <div className="animate-spin h-4 w-4 border-2 border-gray-300 border-t-blue-500 rounded-full" />
            Loading lists…
          </div>
        ) : lists.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-3xl mb-2">📋</p>
            <p className="text-sm font-medium text-gray-700">
              No subscriber lists yet
            </p>
            <p className="text-xs text-gray-400 mt-1 mb-4">
              Upload a CSV to create your first list
            </p>
            <button
              onClick={() => setShowUploadModal(true)}
              className="px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700"
            >
              Upload CSV
            </button>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  List Name
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Total
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Active
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider min-w-[140px]">
                  Health
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {lists.map((list, i) => {
                const job = processingJobs.get(list._id);
                const isProcessing =
                  job && ["pending", "processing"].includes(job.status);
                const isFailed = job && job.status === "failed";
                const total = list.total_count || list.count || 0;
                const active = list.active_count || 0;
                return (
                  <tr
                    key={`${list._id}-${i}`}
                    className="hover:bg-gray-50 transition-colors"
                  >
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        <span
                          className="font-medium text-gray-900 truncate max-w-[180px]"
                          title={list._id}
                        >
                          {list._id}
                        </span>
                        {isProcessing && (
                          <span className="inline-flex items-center gap-1 text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">
                            <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse" />
                            {job.status === "pending" ? "Queued" : "Processing"}
                          </span>
                        )}
                        {isFailed && (
                          <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full">
                            Failed
                          </span>
                        )}
                      </div>
                      {isProcessing && (job.processed || 0) > 0 && (
                        <p className="text-xs text-blue-600 mt-0.5">
                          +{fmt(job.processed)} being added
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3.5 text-right tabular-nums font-medium text-gray-800">
                      {fmt(total)}
                    </td>
                    <td className="px-4 py-3.5 text-right tabular-nums text-green-600 font-medium">
                      {fmt(active)}
                    </td>
                    <td className="px-4 py-3.5">
                      <ListHealthBar total={total} active={active} />
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() =>
                            navigate(`/subscribers/list/${list._id}`)
                          }
                          className="px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600 transition-colors"
                        >
                          View
                        </button>
                        <button
                          onClick={() => handleExportList(list._id)}
                          className="px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600 transition-colors"
                        >
                          Export
                        </button>
                        {isFailed && (
                          <button
                            onClick={async () => {
                              try {
                                const res = await API.post(
                                  `/subscribers/jobs/${job.job_id}/force-retry`,
                                );
                                if (res.data?.can_retry === false) {
                                  // Chunk files gone — tell user to re-upload
                                  showToast(
                                    `Cannot retry "${job.list_name}" — chunk files were cleaned up. Please re-upload the CSV.`,
                                    "error",
                                  );
                                } else {
                                  showToast(
                                    `Retry started for "${job.list_name}"`,
                                    "success",
                                  );
                                  startPollingJobs();
                                }
                              } catch (e) {
                                showToast(
                                  `Retry failed: ${e.response?.data?.detail || e.message}`,
                                  "error",
                                );
                              }
                            }}
                            className="text-xs bg-orange-600 text-white px-2.5 py-1 rounded hover:bg-orange-700"
                          >
                            Retry
                          </button>
                        )}
                        <button
                          onClick={() => handleDeleteList(list._id)}
                          className="px-3 py-1.5 text-xs font-medium border border-red-200 rounded-lg hover:bg-red-50 text-red-600 transition-colors"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
            {lists.length > 1 && (
              <tfoot>
                <tr className="bg-gray-50 border-t-2 border-gray-200">
                  <td className="px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Total ({lists.length} lists)
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums font-bold text-gray-800">
                    {fmt(totalAcrossLists)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums font-bold text-green-600">
                    {fmt(totalActive)}
                  </td>
                  <td className="px-4 py-3">
                    <ListHealthBar
                      total={totalAcrossLists}
                      active={totalActive}
                    />
                  </td>
                  <td />
                </tr>
              </tfoot>
            )}
          </table>
        )}
      </section>

      {/* All Subscribers */}
      <section className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-gray-100">
          <div>
            <h2 className="text-sm font-semibold text-gray-700">
              All Subscribers
            </h2>
            {subscriberTotal > 0 && (
              <p className="text-xs text-gray-400 mt-0.5">
                {isSearchMode
                  ? `${fmt(subscriberTotal)} results`
                  : `${fmt(subscriberTotal)} total`}
                {searchStats?.search_time_ms &&
                  ` · ${searchStats.search_time_ms}ms`}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
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
            <div className="relative">
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs">
                🔍
              </span>
              <input
                type="text"
                placeholder="Search by email, name…"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-7 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 w-52"
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
          </div>
        </div>
        {searchWarning && (
          <div className="mx-5 mt-3 px-3 py-2 bg-yellow-50 border border-yellow-200 text-yellow-700 rounded-lg text-xs">
            ⚠️ {searchWarning}
          </div>
        )}
        <div className="overflow-x-auto">
          {loading ? (
            <div className="flex items-center justify-center py-12 gap-2 text-gray-400 text-sm">
              <div className="animate-spin h-4 w-4 border-2 border-gray-300 border-t-blue-500 rounded-full" />
              {isSearchMode ? "Searching…" : "Loading…"}
            </div>
          ) : subscribers.length === 0 ? (
            <div className="py-12 text-center text-gray-400 text-sm">
              {searchTerm || statusFilter ? (
                <>
                  <p className="text-2xl mb-2">🔍</p>
                  <p className="font-medium text-gray-600">
                    No subscribers match your filters
                  </p>
                  <button
                    onClick={() => {
                      setSearchTerm("");
                      setStatusFilter("");
                    }}
                    className="text-xs text-blue-600 mt-2 hover:underline"
                  >
                    Clear filters
                  </button>
                </>
              ) : (
                <>
                  <p className="text-2xl mb-2">👥</p>
                  <p className="font-medium text-gray-600">
                    No subscribers yet
                  </p>
                  <p className="text-xs mt-1">Upload a CSV to get started</p>
                </>
              )}
            </div>
          ) : (
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
                    List
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-24">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {subscribers.map((sub) => (
                  <tr
                    key={sub._id}
                    className="hover:bg-gray-50 transition-colors"
                  >
                    <td className="px-5 py-3 font-medium text-gray-900">
                      {sub.email}
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {[
                        sub.standard_fields?.first_name,
                        sub.standard_fields?.last_name,
                      ]
                        .filter(Boolean)
                        .join(" ") || <span className="text-gray-300">—</span>}
                    </td>
                    <td className="px-4 py-3 text-gray-500">{sub.list}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLE[sub.status] || STATUS_STYLE.inactive}`}
                      >
                        {sub.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => openEditModal(sub)}
                          className="text-xs text-blue-600 hover:underline font-medium"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleDeleteSubscriber(sub._id)}
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
          )}
        </div>
        {subscribers.length > 0 && (
          <div className="px-5 py-3 border-t border-gray-100">
            <Pagination
              page={subscriberPage}
              totalPages={subscriberTotalPages}
              total={subscriberTotal}
              onChange={(p) =>
                fetchAllSubscribers(p, currentSearchTerm, statusFilter)
              }
            />
          </div>
        )}
      </section>

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-3xl max-h-[92vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b shrink-0">
              <h2 className="text-base font-semibold">Upload Subscribers</h2>
              <button
                onClick={() => {
                  setShowUploadModal(false);
                  resetUploadModal();
                }}
                className="text-gray-400 hover:text-gray-600 text-xl"
              >
                ✕
              </button>
            </div>
            <div className="overflow-y-auto flex-1 px-6 py-5 space-y-5">
              {uploadStatus === "" && (
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Choose CSV File
                  </label>
                  <input
                    type="file"
                    accept=".csv"
                    onChange={handleFileUpload}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                  />
                  <p className="text-xs text-gray-400 mt-1">
                    First row must be column headers. All columns will be
                    auto-mapped.
                  </p>
                </div>
              )}
              {uploadStatus === "ready" && csvHeaders.length > 0 && (
                <>
                  <div>
                    <label className="block text-sm font-medium mb-1">
                      List Name *
                    </label>
                    <input
                      type="text"
                      value={listName}
                      onChange={(e) => setListName(e.target.value)}
                      placeholder="e.g. newsletter-2025"
                      autoFocus
                      className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-sm font-medium">
                        Field Mapping
                        <span className="ml-2 text-xs text-gray-400 font-normal">
                          — auto-mapped, review and adjust if needed
                        </span>
                      </p>
                      <span className="text-xs text-gray-400">
                        {csvData.length.toLocaleString()} rows
                      </span>
                    </div>
                    <div className="border border-gray-200 rounded-lg overflow-hidden">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="bg-gray-50 border-b text-xs font-medium text-gray-500 uppercase tracking-wider">
                            <th className="px-3 py-2 text-left w-1/4">
                              CSV Column
                            </th>
                            <th className="px-3 py-2 text-left w-1/4">
                              Sample Value
                            </th>
                            <th className="px-3 py-2 text-left w-5/12">
                              Maps To
                            </th>
                            <th className="px-3 py-2 text-left w-1/6">Type</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {fieldMap.rows.map((row, idx) => {
                            const isEmail = row.mappedTo === "email";
                            const isSkip = row.mappedTo === "skip";
                            return (
                              <tr
                                key={idx}
                                className={
                                  isSkip
                                    ? "bg-gray-50 opacity-50"
                                    : isEmail
                                      ? "bg-blue-50"
                                      : ""
                                }
                              >
                                <td className="px-3 py-2 font-medium text-gray-800 whitespace-nowrap">
                                  {isEmail && (
                                    <span className="mr-1 text-blue-500">
                                      ✉
                                    </span>
                                  )}
                                  {row.csvHeader}
                                </td>
                                <td
                                  className="px-3 py-2 text-gray-400 text-xs truncate max-w-[120px]"
                                  title={row.sampleValue}
                                >
                                  {row.sampleValue || (
                                    <span className="italic">empty</span>
                                  )}
                                </td>
                                <td className="px-3 py-2">
                                  <select
                                    value={row.mappedTo}
                                    onChange={(e) => {
                                      const r = [...fieldMap.rows];
                                      r[idx] = {
                                        ...r[idx],
                                        mappedTo: e.target.value,
                                      };
                                      setFieldMap({ rows: r });
                                    }}
                                    className="w-full px-2 py-1 border rounded text-xs focus:ring-2 focus:ring-blue-500 bg-white"
                                  >
                                    <option value="email">
                                      ✉ email (required)
                                    </option>
                                    <optgroup label="Standard Fields">
                                      {ALL_STANDARD_FIELDS.map((sf) => (
                                        <option
                                          key={sf}
                                          value={`standard.${sf}`}
                                        >
                                          {sf.replace(/_/g, " ")}
                                        </option>
                                      ))}
                                    </optgroup>
                                    <optgroup label="Custom Field">
                                      <option
                                        value={`custom.${row.csvHeader.trim().toLowerCase().replace(/\s+/g, "_")}`}
                                      >
                                        custom:{" "}
                                        {row.csvHeader
                                          .trim()
                                          .toLowerCase()
                                          .replace(/\s+/g, "_")}
                                      </option>
                                    </optgroup>
                                    <option value="skip">
                                      — skip this column
                                    </option>
                                  </select>
                                </td>
                                <td className="px-3 py-2">
                                  {row.mappedTo.startsWith("custom.") ? (
                                    <select
                                      value={row.fieldType || "string"}
                                      onChange={(e) => {
                                        const r = [...fieldMap.rows];
                                        r[idx] = {
                                          ...r[idx],
                                          fieldType: e.target.value,
                                        };
                                        setFieldMap({ rows: r });
                                      }}
                                      className="w-full px-2 py-1 border rounded text-xs focus:ring-2 focus:ring-blue-500 bg-white"
                                    >
                                      <option value="string">Text</option>
                                      <option value="number">Number</option>
                                      <option value="boolean">Boolean</option>
                                      <option value="date">Date</option>
                                    </select>
                                  ) : (
                                    <span className="text-xs text-gray-300">
                                      —
                                    </span>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                    {!fieldMap.rows.some((r) => r.mappedTo === "email") && (
                      <p className="text-xs text-red-500 mt-1.5">
                        ⚠ No column mapped to email
                      </p>
                    )}
                  </div>
                  <div className="border border-gray-200 rounded-lg overflow-hidden">
                    <div className="px-3 py-2 bg-gray-50 border-b text-xs font-medium text-gray-600">
                      Raw preview — first 3 rows
                    </div>
                    <div className="overflow-x-auto max-h-28">
                      <table className="w-full text-xs">
                        <thead>
                          <tr>
                            {csvHeaders.map((h, i) => (
                              <th
                                key={i}
                                className="px-2 py-1.5 text-left bg-gray-50 border-b font-medium text-gray-600 whitespace-nowrap"
                              >
                                {h}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {csvData.slice(0, 3).map((row, r) => (
                            <tr key={r} className="border-b last:border-0">
                              {row.map((cell, c) => (
                                <td
                                  key={c}
                                  className="px-2 py-1.5 whitespace-nowrap text-gray-700"
                                >
                                  {cell}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              )}
            </div>
            {uploadStatus === "ready" && (
              <div className="flex gap-3 px-6 py-4 border-t bg-gray-50 rounded-b-xl shrink-0">
                <button
                  onClick={handleUploadList}
                  disabled={
                    !fieldMap.rows.some((r) => r.mappedTo === "email") ||
                    !listName.trim()
                  }
                  className="flex-1 py-2.5 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  🚀 Start Upload ({fmt(csvData.length)} rows)
                </button>
                <button
                  onClick={() => {
                    setShowUploadModal(false);
                    resetUploadModal();
                  }}
                  className="px-5 py-2.5 border text-sm font-medium rounded-lg hover:bg-gray-100"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Add/Edit Modal */}
      {showAddModal && (
        <AddSubscriberModal
          editingSubscriber={editingSubscriber}
          subscriberForm={subscriberForm}
          setSubscriberForm={setSubscriberForm}
          lists={lists}
          listFields={listFields}
          loadingFields={loadingFields}
          isNewList={isNewList}
          setIsNewList={setIsNewList}
          emptyForm={emptyForm}
          handleListSelectForAdd={handleListSelectForAdd}
          handleAddSubscriber={handleAddSubscriber}
          handleEditSubscriber={handleEditSubscriber}
          onClose={() => {
            setShowAddModal(false);
            setEditingSubscriber(null);
            setSubscriberForm(emptyForm);
            setListFields({ standard: [], custom: [] });
            setIsNewList(false);
          }}
        />
      )}
    </div>
  );
}
