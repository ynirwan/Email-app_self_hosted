import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import API from '../api';
import { Monitor, Smartphone, Tablet } from 'lucide-react';

export default function CreateCampaign() {
  // Step state: 1 = Content, 2 = Audience + Template Select + Field Mapping, 3 = Preview/Test
  const [step, setStep] = useState(1);
  
  // Form data fields
  const [title, setTitle] = useState('');
  const [subject, setSubject] = useState('');
  const [senderName, setSenderName] = useState('');
  const [senderEmail, setSenderEmail] = useState('');
  const [replyTo, setReplyTo] = useState('');
  const isValidEmail = (email) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  
  // Template and preview HTML
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [previewHtml, setPreviewHtml] = useState('');
  
  // Dynamic fields to map with audience list columns
  const [dynamicFields, setDynamicFields] = useState([]);
  const [fieldMap, setFieldMap] = useState({});
  const [fallbackValues, setFallbackValues] = useState({});
  
  // Available fields state
  const [availableFields, setAvailableFields] = useState({
    universal: [],
    standard: [],
    custom: []
  });
  
  // Audience lists and selection
  const [lists, setLists] = useState([]);
  const [selectedLists, setSelectedLists] = useState([]);
  
  // Segmentation Integration
  const [segments, setSegments] = useState([]);
  const [selectedSegments, setSelectedSegments] = useState([]);
  const [loadingSegments, setLoadingSegments] = useState(false);
  const [audienceMode, setAudienceMode] = useState('lists'); // 'lists', 'segments', 'both'
  
  // Loading and error states
  const [loadingLists, setLoadingLists] = useState(false);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [error, setError] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');
  
  // Test email states for step 3
  const [testEmail, setTestEmail] = useState('');
  const [sendingTest, setSendingTest] = useState(false);
  const [testSent, setTestSent] = useState(false);
  
  // Preview mode state
  const [previewMode, setPreviewMode] = useState('desktop');
  
  const navigate = useNavigate();

  // Fetch templates on mount
  useEffect(() => {
    setLoadingTemplates(true);
    API.get('/templates')
      .then((res) => setTemplates(res.data))
      .catch(() => setError('Failed to load templates'))
      .finally(() => setLoadingTemplates(false));
  }, []);

  // Fetch subscriber lists on mount
  useEffect(() => {
    setLoadingLists(true);
    API.get('/subscribers/lists')
      .then((res) => setLists(res.data))
      .catch(() => setError('Failed to load subscriber lists'))
      .finally(() => setLoadingLists(false));
  }, []);

  // Fetch segments on mount
  useEffect(() => {
    setLoadingSegments(true);
    API.get('/segments')
      .then((res) => {
        const segmentsData = res.data?.segments || res.data || [];
        setSegments(Array.isArray(segmentsData) ? segmentsData : []);
      })
      .catch(() => {
        console.error('Failed to load segments');
        setSegments([]);
      })
      .finally(() => setLoadingSegments(false));
  }, []);

  // When template changes, extract HTML for preview & fetch dynamic fields
  useEffect(() => {
    if (!selectedTemplate) {
      setPreviewHtml('');
      setDynamicFields([]);
      setFieldMap({});
      return;
    }

    // Extract HTML from template based on its mode
    const htmlContent = extractHtmlFromTemplate(selectedTemplate);
    setPreviewHtml(htmlContent);

    // Fetch dynamic fields
    API.get(`/templates/${selectedTemplate._id || selectedTemplate.id}/fields`)
      .then((res) => {
        setDynamicFields(res.data);
        setFieldMap({});
      })
      .catch(() => setDynamicFields([]));
  }, [selectedTemplate]);

  // Extract HTML from different template types
  const extractHtmlFromTemplate = (template) => {
    if (!template) return "";

    const contentJson = template.content_json || {};
    
    // Handle different template modes
    if (contentJson.mode === 'html' && contentJson.content) {
      return contentJson.content;
    } else if (contentJson.mode === 'drag-drop' && contentJson.blocks) {
      return contentJson.blocks.map(block => block.content || '').join('\n');
    } else if (contentJson.mode === 'visual' && contentJson.content) {
      return contentJson.content;
    } else if (template.html) {
      // Fallback to stored HTML
      return template.html;
    } else if (contentJson.body && contentJson.body.rows) {
      // Handle legacy Unlayer format
      let extractedHtml = '';
      try {
        contentJson.body.rows.forEach(row => {
          row.columns?.forEach(column => {
            column.contents?.forEach(content => {
              if (content.type === 'html' && content.values?.html) {
                extractedHtml += content.values.html + '\n';
              }
            });
          });
        });
        return extractedHtml;
      } catch (e) {
        console.error('Error extracting HTML from legacy format:', e);
        return '<p>Error rendering template preview</p>';
      }
    }
    
    return '<p>No preview available</p>';
  };

  // Available fields useEffect - updated for segments
  useEffect(() => {
    if (selectedLists.length > 0 || selectedSegments.length > 0) {
      getAllColumns()
        .then(setAvailableFields)
        .catch(console.error);
    } else {
      setAvailableFields({
        universal: [],
        standard: [],
        custom: []
      });
    }
  }, [selectedLists, selectedSegments]);

  // Validation for Step 1
  const validateStep1 = () =>
    title.trim() !== '' && subject.trim() !== '' && senderEmail.trim() !== '' && isValidEmail(senderEmail);

  // Validation for Step 2 with segments
  const validateStep2 = () => {
    if (!selectedTemplate) return false;
    // Must have either lists or segments selected
    if (selectedLists.length === 0 && selectedSegments.length === 0) return false;
    // All dynamic fields must be mapped
    for (const field of dynamicFields) {
      if (!fieldMap[field] || fieldMap[field].trim() === '') return false;
    }
    return true;
  };

  // Get total recipients including segments
  const getTotalRecipients = () => {
    const listRecipients = lists
      .filter((list) => selectedLists.includes(list._id))
      .reduce((sum, list) => sum + (list.count || 0), 0);
    const segmentRecipients = segments
      .filter((segment) => selectedSegments.includes(segment._id))
      .reduce((sum, segment) => sum + (segment.subscriber_count || 0), 0);
    return listRecipients + segmentRecipients;
  };

  // Toggle audience lists
  const handleListToggle = (listId) => {
    setSelectedLists((prev) =>
      prev.includes(listId) ? prev.filter((id) => id !== listId) : [...prev, listId]
    );
  };

  // Toggle segments
  const handleSegmentToggle = (segmentId) => {
    setSelectedSegments((prev) =>
      prev.includes(segmentId) ? prev.filter((id) => id !== segmentId) : [...prev, segmentId]
    );
  };

  const handleFieldChange = (field, value) => {
    setFieldMap((prev) => ({ ...prev, [field]: value }));
  };

  // Get columns from both lists and segments
  const getAllColumns = async () => {
    if (selectedLists.length === 0 && selectedSegments.length === 0) {
      return { universal: [], standard: [], custom: [] };
    }
    try {
      // Call backend to analyze actual subscriber data from both lists and segments
      const payload = {};
      if (selectedLists.length > 0) payload.listIds = selectedLists;
      if (selectedSegments.length > 0) payload.segmentIds = selectedSegments;
      const response = await API.post('/subscribers/analyze-fields', payload);
      return response.data;
    } catch (error) {
      console.error('Failed to analyze fields:', error);
      return {
        universal: ['email'],
        standard: [],
        custom: []
      };
    }
  };

  // Create campaign with segments
  const handleCreateCampaign = async () => {
    setSuccessMsg('');
    if (!validateStep1() || !validateStep2()) {
      alert('Please fill all required fields, select template, audience (lists/segments), and map all dynamic fields.');
      return;
    }
    setIsSaving(true);
    try {
      await API.post('/campaigns', {
        title,
        subject,
        sender_name: senderName,
        sender_email: senderEmail,
        reply_to: replyTo,
        target_lists: selectedLists,
        target_segments: selectedSegments,
        template_id: selectedTemplate._id || selectedTemplate.id,
        field_map: fieldMap,
        fallback_values: fallbackValues,
        status: 'draft',
      });
      setSuccessMsg('Campaign created successfully!');
      navigate('/campaigns');
    } catch (err) {
      alert(`Failed to create campaign: ${err.response?.data?.detail || err.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  // Send test email with template rendering
  const sendTestEmail = async () => {
    if (!testEmail.trim()) {
      alert('Please enter an email to send test.');
      return;
    }
    
    if (!selectedTemplate || !previewHtml) {
      alert('Please select a template first.');
      return;
    }

    setSendingTest(true);
    setTestSent(false);
    
    try {
      await API.post('/campaigns/send-test', {
        to: testEmail,
        subject,
        content: previewHtml,
        sender_name: senderName,
        sender_email: senderEmail,
        template_id: selectedTemplate._id || selectedTemplate.id,
      });
      setTestSent(true);
      alert(`Test email sent to ${testEmail}!`);
    } catch (err) {
      alert(`Failed to send test email: ${err.response?.data?.detail || err.message}`);
    } finally {
      setSendingTest(false);
    }
  };

  // Step 1 UI: Basic campaign info
  const renderStep1 = () => (
    <>
      <h3 className="text-xl font-semibold mb-4">📝 Campaign Content</h3>
      <div className="mb-4">
        <label className="block font-medium mb-1" htmlFor="title">
          Campaign Name <span className="text-red-600">*</span>
        </label>
        <input
          id="title"
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className={`w-full px-3 py-2 border rounded ${
            title.trim() === '' ? 'border-red-500' : 'border-gray-300'
          }`}
          placeholder="Internal campaign name"
        />
      </div>
      <div className="mb-4">
        <label className="block font-medium mb-1" htmlFor="subject">
          Email Subject <span className="text-red-600">*</span>
        </label>
        <input
          id="subject"
          type="text"
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          className={`w-full px-3 py-2 border rounded ${
            subject.trim() === '' ? 'border-red-500' : 'border-gray-300'
          }`}
          placeholder="Email subject line"
        />
      </div>
      <div className="mb-4">
        <label className="block font-medium mb-1" htmlFor="senderName">
          Sender Name
        </label>
        <input
          id="senderName"
          type="text"
          value={senderName}
          onChange={(e) => setSenderName(e.target.value)}
          className="w-full px-3 py-2 border rounded border-gray-300"
          placeholder="Your name or company"
        />
      </div>
      <div className="mb-4">
        <label className="block font-medium mb-1" htmlFor="senderEmail">
          Sender Email <span className="text-red-600">*</span>
        </label>
        <input
          id="senderEmail"
          type="email"
          required
          value={senderEmail}
          onChange={(e) => setSenderEmail(e.target.value)}
          className={`w-full px-3 py-2 border rounded ${
            senderEmail.trim() === '' ? 'border-red-500' : 'border-gray-300'
          }`}
          placeholder="sender@example.com"
        />
      </div>
      <div className="mb-6">
        <label className="block font-medium mb-1" htmlFor="replyTo">
          Reply-To Email
        </label>
        <input
          id="replyTo"
          type="email"
          value={replyTo}
          onChange={(e) => setReplyTo(e.target.value)}
          className="w-full px-3 py-2 border rounded border-gray-300"
          placeholder="replyto@example.com"
        />
      </div>
    </>
  );

  // Step 2 UI with segmentation integration
  const renderStep2 = () => {
    return (
      <>
        <h3 className="text-xl font-semibold mb-4">🎯 Select Audience & Template</h3>
        {loadingLists || loadingTemplates || loadingSegments ? (
          <p>Loading data...</p>
        ) : (
          <>
            {/* Enhanced audience summary */}
            <div className="mb-4 p-4 bg-blue-50 rounded">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <p className="font-semibold text-blue-800">Lists Selected</p>
                  <p className="text-lg">{selectedLists.length}</p>
                </div>
                <div>
                  <p className="font-semibold text-blue-800">Segments Selected</p>
                  <p className="text-lg">{selectedSegments.length}</p>
                </div>
                <div>
                  <p className="font-semibold text-blue-800">Total Recipients</p>
                  <p className="text-xl font-bold">{getTotalRecipients().toLocaleString()}</p>
                </div>
              </div>
            </div>

            {/* Audience mode selector */}
            <div className="mb-6">
              <label className="block font-medium mb-3">Target Audience Type</label>
              <div className="flex gap-4 mb-4">
                <label className="flex items-center">
                  <input
                    type="radio"
                    name="audienceMode"
                    value="lists"
                    checked={audienceMode === 'lists'}
                    onChange={(e) => setAudienceMode(e.target.value)}
                    className="mr-2"
                  />
                  📋 Lists Only
                </label>
                <label className="flex items-center">
                  <input
                    type="radio"
                    name="audienceMode"
                    value="segments"
                    checked={audienceMode === 'segments'}
                    onChange={(e) => setAudienceMode(e.target.value)}
                    className="mr-2"
                  />
                  🎯 Segments Only
                </label>
                <label className="flex items-center">
                  <input
                    type="radio"
                    name="audienceMode"
                    value="both"
                    checked={audienceMode === 'both'}
                    onChange={(e) => setAudienceMode(e.target.value)}
                    className="mr-2"
                  />
                  📋🎯 Both Lists & Segments
                </label>
              </div>
            </div>

            {/* Conditional rendering based on audience mode */}
            {(audienceMode === 'lists' || audienceMode === 'both') && (
              <div className="mb-6">
                <h4 className="font-semibold mb-3">📋 Subscriber Lists</h4>
                <div className="max-h-64 overflow-auto border rounded p-3">
                  {lists.length === 0 ? (
                    <p className="text-gray-600">No subscriber lists available</p>
                  ) : (
                    lists.map((list) => (
                      <label
                        key={list._id}
                        className="flex items-center mb-2 cursor-pointer hover:bg-gray-100 p-2 rounded"
                      >
                        <input
                          type="checkbox"
                          checked={selectedLists.includes(list._id)}
                          onChange={() => handleListToggle(list._id)}
                          className="mr-3"
                        />
                        <span className="font-medium">{list._id}</span>
                        <span className="ml-2 text-gray-500">({list.count || 0} subscribers)</span>
                      </label>
                    ))
                  )}
                </div>
              </div>
            )}

            {/* Segments selection */}
            {(audienceMode === 'segments' || audienceMode === 'both') && (
              <div className="mb-6">
                <h4 className="font-semibold mb-3 flex items-center gap-2">
                  🎯 Targeted Segments
                  <span className="text-sm font-normal text-blue-600">
                    ({segments.length} available)
                  </span>
                </h4>
                <div className="max-h-80 overflow-auto border rounded p-3">
                  {segments.length === 0 ? (
                    <div className="text-center py-6 text-gray-600">
                      <p className="mb-2">No segments available</p>
                      <button
                        onClick={() => window.open('/segmentation', '_blank')}
                        className="text-blue-600 hover:underline text-sm"
                      >
                        ➕ Create Your First Segment
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {segments.map((segment) => (
                        <label
                          key={segment._id}
                          className="flex items-start cursor-pointer hover:bg-gray-50 p-3 rounded border"
                        >
                          <input
                            type="checkbox"
                            checked={selectedSegments.includes(segment._id)}
                            onChange={() => handleSegmentToggle(segment._id)}
                            className="mr-3 mt-1"
                          />
                          <div className="flex-1">
                            <div className="flex items-center justify-between mb-1">
                              <span className="font-semibold text-blue-800">{segment.name}</span>
                              <span className="text-sm font-medium text-gray-700">
                                {segment.subscriber_count?.toLocaleString() || '0'} subscribers
                              </span>
                            </div>
                            <p className="text-sm text-gray-600 mb-2">{segment.description}</p>
                            <div className="flex flex-wrap gap-1">
                              {segment.criteria?.status?.map(status => (
                                <span key={status} className="bg-blue-100 text-blue-800 px-2 py-1 rounded text-xs">
                                  {status}
                                </span>
                              ))}
                              {segment.criteria?.lists?.map(list => (
                                <span key={list} className="bg-green-100 text-green-800 px-2 py-1 rounded text-xs">
                                  {list}
                                </span>
                              ))}
                              {segment.criteria?.dateRange && (
                                <span className="bg-purple-100 text-purple-800 px-2 py-1 rounded text-xs">
                                  Last {segment.criteria.dateRange} days
                                </span>
                              )}
                              {segment.criteria_types && segment.criteria_types.length > 0 && (
                                <span className="bg-gray-100 text-gray-700 px-2 py-1 rounded text-xs">
                                  {segment.criteria_types.length} criteria types
                                </span>
                              )}
                            </div>
                          </div>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Template Selection */}
            <div className="mb-6">
              <label className="block font-medium mb-1" htmlFor="templateSelect">
                Select Template <span className="text-red-600">*</span>
              </label>
              <select
                id="templateSelect"
                value={selectedTemplate ? selectedTemplate._id || selectedTemplate.id : ''}
                onChange={(e) =>
                  setSelectedTemplate(
                    templates.find((t) => (t._id || t.id) === e.target.value) || null
                  )
                }
                className={`w-full px-3 py-2 border rounded ${
                  selectedTemplate ? 'border-gray-300' : 'border-red-500'
                }`}
              >
                <option value="" disabled>
                  -- Select a Template --
                </option>
                {templates.map((template) => (
                  <option key={template._id || template.id} value={template._id || template.id}>
                    {template.name} ({template.content_json?.mode || 'legacy'})
                  </option>
                ))}
              </select>
              
              {/* Show selected template info */}
              {selectedTemplate && (
                <div className="mt-2 p-2 bg-gray-50 rounded text-sm">
                  <strong>Selected:</strong> {selectedTemplate.name} • 
                  <span className="ml-1 px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs">
                    {selectedTemplate.content_json?.mode || 'legacy'}
                  </span>
                  {selectedTemplate.description && (
                    <p className="text-gray-600 mt-1">{selectedTemplate.description}</p>
                  )}
                </div>
              )}
            </div>

            {/* Field mapping section */}
            {dynamicFields.length > 0 && (
              <div className="mb-4">
                <h4 className="font-semibold mb-2">Map Template Dynamic Fields</h4>
                <p className="text-sm text-gray-600 mb-3">
                  Map each template field to subscriber data fields.
                </p>
                {dynamicFields.map((field) => (
                  <div key={field} className="mb-4 p-4 border rounded bg-gray-50">
                    <label className="block mb-2 font-medium">{field} <span className="text-red-600">*</span></label>
                    <select
                      className={`w-full px-3 py-2 border rounded mb-2 ${
                        !fieldMap[field] ? 'border-red-500' : 'border-gray-300'
                      }`}
                      value={fieldMap[field] || ''}
                      onChange={(e) => handleFieldChange(field, e.target.value)}
                    >
                      <option value="" disabled>
                        Select field mapping...
                      </option>
                      {/* Universal Fields */}
                      {availableFields.universal.length > 0 && (
                        <optgroup label="🌍 Universal Fields">
                          {availableFields.universal.map(universalField => (
                            <option key={universalField} value={universalField}>
                              {universalField.charAt(0).toUpperCase() + universalField.slice(1)}
                            </option>
                          ))}
                        </optgroup>
                      )}
                      {/* Standard Fields */}
                      {availableFields.standard.length > 0 && (
                        <optgroup label="⭐ Standard Fields">
                          {availableFields.standard.map(standardField => (
                            <option key={standardField} value={`standard.${standardField}`}>
                              {standardField.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                            </option>
                          ))}
                        </optgroup>
                      )}
                      {/* Custom Fields */}
                      {availableFields.custom.length > 0 && (
                        <optgroup label="🔧 Custom Fields">
                          {availableFields.custom.map(customField => (
                            <option key={customField} value={`custom.${customField}`}>
                              {customField.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                            </option>
                          ))}
                        </optgroup>
                      )}
                      {/* Fallback Options */}
                      <optgroup label="🔄 Fallback Options">
                        <option value="__EMPTY__">Leave Empty</option>
                        <option value="__DEFAULT__">Use Default Value</option>
                      </optgroup>
                    </select>
                    {/* Show available fields info */}
                    <div className="text-xs text-gray-500 mb-2">
                      <strong>Available fields:</strong>
                      <br />
                      🌍 Universal: {availableFields.universal.join(', ') || 'None'}
                      <br />
                      ⭐ Standard: {availableFields.standard.join(', ') || 'None'}
                      <br />
                      🔧 Custom: {availableFields.custom.join(', ') || 'None'}
                    </div>
                    {/* Show selected mapping info */}
                    {fieldMap[field] && (
                      <div className="text-xs text-blue-600 mb-2">
                        Selected: <strong>{fieldMap[field]}</strong>
                      </div>
                    )}
                    {/* Fallback value input */}
                    {fieldMap[field] === '__DEFAULT__' && (
                      <div className="mt-2">
                        <input
                          type="text"
                          placeholder="Enter default value for this field"
                          className="w-full px-3 py-2 border rounded border-blue-300 bg-blue-50"
                          value={fallbackValues[field] || ''}
                          onChange={(e) => setFallbackValues(prev => ({...prev, [field]: e.target.value}))}
                        />
                        <p className="text-xs text-blue-600 mt-1">
                          This value will be used when subscriber data is missing
                        </p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Warning for multiple targeting methods */}
            {(selectedLists.length > 0 && selectedSegments.length > 0) && (
              <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded">
                <h5 className="font-medium text-amber-800 mb-2">⚠️ Hybrid Targeting Active</h5>
                <div className="text-sm text-amber-700">
                  <p>You've selected both lists ({selectedLists.length}) and segments ({selectedSegments.length}).</p>
                  <p>📋 List subscribers: Direct from subscriber lists</p>
                  <p>🎯 Segment subscribers: Filtered based on criteria</p>
                  <p>⚡ Campaign will reach: {getTotalRecipients().toLocaleString()} total recipients</p>
                </div>
              </div>
            )}
          </>
        )}
      </>
    );
  };
  // ✅desktop UPDATED: Step 3 UI with lightweight HTML preview
  const renderStep3 = () => (
    <>
      <h3 className="text-xl font-semibold mb-4">👀 Preview & Test</h3>
      
      {/* Test Email Section */}
      <div className="mb-6 p-4 bg-green-50 rounded border border-green-300">
        <label className="block font-medium mb-2">Test Email Address</label>
        <input
          type="email"
          className="w-full px-3 py-2 border rounded border-green-300 mb-3"
          value={testEmail}
          onChdesktopdesktopange={(e) => setTestEmail(e.target.value)}
          placeholder="your-email@example.com"
        />
        <button
          onClick={sendTestEmail}
          disabled={sendingTest || !testEmail.trim() || !selectedTemplate}
          className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded disabled:opacity-50"
        >
          {sendingTest ? 'Sending...' : 'Send Test Email'}
        </button>
        {testSent && <p className="mt-2 text-green-700">Test email sent successfully!</p>}
      </div>

      {/* Enhanced campaign summary with segments */}
      <div className="mb-6 p-4 bg-gray-50 rounded">
        <h4 className="font-semibold mb-3">📊 Campaign Summary</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <div>
            <p><strong>Campaign Name:</strong> {title}</p>
            <p><strong>Subject:</strong> {subject}</p>
            <p><strong>Template:</strong> {selectedTemplate?.name || 'No template selected'} 
              {selectedTemplate?.content_json?.mode && (
                <span className="ml-2 px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs">
                  {selectedTemplate.content_json.mode}
                </span>
              )}
            </p>
            <p><strong>Dynamic Fields:</strong> {dynamicFields.length > 0 ? dynamicFields.length : 'None'}</p>
          </div>
          <div>
            <p><strong>Sender:</strong> {senderName || 'Not specified'} &lt;{senderEmail || 'Not specified'}&gt;</p>
            <p><strong>Reply-To:</strong> {replyTo || 'Not specified'}</p>
            <p><strong>Total Recipients:</strong> {getTotalRecipients().toLocaleString()}</p>
            <p><strong>Targeting:</strong>
              {selectedLists.length > 0 && selectedSegments.length > 0 ? 'Lists + Segments' :
               selectedLists.length > 0 ? 'Lists Only' :
               selectedSegments.length > 0 ? 'Segments Only' : 'None'}
            </p>
          </div>
        </div>

        {/* Audience breakdown */}
        {(selectedLists.length > 0 || selectedSegments.length > 0) && (
          <div className="mt-4 pt-4 border-t">
            <h5 className="font-medium mb-2">🎯 Audience Breakdown:</h5>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {selectedLists.length > 0 && (
                <div>
                  <h6 className="text-sm font-medium text-blue-800 mb-1">📋 Selected Lists ({selectedLists.length})</h6>
                  <div className="space-y-1">
                    {selectedLists.map(listId => {
                      const list = lists.find(l => l._id === listId);
                      return (
                        <div key={listId} className="text-xs flex justify-between">
                          <span>{list?._id || listId}</span>
                          <span className="text-gray-600">{list?.count || 0}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
              {selectedSegments.length > 0 && (
                <div>
                  <h6 className="text-sm font-medium text-purple-800 mb-1">🎯 Selected Segments ({selectedSegments.length})</h6>
                  <div className="space-y-1">
                    {selectedSegments.map(segmentId => {
                      const segment = segments.find(s => s._id === segmentId);
                      return (
                        <div key={segmentId} className="text-xs">
                          <div className="flex justify-between">
                            <span className="font-medium">{segment?.name || segmentId}</span>
                            <span className="text-gray-600">{segment?.subscriber_count || 0}</span>
                          </div>
                          {segment?.description && (
                            <p className="text-gray-500 text-xs mt-1">{segment.description}</p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Field mapping summary */}
        {Object.keys(fieldMap).length > 0 && (
          <div className="mt-4 pt-4 border-t">
            <h5 className="font-medium mb-2">🔗 Field Mappings:</h5>
            <div className="space-y-1 text-xs">
              {Object.entries(fieldMap).map(([field, mapping]) => (
                <div key={field} className="flex justify-between">
                  <span className="font-medium">{field}:</span>
                  <span className={`px-2 py-1 rounded ${
                    mapping.startsWith('universal.') ? 'bg-blue-100 text-blue-800' :
                    mapping.startsWith('standard.') ? 'bg-green-100 text-green-800' :
                    mapping.startsWith('custom.') ? 'bg-purple-100 text-purple-800' :
                    'bg-gray-100 text-gray-800'
                  }`}>
                    {mapping}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ✅ SIMPLIFIED: Lightweight HTML Preview */}
      <div className="mb-6 p-4 border rounded bg-white">
        <div className="flex justify-between items-center mb-4">
          <h4 className="font-semibold flex items-center gap-2">
            📧 Email Preview 
            {selectedTemplate && (
              <span className="text-sm font-normal text-gray-600">
                ({selectedTemplate.content_json?.mode || 'legacy'} mode)
              </span>
            )}
          </h4>
          
          {/* Device Preview Buttons */}
          <div className="flex items-center gap-2">
            <button
	      type="button" 
              onClick={() => setPreviewMode('desktop')}
              className={`p-2 rounded flex items-center gap-1 ${previewMode === 'desktop' ? 'bg-blue-600 text-white' : 'hover:bg-gray-200'}`}
              title="Desktop Preview"
            >
              <Monitor size={16} />
            </button>
            <button
	      type="button"
              onClick={() => setPreviewMode('tablet')}
              className={`p-2 rounded flex items-center gap-1 ${previewMode === 'tablet' ? 'bg-blue-600 text-white' : 'hover:bg-gray-200'}`}
              title="Tablet Preview"
            >
              <Tablet size={16} />
            </button>
            <button
	      type="button"
              onClick={() => setPreviewMode('mobile')}
              className={`p-2 rounded flex items-center gap-1 ${previewMode === 'mobile' ? 'bg-blue-600 text-white' : 'hover:bg-gray-200'}`}
              title="Mobile Preview"
            >
              <Smartphone size={16} />
            </button>
          </div>
        </div>

        {/* HTML Preview Container */}
        <div className="bg-gray-100 p-4 rounded flex justify-center overflow-auto max-h-[600px]">
          {previewHtml ? (
            <div
              className={`bg-white shadow-lg transition-all duration-300 ${
                previewMode === 'desktop' ? 'w-full max-w-4xl' :
                previewMode === 'tablet' ? 'w-[768px]' : 'w-[375px]'
              }`}
              style={{
                minHeight: '400px',
                border: previewMode !== 'desktop' ? '2px solid #ccc' : 'none',
                borderRadius: previewMode !== 'desktop' ? '8px' : '0'
              }}
            >
              <div
                className="p-4"
                dangerouslySetInnerHTML={{ __html: previewHtml }}
              />
            </div>
          ) : (
            <div className="flex items-center justify-center h-64 bg-gray-100 rounded">
              <p className="text-gray-500">Select a template to preview</p>
            </div>
          )}
        </div>
      </div>
    </>
  );

  return (
    <div className="max-w-5xl mx-auto p-6 bg-white rounded shadow">
      <h2 className="text-2xl font-bold mb-6">🚀 Create Campaign with Advanced Targeting</h2>
      
      {error && <p className="mb-4 text-red-600">{error}</p>}
      {successMsg && (
        <div className="mb-4 p-3 bg-green-100 text-green-800 border border-green-300 rounded">
          {successMsg}
        </div>
      )}

      {/* Step Navigation */}
      <div className="mb-6 flex space-x-4 text-sm font-semibold">
        {[
          { num: 1, label: 'Content', icon: '📝' },
          { num: 2, label: 'Audience & Template', icon: '🎯' },
          { num: 3, label: 'Preview & Test', icon: '👀' }
        ].map(({ num, label, icon }) => (
          <button
            key={num}
            disabled={step === num}
            onClick={() => setStep(num)}
            className={`px-4 py-2 rounded flex items-center gap-2 ${
              step === num ? 'bg-blue-600 text-white' : 'bg-gray-200 hover:bg-gray-300'
            }`}
          >
            <span>{icon}</span>
            <span>Step {num}: {label}</span>
          </button>
        ))}
      </div>

      {/* Main Form */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (step < 3) {
            if (step === 1 && validateStep1()) setStep(2);
            else if (step === 2 && validateStep2()) setStep(3);
          } else {
            handleCreateCampaign();
          }
        }}
      >
        {step === 1 && renderStep1()}
        {step === 2 && renderStep2()}
        {step === 3 && renderStep3()}

        {/* Navigation Buttons */}
        <div className="flex justify-between mt-6">
          {step > 1 && (
            <button
              type="button"
              onClick={() => setStep(step - 1)}
              className="px-6 py-2 bg-gray-300 hover:bg-gray-400 rounded flex items-center gap-2"
            >
              ← Previous
            </button>
          )}
          <button
            type="submit"
            className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded disabled:opacity-50 flex items-center gap-2"
            disabled={
              (step === 1 && !validateStep1()) ||
              (step === 2 && !validateStep2()) ||
              isSaving
            }
          >
            {step < 3 ? (
              <>Next → <span className="text-sm">({step === 1 ? 'Audience' : 'Preview'})</span></>
            ) : (
              <>{isSaving ? '⏳ Creating...' : '🚀 Create Campaign'}</>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}

