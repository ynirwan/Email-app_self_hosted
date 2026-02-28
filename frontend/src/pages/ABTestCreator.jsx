import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import API from '../api';

const ABTestCreator = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [lists, setLists] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [listsLoading, setListsLoading] = useState(true);

  const [testConfig, setTestConfig] = useState({
    test_name: '',
    target_lists: [],
    template_id: '',
    subject: '',
    sender_name: '',
    sender_email: '',
    reply_to: '',
    test_type: 'subject_line',
    variants: [
      {
        name: 'Variant A (Control)',
        subject: '',
        sender_name: '',
        sender_email: '',
        reply_to: ''
      },
      {
        name: 'Variant B (Test)',
        subject: '',
        sender_name: '',
        sender_email: '',
        reply_to: ''
      }
    ],
    split_percentage: 50,
    sample_size: 1000,
    winner_criteria: 'open_rate'
  });

  useEffect(() => {
    fetchListsAndTemplates();
  }, []);

  const fetchListsAndTemplates = async () => {
    setListsLoading(true);
    try {
      const [listsRes, templatesRes] = await Promise.all([
        API.get('/ab-tests/lists'),
        API.get('/ab-tests/templates')
      ]);
      setLists(listsRes.data.lists || []);
      setTemplates(templatesRes.data.templates || []);
    } catch (err) {
      console.error('Failed to load lists/templates:', err);
      setError('Failed to load lists and templates');
    } finally {
      setListsLoading(false);
    }
  };

  const totalSelectedSubscribers = lists
    .filter(l => testConfig.target_lists.includes(l.name))
    .reduce((sum, l) => sum + l.count, 0);

  const handleListToggle = (listName) => {
    setTestConfig(prev => {
      const current = prev.target_lists;
      const updated = current.includes(listName)
        ? current.filter(n => n !== listName)
        : [...current, listName];
      return { ...prev, target_lists: updated };
    });
  };

  const handleTemplateSelect = (templateId) => {
    setTestConfig(prev => ({ ...prev, template_id: templateId }));
    const selected = templates.find(t => t._id === templateId);
    if (selected && selected.subject && !testConfig.subject) {
      setTestConfig(prev => ({
        ...prev,
        subject: selected.subject,
        variants: [
          { ...prev.variants[0], subject: selected.subject },
          { ...prev.variants[1] }
        ]
      }));
    }
  };

  const handleTestTypeChange = (newType) => {
    setTestConfig(prev => {
      const updatedVariants = [...prev.variants];
      if (newType === 'subject_line') {
        updatedVariants[0] = { ...updatedVariants[0], subject: prev.subject };
        updatedVariants[1] = { ...updatedVariants[1], subject: '' };
      } else if (newType === 'sender_name') {
        updatedVariants[0] = { ...updatedVariants[0], sender_name: prev.sender_name };
        updatedVariants[1] = { ...updatedVariants[1], sender_name: '' };
      } else if (newType === 'sender_email') {
        updatedVariants[0] = { ...updatedVariants[0], sender_email: prev.sender_email };
        updatedVariants[1] = { ...updatedVariants[1], sender_email: '' };
      } else if (newType === 'reply_to') {
        updatedVariants[0] = { ...updatedVariants[0], reply_to: prev.reply_to || prev.sender_email };
        updatedVariants[1] = { ...updatedVariants[1], reply_to: '' };
      }
      return { ...prev, test_type: newType, variants: updatedVariants };
    });
  };

  const handleVariantChange = (variantIndex, field, value) => {
    setTestConfig(prev => {
      const newVariants = [...prev.variants];
      newVariants[variantIndex] = { ...newVariants[variantIndex], [field]: value };
      return { ...prev, variants: newVariants };
    });
  };

  const validateTest = () => {
    if (!testConfig.test_name.trim()) return 'Test name is required';
    if (testConfig.target_lists.length === 0) return 'Select at least one subscriber list';
    if (!testConfig.template_id) return 'Select a template';
    if (!testConfig.subject.trim()) return 'Subject line is required';
    if (!testConfig.sender_name.trim()) return 'Sender name is required';
    if (!testConfig.sender_email.trim()) return 'Sender email is required';

    if (testConfig.test_type === 'subject_line' && !testConfig.variants[1].subject.trim())
      return 'Variant B subject line is required';
    if (testConfig.test_type === 'sender_name' && !testConfig.variants[1].sender_name.trim())
      return 'Variant B sender name is required';
    if (testConfig.test_type === 'sender_email' && !testConfig.variants[1].sender_email.trim())
      return 'Variant B sender email is required';
    if (testConfig.test_type === 'reply_to' && !testConfig.variants[1].reply_to.trim())
      return 'Variant B reply-to address is required';

    if (testConfig.sample_size < 100) return 'Sample size must be at least 100';
    return null;
  };

  const handleCreateTest = async () => {
    setError('');
    const validationError = validateTest();
    if (validationError) {
      setError(validationError);
      return;
    }

    setLoading(true);
    try {
      await API.post('/ab-tests', testConfig);
      navigate('/ab-testing');
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create A/B test');
    } finally {
      setLoading(false);
    }
  };

  const renderVariantField = (variantIndex, isControl = false) => {
    const variant = testConfig.variants[variantIndex];
    const variantLabel = isControl ? 'Variant A (Control)' : 'Variant B (Test)';
    const fieldMap = {
      subject_line: { field: 'subject', label: 'Subject Line', type: 'text' },
      sender_name: { field: 'sender_name', label: 'Sender Name', type: 'text' },
      sender_email: { field: 'sender_email', label: 'Sender Email', type: 'email' },
      reply_to: { field: 'reply_to', label: 'Reply-To Address', type: 'email' }
    };
    const config = fieldMap[testConfig.test_type];

    return (
      <div className={`border rounded-lg p-4 ${isControl ? 'bg-blue-50 border-blue-200' : 'bg-orange-50 border-orange-200'}`}>
        <h4 className="text-lg font-semibold mb-3 text-gray-800">{variantLabel}</h4>
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-700">{config.label}</label>
          <input
            type={config.type}
            value={variant[config.field] || ''}
            onChange={(e) => handleVariantChange(variantIndex, config.field, e.target.value)}
            placeholder={isControl ? `Current ${config.label.toLowerCase()}` : `Enter test ${config.label.toLowerCase()}`}
            readOnly={isControl}
            className={`w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              isControl ? 'bg-gray-100 text-gray-600 cursor-not-allowed' : 'bg-white text-gray-900'
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
          onClick={() => navigate('/ab-testing')}
          className="text-gray-600 hover:text-gray-800 px-4 py-2 border rounded-lg"
        >
          Cancel
        </button>
      </div>

      <div className="space-y-8">
        {/* Test Name */}
        <div className="bg-white border rounded-lg p-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">Test Name *</label>
          <input
            type="text"
            placeholder="e.g., Subject Line Test - January Promo"
            value={testConfig.test_name}
            onChange={(e) => setTestConfig({ ...testConfig, test_name: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Target Lists */}
        <div className="bg-white border rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">Target Lists *</h3>
          <p className="text-sm text-gray-500 mb-4">Select subscriber lists for this A/B test</p>
          {lists.length === 0 ? (
            <p className="text-gray-500 text-sm">No subscriber lists found. Upload subscribers first.</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {lists.map(list => (
                <label
                  key={list.name}
                  className={`flex items-center justify-between p-3 border rounded-lg cursor-pointer transition-colors ${
                    testConfig.target_lists.includes(list.name)
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      checked={testConfig.target_lists.includes(list.name)}
                      onChange={() => handleListToggle(list.name)}
                      className="h-4 w-4 text-blue-600 rounded"
                    />
                    <span className="font-medium text-gray-900">{list.name}</span>
                  </div>
                  <span className="text-sm text-gray-500">{list.count.toLocaleString()} subscribers</span>
                </label>
              ))}
            </div>
          )}
          {testConfig.target_lists.length > 0 && (
            <div className="mt-4 p-3 bg-blue-50 rounded-lg text-sm text-blue-700">
              Total selected: {totalSelectedSubscribers.toLocaleString()} active subscribers across {testConfig.target_lists.length} list(s)
            </div>
          )}
        </div>

        {/* Template Selection */}
        <div className="bg-white border rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">Email Template *</h3>
          {templates.length === 0 ? (
            <p className="text-gray-500 text-sm">No templates found. Create a template first.</p>
          ) : (
            <select
              value={testConfig.template_id}
              onChange={(e) => handleTemplateSelect(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Select a template...</option>
              {templates.map(t => (
                <option key={t._id} value={t._id}>
                  {t.name} {t.subject ? `- "${t.subject}"` : ''}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Sender Info */}
        <div className="bg-white border rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">Sender Details *</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Subject Line *</label>
              <input
                type="text"
                value={testConfig.subject}
                onChange={(e) => {
                  setTestConfig(prev => ({
                    ...prev,
                    subject: e.target.value,
                    variants: [
                      { ...prev.variants[0], subject: e.target.value },
                      prev.variants[1]
                    ]
                  }));
                }}
                placeholder="Email subject line"
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Sender Name *</label>
              <input
                type="text"
                value={testConfig.sender_name}
                onChange={(e) => {
                  setTestConfig(prev => ({
                    ...prev,
                    sender_name: e.target.value,
                    variants: [
                      { ...prev.variants[0], sender_name: e.target.value },
                      prev.variants[1]
                    ]
                  }));
                }}
                placeholder="e.g., Marketing Team"
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Sender Email *</label>
              <input
                type="email"
                value={testConfig.sender_email}
                onChange={(e) => {
                  setTestConfig(prev => ({
                    ...prev,
                    sender_email: e.target.value,
                    variants: [
                      { ...prev.variants[0], sender_email: e.target.value },
                      prev.variants[1]
                    ]
                  }));
                }}
                placeholder="sender@yourdomain.com"
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Reply-To Email</label>
              <input
                type="email"
                value={testConfig.reply_to}
                onChange={(e) => setTestConfig({ ...testConfig, reply_to: e.target.value })}
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
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Test Type</label>
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
                  Split: {testConfig.split_percentage}% / {100 - testConfig.split_percentage}%
                </label>
                <input
                  type="range"
                  min="10"
                  max="90"
                  value={testConfig.split_percentage}
                  onChange={(e) => setTestConfig({ ...testConfig, split_percentage: parseInt(e.target.value) })}
                  className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Sample Size</label>
                <input
                  type="number"
                  value={testConfig.sample_size}
                  onChange={(e) => setTestConfig({ ...testConfig, sample_size: parseInt(e.target.value) || 100 })}
                  min="100"
                  max={totalSelectedSubscribers || 100000}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Winner Criteria</label>
                <select
                  value={testConfig.winner_criteria}
                  onChange={(e) => setTestConfig({ ...testConfig, winner_criteria: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="open_rate">Open Rate</option>
                  <option value="click_rate">Click Rate</option>
                </select>
              </div>
            </div>
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-sm text-red-800">{error}</p>
          </div>
        )}

        <div className="flex justify-end space-x-3 pb-6">
          <button
            onClick={() => navigate('/ab-testing')}
            className="px-6 py-2 text-sm font-medium text-gray-700 bg-gray-100 border border-gray-300 rounded-lg hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            onClick={handleCreateTest}
            disabled={loading}
            className="px-6 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? 'Creating...' : 'Create A/B Test'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ABTestCreator;
