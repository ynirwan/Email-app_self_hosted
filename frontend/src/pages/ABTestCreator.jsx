import React, { useEffect, useState, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useSettings } from "../contexts/SettingsContext";
import API from "../api";

// ── Steps ─────────────────────────────────────────────────────────────────────
const STEPS = [
  { id: 1, label: "Setup", icon: "⚙️", desc: "Name & sender details" },
  { id: 2, label: "Audience", icon: "👥", desc: "Lists & segments" },
  { id: 3, label: "Template", icon: "🎨", desc: "Pick template & map fields" },
  { id: 4, label: "Variants", icon: "⚖️", desc: "Configure A vs B" },
  { id: 5, label: "Launch", icon: "🚀", desc: "Review & create" },
];

const mapTestToConfig = (test) => ({
  test_name: test.test_name || "",
  target_lists: test.target_lists || [],
  target_segments: test.target_segments || [],
  audience_mode: test.audience_mode || "lists",
  template_id: test.template_id || "",
  subject: test.subject || "",
  sender_name: test.sender_name || "",
  sender_email: test.sender_email || "",
  reply_to: test.reply_to || "",
  test_type: test.test_type || "subject_line",
  variants: [
    {
      name: test.variants?.[0]?.name || "Variant A (Control)",
      subject: test.variants?.[0]?.subject || "",
      sender_name: test.variants?.[0]?.sender_name || "",
      sender_email: test.variants?.[0]?.sender_email || "",
      reply_to: test.variants?.[0]?.reply_to || "",
    },
    {
      name: test.variants?.[1]?.name || "Variant B (Test)",
      subject: test.variants?.[1]?.subject || "",
      sender_name: test.variants?.[1]?.sender_name || "",
      sender_email: test.variants?.[1]?.sender_email || "",
      reply_to: test.variants?.[1]?.reply_to || "",
    },
  ],
  split_percentage: test.split_percentage ?? 50,
  sample_size: test.sample_size ?? 1000,
  winner_criteria: test.winner_criteria || "open_rate",
  test_duration_hours: test.test_duration_hours ?? 24,
  auto_send_winner: test.auto_send_winner ?? true,
  field_map: test.field_map || {},
  fallback_values: test.fallback_values || {},
});

const TEST_TYPE_CONFIG = {
  subject_line: {
    field: "subject",
    label: "Subject Line",
    placeholder: "Try a different angle...",
  },
  sender_name: {
    field: "sender_name",
    label: "Sender Name",
    placeholder: "e.g., Sarah from Acme",
  },
  sender_email: {
    field: "sender_email",
    label: "Sender Email",
    placeholder: "test@domain.com",
  },
  reply_to: {
    field: "reply_to",
    label: "Reply-To Address",
    placeholder: "replies@domain.com",
  },
};

const fmt = (n) => Number(n ?? 0).toLocaleString();
const inputCls = (err) =>
  `w-full px-3.5 py-2.5 rounded-xl border text-sm focus:outline-none focus:ring-2 focus:ring-violet-400 focus:border-violet-400 transition-all ${
    err
      ? "border-red-300 bg-red-50"
      : "border-gray-200 bg-white hover:border-gray-300"
  }`;

