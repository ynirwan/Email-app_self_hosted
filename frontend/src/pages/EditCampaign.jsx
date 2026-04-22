import { useState, useEffect, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import API from "../api";

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
                className={`h-px w-4 md:w-6 mx-1 ${completedSteps.includes(step.id) ? "bg-green-300" : "bg-gray-200"}`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── InputField ────────────────────────────────────────────────────────────────
function InputField({ label, required, hint, error, children }) {
  return (
    <div className="space-y-1.5">
      <label className="flex items-center gap-1.5 text-sm font-semibold text-gray-700">
        {label}
        {required && <span className="text-red-400">*</span>}
        {hint && (
          <span className="text-xs font-normal text-gray-400 ml-1">
            — {hint}
          </span>
        )}
      </label>
      {children}
      {error && <p className="text-xs text-red-500">⚠ {error}</p>}
    </div>
  );
}

const inputCls = (error) =>
  `w-full px-3.5 py-2.5 rounded-xl border text-sm transition-all focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-indigo-400 ${
    error
      ? "border-red-300 bg-red-50"
      : "border-gray-200 bg-white hover:border-gray-300"
  }`;

// ── TemplateCard ──────────────────────────────────────────────────────────────
function TemplateCard({ template, selected, onClick }) {
  const mode = template.content_json?.mode || "legacy";
  const modeColors = {
    html: "bg-blue-100 text-blue-700",
    "drag-drop": "bg-purple-100 text-purple-700",
    visual: "bg-green-100 text-green-700",
    legacy: "bg-gray-100 text-gray-600",
  };
  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-4 rounded-xl border-2 transition-all hover:shadow-md group ${
        selected
          ? "border-indigo-500 bg-indigo-50 shadow-indigo-100 shadow-lg"
          : "border-gray-200 hover:border-indigo-300 bg-white"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p
            className={`text-sm font-semibold truncate ${selected ? "text-indigo-800" : "text-gray-800"}`}
          >
            {template.name || "Untitled"}
          </p>
          {template.subject && (
            <p className="text-xs text-gray-400 truncate mt-0.5">
              {template.subject}
            </p>
          )}
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <span
            className={`text-xs px-2 py-0.5 rounded-full font-medium ${modeColors[mode]}`}
          >
            {mode}
          </span>
          {selected && <span className="text-indigo-600">✓</span>}
        </div>
      </div>
    </button>
  );
}

// ── AudienceCard ──────────────────────────────────────────────────────────────
function AudienceCard({
  name,
  count,
  activeCount,
  selected,
  onClick,
  type = "list",
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-3 w-full p-3 rounded-xl border-2 text-left transition-all ${
        selected
          ? "border-indigo-500 bg-indigo-50"
          : "border-gray-200 hover:border-gray-300 hover:bg-gray-50 bg-white"
      }`}
    >
      <div
        className={`w-8 h-8 rounded-lg flex items-center justify-center text-sm flex-shrink-0 ${selected ? "bg-indigo-100" : "bg-gray-100"}`}
      >
        {type === "list" ? "📋" : "🎯"}
      </div>
      <div className="flex-1 min-w-0">
        <p
          className={`text-sm font-semibold truncate ${selected ? "text-indigo-800" : "text-gray-800"}`}
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

// ── Main EditCampaign ─────────────────────────────────────────────────────────
export default function EditCampaign() {
  const navigate = useNavigate();
  const { id: campaignId } = useParams();

  const [step, setStep] = useState(1);
  const [completedSteps, setCompletedSteps] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [loadingCampaign, setLoadingCampaign] = useState(true);
  const [errors, setErrors] = useState({});
  const [globalError, setGlobalError] = useState("");
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [originalStatus, setOriginalStatus] = useState("draft");

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

  // ── Load campaign ─────────────────────────────────────────────────────────
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
        setOriginalStatus(camp.status || "draft");
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
        // Mark all steps as completed (existing campaign)
        setCompletedSteps([1, 2, 3, 4]);
      })
      .catch((err) =>
        setGlobalError(err.response?.data?.detail || "Failed to load campaign"),
      )
      .finally(() => setLoadingCampaign(false));
  }, [campaignId]);

  // Template preview + fields
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

  // Available fields from audience
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

  // Auto-map new fields when template changes (keep existing mappings)
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
        if (next[field]?.trim()) return; // keep existing mapping
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

  // ── Loading state ─────────────────────────────────────────────────────────
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

      {isNonDraft && (
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

      <InputField label="Campaign Title" required error={errors.title}>
        <input
          className={inputCls(errors.title)}
          placeholder="e.g., April Newsletter, Product Launch..."
          value={form.title}
          onChange={(e) => set("title", e.target.value)}
          autoFocus
        />
      </InputField>

      <InputField
        label="Subject Line"
        required
        hint="what subscribers see in their inbox"
        error={errors.subject}
      >
        <input
          className={inputCls(errors.subject)}
          placeholder="e.g., 🚀 Big news — you're going to love this"
          value={form.subject}
          onChange={(e) => set("subject", e.target.value)}
        />
        <p className="text-xs text-gray-400">
          {form.subject.length} chars
          {form.subject.length > 60 && " · may truncate on mobile"}
        </p>
      </InputField>

      {senderProfiles.length > 0 && (
        <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            Quick fill from sender profile
          </p>
          <div className="flex flex-wrap gap-2">
            {senderProfiles.map((sp) => (
              <button
                key={sp._id || sp.id}
                onClick={() => {
                  set("sender_name", sp.name || sp.sender_name || "");
                  set("sender_email", sp.email || sp.sender_email || "");
                  set(
                    "reply_to",
                    sp.reply_to || sp.email || sp.sender_email || "",
                  );
                }}
                className="px-3 py-1.5 text-xs font-medium bg-white border border-gray-200 rounded-lg hover:border-indigo-300 hover:text-indigo-700 transition-colors"
              >
                {sp.name || sp.sender_name}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <InputField label="Sender Name" required error={errors.sender_name}>
          <input
            className={inputCls(errors.sender_name)}
            placeholder="e.g., Acme Team"
            value={form.sender_name}
            onChange={(e) => set("sender_name", e.target.value)}
          />
        </InputField>
        <InputField label="Sender Email" required error={errors.sender_email}>
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
            <p className="text-xl font-bold text-indigo-700">
              {fmt(totalAudienceSize)}
            </p>
            <p className="text-xs text-indigo-500">estimated recipients</p>
          </div>
        )}
      </div>

      {errors.audience && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-700">
          ⚠ {errors.audience}
        </div>
      )}

      {lists.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-700">
              📋 Subscriber Lists
              {form.target_lists.length > 0 && (
                <span className="ml-2 px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded-full text-xs">
                  {form.target_lists.length} selected
                </span>
              )}
            </h3>
            {form.target_lists.length > 0 && (
              <button
                onClick={() => set("target_lists", [])}
                className="text-xs text-gray-400 hover:text-red-500"
              >
                Clear
              </button>
            )}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 max-h-64 overflow-y-auto pr-1">
            {lists.map((l) => {
              const id = l._id || l.name;
              return (
                <AudienceCard
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
                  type="list"
                />
              );
            })}
          </div>
        </div>
      )}

      {segments.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            🎯 Segments
            {form.target_segments.length > 0 && (
              <span className="ml-2 px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded-full text-xs">
                {form.target_segments.length} selected
              </span>
            )}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 max-h-52 overflow-y-auto pr-1">
            {segments.map((sg) => (
              <AudienceCard
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
                type="segment"
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );

  const renderStep3 = () => (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-purple-100 rounded-xl flex items-center justify-center text-xl">
          🎨
        </div>
        <div>
          <h2 className="text-lg font-bold text-gray-900">Email Template</h2>
          <p className="text-sm text-gray-500">
            Select the template to use for this campaign
          </p>
        </div>
      </div>

      {errors.template_id && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-700">
          ⚠ {errors.template_id}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-72 overflow-y-auto pr-1">
        {templates.map((t) => (
          <TemplateCard
            key={t._id || t.id}
            template={t}
            selected={form.template_id === (t._id || t.id)}
            onClick={() => set("template_id", t._id || t.id)}
          />
        ))}
      </div>

      {selectedTemplate && previewHtml && (
        <div className="border border-gray-200 rounded-xl overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200">
            <p className="text-sm font-semibold text-gray-700">
              Preview — {selectedTemplate.name}
            </p>
            <div className="flex gap-1">
              {["desktop", "tablet", "mobile"].map((m) => (
                <button
                  key={m}
                  onClick={() => setPreviewMode(m)}
                  className={`px-2.5 py-1 text-xs rounded-lg font-medium transition-all ${
                    previewMode === m
                      ? "bg-indigo-600 text-white"
                      : "text-gray-400 hover:bg-gray-200"
                  }`}
                >
                  {m === "desktop" ? "🖥" : m === "tablet" ? "📟" : "📱"}
                </button>
              ))}
            </div>
          </div>
          <div className="bg-gray-100 p-4 flex justify-center overflow-hidden max-h-56">
            <div
              className={`bg-white shadow-sm overflow-auto ${
                previewMode === "desktop"
                  ? "w-full"
                  : previewMode === "tablet"
                    ? "w-[480px]"
                    : "w-[320px]"
              }`}
              style={{ maxHeight: "200px" }}
              dangerouslySetInnerHTML={{ __html: previewHtml }}
            />
          </div>
        </div>
      )}
    </div>
  );

  const renderStep4 = () => (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-amber-100 rounded-xl flex items-center justify-center text-xl">
          🔗
        </div>
        <div>
          <h2 className="text-lg font-bold text-gray-900">Field Mapping</h2>
          <p className="text-sm text-gray-500">
            Map template variables to subscriber data
          </p>
        </div>
      </div>

      {fieldsLoading ? (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              className="h-20 bg-gray-100 rounded-xl animate-pulse"
            />
          ))}
        </div>
      ) : dynamicFields.length === 0 ? (
        <div className="bg-green-50 border border-green-200 rounded-xl p-5 text-center">
          <p className="text-2xl mb-2">✅</p>
          <p className="text-sm font-semibold text-green-800">
            No dynamic fields
          </p>
          <p className="text-xs text-green-600 mt-1">
            This template has no personalization variables.
          </p>
        </div>
      ) : (
        <>
          {unmappedCount > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 flex items-center gap-2 text-sm text-amber-800">
              ⚠ {unmappedCount} field{unmappedCount > 1 ? "s" : ""} still need
              mapping
            </div>
          )}
          <div className="space-y-3">
            {dynamicFields.map((field) => {
              const hasError = errors[`field_${field}`];
              const isMapped = !!form.field_map[field]?.trim();
              return (
                <div
                  key={field}
                  className={`rounded-xl border-2 p-4 transition-all ${
                    hasError
                      ? "border-red-200 bg-red-50"
                      : isMapped
                        ? "border-green-200 bg-green-50"
                        : "border-gray-200 bg-white"
                  }`}
                >
                  <div className="flex items-center justify-between mb-2.5">
                    <code
                      className={`text-sm font-mono font-bold px-2 py-0.5 rounded-lg ${isMapped ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-700"}`}
                    >
                      {`{{${field}}}`}
                    </code>
                    {isMapped && !hasError && (
                      <span className="text-xs text-green-600 font-medium">
                        ✓ Mapped
                      </span>
                    )}
                    {hasError && (
                      <span className="text-xs text-red-500">⚠ Required</span>
                    )}
                  </div>
                  <select
                    value={form.field_map[field] || ""}
                    onChange={(e) => setMap(field, e.target.value)}
                    className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 ${hasError ? "border-red-300" : "border-gray-200"}`}
                  >
                    <option value="">— Select a data source —</option>
                    <option value="__DEFAULT__">
                      Use fallback / default value
                    </option>
                    <option value="__EMPTY__">Leave empty</option>
                    {availableFields.universal.length > 0 && (
                      <optgroup label="Universal">
                        {availableFields.universal.map((f) => (
                          <option key={f} value={f}>
                            {f}
                          </option>
                        ))}
                      </optgroup>
                    )}
                    {availableFields.standard.length > 0 && (
                      <optgroup label="Standard Fields">
                        {availableFields.standard.map((f) => (
                          <option key={f} value={`standard.${f}`}>
                            {f}
                          </option>
                        ))}
                      </optgroup>
                    )}
                    {availableFields.custom.length > 0 && (
                      <optgroup label="Custom Fields">
                        {availableFields.custom.map((f) => (
                          <option key={f} value={`custom.${f}`}>
                            {f}
                          </option>
                        ))}
                      </optgroup>
                    )}
                  </select>
                  {form.field_map[field] &&
                    form.field_map[field] !== "__EMPTY__" && (
                      <input
                        type="text"
                        placeholder={
                          form.field_map[field] === "__DEFAULT__"
                            ? `Default value for {{${field}}}`
                            : "Fallback if subscriber's value is empty"
                        }
                        value={form.fallback_values[field] || ""}
                        onChange={(e) => setFallback(field, e.target.value)}
                        className="mt-2 w-full px-3 py-2 border border-indigo-200 bg-indigo-50 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                      />
                    )}
                </div>
              );
            })}
          </div>

          <details className="bg-gray-50 rounded-xl border border-gray-200">
            <summary className="px-4 py-3 text-xs text-gray-500 cursor-pointer font-semibold">
              Available subscriber fields
            </summary>
            <div className="px-4 pb-4 space-y-1 text-xs text-gray-500">
              <p>
                Universal: {availableFields.universal.join(", ") || "email"}
              </p>
              <p>Standard: {availableFields.standard.join(", ") || "none"}</p>
              <p>Custom: {availableFields.custom.join(", ") || "none"}</p>
            </div>
          </details>
        </>
      )}
    </div>
  );

  const renderStep5 = () => (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-rose-100 rounded-xl flex items-center justify-center text-xl">
          💾
        </div>
        <div>
          <h2 className="text-lg font-bold text-gray-900">Review & Save</h2>
          <p className="text-sm text-gray-500">
            Confirm your changes before saving
          </p>
        </div>
      </div>

      {globalError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
          ⚠ {globalError}
        </div>
      )}

      {saveSuccess && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-sm text-green-700 flex items-center gap-2">
          ✅ Campaign saved! Redirecting…
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-gray-50 rounded-xl border border-gray-200 p-4 space-y-3">
          <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider">
            Campaign Details
          </h3>
          {[
            ["Title", form.title],
            ["Subject", form.subject],
            ["Sender", `${form.sender_name} <${form.sender_email}>`],
            ["Reply-To", form.reply_to || form.sender_email || "—"],
            ["Status", originalStatus],
          ].map(([label, value]) => (
            <div key={label} className="flex gap-3">
              <span className="text-xs text-gray-400 w-16 flex-shrink-0">
                {label}
              </span>
              <span className="text-xs font-medium text-gray-800 break-all capitalize">
                {value || "—"}
              </span>
            </div>
          ))}
        </div>

        <div className="bg-gray-50 rounded-xl border border-gray-200 p-4 space-y-3">
          <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider">
            Audience & Template
          </h3>
          <div className="flex gap-3">
            <span className="text-xs text-gray-400 w-16 flex-shrink-0">
              Lists
            </span>
            <span className="text-xs font-medium text-gray-800">
              {form.target_lists.length ? form.target_lists.join(", ") : "None"}
            </span>
          </div>
          {form.target_segments.length > 0 && (
            <div className="flex gap-3">
              <span className="text-xs text-gray-400 w-16 flex-shrink-0">
                Segments
              </span>
              <span className="text-xs font-medium text-gray-800">
                {form.target_segments.length} selected
              </span>
            </div>
          )}
          <div className="flex gap-3">
            <span className="text-xs text-gray-400 w-16 flex-shrink-0">
              Template
            </span>
            <span className="text-xs font-medium text-gray-800">
              {selectedTemplate?.name || "—"}
            </span>
          </div>
          <div className="flex gap-3">
            <span className="text-xs text-gray-400 w-16 flex-shrink-0">
              Recipients
            </span>
            <span className="text-xs font-bold text-indigo-700">
              {fmt(totalAudienceSize)}
            </span>
          </div>
          <div className="flex gap-3">
            <span className="text-xs text-gray-400 w-16 flex-shrink-0">
              Fields
            </span>
            <span className="text-xs font-medium text-gray-800">
              {dynamicFields.length} variable
              {dynamicFields.length !== 1 ? "s" : ""}
              {unmappedCount > 0
                ? `, ${unmappedCount} unmapped`
                : " (all mapped)"}
            </span>
          </div>
        </div>
      </div>

      {previewHtml && (
        <div className="border border-gray-200 rounded-xl overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
            <p className="text-sm font-semibold text-gray-700">Email Preview</p>
            <div className="flex gap-1">
              {["desktop", "tablet", "mobile"].map((m) => (
                <button
                  key={m}
                  onClick={() => setPreviewMode(m)}
                  className={`px-2.5 py-1 text-xs rounded-lg font-medium ${previewMode === m ? "bg-indigo-600 text-white" : "text-gray-400 hover:bg-gray-200"}`}
                >
                  {m === "desktop" ? "🖥" : m === "tablet" ? "📟" : "📱"}
                </button>
              ))}
            </div>
          </div>
          <div
            className="bg-gray-100 p-4 flex justify-center overflow-hidden"
            style={{ maxHeight: "260px" }}
          >
            <div
              className={`bg-white shadow-sm overflow-auto ${
                previewMode === "desktop"
                  ? "w-full"
                  : previewMode === "tablet"
                    ? "w-[480px]"
                    : "w-[320px]"
              }`}
              style={{ maxHeight: "220px" }}
              dangerouslySetInnerHTML={{ __html: previewHtml }}
            />
          </div>
        </div>
      )}

      {/* Save CTA */}
      <div className="bg-gradient-to-br from-indigo-50 to-purple-50 border border-indigo-200 rounded-2xl p-6">
        <div className="flex flex-col sm:flex-row gap-3">
          <button
            onClick={() => navigate("/campaigns")}
            className="flex-1 py-3 px-6 bg-white border-2 border-gray-200 text-gray-700 font-semibold text-sm rounded-xl hover:border-gray-300 hover:bg-gray-50 transition-all"
          >
            ← Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={submitting || saveSuccess}
            className="flex-1 py-3 px-6 bg-indigo-600 text-white font-bold text-sm rounded-xl hover:bg-indigo-700 shadow-lg shadow-indigo-200 transition-all disabled:opacity-50"
          >
            {submitting
              ? "⏳ Saving..."
              : saveSuccess
                ? "✅ Saved!"
                : "💾 Save Changes"}
          </button>
        </div>
        {isNonDraft && (
          <p className="text-xs text-amber-600 mt-3 text-center">
            ⚠ This campaign is "{originalStatus}" — changes will update
            metadata only. Sent emails are unaffected.
          </p>
        )}
      </div>
    </div>
  );

  const stepRenderers = [
    renderStep1,
    renderStep2,
    renderStep3,
    renderStep4,
    renderStep5,
  ];

  return (
    <div className="max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-2 mb-0.5">
            <h1 className="text-2xl font-bold text-gray-900">Edit Campaign</h1>
            {originalStatus !== "draft" && (
              <span
                className={`text-xs px-2.5 py-1 rounded-full font-semibold ${
                  originalStatus === "sending"
                    ? "bg-blue-100 text-blue-800"
                    : originalStatus === "completed" ||
                        originalStatus === "sent"
                      ? "bg-green-100 text-green-800"
                      : originalStatus === "paused"
                        ? "bg-orange-100 text-orange-800"
                        : "bg-gray-100 text-gray-600"
                }`}
              >
                {originalStatus}
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

      {/* Step nav */}
      <div className="mb-8">
        <StepNav
          current={step}
          steps={STEPS}
          onGoto={(s) => setStep(s)}
          completedSteps={completedSteps}
        />
      </div>

      {/* Progress */}
      <div className="mb-8 bg-gray-100 rounded-full h-1.5">
        <div
          className="bg-indigo-500 h-1.5 rounded-full transition-all duration-500"
          style={{ width: `${((step - 1) / (STEPS.length - 1)) * 100}%` }}
        />
      </div>

      {/* Card */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-8">
        {stepRenderers[step - 1]()}

        {step < 5 && (
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
        )}
      </div>
    </div>
  );
}
