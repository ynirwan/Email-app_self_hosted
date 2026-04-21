import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Monitor, Smartphone, Tablet } from "lucide-react";
import API from "../api";

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
});

const ABTestCreator = ({ editMode = false }) => {
  const navigate = useNavigate();
  const { testId } = useParams();

  const [step, setStep] = useState(1); // 1=Content, 2=Audience+Template+Mapping, 3=Preview+Config

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [loadingEdit, setLoadingEdit] = useState(editMode);

  const [lists, setLists] = useState([]);
  const [segments, setSegments] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [senderProfiles, setSenderProfiles] = useState([]);

  const [loadingLists, setLoadingLists] = useState(false);
  const [loadingSegments, setLoadingSegments] = useState(false);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [loadingSenderProfiles, setLoadingSenderProfiles] = useState(false);
  const [fieldsLoading, setFieldsLoading] = useState(false);

  const [previewHtml, setPreviewHtml] = useState("");
  const [previewMode, setPreviewMode] = useState("desktop");

  const [testEmail, setTestEmail] = useState("");
  const [sendingTest, setSendingTest] = useState(false);
  const [testSent, setTestSent] = useState(false);

  const [dynamicFields, setDynamicFields] = useState([]);
  const [fieldMap, setFieldMap] = useState({});
  const [fallbackValues, setFallbackValues] = useState({});
  const [availableFields, setAvailableFields] = useState({
    universal: [],
    standard: [],
    custom: [],
  });

  const [testConfig, setTestConfig] = useState({
    test_name: "",
    target_lists: [],
    target_segments: [],
    audience_mode: "lists", // lists | segments | both
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

  const selectedTemplate =
    templates.find((t) => (t._id || t.id) === testConfig.template_id) || null;

  const extractHtmlFromTemplate = (template) => {
    if (!template) return "";

    const contentJson = template.content_json || {};
    if (contentJson.mode === "html" && contentJson.content)
      return contentJson.content;
    if (contentJson.mode === "drag-drop" && contentJson.blocks) {
      return contentJson.blocks.map((block) => block.content || "").join("\n");
    }
    if (contentJson.mode === "visual" && contentJson.content)
      return contentJson.content;
    if (template.html) return template.html;

    try {
      let extracted = "";
      contentJson.body?.rows?.forEach((row) => {
        row.columns?.forEach((column) => {
          column.contents?.forEach((content) => {
            if (content.type === "html" && content.values?.html) {
              extracted += `${content.values.html}\n`;
            }
          });
        });
      });
      return extracted || "<p>No preview available</p>";
    } catch {
      return "<p>No preview available</p>";
    }
  };

  const getAudienceError = () => {
    const mode = testConfig.audience_mode;
    if (mode === "lists" && testConfig.target_lists.length === 0) {
      return "Select at least one subscriber list.";
    }
    if (mode === "segments" && testConfig.target_segments.length === 0) {
      return "Select at least one segment.";
    }
    if (mode === "both") {
      if (
        testConfig.target_lists.length === 0 ||
        testConfig.target_segments.length === 0
      ) {
        return "Select at least one list and one segment for 'Both' mode.";
      }
    }
    return null;
  };

  const getTotalRecipients = () => {
    const listCount = lists
      .filter((l) => testConfig.target_lists.includes(l._id || l.name))
      .reduce(
        (sum, l) => sum + (l.total_count || l.count || l.active_count || 0),
        0,
      );

    const segmentCount = segments
      .filter((s) => testConfig.target_segments.includes(s._id))
      .reduce((sum, s) => sum + (s.subscriber_count || 0), 0);

    return listCount + segmentCount;
  };

  const totalSelectedSubscribers = getTotalRecipients();

  useEffect(() => {
    const loadInitialData = async () => {
      setLoadingLists(true);
      setLoadingSegments(true);
      setLoadingTemplates(true);
      setLoadingSenderProfiles(true);
      setError("");

      try {
        const [listsRes, segmentsRes, templatesRes, senderProfilesRes] =
          await Promise.all([
          API.get("/subscribers/lists"),
          API.get("/segments"),
          API.get("/templates"),
          API.get("/settings/sender-profiles").catch(() => ({ data: [] })),
        ]);

        setLists(Array.isArray(listsRes.data) ? listsRes.data : []);
        const segmentData = segmentsRes.data?.segments || segmentsRes.data || [];
        setSegments(Array.isArray(segmentData) ? segmentData : []);
        setTemplates(Array.isArray(templatesRes.data) ? templatesRes.data : []);
        setSenderProfiles(
          Array.isArray(senderProfilesRes.data) ? senderProfilesRes.data : [],
        );
      } catch (err) {
        console.error("Failed to load A/B test setup data:", err);
        setError("Failed to load lists, segments, or templates");
      } finally {
        setLoadingLists(false);
        setLoadingSegments(false);
        setLoadingTemplates(false);
        setLoadingSenderProfiles(false);
      }
    };

    loadInitialData();
  }, []);

  useEffect(() => {
    if (!editMode || !testId) {
      setLoadingEdit(false);
      return;
    }

    const loadTestForEdit = async () => {
      setLoadingEdit(true);
      setError("");
      try {
        const res = await API.get(`/ab-tests/${testId}`);
        const test = res.data?.test || res.data;
        if (test?.status && test.status !== "draft") {
          setError(
            `Cannot edit a test with status "${test.status}". Only draft tests are editable.`,
          );
          return;
        }

        setTestConfig(mapTestToConfig(test || {}));
        setFieldMap(test?.field_map || {});
        setFallbackValues(test?.fallback_values || {});
      } catch (err) {
        setError(err.response?.data?.detail || "Failed to load A/B test");
      } finally {
        setLoadingEdit(false);
      }
    };

    loadTestForEdit();
  }, [editMode, testId]);

  useEffect(() => {
    if (!selectedTemplate) {
      setPreviewHtml("");
      setDynamicFields([]);
      setFieldMap({});
      setFallbackValues({});
      return;
    }

    setPreviewHtml(extractHtmlFromTemplate(selectedTemplate));

    if (selectedTemplate.subject && !testConfig.subject) {
      setTestConfig((prev) => ({
        ...prev,
        subject: selectedTemplate.subject,
        variants: [
          { ...prev.variants[0], subject: selectedTemplate.subject },
          { ...prev.variants[1] },
        ],
      }));
    }

    setFieldMap({});
    setFallbackValues({});

    setFieldsLoading(true);
    API.get(`/templates/${selectedTemplate._id || selectedTemplate.id}/fields`)
      .then((res) => setDynamicFields(Array.isArray(res.data) ? res.data : []))
      .catch(() => setDynamicFields([]))
      .finally(() => setFieldsLoading(false));
  }, [selectedTemplate]);

  useEffect(() => {
    const hasAudience =
      testConfig.target_lists.length > 0 || testConfig.target_segments.length > 0;

    if (!hasAudience) {
      setAvailableFields({ universal: [], standard: [], custom: [] });
      return;
    }

    const payload = {};
    if (testConfig.target_lists.length > 0) payload.listIds = testConfig.target_lists;
    if (testConfig.target_segments.length > 0) {
      payload.segmentIds = testConfig.target_segments;
    }

    API.post("/subscribers/analyze-fields", payload)
      .then((res) =>
        setAvailableFields(
          res.data || { universal: ["email"], standard: [], custom: [] },
        ),
      )
      .catch(() =>
        setAvailableFields({ universal: ["email"], standard: [], custom: [] }),
      );
  }, [testConfig.target_lists, testConfig.target_segments]);

  useEffect(() => {
    if (!dynamicFields.length) return;

    const allAvailable = [
      ...availableFields.universal,
      ...availableFields.standard.map((f) => `standard.${f}`),
      ...availableFields.custom.map((f) => `custom.${f}`),
    ];
    if (!allAvailable.length) return;

    const normalize = (s) => (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");

    const lookup = {};
    availableFields.universal.forEach((f) => {
      lookup[normalize(f)] = f;
    });
    availableFields.standard.forEach((f) => {
      lookup[normalize(f)] = `standard.${f}`;
    });
    availableFields.custom.forEach((f) => {
      lookup[normalize(f)] = `custom.${f}`;
    });

    setFieldMap((prev) => {
      const next = { ...prev };
      dynamicFields.forEach((field) => {
        if (next[field] && next[field].trim() !== "") return;
        const n = normalize(field);

        if (lookup[n]) {
          next[field] = lookup[n];
          return;
        }

        const partial = allAvailable.find((candidate) => {
          const stripped = candidate.replace(/^(standard|custom)\./, "");
          const c = normalize(stripped);
          return c.includes(n) || n.includes(c);
        });

        if (partial) next[field] = partial;
      });
      return next;
    });
  }, [dynamicFields, availableFields]);

  const handleListToggle = (listId) => {
    setTestConfig((prev) => ({
      ...prev,
      target_lists: prev.target_lists.includes(listId)
        ? prev.target_lists.filter((id) => id !== listId)
        : [...prev.target_lists, listId],
    }));
  };

  const handleSegmentToggle = (segmentId) => {
    setTestConfig((prev) => ({
      ...prev,
      target_segments: prev.target_segments.includes(segmentId)
        ? prev.target_segments.filter((id) => id !== segmentId)
        : [...prev.target_segments, segmentId],
    }));
  };

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
      const updated = [...prev.variants];
      updated[variantIndex] = { ...updated[variantIndex], [field]: value };
      return { ...prev, variants: updated };
    });
  };

  const validateStep1 = () => {
    if (!testConfig.test_name.trim()) return false;
    if (!testConfig.subject.trim()) return false;
    if (!testConfig.sender_name.trim()) return false;
    if (!testConfig.sender_email.trim()) return false;
    return true;
  };

  const validateStep2 = () => {
    if (getAudienceError()) return false;
    if (!testConfig.template_id) return false;

    for (const field of dynamicFields) {
      if (!fieldMap[field] || fieldMap[field].trim() === "") return false;
    }

    return true;
  };

  const validateStep3 = () => {
    if (
      testConfig.test_type === "subject_line" &&
      !testConfig.variants[1].subject.trim()
    ) {
      return "Variant B subject line is required";
    }
    if (
      testConfig.test_type === "sender_name" &&
      !testConfig.variants[1].sender_name.trim()
    ) {
      return "Variant B sender name is required";
    }
    if (
      testConfig.test_type === "sender_email" &&
      !testConfig.variants[1].sender_email.trim()
    ) {
      return "Variant B sender email is required";
    }
    if (
      testConfig.test_type === "reply_to" &&
      !testConfig.variants[1].reply_to.trim()
    ) {
      return "Variant B reply-to address is required";
    }

    if (testConfig.sample_size < 100) return "Sample size must be at least 100";
    if (!testConfig.test_duration_hours || testConfig.test_duration_hours < 1) {
      return "Test duration must be at least 1 hour";
    }

    return null;
  };

  const applySenderProfile = (profileId) => {
    const profile = senderProfiles.find(
      (sp) => (sp._id || sp.id) === profileId,
    );
    if (!profile) return;

    const senderName = profile.name || profile.sender_name || "";
    const senderEmail = profile.email || profile.sender_email || "";
    const replyTo = profile.reply_to || senderEmail;
    setTestConfig((prev) => ({
      ...prev,
      sender_name: senderName,
      sender_email: senderEmail,
      reply_to: replyTo,
      variants: [
        { ...prev.variants[0], sender_name: senderName, sender_email: senderEmail },
        prev.variants[1],
      ],
    }));
  };

  const handleSaveTest = async () => {
    setError("");

    if (!validateStep1()) {
      setError("Please complete required fields in Step 1.");
      setStep(1);
      return;
    }
    if (!validateStep2()) {
      setError(
        getAudienceError() ||
          "Please complete audience, template, and field mapping in Step 2.",
      );
      setStep(2);
      return;
    }

    const step3Error = validateStep3();
    if (step3Error) {
      setError(step3Error);
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

      const payload = {
        ...testConfig,
        field_map: cleanFieldMap,
        fallback_values: cleanFallback,
        reply_to: testConfig.reply_to || testConfig.sender_email,
      };

      if (editMode && testId) {
        await API.put(`/ab-tests/${testId}`, payload);
        navigate(`/ab-testing?updated=${testId}`);
      } else {
        await API.post("/ab-tests", payload);
        navigate("/ab-testing");
      }
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          (editMode ? "Failed to update A/B test" : "Failed to create A/B test"),
      );
    } finally {
      setLoading(false);
    }
  };

  const sendTestEmail = async () => {
    if (!testEmail.trim()) {
      setError("Please enter an email address to send test.");
      return;
    }

    if (!selectedTemplate || !previewHtml) {
      setError("Please select a template first.");
      return;
    }

    setSendingTest(true);
    setTestSent(false);
    setError("");

    try {
      await API.post("/campaigns/send-test", {
        to: testEmail,
        subject: testConfig.subject,
        content: previewHtml,
        sender_name: testConfig.sender_name,
        sender_email: testConfig.sender_email,
        template_id: selectedTemplate._id || selectedTemplate.id,
      });
      setTestSent(true);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to send test email");
    } finally {
      setSendingTest(false);
    }
  };

  const renderVariantField = (variantIndex, isControl = false) => {
    const variant = testConfig.variants[variantIndex];
    const variantLabel = isControl ? "Variant A (Control)" : "Variant B (Test)";
    const typeConfig = {
      subject_line: { field: "subject", label: "Subject Line", type: "text" },
      sender_name: { field: "sender_name", label: "Sender Name", type: "text" },
      sender_email: {
        field: "sender_email",
        label: "Sender Email",
        type: "email",
      },
      reply_to: { field: "reply_to", label: "Reply-To Address", type: "email" },
    };
    const config = typeConfig[testConfig.test_type];

    return (
      <div
        className={`border rounded-lg p-4 ${isControl ? "bg-blue-50 border-blue-200" : "bg-orange-50 border-orange-200"}`}
      >
        <h4 className="text-lg font-semibold mb-3 text-gray-800">{variantLabel}</h4>
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

  const renderStep1 = () => (
    <div className="space-y-6">
      <h3 className="text-xl font-semibold">Campaign Content</h3>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Test Name *
        </label>
        <input
          type="text"
          placeholder="e.g., Subject Line Test - April Promo"
          value={testConfig.test_name}
          onChange={(e) =>
            setTestConfig((prev) => ({ ...prev, test_name: e.target.value }))
          }
          className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Subject Line *
          </label>
          <input
            type="text"
            value={testConfig.subject}
            onChange={(e) => {
              const value = e.target.value;
              setTestConfig((prev) => ({
                ...prev,
                subject: value,
                variants: [{ ...prev.variants[0], subject: value }, prev.variants[1]],
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
              const value = e.target.value;
              setTestConfig((prev) => ({
                ...prev,
                sender_name: value,
                variants: [
                  { ...prev.variants[0], sender_name: value },
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
              const value = e.target.value;
              setTestConfig((prev) => ({
                ...prev,
                sender_email: value,
                variants: [
                  { ...prev.variants[0], sender_email: value },
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
              setTestConfig((prev) => ({ ...prev, reply_to: e.target.value }))
            }
            placeholder="reply@yourdomain.com (optional)"
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>
    </div>
  );

  const renderStep2 = () => (
    <div className="space-y-6">
      <h3 className="text-xl font-semibold">Audience, Template, and Mapping</h3>

      <div className="p-4 bg-blue-50 rounded">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <p className="font-semibold text-blue-800">Lists Selected</p>
            <p className="text-lg">{testConfig.target_lists.length}</p>
          </div>
          <div>
            <p className="font-semibold text-blue-800">Segments Selected</p>
            <p className="text-lg">{testConfig.target_segments.length}</p>
          </div>
          <div>
            <p className="font-semibold text-blue-800">Estimated Recipients</p>
            <p className="text-xl font-bold">
              {totalSelectedSubscribers.toLocaleString()}
            </p>
          </div>
        </div>
      </div>

      <div>
        <label className="block font-medium mb-3">Target Audience Type</label>
        <div className="flex flex-wrap gap-4">
          {[
            { value: "lists", label: "Lists Only" },
            { value: "segments", label: "Segments Only" },
            { value: "both", label: "Both Lists and Segments" },
          ].map((option) => (
            <label key={option.value} className="flex items-center">
              <input
                type="radio"
                name="audienceMode"
                value={option.value}
                checked={testConfig.audience_mode === option.value}
                onChange={(e) =>
                  setTestConfig((prev) => ({
                    ...prev,
                    audience_mode: e.target.value,
                  }))
                }
                className="mr-2"
              />
              {option.label}
            </label>
          ))}
        </div>
      </div>

      {(testConfig.audience_mode === "lists" ||
        testConfig.audience_mode === "both") && (
        <div>
          <h4 className="font-semibold mb-3">Subscriber Lists</h4>
          <div className="max-h-64 overflow-auto border rounded p-3">
            {loadingLists ? (
              <p className="text-gray-600">Loading lists...</p>
            ) : lists.length === 0 ? (
              <p className="text-gray-600">No subscriber lists available</p>
            ) : (
              lists.map((list) => {
                const listId = list._id || list.name;
                return (
                  <label
                    key={listId}
                    className="flex items-center mb-2 cursor-pointer hover:bg-gray-100 p-2 rounded"
                  >
                    <input
                      type="checkbox"
                      className="mr-3"
                      checked={testConfig.target_lists.includes(listId)}
                      onChange={() => handleListToggle(listId)}
                    />
                    <span className="font-medium">{list.name || listId}</span>
                    <span className="ml-2 text-gray-500">
                      ({(list.total_count || list.count || 0).toLocaleString()})
                    </span>
                  </label>
                );
              })
            )}
          </div>
        </div>
      )}

      {(testConfig.audience_mode === "segments" ||
        testConfig.audience_mode === "both") && (
        <div>
          <h4 className="font-semibold mb-3">Targeted Segments</h4>
          <div className="max-h-72 overflow-auto border rounded p-3">
            {loadingSegments ? (
              <p className="text-gray-600">Loading segments...</p>
            ) : segments.length === 0 ? (
              <p className="text-gray-600">No segments available</p>
            ) : (
              segments.map((segment) => (
                <label
                  key={segment._id}
                  className="flex items-start mb-2 cursor-pointer hover:bg-gray-50 p-3 rounded border"
                >
                  <input
                    type="checkbox"
                    className="mr-3 mt-1"
                    checked={testConfig.target_segments.includes(segment._id)}
                    onChange={() => handleSegmentToggle(segment._id)}
                  />
                  <div className="flex-1">
                    <div className="flex justify-between">
                      <span className="font-semibold text-blue-800">
                        {segment.name}
                      </span>
                      <span className="text-sm text-gray-700">
                        {(segment.subscriber_count || 0).toLocaleString()}
                      </span>
                    </div>
                    <p className="text-sm text-gray-600">{segment.description}</p>
                  </div>
                </label>
              ))
            )}
          </div>
        </div>
      )}

      <div>
        <label className="block font-medium mb-1">Select Template *</label>
        <select
          value={testConfig.template_id}
          onChange={(e) =>
            setTestConfig((prev) => ({ ...prev, template_id: e.target.value }))
          }
          className="w-full px-3 py-2 border border-gray-300 rounded"
        >
          <option value="">-- Select a Template --</option>
          {loadingTemplates ? (
            <option disabled>Loading...</option>
          ) : (
            templates.map((t) => (
              <option key={t._id || t.id} value={t._id || t.id}>
                {t.name} ({t.content_json?.mode || "legacy"})
              </option>
            ))
          )}
        </select>
      </div>
      {senderProfiles.length > 0 && (
        <div>
          <label className="block font-medium mb-1">Quick-fill Sender Profile</label>
          <select
            defaultValue=""
            onChange={(e) => applySenderProfile(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded"
          >
            <option value="">-- Select sender profile --</option>
            {senderProfiles.map((profile) => (
              <option key={profile._id || profile.id} value={profile._id || profile.id}>
                {profile.name || profile.sender_name}
              </option>
            ))}
          </select>
        </div>
      )}

      {testConfig.template_id && (
        <div className="bg-white border rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-1">Field Mapping</h3>
          <p className="text-sm text-gray-500 mb-4">
            Map each <code className="bg-gray-100 px-1 rounded">{"{{variable}}"}</code>{" "}
            in your template to subscriber data.
          </p>

          {fieldsLoading ? (
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500"></div>
              Analyzing template fields...
            </div>
          ) : dynamicFields.length === 0 ? (
            <p className="text-sm text-green-700 bg-green-50 border border-green-200 rounded p-3">
              This template has no dynamic fields. No mapping required.
            </p>
          ) : getAudienceError() ? (
            <p className="text-sm text-yellow-700 bg-yellow-50 border border-yellow-200 rounded p-3">
              {getAudienceError()} Select audience above to load available columns.
            </p>
          ) : (
            <div className="space-y-4">
              {dynamicFields.map((field) => {
                const showFallbackInput =
                  fieldMap[field] &&
                  fieldMap[field] !== "__EMPTY__" &&
                  (fieldMap[field] === "__DEFAULT__" ||
                    !fieldMap[field].startsWith("__"));

                return (
                  <div key={field} className="border rounded-lg p-4 bg-gray-50">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-mono font-semibold text-purple-700">
                        {`{{${field}}}`}
                      </span>
                      {fieldMap[field] && (
                        <span className="text-xs text-green-600 font-medium">
                          Mapped
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
                      <option value="">Select field mapping</option>
                      <option value="__DEFAULT__">Use default/fallback value</option>
                      <option value="__EMPTY__">Leave empty</option>

                      {availableFields.universal.length > 0 && (
                        <optgroup label="Universal">
                          {availableFields.universal.map((f) => (
                            <option key={`universal.${f}`} value={f}>
                              {f}
                            </option>
                          ))}
                        </optgroup>
                      )}
                      {availableFields.standard.length > 0 && (
                        <optgroup label="Standard Fields">
                          {availableFields.standard.map((f) => (
                            <option key={`standard.${f}`} value={`standard.${f}`}>
                              {f}
                            </option>
                          ))}
                        </optgroup>
                      )}
                      {availableFields.custom.length > 0 && (
                        <optgroup label="Custom Fields">
                          {availableFields.custom.map((f) => (
                            <option key={`custom.${f}`} value={`custom.${f}`}>
                              {f}
                            </option>
                          ))}
                        </optgroup>
                      )}
                    </select>

                    {showFallbackInput && (
                      <div className="mt-2">
                        <input
                          type="text"
                          placeholder={
                            fieldMap[field] === "__DEFAULT__"
                              ? `Default value for {{${field}}}`
                              : `Fallback if subscriber's ${fieldMap[field]} is empty`
                          }
                          value={fallbackValues[field] || ""}
                          onChange={(e) =>
                            setFallbackValues((prev) => ({
                              ...prev,
                              [field]: e.target.value,
                            }))
                          }
                          className="w-full px-3 py-2 border border-blue-300 rounded-md text-sm bg-blue-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                        {fieldMap[field] !== "__DEFAULT__" && (
                          <p className="text-xs text-blue-600 mt-1">
                            Used when this subscriber field is empty or missing.
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}

              <div className="text-xs text-gray-500 bg-gray-100 rounded p-3 space-y-1">
                <p className="font-medium text-gray-600">
                  Available columns in selected audience:
                </p>
                <p>Universal: {availableFields.universal.join(", ") || "None"}</p>
                <p>Standard: {availableFields.standard.join(", ") || "None"}</p>
                <p>Custom: {availableFields.custom.join(", ") || "None"}</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );

  const renderStep3 = () => (
    <div className="space-y-6">
      <h3 className="text-xl font-semibold">Preview, Test, and A/B Configuration</h3>

      <div className="p-4 bg-gray-50 rounded">
        <h4 className="font-semibold mb-3">A/B Test Summary</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <div>
            <p>
              <strong>Test Name:</strong> {testConfig.test_name || "-"}
            </p>
            <p>
              <strong>Subject:</strong> {testConfig.subject || "-"}
            </p>
            <p>
              <strong>Template:</strong> {selectedTemplate?.name || "-"}
            </p>
          </div>
          <div>
            <p>
              <strong>Audience:</strong>{" "}
              {testConfig.audience_mode === "both"
                ? "Lists + Segments"
                : testConfig.audience_mode === "segments"
                  ? "Segments"
                  : "Lists"}
            </p>
            <p>
              <strong>Estimated Recipients:</strong>{" "}
              {totalSelectedSubscribers.toLocaleString()}
            </p>
            <p>
              <strong>Sender:</strong> {testConfig.sender_name || "-"} &lt;
              {testConfig.sender_email || "-"}&gt;
            </p>
          </div>
        </div>
      </div>

      <div className="p-4 bg-green-50 rounded border border-green-300">
        <label className="block font-medium mb-1">Test Email Address</label>
        <input
          type="email"
          className="w-full px-3 py-2 border rounded border-green-300 mb-3"
          value={testEmail}
          onChange={(e) => setTestEmail(e.target.value)}
        />
        <button
          type="button"
          onClick={sendTestEmail}
          disabled={sendingTest || !testEmail.trim()}
          className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded disabled:opacity-50"
        >
          {sendingTest ? "Sending..." : "Send Test Email"}
        </button>
        {testSent && (
          <p className="mt-2 text-green-700">Test email sent successfully.</p>
        )}
      </div>

      <div className="p-4 border rounded bg-white">
        <div className="flex justify-between items-center mb-4">
          <h4 className="font-semibold">Email Preview</h4>
          <div className="flex gap-2">
            {[
              { mode: "desktop", icon: <Monitor size={16} /> },
              { mode: "tablet", icon: <Tablet size={16} /> },
              { mode: "mobile", icon: <Smartphone size={16} /> },
            ].map((button) => (
              <button
                key={button.mode}
                type="button"
                onClick={() => setPreviewMode(button.mode)}
                className={`p-2 rounded ${
                  previewMode === button.mode
                    ? "bg-blue-600 text-white"
                    : "hover:bg-gray-200"
                }`}
              >
                {button.icon}
              </button>
            ))}
          </div>
        </div>

        <div className="bg-gray-100 p-4 rounded flex justify-center overflow-auto max-h-[600px]">
          {previewHtml ? (
            <div
              dangerouslySetInnerHTML={{ __html: previewHtml }}
              className={`bg-white shadow-lg ${
                previewMode === "desktop"
                  ? "w-full max-w-4xl"
                  : previewMode === "tablet"
                    ? "w-[768px]"
                    : "w-[375px]"
              }`}
            />
          ) : (
            <p className="text-gray-500">Select a template to preview</p>
          )}
        </div>
      </div>

      <div className="bg-white border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">Test Configuration</h3>
        <div className="space-y-6">
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

          <div>
            <h4 className="text-md font-semibold text-gray-900 mb-4">Variants</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {renderVariantField(0, true)}
              {renderVariantField(1, false)}
            </div>
          </div>

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
                  setTestConfig((prev) => ({
                    ...prev,
                    split_percentage: parseInt(e.target.value, 10),
                  }))
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
                  setTestConfig((prev) => ({
                    ...prev,
                    sample_size: parseInt(e.target.value, 10) || 100,
                  }))
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
                  setTestConfig((prev) => ({
                    ...prev,
                    winner_criteria: e.target.value,
                  }))
                }
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="open_rate">Open Rate</option>
                <option value="click_rate">Click Rate</option>
              </select>
            </div>
          </div>

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
                setTestConfig((prev) => ({
                  ...prev,
                  test_duration_hours: parseInt(e.target.value, 10),
                }))
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
                setTestConfig((prev) => ({
                  ...prev,
                  auto_send_winner: e.target.checked,
                }))
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
                When test ends, the winner can be automatically applied and sent
                to subscribers not included in the A/B sample.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const isInitialLoading =
    loadingLists || loadingSegments || loadingTemplates || loadingSenderProfiles;

  if (loadingEdit) {
    return (
      <div className="max-w-5xl mx-auto p-6">
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading A/B test builder...</p>
        </div>
      </div>
    );
  }

  if (error && editMode && !testConfig.test_name) {
    return (
      <div className="max-w-3xl mx-auto p-6">
        <div className="text-center py-12 border rounded-lg bg-white shadow">
          <p className="text-4xl mb-3">⚠️</p>
          <p className="font-semibold text-gray-800 mb-1">Cannot Edit Test</p>
          <p className="text-sm text-gray-500 mb-4">{error}</p>
          <button
            onClick={() => navigate("/ab-testing")}
            className="px-5 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700"
          >
            ← Back to Tests
          </button>
        </div>
      </div>
    );
  }

  if (isInitialLoading && !lists.length && !templates.length) {
    return (
      <div className="max-w-5xl mx-auto p-6">
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading A/B test builder...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto p-6 bg-white rounded shadow">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">
          {editMode ? "✏️ Edit A/B Test" : "🧪 Create A/B Test"}
        </h1>
        <button
          onClick={() => navigate("/ab-testing")}
          className="text-gray-600 hover:text-gray-800 px-4 py-2 border rounded-lg"
        >
          Cancel
        </button>
      </div>

      <div className="mb-6 flex gap-4 text-sm font-semibold">
        {[1, 2, 3].map((n) => (
          <button
            key={n}
            type="button"
            disabled={step === n}
            onClick={() => setStep(n)}
            className={`px-4 py-2 rounded ${
              step === n ? "bg-blue-600 text-white" : "bg-gray-200 hover:bg-gray-300"
            }`}
          >
            Step {n}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-6 bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-sm text-red-800">{error}</p>
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (step === 1) {
            if (validateStep1()) {
              setError("");
              setStep(2);
            } else {
              setError("Please complete all required fields in Step 1.");
            }
            return;
          }

          if (step === 2) {
            if (validateStep2()) {
              setError("");
              setStep(3);
            } else {
              setError(
                getAudienceError() || "Please complete Step 2 before continuing.",
              );
            }
            return;
          }

          handleSaveTest();
        }}
      >
        {step === 1 && renderStep1()}
        {step === 2 && renderStep2()}
        {step === 3 && renderStep3()}

        <div className="flex justify-between mt-6">
          {step > 1 ? (
            <button
              type="button"
              onClick={() => setStep((prev) => prev - 1)}
              className="px-6 py-2 bg-gray-300 hover:bg-gray-400 rounded"
            >
              Previous
            </button>
          ) : (
            <div />
          )}

          <button
            type="submit"
            disabled={
              loading ||
              (step === 1 && !validateStep1()) ||
              (step === 2 && !validateStep2())
            }
            className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded disabled:opacity-50"
          >
            {step < 3
              ? "Next"
              : loading
                ? editMode
                  ? "Saving..."
                  : "Creating..."
                : editMode
                  ? "Save Changes"
                  : "Create A/B Test"}
          </button>
        </div>
      </form>
    </div>
  );
};

export default ABTestCreator;