// ── StepNav ───────────────────────────────────────────────────────────────────
function StepNav({ current, steps, completed, onGoto }) {
  return (
    <div className="flex items-center gap-0 overflow-x-auto pb-2">
      {steps.map((step, i) => {
        const isDone = completed.includes(step.id);
        const isActive = current === step.id;
        return (
          <div key={step.id} className="flex items-center">
            <button
              onClick={() => (isDone || isActive) && onGoto(step.id)}
              disabled={!isDone && !isActive}
              className={`flex flex-col items-center gap-1 px-3 py-2 rounded-xl transition-all duration-200 min-w-[80px] ${
                isActive
                  ? "bg-violet-600 text-white shadow-lg shadow-violet-200 scale-105"
                  : isDone
                    ? "bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200"
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
                className={`h-px w-4 mx-1 ${isDone ? "bg-emerald-300" : "bg-gray-200"}`}
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

// ── AudienceCard ─────────────────────────────────────────────────────────────
function AudienceCard({ name, count, selected, onClick, icon = "📋" }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-3 w-full p-3 rounded-xl border-2 text-left transition-all ${
        selected
          ? "border-violet-500 bg-violet-50"
          : "border-gray-200 hover:border-gray-300 bg-white"
      }`}
    >
      <div
        className={`w-8 h-8 rounded-lg flex items-center justify-center text-sm flex-shrink-0 ${selected ? "bg-violet-100" : "bg-gray-100"}`}
      >
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <p
          className={`text-sm font-semibold truncate ${selected ? "text-violet-800" : "text-gray-800"}`}
        >
          {name}
        </p>
        {count != null && (
          <p className="text-xs text-gray-400">{fmt(count)} subscribers</p>
        )}
      </div>
      <div
        className={`w-5 h-5 rounded-md border-2 flex items-center justify-center flex-shrink-0 transition-all ${
          selected ? "bg-violet-600 border-violet-600" : "border-gray-300"
        }`}
      >
        {selected && <span className="text-white text-xs">✓</span>}
      </div>
    </button>
  );
}

// ── VariantCard ───────────────────────────────────────────────────────────────
function VariantCard({
  variant,
  index,
  testType,
  onChange,
  controlValue,
  isControl,
}) {
  const cfg = TEST_TYPE_CONFIG[testType] || TEST_TYPE_CONFIG.subject_line;
  const colors = isControl
    ? {
        bg: "bg-blue-50",
        border: "border-blue-200",
        badge: "bg-blue-100 text-blue-700",
        label: "text-blue-800",
      }
    : {
        bg: "bg-orange-50",
        border: "border-orange-200",
        badge: "bg-orange-100 text-orange-700",
        label: "text-orange-800",
      };

  return (
    <div className={`rounded-2xl border-2 p-5 ${colors.bg} ${colors.border}`}>
      <div className="flex items-center gap-3 mb-4">
        <div
          className={`text-xs font-bold px-2.5 py-1 rounded-full ${colors.badge}`}
        >
          {isControl ? "A — Control" : "B — Test"}
        </div>
        {isControl && (
          <span className="text-xs text-blue-500 italic">
            locked to your base settings
          </span>
        )}
      </div>

      <div>
        <label
          className={`block text-xs font-bold uppercase tracking-wider mb-2 ${colors.label}`}
        >
          {cfg.label}
        </label>
        <input
          type={
            testType === "sender_email" || testType === "reply_to"
              ? "email"
              : "text"
          }
          value={variant[cfg.field] || ""}
          onChange={(e) => onChange(cfg.field, e.target.value)}
          placeholder={
            isControl
              ? controlValue || `Current ${cfg.label.toLowerCase()}`
              : cfg.placeholder
          }
          readOnly={isControl}
          className={`w-full px-3 py-2.5 text-sm rounded-xl border font-medium focus:outline-none ${
            isControl
              ? "bg-white/60 border-blue-200 text-gray-600 cursor-not-allowed"
              : "bg-white border-orange-200 focus:ring-2 focus:ring-orange-300 text-gray-900"
          }`}
        />
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────
const ABTestCreator = ({ editMode = false }) => {
  const { t } = useSettings();
  const navigate = useNavigate();
  const { testId } = useParams();

  const [step, setStep] = useState(1);
  const [completed, setCompleted] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadingEdit, setLoadingEdit] = useState(editMode);
  const [errors, setErrors] = useState({});
  const [globalError, setGlobalError] = useState("");

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
  const [previewHtml, setPreviewHtml] = useState("");
  const [previewMode, setPreviewMode] = useState("desktop");
  const [fieldsLoading, setFieldsLoading] = useState(false);

  const [testConfig, setTestConfig] = useState({
    test_name: "",
    target_lists: [],
    target_segments: [],
    audience_mode: "lists",
    template_id: "",
    subject: "",
    sender_name: "",
    sender_email: "",
    reply_to: "",
    test_type: "subject_line",
    variants: [
      {
        name: "Variant A (Control)",
        subject: "",
        sender_name: "",
        sender_email: "",
        reply_to: "",
      },
      {
        name: "Variant B (Test)",
        subject: "",
        sender_name: "",
        sender_email: "",
        reply_to: "",
      },
    ],
    split_percentage: 50,
    sample_size: 1000,
    winner_criteria: "open_rate",
    test_duration_hours: 24,
    auto_send_winner: true,
    field_map: {},
    fallback_values: {},
  });

  const set = useCallback(
    (key, val) => setTestConfig((prev) => ({ ...prev, [key]: val })),
    [],
  );
  const selectedTemplate = templates.find(
    (t) => (t._id || t.id) === testConfig.template_id,
  );

  const totalAudienceSize =
    lists
      .filter((l) => testConfig.target_lists.includes(l._id || l.name))
      .reduce((s, l) => s + (l.total_count || l.count || 0), 0) +
    segments
      .filter((sg) => testConfig.target_segments.includes(sg._id))
      .reduce((s, sg) => s + (sg.subscriber_count || 0), 0);

  // ── Data loading ──────────────────────────────────────────────────────────
  useEffect(() => {
    Promise.all([
      API.get("/subscribers/lists"),
      API.get("/segments").catch(() => ({ data: [] })),
      API.get("/templates"),
      API.get("/settings/sender-profiles").catch(() => ({ data: [] })),
    ])
      .then(([listsR, segR, tplR, spR]) => {
        setLists(Array.isArray(listsR.data) ? listsR.data : []);
        const segData = segR.data?.segments || segR.data || [];
        setSegments(Array.isArray(segData) ? segData : []);
        setTemplates(Array.isArray(tplR.data) ? tplR.data : []);
        setSenderProfiles(Array.isArray(spR.data) ? spR.data : []);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!editMode || !testId) {
      setLoadingEdit(false);
      return;
    }
    API.get(`/ab-tests/${testId}`)
      .then((r) => {
        const test = r.data?.test || r.data;
        if (test?.status && test.status !== "draft") {
          setGlobalError(
            `Cannot edit a "${test.status}" test. Only drafts are editable.`,
          );
          return;
        }
        setTestConfig(mapTestToConfig(test || {}));
      })
      .catch((err) =>
        setGlobalError(err.response?.data?.detail || "Failed to load test"),
      )
      .finally(() => setLoadingEdit(false));
  }, [editMode, testId]);

  // Template fields & preview
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
    setPreviewHtml(html);

    if (selectedTemplate.subject && !testConfig.subject) {
      set("subject", selectedTemplate.subject);
      setTestConfig((prev) => ({
        ...prev,
        subject: selectedTemplate.subject,
        variants: [
          { ...prev.variants[0], subject: selectedTemplate.subject },
          prev.variants[1],
        ],
      }));
    }

    setFieldsLoading(true);
    API.get(`/templates/${selectedTemplate._id || selectedTemplate.id}/fields`)
      .then((r) => setDynamicFields(Array.isArray(r.data) ? r.data : []))
      .catch(() => setDynamicFields([]))
      .finally(() => setFieldsLoading(false));
  }, [selectedTemplate]);

  // Audience field analysis
  useEffect(() => {
    const hasAudience =
      testConfig.target_lists.length > 0 ||
      testConfig.target_segments.length > 0;
    if (!hasAudience) {
      setAvailableFields({ universal: ["email"], standard: [], custom: [] });
      return;
    }
    const payload = {};
    if (testConfig.target_lists.length)
      payload.listIds = testConfig.target_lists;
    if (testConfig.target_segments.length)
      payload.segmentIds = testConfig.target_segments;
    API.post("/subscribers/analyze-fields", payload)
      .then((r) =>
        setAvailableFields(
          r.data || { universal: ["email"], standard: [], custom: [] },
        ),
      )
      .catch(() => {});
  }, [testConfig.target_lists, testConfig.target_segments]);

  // Auto-map fields
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
    setTestConfig((prev) => {
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
          return norm(stripped).includes(n) || n.includes(norm(stripped));
        });
        if (partial) next[field] = partial;
      });
      return { ...prev, field_map: next };
    });
  }, [dynamicFields, availableFields]);

  // ── Test type change ──────────────────────────────────────────────────────
  const handleTestTypeChange = (newType) => {
    setTestConfig((prev) => {
      const cfg = TEST_TYPE_CONFIG[newType];
      const updatedVariants = [...prev.variants];
      updatedVariants[0] = {
        ...updatedVariants[0],
        [cfg.field]: prev[cfg.field],
      };
      updatedVariants[1] = { ...updatedVariants[1], [cfg.field]: "" };
      return { ...prev, test_type: newType, variants: updatedVariants };
    });
  };

  const handleVariantChange = (idx, field, val) => {
    setTestConfig((prev) => {
      const updated = [...prev.variants];
      updated[idx] = { ...updated[idx], [field]: val };
      return { ...prev, variants: updated };
    });
  };

  // ── Validation ────────────────────────────────────────────────────────────
  const validateStep = (s) => {
    const errs = {};
    if (s === 1) {
      if (!testConfig.test_name.trim())
        errs.test_name = "Test name is required";
      if (!testConfig.subject.trim()) errs.subject = "Subject is required";
      if (!testConfig.sender_name.trim())
        errs.sender_name = "Sender name is required";
      if (!testConfig.sender_email.trim())
        errs.sender_email = "Sender email is required";
    }
    if (s === 2) {
      if (!testConfig.target_lists.length && !testConfig.target_segments.length)
        errs.audience = "Select at least one list or segment";
    }
    if (s === 3) {
      if (!testConfig.template_id) errs.template_id = "Select a template";
    }
    if (s === 4) {
      const cfg = TEST_TYPE_CONFIG[testConfig.test_type];
      if (!testConfig.variants[1][cfg.field]?.trim())
        errs.variant_b = `Variant B ${cfg.label.toLowerCase()} is required`;
      if (testConfig.sample_size < 100)
        errs.sample_size = "Sample size must be at least 100";
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
    setCompleted((prev) => [...new Set([...prev, step])]);
    setStep((s) => s + 1);
  };

  // ── Submit ────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    setGlobalError("");
    setLoading(true);
    try {
      const payload = {
        ...testConfig,
        reply_to: testConfig.reply_to || testConfig.sender_email,
      };
      if (editMode && testId) {
        await API.put(`/ab-tests/${testId}`, payload);
        navigate("/ab-testing");
      } else {
        await API.post("/ab-tests", payload);
        navigate("/ab-testing");
      }
    } catch (err) {
      setGlobalError(err.response?.data?.detail || "Failed to save A/B test");
    } finally {
      setLoading(false);
    }
  };

  if (loadingEdit) {
    return (
      <div className="flex items-center justify-center py-24 gap-3 text-gray-400">
        <div className="animate-spin h-6 w-6 border-2 border-gray-300 border-t-violet-500 rounded-full" />
        Loading test editor…
      </div>
    );
  }

  // ── Step renderers ────────────────────────────────────────────────────────
  const renderStep1 = () => (
    <div className="space-y-6">
      <div className="flex items-center gap-3 mb-2">
        <div className="w-10 h-10 bg-violet-100 rounded-xl flex items-center justify-center text-xl">
          ⚙️
        </div>
        <div>
          <h2 className="text-lg font-bold text-gray-900">Test Setup</h2>
          <p className="text-sm text-gray-500">
            Name your test and configure the base sender
          </p>
        </div>
      </div>

      <InputField label={t('abtest.form.name')} required error={errors.test_name}>
        <input
          className={inputCls(errors.test_name)}
          autoFocus
          placeholder="e.g., Subject Line Test — April Campaign"
          value={testConfig.test_name}
          onChange={(e) => set("test_name", e.target.value)}
        />
      </InputField>

      <div className="border-t border-gray-100 pt-5">
        <p className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-4">
          Base Sender (used as Variant A)
        </p>

        {senderProfiles.length > 0 && (
          <div className="bg-gray-50 border border-gray-200 rounded-xl p-3 mb-4">
            <p className="text-xs text-gray-500 mb-2 font-semibold">
              Quick fill from profile
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
                    setTestConfig((prev) => ({
                      ...prev,
                      sender_name: sp.name || "",
                      sender_email: sp.email || "",
                      variants: [
                        {
                          ...prev.variants[0],
                          sender_name: sp.name || "",
                          sender_email: sp.email || "",
                        },
                        prev.variants[1],
                      ],
                    }));
                  }}
                  className="px-3 py-1.5 text-xs bg-white border border-gray-200 rounded-lg hover:border-violet-300 hover:text-violet-700 font-medium transition-all"
                >
                  {sp.name || sp.sender_name}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <InputField label={t('campaign.form.subject')} required error={errors.subject}>
            <input
              className={inputCls(errors.subject)}
              placeholder="Your base subject line"
              value={testConfig.subject}
              onChange={(e) => {
                set("subject", e.target.value);
                setTestConfig((prev) => ({
                  ...prev,
                  subject: e.target.value,
                  variants: [
                    { ...prev.variants[0], subject: e.target.value },
                    prev.variants[1],
                  ],
                }));
              }}
            />
          </InputField>
          <InputField label="Sender Name" required error={errors.sender_name}>
            <input
              className={inputCls(errors.sender_name)}
              placeholder="e.g., Acme Team"
              value={testConfig.sender_name}
              onChange={(e) => {
                set("sender_name", e.target.value);
                setTestConfig((prev) => ({
                  ...prev,
                  sender_name: e.target.value,
                  variants: [
                    { ...prev.variants[0], sender_name: e.target.value },
                    prev.variants[1],
                  ],
                }));
              }}
            />
          </InputField>
          <InputField label="Sender Email" required error={errors.sender_email}>
            <input
              type="email"
              className={inputCls(errors.sender_email)}
              placeholder="sender@company.com"
              value={testConfig.sender_email}
              onChange={(e) => {
                set("sender_email", e.target.value);
                setTestConfig((prev) => ({
                  ...prev,
                  sender_email: e.target.value,
                  variants: [
                    { ...prev.variants[0], sender_email: e.target.value },
                    prev.variants[1],
                  ],
                }));
              }}
            />
          </InputField>
          <InputField label="Reply-To" hint="optional">
            <input
              type="email"
              className={inputCls(false)}
              placeholder="replies@company.com"
              value={testConfig.reply_to}
              onChange={(e) => set("reply_to", e.target.value)}
            />
          </InputField>
        </div>
      </div>
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
              Who will participate in this test?
            </p>
          </div>
        </div>
        {totalAudienceSize > 0 && (
          <div className="bg-violet-50 border border-violet-200 rounded-xl px-4 py-2 text-center">
            <p className="text-xl font-bold text-violet-700">
              {fmt(totalAudienceSize)}
            </p>
            <p className="text-xs text-violet-400">total reachable</p>
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
              📋 Lists
              {testConfig.target_lists.length > 0 && (
                <span className="ml-2 px-2 py-0.5 bg-violet-100 text-violet-700 rounded-full text-xs">
                  {testConfig.target_lists.length} selected
                </span>
              )}
            </h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 max-h-56 overflow-y-auto pr-1">
            {lists.map((l) => {
              const id = l._id || l.name;
              return (
                <AudienceCard
                  key={id}
                  name={l.name || id}
                  count={l.total_count || l.count}
                  selected={testConfig.target_lists.includes(id)}
                  onClick={() =>
                    set(
                      "target_lists",
                      testConfig.target_lists.includes(id)
                        ? testConfig.target_lists.filter((x) => x !== id)
                        : [...testConfig.target_lists, id],
                    )
                  }
                  icon="📋"
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
            {testConfig.target_segments.length > 0 && (
              <span className="ml-2 px-2 py-0.5 bg-violet-100 text-violet-700 rounded-full text-xs">
                {testConfig.target_segments.length} selected
              </span>
            )}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 max-h-48 overflow-y-auto pr-1">
            {segments.map((sg) => (
              <AudienceCard
                key={sg._id}
                name={sg.name}
                count={sg.subscriber_count}
                selected={testConfig.target_segments.includes(sg._id)}
                onClick={() =>
                  set(
                    "target_segments",
                    testConfig.target_segments.includes(sg._id)
                      ? testConfig.target_segments.filter((x) => x !== sg._id)
                      : [...testConfig.target_segments, sg._id],
                  )
                }
                icon="🎯"
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
          <h2 className="text-lg font-bold text-gray-900">
            Template & Field Mapping
          </h2>
          <p className="text-sm text-gray-500">
            Both variants share the same template
          </p>
        </div>
      </div>

      {errors.template_id && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-700">
          ⚠ {errors.template_id}
        </div>
      )}

      {/* Template picker */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-56 overflow-y-auto pr-1">
        {templates.map((t) => {
          const id = t._id || t.id;
          const selected = testConfig.template_id === id;
          const mode = t.content_json?.mode || "legacy";
          const modeColors = {
            html: "bg-blue-100 text-blue-700",
            "drag-drop": "bg-purple-100 text-purple-700",
            visual: "bg-green-100 text-green-700",
            legacy: "bg-gray-100 text-gray-600",
          };
          return (
            <button
              key={id}
              onClick={() => set("template_id", id)}
              className={`flex items-start gap-3 p-3 rounded-xl border-2 text-left transition-all ${
                selected
                  ? "border-violet-500 bg-violet-50"
                  : "border-gray-200 hover:border-gray-300 bg-white"
              }`}
            >
              <div
                className={`w-8 h-8 rounded-lg flex items-center justify-center text-sm flex-shrink-0 ${selected ? "bg-violet-100" : "bg-gray-100"}`}
              >
                🎨
              </div>
              <div className="flex-1 min-w-0">
                <p
                  className={`text-sm font-semibold truncate ${selected ? "text-violet-800" : "text-gray-800"}`}
                >
                  {t.name || "Untitled"}
                </p>
                <span
                  className={`text-xs px-1.5 py-0.5 rounded font-medium ${modeColors[mode]}`}
                >
                  {mode}
                </span>
              </div>
              {selected && (
                <span className="text-violet-600 flex-shrink-0">✓</span>
              )}
            </button>
          );
        })}
      </div>

      {/* Field mapping (if template selected and has fields) */}
      {testConfig.template_id && (
        <div>
          {fieldsLoading ? (
            <div className="space-y-3">
              {[1, 2].map((i) => (
                <div
                  key={i}
                  className="h-16 bg-gray-100 rounded-xl animate-pulse"
                />
              ))}
            </div>
          ) : dynamicFields.length === 0 ? (
            <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-center">
              <p className="text-sm text-green-700 font-medium">
                ✅ No dynamic fields — no mapping needed
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-700">
                  Field Mapping
                </h3>
                <span className="text-xs text-gray-400">
                  {
                    dynamicFields.filter((f) => testConfig.field_map[f]?.trim())
                      .length
                  }{" "}
                  / {dynamicFields.length} mapped
                </span>
              </div>
              {dynamicFields.map((field) => {
                const isMapped = !!testConfig.field_map[field]?.trim();
                return (
                  <div
                    key={field}
                    className={`rounded-xl border-2 p-4 ${isMapped ? "border-green-200 bg-green-50" : "border-gray-200 bg-white"}`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <code
                        className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${isMapped ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-700"}`}
                      >
                        {`{{${field}}}`}
                      </code>
                      {isMapped && (
                        <span className="text-xs text-green-600">✓ Mapped</span>
                      )}
                    </div>
                    <select
                      value={testConfig.field_map[field] || ""}
                      onChange={(e) =>
                        setTestConfig((prev) => ({
                          ...prev,
                          field_map: {
                            ...prev.field_map,
                            [field]: e.target.value,
                          },
                        }))
                      }
                      className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-violet-400"
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
                    {testConfig.field_map[field] &&
                      testConfig.field_map[field] !== "__EMPTY__" && (
                        <input
                          type="text"
                          placeholder={
                            testConfig.field_map[field] === "__DEFAULT__"
                              ? `Default value for {{${field}}}`
                              : "Fallback if field is empty"
                          }
                          value={testConfig.fallback_values[field] || ""}
                          onChange={(e) =>
                            setTestConfig((prev) => ({
                              ...prev,
                              fallback_values: {
                                ...prev.fallback_values,
                                [field]: e.target.value,
                              },
                            }))
                          }
                          className="mt-2 w-full px-3 py-2 border border-violet-200 bg-violet-50 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-violet-400"
                        />
                      )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Preview */}
      {previewHtml && (
        <div className="border border-gray-200 rounded-xl overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200">
            <p className="text-sm font-semibold text-gray-700">
              Template Preview
            </p>
            <div className="flex gap-1">
              {["desktop", "tablet", "mobile"].map((m) => (
                <button
                  key={m}
                  onClick={() => setPreviewMode(m)}
                  className={`px-2.5 py-1 text-xs rounded-lg font-medium ${previewMode === m ? "bg-violet-600 text-white" : "text-gray-400 hover:bg-gray-200"}`}
                >
                  {m === "desktop" ? "🖥" : m === "tablet" ? "📟" : "📱"}
                </button>
              ))}
            </div>
          </div>
          <div
            className="bg-gray-100 p-3 flex justify-center overflow-hidden"
            style={{ maxHeight: "200px" }}
          >
            <div
              className={`bg-white shadow-sm overflow-auto ${previewMode === "desktop" ? "w-full" : previewMode === "tablet" ? "w-[400px]" : "w-[280px]"}`}
              style={{ maxHeight: "170px" }}
              dangerouslySetInnerHTML={{ __html: previewHtml }}
            />
          </div>
        </div>
      )}
    </div>
  );

  const renderStep4 = () => {
    const cfg = TEST_TYPE_CONFIG[testConfig.test_type];
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-orange-100 rounded-xl flex items-center justify-center text-xl">
            ⚖️
          </div>
          <div>
            <h2 className="text-lg font-bold text-gray-900">
              Configure Variants
            </h2>
            <p className="text-sm text-gray-500">
              Define what's different between A and B
            </p>
          </div>
        </div>

        {/* Test type selector */}
        <div>
          <p className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3">
            What are you testing?
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {Object.entries(TEST_TYPE_CONFIG).map(([type, conf]) => (
              <button
                key={type}
                onClick={() => handleTestTypeChange(type)}
                className={`p-3 rounded-xl border-2 text-left transition-all ${
                  testConfig.test_type === type
                    ? "border-violet-500 bg-violet-50"
                    : "border-gray-200 hover:border-gray-300 bg-white"
                }`}
              >
                <p
                  className={`text-xs font-bold ${testConfig.test_type === type ? "text-violet-800" : "text-gray-700"}`}
                >
                  {conf.label}
                </p>
              </button>
            ))}
          </div>
        </div>

        {/* Variants side-by-side */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <VariantCard
            variant={testConfig.variants[0]}
            index={0}
            testType={testConfig.test_type}
            onChange={(field, val) => handleVariantChange(0, field, val)}
            controlValue={testConfig[cfg.field]}
            isControl={true}
          />
          <VariantCard
            variant={testConfig.variants[1]}
            index={1}
            testType={testConfig.test_type}
            onChange={(field, val) => handleVariantChange(1, field, val)}
            controlValue={testConfig[cfg.field]}
            isControl={false}
          />
        </div>
        {errors.variant_b && (
          <p className="text-xs text-red-500 -mt-2">⚠ {errors.variant_b}</p>
        )}

        {/* Test parameters */}
        <div className="bg-gray-50 rounded-2xl border border-gray-200 p-6 space-y-6">
          <p className="text-xs font-bold text-gray-400 uppercase tracking-wider">
            Test Parameters
          </p>

          {/* Split slider */}
          <div>
            <div className="flex justify-between mb-2">
              <span className="text-sm font-semibold text-gray-700">
                {t('abtest.form.splitRatio')}
              </span>
              <span className="text-sm text-gray-500">
                A: {testConfig.split_percentage}% · B:{" "}
                {100 - testConfig.split_percentage}%
              </span>
            </div>
            <input
              type="range"
              min="10"
              max="90"
              value={testConfig.split_percentage}
              onChange={(e) =>
                set("split_percentage", parseInt(e.target.value))
              }
              className="w-full h-2 bg-gray-200 rounded-full appearance-none cursor-pointer accent-violet-600"
            />
            <div className="flex justify-between mt-1 text-xs text-gray-400">
              <span>10%</span>
              <span>90%</span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1.5">
                Sample Size
                {errors.sample_size && (
                  <span className="text-red-400 ml-1 font-normal">
                    ⚠ {errors.sample_size}
                  </span>
                )}
              </label>
              <input
                type="number"
                min="100"
                value={testConfig.sample_size}
                onChange={(e) =>
                  set("sample_size", parseInt(e.target.value) || 100)
                }
                className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-violet-400"
              />
              {totalAudienceSize > 0 && (
                <p className="text-xs text-gray-400 mt-1">
                  Max: {formatDate(totalAudienceSize)}
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1.5">
                {t('abtest.form.winnerCriteria')}
              </label>
              <select
                value={testConfig.winner_criteria}
                onChange={(e) => set("winner_criteria", e.target.value)}
                className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-violet-400"
              >
                <option value="open_rate">Open Rate</option>
                <option value="click_rate">Click Rate</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1.5">
                {t('abtest.form.duration')}
              </label>
              <select
                value={testConfig.test_duration_hours}
                onChange={(e) =>
                  set("test_duration_hours", parseInt(e.target.value))
                }
                className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-violet-400"
              >
                {[1, 2, 4, 8, 12, 24, 48, 72, 168].map((h) => (
                  <option key={h} value={h}>
                    {h < 24
                      ? `${h} hour${h > 1 ? "s" : ""}`
                      : h === 168
                        ? "7 days"
                        : `${h / 24} days`}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Auto-send toggle */}
          <div
            onClick={() =>
              set("auto_send_winner", !testConfig.auto_send_winner)
            }
            className={`flex items-start gap-3 p-4 rounded-xl border-2 cursor-pointer transition-all ${
              testConfig.auto_send_winner
                ? "border-green-300 bg-green-50"
                : "border-gray-200 bg-white"
            }`}
          >
            <div
              className={`w-5 h-5 rounded-md border-2 flex items-center justify-center flex-shrink-0 mt-0.5 transition-all ${
                testConfig.auto_send_winner
                  ? "bg-green-600 border-green-600"
                  : "border-gray-300"
              }`}
            >
              {testConfig.auto_send_winner && (
                <span className="text-white text-xs">✓</span>
              )}
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-800">
                Auto-send winning variant
              </p>
              <p className="text-xs text-gray-500 mt-0.5">
                After the test ends, automatically send the winner to all
                remaining subscribers.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderStep5 = () => {
    const cfg = TEST_TYPE_CONFIG[testConfig.test_type];
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-rose-100 rounded-xl flex items-center justify-center text-xl">
            🚀
          </div>
          <div>
            <h2 className="text-lg font-bold text-gray-900">Review & Launch</h2>
            <p className="text-sm text-gray-500">
              Double-check everything before creating the test
            </p>
          </div>
        </div>

        {globalError && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
            ⚠ {globalError}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-gray-50 rounded-xl border border-gray-200 p-4 space-y-2.5">
            <p className="text-xs font-bold text-gray-400 uppercase tracking-wider">
              Test Details
            </p>
            {[
              ["Name", testConfig.test_name],
              ["Type", testConfig.test_type.replace("_", " ")],
              ["Subject", testConfig.subject],
              [
                "Sender",
                `${testConfig.sender_name} <${testConfig.sender_email}>`,
              ],
            ].map(([l, v]) => (
              <div key={l} className="flex gap-3">
                <span className="text-xs text-gray-400 w-14 flex-shrink-0">
                  {l}
                </span>
                <span className="text-xs font-medium text-gray-800 break-all capitalize">
                  {v || "—"}
                </span>
              </div>
            ))}
          </div>

          <div className="bg-gray-50 rounded-xl border border-gray-200 p-4 space-y-2.5">
            <p className="text-xs font-bold text-gray-400 uppercase tracking-wider">
              Test Configuration
            </p>
            {[
              ["Audience", fmt(totalAudienceSize) + " total"],
              ["Sample", fmt(testConfig.sample_size) + " subscribers"],
              [
                "Split",
                `${testConfig.split_percentage}% A / ${100 - testConfig.split_percentage}% B`,
              ],
              ["Duration", `${testConfig.test_duration_hours}h`],
              ["Criteria", testConfig.winner_criteria.replace("_", " ")],
              ["Auto-send", testConfig.auto_send_winner ? "Yes" : "No"],
            ].map(([l, v]) => (
              <div key={l} className="flex gap-3">
                <span className="text-xs text-gray-400 w-14 flex-shrink-0">
                  {l}
                </span>
                <span className="text-xs font-medium text-gray-800">{v}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Variants preview */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[0, 1].map((i) => (
            <div
              key={i}
              className={`rounded-xl border-2 p-4 ${i === 0 ? "border-blue-200 bg-blue-50" : "border-orange-200 bg-orange-50"}`}
            >
              <p
                className={`text-xs font-bold mb-2 ${i === 0 ? "text-blue-700" : "text-orange-700"}`}
              >
                Variant {i === 0 ? "A — Control" : "B — Test"}
              </p>
              <p className="text-sm font-semibold text-gray-800">
                {testConfig.variants[i][cfg.field] || (
                  <span className="text-gray-400 italic">not set</span>
                )}
              </p>
            </div>
          ))}
        </div>

        {/* Launch CTA */}
        <div className="bg-gradient-to-br from-violet-50 to-purple-50 border border-violet-200 rounded-2xl p-6">
          <button
            onClick={handleSave}
            disabled={loading}
            className="w-full py-3.5 bg-violet-600 text-white font-bold text-base rounded-xl hover:bg-violet-700 shadow-lg shadow-violet-200 hover:shadow-violet-300 transition-all disabled:opacity-50"
          >
            {loading
              ? "⏳ Creating..."
              : editMode
                ? "💾 Save Changes"
                : "🧪 Create A/B Test"}
          </button>
          <p className="text-xs text-gray-400 mt-3 text-center">
            The test will stay in Draft status until you start it from the
            dashboard.
          </p>
        </div>
      </div>
    );
  };

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
          <h1 className="text-2xl font-bold text-gray-900">
            {editMode ? "Edit A/B Test" : "Create A/B Test"}
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Step {step} of {STEPS.length}
          </p>
        </div>
        <button
          onClick={() => navigate("/ab-testing")}
          className="text-sm text-gray-500 hover:text-gray-700 border border-gray-200 px-3 py-1.5 rounded-lg hover:bg-gray-50"
        >
          ← Dashboard
        </button>
      </div>

      {/* Step nav */}
      <div className="mb-8">
        <StepNav
          current={step}
          steps={STEPS}
          completed={completed}
          onGoto={(s) => (completed.includes(s) || s === step) && setStep(s)}
        />
      </div>

      {/* Progress */}
      <div className="mb-8 bg-gray-100 rounded-full h-1.5">
        <div
          className="bg-violet-500 h-1.5 rounded-full transition-all duration-500"
          style={{ width: `${((step - 1) / (STEPS.length - 1)) * 100}%` }}
        />
      </div>

      {/* Card */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-8">
        {globalError && step === 1 && (
          <div className="mb-6 bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
            ⚠ {globalError}
          </div>
        )}
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
                className="px-6 py-2.5 text-sm font-bold text-white bg-violet-600 rounded-xl hover:bg-violet-700 shadow-md shadow-violet-200"
              >
                Continue →
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ABTestCreator;
