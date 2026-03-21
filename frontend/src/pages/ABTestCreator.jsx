import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import API from "../api";

const ABTestCreator = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [lists, setLists] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [listsLoading, setListsLoading] = useState(true);

  // ── Field-mapping state (mirrors CreateCampaign) ──────────
  const [dynamicFields, setDynamicFields] = useState([]);
  const [fieldMap, setFieldMap] = useState({});
  const [fallbackValues, setFallbackValues] = useState({});
  const [availableFields, setAvailableFields] = useState({
    universal: [],
    standard: [],
    custom: [],
  });
  const [fieldsLoading, setFieldsLoading] = useState(false);

  const [testConfig, setTestConfig] = useState({
    test_name: "",
    target_lists: [],
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
  });

  useEffect(() => {
    fetchListsAndTemplates();
  }, []);

  const fetchListsAndTemplates = async () => {
    setListsLoading(true);
    try {
      const [listsRes, templatesRes] = await Promise.all([
        API.get("/ab-tests/lists"),
        API.get("/ab-tests/templates"),
      ]);
      setLists(listsRes.data.lists || []);
      setTemplates(templatesRes.data.templates || []);
    } catch (err) {
      console.error("Failed to load lists/templates:", err);
      setError("Failed to load lists and templates");
    } finally {
      setListsLoading(false);
    }
  };

  const totalSelectedSubscribers = lists
    .filter((l) => testConfig.target_lists.includes(l.name))
    .reduce((sum, l) => sum + l.count, 0);

  const handleListToggle = (listName) => {
    setTestConfig((prev) => {
      const current = prev.target_lists;
      const updated = current.includes(listName)
        ? current.filter((n) => n !== listName)
        : [...current, listName];
      return { ...prev, target_lists: updated };
    });
  };

  const handleTemplateSelect = async (templateId) => {
    setTestConfig((prev) => ({ ...prev, template_id: templateId }));
    // Reset field mapping when template changes
    setDynamicFields([]);
    setFieldMap({});
    setFallbackValues({});

    if (!templateId) return;

    const selected = templates.find((t) => t._id === templateId);
    if (selected && selected.subject && !testConfig.subject) {
      setTestConfig((prev) => ({
        ...prev,
        subject: selected.subject,
        variants: [
          { ...prev.variants[0], subject: selected.subject },
          { ...prev.variants[1] },
        ],
      }));
    }

    // Fetch dynamic fields from the template (same as CreateCampaign)
    setFieldsLoading(true);
    try {
      const res = await API.get(`/templates/${templateId}/fields`);
      setDynamicFields(res.data || []);
    } catch (err) {
      console.error("Failed to fetch template fields:", err);
      setDynamicFields([]);
    } finally {
      setFieldsLoading(false);
    }
  };

  // Fetch available subscriber columns whenever target lists change
  useEffect(() => {
    if (testConfig.target_lists.length === 0) {
      setAvailableFields({ universal: [], standard: [], custom: [] });
      return;
    }
    API.post("/subscribers/analyze-fields", {
      listIds: testConfig.target_lists,
    })
      .then((res) =>
        setAvailableFields(
          res.data || { universal: [], standard: [], custom: [] },
        ),
      )
      .catch(() =>
        setAvailableFields({ universal: ["email"], standard: [], custom: [] }),
      );
  }, [testConfig.target_lists]);

  const handleTestTypeChange = (newType) => {
    setTestConfig((prev) => {
      const updatedVariants = [...prev.variants];
      if (newType === "subject_line") {
        updatedVariants[0] = { ...updatedVariants[0], subject: prev.subject };
        updatedVariants[1] = { ...updatedVariants[1], subject: "" };
      } else if (newType === "sender_name") {
        updatedVariants[0] = {
          ...updatedVariants[0],
          sender_name: prev.sender_name,
        };
        updatedVariants[1] = { ...updatedVariants[1], sender_name: "" };
      } else if (newType === "sender_email") {
        updatedVariants[0] = {
          ...updatedVariants[0],
          sender_email: prev.sender_email,
        };
        updatedVariants[1] = { ...updatedVariants[1], sender_email: "" };
      } else if (newType === "reply_to") {
        updatedVariants[0] = {
          ...updatedVariants[0],
          reply_to: prev.reply_to || prev.sender_email,
        };
        updatedVariants[1] = { ...updatedVariants[1], reply_to: "" };
      }
      return { ...prev, test_type: newType, variants: updatedVariants };
    });
  };

  const handleVariantChange = (variantIndex, field, value) => {
    setTestConfig((prev) => {
      const newVariants = [...prev.variants];
      newVariants[variantIndex] = {
        ...newVariants[variantIndex],
        [field]: value,
      };
      return { ...prev, variants: newVariants };
    });
  };

  const validateTest = () => {
    if (!testConfig.test_name.trim()) return "Test name is required";
    if (testConfig.target_lists.length === 0)
      return "Select at least one subscriber list";
    if (!testConfig.template_id) return "Select a template";
    if (!testConfig.subject.trim()) return "Subject line is required";
    if (!testConfig.sender_name.trim()) return "Sender name is required";
    if (!testConfig.sender_email.trim()) return "Sender email is required";

    if (
      testConfig.test_type === "subject_line" &&
      !testConfig.variants[1].subject.trim()
    )
      return "Variant B subject line is required";
    if (
      testConfig.test_type === "sender_name" &&
      !testConfig.variants[1].sender_name.trim()
    )
      return "Variant B sender name is required";
    if (
      testConfig.test_type === "sender_email" &&
      !testConfig.variants[1].sender_email.trim()
    )
      return "Variant B sender email is required";
    if (
      testConfig.test_type === "reply_to" &&
      !testConfig.variants[1].reply_to.trim()
    )
      return "Variant B reply-to address is required";

    // Validate all dynamic fields are mapped
    for (const field of dynamicFields) {
      if (!fieldMap[field] || fieldMap[field].trim() === "") {
        return `Please map the template field "{{${field}}}" to a subscriber data column`;
      }
    }

    if (testConfig.sample_size < 100) return "Sample size must be at least 100";
    if (!testConfig.test_duration_hours || testConfig.test_duration_hours < 1)
      return "Test duration must be at least 1 hour";
    return null;
  };

  const handleCreateTest = async () => {
    setError("");
    const validationError = validateTest();
    if (validationError) {
      setError(validationError);
      return;
    }

    setLoading(true);
    try {
      const cleanFieldMap = Object.fromEntries(
        Object.entries(fieldMap).map(([k, v]) => [k.trim(), v]),
      );
      const cleanFallback = Object.fromEntries(
        Object.entries(fallbackValues).map(([k, v]) => [k.trim(), v]),
      );
      await API.post("/ab-tests", {
        ...testConfig,
        field_map: cleanFieldMap,
        fallback_values: cleanFallback,
        test_duration_hours: testConfig.test_duration_hours,
        auto_send_winner: testConfig.auto_send_winner,
      });
      navigate("/ab-testing");
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to create A/B test");
    } finally {
      setLoading(false);
    }
  };

  const renderVariantField = (variantIndex, isControl = false) => {
    const variant = testConfig.variants[variantIndex];
    const variantLabel = isControl ? "Variant A (Control)" : "Variant B (Test)";
    const fieldMap = {
      subject_line: { field: "subject", label: "Subject Line", type: "text" },
      sender_name: { field: "sender_name", label: "Sender Name", type: "text" },
      sender_email: {
        field: "sender_email",
        label: "Sender Email",
        type: "email",
      },
      reply_to: { field: "reply_to", label: "Reply-To Address", type: "email" },
    };
    const config = fieldMap[testConfig.test_type];

    return (
      <div
        className={`border rounded-lg p-4 ${isControl ? "bg-blue-50 border-blue-200" : "bg-orange-50 border-orange-200"}`}
      >
        <h4 className="text-lg font-semibold mb-3 text-gray-800">
          {variantLabel}
        </h4>
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-700">
            {config.label}
          </label>
          <input
            type={config.type}
            value={variant[config.field] || ""}
            onChange={(e) =>
              handleVariantChange(variantIndex, config.field, e.target.value)
            }
            placeholder={
              isControl
                ? `Current ${config.label.toLowerCase()}`
                : `Enter test ${config.label.toLowerCase()}`
            }
            readOnly={isControl}
            className={`w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              isControl
                ? "bg-gray-100 text-gray-600 cursor-not-allowed"
                : "bg-white text-gray-900"
            }`}
          />
        </div>
      </div>
    );
  };

  if (listsLoading) {
    return (
      <div className="max-w-4xl mx-auto p-6">
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Create A/B Test</h1>
        <button
          onClick={() => navigate("/ab-testing")}
          className="text-gray-600 hover:text-gray-800 px-4 py-2 border rounded-lg"
        >
          Cancel
        </button>
      </div>

      <div className="space-y-8">
        {/* Test Name */}
        <div className="bg-white border rounded-lg p-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Test Name *
          </label>
          <input
            type="text"
            placeholder="e.g., Subject Line Test - January Promo"
            value={testConfig.test_name}
            onChange={(e) =>
              setTestConfig({ ...testConfig, test_name: e.target.value })
            }
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Target Lists */}
        <div className="bg-white border rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-1">Target Lists *</h3>
          <p className="text-sm text-gray-500 mb-4">
            Select subscriber lists for this A/B test
          </p>
          {lists.length === 0 ? (
            <p className="text-gray-500 text-sm">
              No subscriber lists found. Upload subscribers first.
            </p>
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {lists.map((list) => (
                  <label
                    key={list.name}
                    className={`flex items-center justify-between p-3 border rounded-lg cursor-pointer transition-colors ${
                      testConfig.target_lists.includes(list.name)
                        ? "bg-blue-50 border-blue-400"
                        : "bg-white border-gray-200 hover:bg-gray-50"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={testConfig.target_lists.includes(list.name)}
                        onChange={() => handleListToggle(list.name)}
                        className="h-4 w-4 text-blue-600 rounded border-gray-300"
                      />
                      <span className="text-sm font-medium text-gray-800">
                        {list.name}
                      </span>
                    </div>
                    <span className="text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full">
                      {list.count.toLocaleString()} subscribers
                    </span>
                  </label>
                ))}
              </div>
              {testConfig.target_lists.length > 0 && (
                <p className="mt-3 text-sm text-blue-700 font-medium">
                  ✓ {totalSelectedSubscribers.toLocaleString()} total
                  subscribers selected
                </p>
              )}
            </>
          )}
        </div>

        {/* Template */}
        <div className="bg-white border rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-1">Email Template *</h3>
          <p className="text-sm text-gray-500 mb-4">
            Select the base template for this test
          </p>
          {templates.length === 0 ? (
            <p className="text-gray-500 text-sm">
              No templates found. Create a template first.
            </p>
          ) : (
            <select
              value={testConfig.template_id}
              onChange={(e) => handleTemplateSelect(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Select a template...</option>
              {templates.map((t) => (
                <option key={t._id} value={t._id}>
                  {t.name} {t.subject ? `- "${t.subject}"` : ""}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* ── Field Mapping (shown after template selected) ── */}
        {testConfig.template_id && (
          <div className="bg-white border rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-1">Field Mapping</h3>
            <p className="text-sm text-gray-500 mb-4">
              Map each{" "}
              <code className="bg-gray-100 px-1 rounded">{"{{variable}}"}</code>{" "}
              in your template to a subscriber data column.
            </p>

            {fieldsLoading ? (
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500"></div>
                Analysing template fields…
              </div>
            ) : dynamicFields.length === 0 ? (
              <p className="text-sm text-green-700 bg-green-50 border border-green-200 rounded p-3">
                ✓ This template has no dynamic fields — no mapping required.
              </p>
            ) : testConfig.target_lists.length === 0 ? (
              <p className="text-sm text-yellow-700 bg-yellow-50 border border-yellow-200 rounded p-3">
                ⚠ Select at least one subscriber list above to load available
                data columns.
              </p>
            ) : (
              <div className="space-y-4">
                {dynamicFields.map((field) => (
                  <div key={field} className="border rounded-lg p-4 bg-gray-50">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-mono font-semibold text-purple-700">
                        {`{{${field}}}`}
                      </span>
                      {fieldMap[field] && (
                        <span className="text-xs text-green-600 font-medium">
                          ✓ Mapped
                        </span>
                      )}
                    </div>

                    <select
                      className={`w-full px-3 py-2 border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                        !fieldMap[field]
                          ? "border-red-400 bg-white"
                          : "border-gray-300 bg-white"
                      }`}
                      value={fieldMap[field] || ""}
                      onChange={(e) =>
                        setFieldMap((prev) => ({
                          ...prev,
                          [field]: e.target.value,
                        }))
                      }
                    >
                      <option value="">— Select field mapping —</option>
                      <option value="__DEFAULT__">
                        Use default/fallback value
                      </option>
                      <option value="__EMPTY__">Leave empty</option>

                      {availableFields.universal.length > 0 && (
                        <optgroup label="🌍 Universal">
                          {availableFields.universal.map((f) => (
                            <option
                              key={`universal.${f}`}
                              value={`universal.${f}`}
                            >
                              {f}
                            </option>
                          ))}
                        </optgroup>
                      )}
                      {availableFields.standard.length > 0 && (
                        <optgroup label="⭐ Standard Fields">
                          {availableFields.standard.map((f) => (
                            <option
                              key={`standard.${f}`}
                              value={`standard.${f}`}
                            >
                              {f}
                            </option>
                          ))}
                        </optgroup>
                      )}
                      {availableFields.custom.length > 0 && (
                        <optgroup label="🔧 Custom Fields">
                          {availableFields.custom.map((f) => (
                            <option key={`custom.${f}`} value={`custom.${f}`}>
                              {f}
                            </option>
                          ))}
                        </optgroup>
                      )}
                    </select>

                    {fieldMap[field] === "__DEFAULT__" && (
                      <input
                        type="text"
                        placeholder={`Default value for {{${field}}}`}
                        value={fallbackValues[field] || ""}
                        onChange={(e) =>
                          setFallbackValues((prev) => ({
                            ...prev,
                            [field]: e.target.value,
                          }))
                        }
                        className="mt-2 w-full px-3 py-2 border border-blue-300 rounded-md text-sm bg-blue-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    )}
                    {fieldMap[field] &&
                      fieldMap[field] !== "__DEFAULT__" &&
                      fieldMap[field] !== "__EMPTY__" && (
                        <div className="mt-2">
                          <input
                            type="text"
                            placeholder={`Fallback if subscriber's ${fieldMap[field]} is empty`}
                            value={fallbackValues[field] || ""}
                            onChange={(e) =>
                              setFallbackValues((prev) => ({
                                ...prev,
                                [field]: e.target.value,
                              }))
                            }
                            className="w-full px-3 py-2 border border-blue-300 rounded-md text-sm bg-blue-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                          />
                          <p className="text-xs text-blue-600 mt-1">
                            Used when this subscriber's field is empty or
                            missing. Leave blank to send empty.
                          </p>
                        </div>
                      )}
                  </div>
                ))}

                {/* Mapping summary */}
                <div className="text-xs text-gray-500 bg-gray-100 rounded p-3 space-y-1">
                  <p className="font-medium text-gray-600">
                    Available columns in selected lists:
                  </p>
                  <p>
                    🌍 Universal:{" "}
                    {availableFields.universal.join(", ") || "None"}
                  </p>
                  <p>
                    ⭐ Standard: {availableFields.standard.join(", ") || "None"}
                  </p>
                  <p>
                    🔧 Custom: {availableFields.custom.join(", ") || "None"}
                  </p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Sender Info */}
        <div className="bg-white border rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">Sender Details *</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Subject Line *
              </label>
              <input
                type="text"
                value={testConfig.subject}
                onChange={(e) => {
                  setTestConfig((prev) => ({
                    ...prev,
                    subject: e.target.value,
                    variants: [
                      { ...prev.variants[0], subject: e.target.value },
                      prev.variants[1],
                    ],
                  }));
                }}
                placeholder="Email subject line"
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Sender Name *
              </label>
              <input
                type="text"
                value={testConfig.sender_name}
                onChange={(e) => {
                  setTestConfig((prev) => ({
                    ...prev,
                    sender_name: e.target.value,
                    variants: [
                      { ...prev.variants[0], sender_name: e.target.value },
                      prev.variants[1],
                    ],
                  }));
                }}
                placeholder="e.g., Marketing Team"
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Sender Email *
              </label>
              <input
                type="email"
                value={testConfig.sender_email}
                onChange={(e) => {
                  setTestConfig((prev) => ({
                    ...prev,
                    sender_email: e.target.value,
                    variants: [
                      { ...prev.variants[0], sender_email: e.target.value },
                      prev.variants[1],
                    ],
                  }));
                }}
                placeholder="sender@yourdomain.com"
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Reply-To Email
              </label>
              <input
                type="email"
                value={testConfig.reply_to}
                onChange={(e) =>
                  setTestConfig({ ...testConfig, reply_to: e.target.value })
                }
                placeholder="reply@yourdomain.com (optional)"
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>

        {/* Test Configuration */}
        <div className="bg-white border rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">Test Configuration</h3>
          <div className="space-y-6">
            {/* Test Type */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Test Type
              </label>
              <select
                value={testConfig.test_type}
                onChange={(e) => handleTestTypeChange(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="subject_line">Subject Line</option>
                <option value="sender_name">Sender Name</option>
                <option value="sender_email">Sender Email</option>
                <option value="reply_to">Reply-To Address</option>
              </select>
            </div>

            {/* Variants */}
            <div>
              <h4 className="text-md font-semibold text-gray-900 mb-4">
                Variants
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {renderVariantField(0, true)}
                {renderVariantField(1, false)}
              </div>
            </div>

            {/* Split / Sample / Criteria */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Split: {testConfig.split_percentage}% /{" "}
                  {100 - testConfig.split_percentage}%
                </label>
                <input
                  type="range"
                  min="10"
                  max="90"
                  value={testConfig.split_percentage}
                  onChange={(e) =>
                    setTestConfig({
                      ...testConfig,
                      split_percentage: parseInt(e.target.value),
                    })
                  }
                  className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
                />
                <div className="flex justify-between text-xs text-gray-400 mt-1">
                  <span>A: {testConfig.split_percentage}%</span>
                  <span>B: {100 - testConfig.split_percentage}%</span>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Sample Size
                </label>
                <input
                  type="number"
                  value={testConfig.sample_size}
                  onChange={(e) =>
                    setTestConfig({
                      ...testConfig,
                      sample_size: parseInt(e.target.value) || 100,
                    })
                  }
                  min="100"
                  max={totalSelectedSubscribers || 100000}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                {totalSelectedSubscribers > 0 && (
                  <p className="text-xs text-gray-500 mt-1">
                    Max: {totalSelectedSubscribers.toLocaleString()} subscribers
                  </p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Winner Criteria
                </label>
                <select
                  value={testConfig.winner_criteria}
                  onChange={(e) =>
                    setTestConfig({
                      ...testConfig,
                      winner_criteria: e.target.value,
                    })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="open_rate">Open Rate</option>
                  <option value="click_rate">Click Rate</option>
                </select>
              </div>
            </div>

            {/* ── NEW: Test Duration ── */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Test Duration
                <span className="ml-2 text-xs font-normal text-gray-500">
                  Winner is auto-declared after this period
                </span>
              </label>
              <select
                value={testConfig.test_duration_hours}
                onChange={(e) =>
                  setTestConfig({
                    ...testConfig,
                    test_duration_hours: parseInt(e.target.value),
                  })
                }
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value={1}>1 hour</option>
                <option value={2}>2 hours</option>
                <option value={4}>4 hours</option>
                <option value={8}>8 hours</option>
                <option value={12}>12 hours</option>
                <option value={24}>24 hours (recommended)</option>
                <option value={48}>48 hours</option>
                <option value={72}>72 hours</option>
                <option value={168}>7 days</option>
              </select>
            </div>

            {/* ── NEW: Auto-send Winner ── */}
            <div
              className={`flex items-start gap-3 p-4 rounded-lg border transition-colors cursor-pointer ${
                testConfig.auto_send_winner
                  ? "bg-green-50 border-green-300"
                  : "bg-gray-50 border-gray-200"
              }`}
              onClick={() =>
                setTestConfig((prev) => ({
                  ...prev,
                  auto_send_winner: !prev.auto_send_winner,
                }))
              }
            >
              <input
                id="auto_send_winner"
                type="checkbox"
                checked={testConfig.auto_send_winner}
                onChange={(e) =>
                  setTestConfig({
                    ...testConfig,
                    auto_send_winner: e.target.checked,
                  })
                }
                className="mt-0.5 h-4 w-4 text-green-600 rounded border-gray-300 cursor-pointer"
                onClick={(e) => e.stopPropagation()}
              />
              <div>
                <label
                  htmlFor="auto_send_winner"
                  className="text-sm font-medium text-gray-800 cursor-pointer"
                >
                  Auto-send winning variant to remaining subscribers
                </label>
                <p className="text-xs text-gray-500 mt-0.5">
                  When the test ends, the winning variant is automatically
                  applied to the campaign and sent to all subscribers who were{" "}
                  <strong>not</strong> part of the A/B test sample. If disabled,
                  you can trigger the send manually from the results page.
                </p>
              </div>
            </div>
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-sm text-red-800">⚠️ {error}</p>
          </div>
        )}

        <div className="flex justify-end space-x-3 pb-6">
          <button
            onClick={() => navigate("/ab-testing")}
            className="px-6 py-2 text-sm font-medium text-gray-700 bg-gray-100 border border-gray-300 rounded-lg hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            onClick={handleCreateTest}
            disabled={loading}
            className="px-6 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Creating..." : "Create A/B Test"}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ABTestCreator;
