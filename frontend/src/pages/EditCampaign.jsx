// frontend/src/pages/EditCampaign.jsx
import { useState, useEffect, useCallback, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import API from "../api";
import ProviderErrorBanner from "../components/ProviderErrorBanner";
import { useSettings } from "../contexts/SettingsContext";

// ── Helpers ───────────────────────────────────────────────────────────────────
const fmt = (n) => Number(n ?? 0).toLocaleString();

const STEPS = [
  { id: 1, label: "Details", icon: "✉️", desc: "Name, subject & sender" },
  { id: 2, label: "Audience", icon: "👥", desc: "Lists & segments" },
  { id: 3, label: "Template", icon: "🎨", desc: "Pick your template" },
  { id: 4, label: "Mapping", icon: "🔗", desc: "Field variables" },
  { id: 5, label: "Review", icon: "💾", desc: "Preview & save" },
];

// ── StepNav ───────────────────────────────────────────────────────────────────
function StepNav({ current, steps, onGoto, completedSteps }) {
  return (
    <div className="flex items-center gap-0 overflow-x-auto pb-1">
      {steps.map((step, i) => {
        const isDone = completedSteps.includes(step.id);
        const isActive = current === step.id;
        const isClickable = isDone || isActive;
        return (
          <div key={step.id} className="flex items-center">
            <button
              onClick={() => isClickable && onGoto(step.id)}
              disabled={!isClickable}
              className={`flex flex-col items-center gap-1 px-3 py-2 rounded-xl transition-all duration-200 min-w-[76px] ${
                isActive
                  ? "bg-indigo-600 text-white shadow-lg shadow-indigo-200 scale-105"
                  : isDone
                    ? "bg-green-50 text-green-700 hover:bg-green-100 border border-green-200"
                    : "text-gray-300 cursor-not-allowed"
              }`}
            >
              <span className="text-sm">
                {isDone && !isActive ? "✓" : step.icon}
              </span>
              <span className="text-xs font-semibold whitespace-nowrap">
                {step.label}
              </span>
            </button>
            {i < steps.length - 1 && (
              <div
                className={`h-px w-4 md:w-6 mx-1 ${
                  completedSteps.includes(step.id)
                    ? "bg-green-300"
                    : "bg-gray-200"
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Small UI helpers ──────────────────────────────────────────────────────────
const inputCls = (err) =>
  `w-full border rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 transition ${
    err ? "border-red-400 bg-red-50" : "border-gray-200"
  }`;

function InputField({ label, hint, required, error, children }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1.5">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
        {hint && (
          <span className="text-gray-400 font-normal ml-1 text-xs">
            ({hint})
          </span>
        )}
      </label>
      {children}
      {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
    </div>
  );
}

function ListItem({ name, count, activeCount, selected, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center justify-between px-4 py-3 rounded-xl border-2 text-left transition-all ${
        selected
          ? "border-indigo-500 bg-indigo-50"
          : "border-gray-200 hover:border-gray-300 bg-white"
      }`}
    >
      <div className="min-w-0 flex-1">
        <p
          className={`text-sm font-medium truncate ${selected ? "text-indigo-800" : "text-gray-800"}`}
        >
          {name}
        </p>
        <p className="text-xs text-gray-400">
          {count != null ? `${fmt(count)} total` : ""}
          {activeCount != null && count !== activeCount
            ? ` · ${fmt(activeCount)} active`
            : ""}
        </p>
      </div>
      <div
        className={`w-5 h-5 rounded-md border-2 flex items-center justify-center flex-shrink-0 transition-all ${
          selected ? "bg-indigo-600 border-indigo-600" : "border-gray-300"
        }`}
      >
        {selected && <span className="text-white text-xs">✓</span>}
      </div>
    </button>
  );
}

// ── Locked step overlay (for limited / sender_only edit modes) ────────────────
function LockedOverlay({ locked, children }) {
  if (!locked) return children;
  return (
    <div className="relative">
      <div className="pointer-events-none opacity-40 select-none">
        {children}
      </div>
      <div className="absolute inset-0 flex items-center justify-center rounded-xl">
        <span className="bg-white border border-gray-300 rounded-lg px-4 py-2 text-sm text-gray-500 font-medium shadow">
          🔒 Locked while campaign is paused
        </span>
      </div>
    </div>
  );
}

// ── Main EditCampaign ─────────────────────────────────────────────────────────
export default function EditCampaign() {
  const { t, formatDate } = useSettings();
  const navigate = useNavigate();
  const { id: campaignId } = useParams();

  const [step, setStep] = useState(1);
  const [completedSteps, setCompletedSteps] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [loadingCampaign, setLoadingCampaign] = useState(true);
  const [errors, setErrors] = useState({});
  const [globalError, setGlobalError] = useState("");
  const [saveSuccess, setSaveSuccess] = useState(false);

  // ── NEW: editMode state ───────────────────────────────────────────────────
  const [originalStatus, setOriginalStatus] = useState("draft");
  const [originalPauseReason, setOriginalPauseReason] = useState("");
  const [providerError, setProviderError] = useState(null);

  // Data
  const [lists, setLists] = useState([]);
  const [segments, setSegments] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [senderProfiles, setSenderProfiles] = useState([]);
  const [dynamicFields, setDynamicFields] = useState([]);
  const [availableFields, setAvailableFields] = useState({
    universal: ["email"],
    standard: [],
    custom: [],
  });
  const [fieldsLoading, setFieldsLoading] = useState(false);
  const [previewHtml, setPreviewHtml] = useState("");
  const [previewMode, setPreviewMode] = useState("desktop");

  // Form state
  const [form, setForm] = useState({
    title: "",
    subject: "",
    sender_name: "",
    sender_email: "",
    reply_to: "",
    target_lists: [],
    target_segments: [],
    template_id: "",
    field_map: {},
    fallback_values: {},
    status: "draft",
  });

  const set = (key, val) => setForm((f) => ({ ...f, [key]: val }));
  const setMap = (key, val) =>
    setForm((f) => ({ ...f, field_map: { ...f.field_map, [key]: val } }));
  const setFallback = (key, val) =>
    setForm((f) => ({
      ...f,
      fallback_values: { ...f.fallback_values, [key]: val },
    }));

  const selectedTemplate = templates.find(
    (t) => (t._id || t.id) === form.template_id,
  );

  // ── editMode derived from originalStatus + originalPauseReason (NEW 6c) ──
  const editMode = useMemo(() => {
    const LOCKED = [
      "sending",
      "queued",
      "completed",
      "sent",
      "stopped",
      "cancelled",
      "failed",
    ];
    if (LOCKED.includes(originalStatus)) return "readonly";
    if (originalStatus === "paused") {
      return originalPauseReason === "provider_error_auto_pause"
        ? "sender_only"
        : "limited";
    }
    return "full";
  }, [originalStatus, originalPauseReason]);

  // ── Redirect readonly campaigns (NEW 6d) ──────────────────────────────────
  useEffect(() => {
    if (!loadingCampaign && editMode === "readonly") {
      navigate(`/analytics/campaign/${campaignId}`, { replace: true });
    }
  }, [editMode, loadingCampaign, campaignId, navigate]);

  // ── Load campaign + supporting data (NEW: 6a + 6b) ───────────────────────
  useEffect(() => {
    setLoadingCampaign(true);
    Promise.all([
      API.get(`/campaigns/${campaignId}`),
      API.get("/subscribers/lists"),
      API.get("/segments").catch(() => ({ data: [] })),
      API.get("/templates"),
      API.get("/settings/sender-profiles").catch(() => ({ data: [] })),
    ])
      .then(([campRes, listsRes, segRes, tplRes, spRes]) => {
        const camp = campRes.data;

        // ── NEW (6a + 6b): store editMode-driving state ───────────────────
        setOriginalStatus(camp.status || "draft");
        setOriginalPauseReason(camp.pause_reason || "");
        setProviderError(camp.provider_error || null);

        setForm({
          title: camp.title || "",
          subject: camp.subject || "",
          sender_name: camp.sender_name || "",
          sender_email: camp.sender_email || "",
          reply_to: camp.reply_to || "",
          target_lists: camp.target_lists || [],
          target_segments: camp.target_segments || [],
          template_id: camp.template_id || "",
          field_map: camp.field_map || {},
          fallback_values: camp.fallback_values || {},
          status: camp.status || "draft",
        });
        setLists(Array.isArray(listsRes.data) ? listsRes.data : []);
        const segData = segRes.data?.segments || segRes.data || [];
        setSegments(Array.isArray(segData) ? segData : []);
        setTemplates(Array.isArray(tplRes.data) ? tplRes.data : []);
        setSenderProfiles(Array.isArray(spRes.data) ? spRes.data : []);
        setCompletedSteps([1, 2, 3, 4]);
      })
      .catch((err) =>
        setGlobalError(err.response?.data?.detail || "Failed to load campaign"),
      )
      .finally(() => setLoadingCampaign(false));
  }, [campaignId]);

  // ── Template preview + fields ─────────────────────────────────────────────
  useEffect(() => {
    if (!selectedTemplate) {
      setPreviewHtml("");
      setDynamicFields([]);
      return;
    }
    const cj = selectedTemplate.content_json || {};
    let html = selectedTemplate.html_content || "";
    if (!html) {
      if (cj.mode === "html" && cj.content) html = cj.content;
      else if (cj.mode === "drag-drop" && cj.blocks)
        html = cj.blocks.map((b) => b.content || "").join("\n");
      else if (cj.mode === "visual" && cj.content) html = cj.content;
    }
    setPreviewHtml(html || "<p>No preview available</p>");
    setFieldsLoading(true);
    API.get(`/templates/${selectedTemplate._id || selectedTemplate.id}/fields`)
      .then((r) => setDynamicFields(Array.isArray(r.data) ? r.data : []))
      .catch(() => setDynamicFields([]))
      .finally(() => setFieldsLoading(false));
  }, [selectedTemplate]);

  // ── Available fields from audience ────────────────────────────────────────
  useEffect(() => {
    if (!form.target_lists.length && !form.target_segments.length) {
      setAvailableFields({ universal: ["email"], standard: [], custom: [] });
      return;
    }
    const payload = {};
    if (form.target_lists.length) payload.listIds = form.target_lists;
    if (form.target_segments.length) payload.segmentIds = form.target_segments;
    API.post("/subscribers/analyze-fields", payload)
      .then((r) =>
        setAvailableFields(
          r.data || { universal: ["email"], standard: [], custom: [] },
        ),
      )
      .catch(() => {});
  }, [form.target_lists, form.target_segments]);

  // ── Auto-map new fields when template changes ────────────────────────────
  useEffect(() => {
    if (!dynamicFields.length) return;
    const norm = (s) => (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");
    const lookup = {};
    availableFields.universal.forEach((f) => {
      lookup[norm(f)] = f;
    });
    availableFields.standard.forEach((f) => {
      lookup[norm(f)] = `standard.${f}`;
    });
    availableFields.custom.forEach((f) => {
      lookup[norm(f)] = `custom.${f}`;
    });
    const all = [
      ...availableFields.universal,
      ...availableFields.standard.map((f) => `standard.${f}`),
      ...availableFields.custom.map((f) => `custom.${f}`),
    ];
    setForm((prev) => {
      const next = { ...prev.field_map };
      dynamicFields.forEach((field) => {
        if (next[field]?.trim()) return;
        const n = norm(field);
        if (lookup[n]) {
          next[field] = lookup[n];
          return;
        }
        const partial = all.find((c) => {
          const stripped = c.replace(/^(standard|custom)\./, "");
          const cv = norm(stripped);
          return cv.includes(n) || n.includes(cv);
        });
        if (partial) next[field] = partial;
      });
      return { ...prev, field_map: next };
    });
  }, [dynamicFields, availableFields]);

  // ── Validation ────────────────────────────────────────────────────────────
  const validateStep = (s) => {
    const errs = {};
    if (s === 1) {
      if (!form.title.trim()) errs.title = "Campaign title is required";
      if (!form.subject.trim()) errs.subject = "Subject line is required";
      if (!form.sender_name.trim())
        errs.sender_name = "Sender name is required";
      if (!form.sender_email.trim())
        errs.sender_email = "Sender email is required";
    }
    if (s === 2) {
      if (!form.target_lists.length && !form.target_segments.length)
        errs.audience = "Select at least one list or segment";
    }
    if (s === 3) {
      if (!form.template_id) errs.template_id = "Select a template";
    }
    return errs;
  };

  const handleNext = () => {
    const errs = validateStep(step);
    if (Object.keys(errs).length) {
      setErrors(errs);
      return;
    }
    setErrors({});
    setCompletedSteps((prev) => [...new Set([...prev, step])]);
    setStep((s) => s + 1);
  };

  // ── Save ──────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    setGlobalError("");
    setSaveSuccess(false);
    setSubmitting(true);
    try {
      await API.put(`/campaigns/${campaignId}`, form);
      setSaveSuccess(true);
      setTimeout(() => navigate("/campaigns"), 1200);
    } catch (err) {
      setGlobalError(err.response?.data?.detail || "Failed to save campaign");
    } finally {
      setSubmitting(false);
    }
  };

  // ── Computed ──────────────────────────────────────────────────────────────
  const totalAudienceSize =
    lists
      .filter((l) => form.target_lists.includes(l._id || l.name))
      .reduce((s, l) => s + (l.total_count || l.count || 0), 0) +
    segments
      .filter((sg) => form.target_segments.includes(sg._id))
      .reduce((s, sg) => s + (sg.subscriber_count || 0), 0);

  const unmappedCount = dynamicFields.filter(
    (f) => !form.field_map[f]?.trim(),
  ).length;
  const isNonDraft =
    originalStatus !== "draft" && originalStatus !== "scheduled";

  // ── Save button label (NEW 6g) ────────────────────────────────────────────
  const saveLabel =
    editMode === "sender_only"
      ? "Save Sender Settings"
      : editMode === "limited"
        ? "Save Changes"
        : submitting
          ? "⏳ Saving…"
          : saveSuccess
            ? "✅ Saved!"
            : "💾 Save Changes";

  // ── Loading skeleton ──────────────────────────────────────────────────────
  if (loadingCampaign) {
    return (
      <div className="max-w-3xl mx-auto space-y-6 animate-pulse">
        <div className="h-10 bg-gray-200 rounded-xl w-48" />
        <div className="flex gap-2">
          {STEPS.map((s) => (
            <div key={s.id} className="h-14 bg-gray-200 rounded-xl flex-1" />
          ))}
        </div>
        <div className="h-96 bg-gray-200 rounded-2xl" />
      </div>
    );
  }

  // ── Step renderers ────────────────────────────────────────────────────────
  const renderStep1 = () => (
    <div className="space-y-6">
      <div className="flex items-center gap-3 mb-2">
        <div className="w-10 h-10 bg-indigo-100 rounded-xl flex items-center justify-center text-xl">
          ✉️
        </div>
        <div>
          <h2 className="text-lg font-bold text-gray-900">Campaign Details</h2>
          <p className="text-sm text-gray-500">
            Core identity and sender information
          </p>
        </div>
      </div>

      {/* Non-draft warning — only for non-error states (NEW 6e replaces this for error-paused) */}
      {isNonDraft && editMode !== "sender_only" && editMode !== "limited" && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3">
          <span className="text-amber-500 text-lg flex-shrink-0">⚠️</span>
          <div>
            <p className="text-sm font-semibold text-amber-800">
              Editing a "{originalStatus}" campaign
            </p>
            <p className="text-xs text-amber-700 mt-0.5">
              Changes will update the campaign record. Emails already sent are
              unaffected.
            </p>
          </div>
        </div>
      )}

      {/* Sender profiles */}
      {senderProfiles.length > 0 && (
        <div>
          <p className="text-sm font-medium text-gray-700 mb-2">
            Saved Sender Profiles
          </p>
          <div className="flex flex-wrap gap-2">
            {senderProfiles.map((sp) => (
              <button
                key={sp._id || sp.name}
                onClick={() => {
                  set("sender_name", sp.sender_name || sp.name || "");
                  set("sender_email", sp.sender_email || sp.email || "");
                  set("reply_to", sp.reply_to || "");
                }}
                className="text-xs px-3 py-1.5 border border-gray-200 rounded-lg hover:border-indigo-400 hover:bg-indigo-50 transition-colors"
              >
                {sp.name || sp.sender_name}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-4">
        <InputField label={t('campaign.form.name')} required error={errors.title}>
          {/* NEW 6h: disabled in sender_only mode */}
          <input
            className={`${inputCls(errors.title)} ${editMode === "sender_only" ? "bg-gray-100 cursor-not-allowed" : ""}`}
            placeholder="e.g., Summer Sale 2025"
            value={form.title}
            onChange={(e) => set("title", e.target.value)}
            disabled={editMode === "sender_only"}
          />
        </InputField>

        <InputField label={t('campaign.form.subject')} required error={errors.subject}>
          {/* NEW 6h: disabled in sender_only mode */}
          <input
            className={`${inputCls(errors.subject)} ${editMode === "sender_only" ? "bg-gray-100 cursor-not-allowed" : ""}`}
            placeholder="e.g., Don't miss our biggest sale ever 🎉"
            value={form.subject}
            onChange={(e) => set("subject", e.target.value)}
            disabled={editMode === "sender_only"}
          />
        </InputField>
      </div>

      {/* Sender fields — always editable in sender_only */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <InputField label={t('campaign.form.fromName')} required error={errors.sender_name}>
          <input
            className={inputCls(errors.sender_name)}
            placeholder="e.g., Acme Team"
            value={form.sender_name}
            onChange={(e) => set("sender_name", e.target.value)}
          />
        </InputField>
        <InputField label={t('campaign.form.fromEmail')} required error={errors.sender_email}>
          <input
            type="email"
            className={inputCls(errors.sender_email)}
            placeholder="hello@yourcompany.com"
            value={form.sender_email}
            onChange={(e) => set("sender_email", e.target.value)}
          />
        </InputField>
      </div>

      <InputField label="Reply-To" hint="optional, defaults to sender email">
        <input
          type="email"
          className={inputCls(false)}
          placeholder="replies@yourcompany.com"
          value={form.reply_to}
          onChange={(e) => set("reply_to", e.target.value)}
        />
      </InputField>
    </div>
  );

  const renderStep2 = () => (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-green-100 rounded-xl flex items-center justify-center text-xl">
            👥
          </div>
          <div>
            <h2 className="text-lg font-bold text-gray-900">Target Audience</h2>
            <p className="text-sm text-gray-500">
              Choose who receives this campaign
            </p>
          </div>
        </div>
        {totalAudienceSize > 0 && (
          <div className="bg-indigo-50 border border-indigo-200 rounded-xl px-4 py-2 text-center">
            <p className="text-lg font-bold text-indigo-800">
              {fmt(totalAudienceSize)}
            </p>
            <p className="text-xs text-indigo-600">recipients</p>
          </div>
        )}
      </div>

      {errors.audience && (
        <p className="text-sm text-red-500 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
          {errors.audience}
        </p>
      )}

      {/* Lists */}
      {lists.length > 0 && (
        <div>
          <p className="text-sm font-semibold text-gray-700 mb-2">
            Subscriber Lists ({lists.length})
          </p>
          <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
            {lists.map((l) => {
              const id = l._id || l.name;
              return (
                <ListItem
                  key={id}
                  name={l.name || l._id}
                  count={l.total_count || l.count}
                  activeCount={l.active_count}
                  selected={form.target_lists.includes(id)}
                  onClick={() =>
                    set(
                      "target_lists",
                      form.target_lists.includes(id)
                        ? form.target_lists.filter((x) => x !== id)
                        : [...form.target_lists, id],
                    )
                  }
                />
              );
            })}
          </div>
        </div>
      )}

      {/* Segments */}
      {segments.length > 0 && (
        <div>
          <p className="text-sm font-semibold text-gray-700 mb-2">
            Segments ({segments.length})
          </p>
          <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
            {segments.map((sg) => (
              <ListItem
                key={sg._id}
                name={sg.name}
                count={sg.subscriber_count}
                selected={form.target_segments.includes(sg._id)}
                onClick={() =>
                  set(
                    "target_segments",
                    form.target_segments.includes(sg._id)
                      ? form.target_segments.filter((x) => x !== sg._id)
                      : [...form.target_segments, sg._id],
                  )
                }
              />
            ))}
          </div>
        </div>
      )}

      {lists.length === 0 && segments.length === 0 && (
        <div className="text-center py-8 text-gray-400">
          <p>No lists or segments found.</p>
        </div>
      )}
    </div>
  );

  const renderStep3 = () => (
    <div className="space-y-6">
      <div className="flex items-center gap-3 mb-2">
        <div className="w-10 h-10 bg-purple-100 rounded-xl flex items-center justify-center text-xl">
          🎨
        </div>
        <div>
          <h2 className="text-lg font-bold text-gray-900">Email Template</h2>
          <p className="text-sm text-gray-500">
            Pick the template for this campaign
          </p>
        </div>
      </div>

      {errors.template_id && (
        <p className="text-sm text-red-500 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
          {errors.template_id}
        </p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-72 overflow-y-auto pr-1">
        {templates.map((t) => {
          const tid = t._id || t.id;
          const isSelected = form.template_id === tid;
          return (
            <button
              key={tid}
              onClick={() => set("template_id", tid)}
              className={`text-left p-4 rounded-xl border-2 transition-all ${
                isSelected
                  ? "border-indigo-500 bg-indigo-50"
                  : "border-gray-200 hover:border-gray-300"
              }`}
            >
              <p
                className={`text-sm font-semibold truncate ${isSelected ? "text-indigo-800" : "text-gray-800"}`}
              >
                {t.name || "Untitled"}
              </p>
              {t.subject && (
                <p className="text-xs text-gray-500 truncate mt-0.5">
                  {t.subject}
                </p>
              )}
              {isSelected && (
                <span className="inline-block mt-2 text-xs bg-indigo-200 text-indigo-800 px-2 py-0.5 rounded-full">
                  ✓ Selected
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );

  const renderStep4 = () => (
    <div className="space-y-6">
      <div className="flex items-center gap-3 mb-2">
        <div className="w-10 h-10 bg-blue-100 rounded-xl flex items-center justify-center text-xl">
          🔗
        </div>
        <div>
          <h2 className="text-lg font-bold text-gray-900">Field Mapping</h2>
          <p className="text-sm text-gray-500">
            Connect template variables to subscriber data
          </p>
        </div>
      </div>

      {fieldsLoading && (
        <div className="text-center py-8 text-gray-400 animate-pulse">
          Analysing template fields…
        </div>
      )}

      {!fieldsLoading && dynamicFields.length === 0 && (
        <div className="text-center py-8 text-gray-400">
          <p>No dynamic fields found in the selected template.</p>
        </div>
      )}

      {!fieldsLoading && dynamicFields.length > 0 && (
        <div className="space-y-4">
          {unmappedCount > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-sm text-amber-700">
              ⚠️ {unmappedCount} field{unmappedCount !== 1 ? "s" : ""} not yet
              mapped. Unmapped fields will render as empty.
            </div>
          )}
          {dynamicFields.map((field) => {
            const allOptions = [
              ...availableFields.universal,
              ...availableFields.standard.map((f) => `standard.${f}`),
              ...availableFields.custom.map((f) => `custom.${f}`),
            ];
            return (
              <div key={field} className="flex items-center gap-3 flex-wrap">
                <div className="bg-gray-100 border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono text-gray-800 flex-shrink-0">
                  {`{{${field}}}`}
                </div>
                <span className="text-gray-400">→</span>
                <select
                  value={form.field_map[field] || ""}
                  onChange={(e) => setMap(field, e.target.value)}
                  className="flex-1 border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                >
                  <option value="">— not mapped —</option>
                  <option value="__EMPTY__">Leave empty</option>
                  <option value="__DEFAULT__">Use fallback value</option>
                  <optgroup label="Universal">
                    {availableFields.universal.map((f) => (
                      <option key={f} value={f}>
                        {f}
                      </option>
                    ))}
                  </optgroup>
                  {availableFields.standard.length > 0 && (
                    <optgroup label="Standard">
                      {availableFields.standard.map((f) => (
                        <option key={f} value={`standard.${f}`}>
                          {f}
                        </option>
                      ))}
                    </optgroup>
                  )}
                  {availableFields.custom.length > 0 && (
                    <optgroup label="Custom">
                      {availableFields.custom.map((f) => (
                        <option key={f} value={`custom.${f}`}>
                          {f}
                        </option>
                      ))}
                    </optgroup>
                  )}
                </select>
                <input
                  type="text"
                  placeholder="Fallback…"
                  value={form.fallback_values[field] || ""}
                  onChange={(e) => setFallback(field, e.target.value)}
                  className="w-32 border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );

  const renderStep5 = () => (
    <div className="space-y-6">
      <div className="flex items-center gap-3 mb-2">
        <div className="w-10 h-10 bg-emerald-100 rounded-xl flex items-center justify-center text-xl">
          💾
        </div>
        <div>
          <h2 className="text-lg font-bold text-gray-900">Review & Save</h2>
          <p className="text-sm text-gray-500">
            Check everything looks right before saving
          </p>
        </div>
      </div>

      {/* Summary */}
      <div className="bg-gray-50 rounded-xl p-5 space-y-3 text-sm">
        {[
          ["Title", form.title],
          ["Subject", form.subject],
          [
            "Sender",
            form.sender_name
              ? `${form.sender_name} <${form.sender_email}>`
              : form.sender_email,
          ],
          ["Reply-To", form.reply_to || form.sender_email],
          [
            "Lists",
            form.target_lists.length
              ? `${form.target_lists.length} list(s)`
              : "—",
          ],
          [
            "Segments",
            form.target_segments.length
              ? `${form.target_segments.length} segment(s)`
              : "—",
          ],
          [
            "Template",
            templates.find((t) => (t._id || t.id) === form.template_id)?.name ||
              "—",
          ],
          [
            "Mapped fields",
            `${dynamicFields.length - unmappedCount} / ${dynamicFields.length}`,
          ],
        ].map(([label, value]) => (
          <div key={label} className="flex gap-3">
            <span className="text-gray-500 w-28 flex-shrink-0">{label}</span>
            <span className="text-gray-900 font-medium">{value}</span>
          </div>
        ))}
      </div>

      {/* Preview */}
      {previewHtml && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <p className="text-sm font-semibold text-gray-700">Preview</p>
            <div className="flex gap-1">
              {["desktop", "tablet", "mobile"].map((m) => (
                <button
                  key={m}
                  onClick={() => setPreviewMode(m)}
                  className={`text-xs px-2.5 py-1 rounded-lg border transition-all ${
                    previewMode === m
                      ? "border-indigo-400 bg-indigo-50 text-indigo-700"
                      : "border-gray-200 text-gray-500 hover:bg-gray-50"
                  }`}
                >
                  {m === "desktop" ? "🖥" : m === "tablet" ? "📱" : "📲"}
                </button>
              ))}
            </div>
          </div>
          <div className="border border-gray-200 rounded-xl overflow-hidden">
            <div
              className="mx-auto transition-all duration-300"
              style={{
                maxWidth:
                  previewMode === "desktop"
                    ? "100%"
                    : previewMode === "tablet"
                      ? 640
                      : 375,
              }}
            >
              <iframe
                srcDoc={previewHtml}
                title="Email Preview"
                className="w-full border-0"
                style={{ height: 400 }}
              />
            </div>
          </div>
        </div>
      )}

      {globalError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
          ⚠ {globalError}
        </div>
      )}

      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={submitting || saveSuccess}
          className="px-8 py-3 bg-indigo-600 text-white font-bold text-sm rounded-xl hover:bg-indigo-700 shadow-md shadow-indigo-200 disabled:opacity-60 transition-all"
        >
          {saveLabel}
        </button>
      </div>

      {isNonDraft && editMode === "full" && (
        <p className="text-xs text-amber-600 text-center">
          ⚠ This campaign is "{originalStatus}" — changes update metadata only.
          Sent emails are unaffected.
        </p>
      )}
    </div>
  );

  const stepRenderers = [
    renderStep1,
    renderStep2,
    renderStep3,
    renderStep4,
    renderStep5,
  ];

  // ── Main render ───────────────────────────────────────────────────────────
  return (
    <div className="max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-2 mb-0.5">
            <h1 className="text-2xl font-bold text-gray-900">{t('campaign.form.edit')}</h1>
            {originalStatus !== "draft" && (
              <span
                className={`text-xs px-2.5 py-1 rounded-full font-semibold ${
                  originalStatus === "sending"
                    ? "bg-blue-100 text-blue-800"
                    : originalStatus === "completed" ||
                        originalStatus === "sent"
                      ? "bg-green-100 text-green-800"
                      : originalStatus === "paused"
                        ? originalPauseReason === "provider_error_auto_pause"
                          ? "bg-red-100 text-red-800"
                          : "bg-orange-100 text-orange-800"
                        : "bg-gray-100 text-gray-600"
                }`}
              >
                {originalStatus === "paused" &&
                originalPauseReason === "provider_error_auto_pause"
                  ? "⚠️ Paused — Error"
                  : originalStatus}
              </span>
            )}
          </div>
          <p className="text-sm text-gray-500">
            Step {step} of {STEPS.length}
          </p>
        </div>
        <button
          onClick={() => navigate("/campaigns")}
          className="text-sm text-gray-500 hover:text-gray-700 border border-gray-200 px-3 py-1.5 rounded-lg hover:bg-gray-50"
        >
          ← Campaigns
        </button>
      </div>

      {/* NEW (6e): Edit-mode banners above the step nav ─────────────────────── */}
      {editMode === "sender_only" && (
        <>
          <ProviderErrorBanner
            providerError={providerError}
            isCampaign={true}
            campaignId={campaignId}
            onFixed={() => {
              // Re-fetch so providerError clears and banner updates
              API.get(`/campaigns/${campaignId}`)
                .then((r) => {
                  setProviderError(r.data.provider_error || null);
                  setOriginalPauseReason(r.data.pause_reason || "");
                })
                .catch(() => {});
            }}
            onResumed={() => navigate("/campaigns")}
          />
          <div className="mb-6 bg-amber-50 border border-amber-300 rounded-xl p-4 text-sm text-amber-800">
            <strong>⚠️ Sender-only edit mode.</strong> This campaign paused due
            to a provider error. Only sender details can be changed. Update them
            below, then resume from the campaign report.
          </div>
        </>
      )}

      {editMode === "limited" && (
        <div className="mb-6 bg-amber-50 border border-amber-300 rounded-xl p-4 text-sm text-amber-800">
          <strong>⏸ Campaign is paused.</strong> You can update sender and
          subject details. Audience and template cannot be changed while sending
          is in progress.
        </div>
      )}

      {/* Step nav — hidden in sender_only (only step 1 matters) (NEW 6e) */}
      {editMode !== "sender_only" && (
        <>
          <div className="mb-8">
            <StepNav
              current={step}
              steps={STEPS}
              onGoto={(s) => setStep(s)}
              completedSteps={completedSteps}
            />
          </div>
          <div className="mb-8 bg-gray-100 rounded-full h-1.5">
            <div
              className="bg-indigo-500 h-1.5 rounded-full transition-all duration-500"
              style={{ width: `${((step - 1) / (STEPS.length - 1)) * 100}%` }}
            />
          </div>
        </>
      )}

      {/* Card */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-8">
        {/* Step 1 always shown */}
        {(editMode === "sender_only" || step === 1) && renderStep1()}

        {/* Steps 2-5 hidden in sender_only (NEW 6e, 6f) */}
        {editMode !== "sender_only" && (
          <>
            {step === 2 && (
              <LockedOverlay locked={editMode === "limited"}>
                {renderStep2()}
              </LockedOverlay>
            )}
            {step === 3 && (
              <LockedOverlay locked={editMode === "limited"}>
                {renderStep3()}
              </LockedOverlay>
            )}
            {step === 4 && renderStep4()}
            {step === 5 && renderStep5()}
          </>
        )}

        {/* Navigation buttons */}
        {editMode === "sender_only" ? (
          /* sender_only: single save button instead of wizard nav */
          <div className="mt-8 pt-6 border-t border-gray-100 flex justify-end">
            <button
              onClick={handleSave}
              disabled={submitting || saveSuccess}
              className="px-8 py-3 bg-indigo-600 text-white font-bold text-sm rounded-xl hover:bg-indigo-700 shadow-md shadow-indigo-200 disabled:opacity-60"
            >
              {saveLabel}
            </button>
          </div>
        ) : (
          step < 5 && (
            <div className="flex items-center justify-between mt-8 pt-6 border-t border-gray-100">
              <button
                onClick={() => setStep((s) => s - 1)}
                disabled={step === 1}
                className="px-5 py-2.5 text-sm font-medium text-gray-600 border border-gray-200 rounded-xl hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed"
              >
                ← Back
              </button>
              <div className="flex items-center gap-3">
                <span className="text-xs text-gray-400">
                  {step} / {STEPS.length}
                </span>
                <button
                  onClick={handleNext}
                  className="px-6 py-2.5 text-sm font-bold text-white bg-indigo-600 rounded-xl hover:bg-indigo-700 shadow-md shadow-indigo-200"
                >
                  Continue →
                </button>
              </div>
            </div>
          )
        )}
      </div>
    </div>
  );
}
