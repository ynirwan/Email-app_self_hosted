// src/pages/AutomationBuilder.jsx - Enhanced Version
import React, { useState, useEffect } from 'react';
import {
  Save, Plus, Trash2, ArrowDown, Users, Target, Mail,
  Clock, Settings, AlertCircle, CheckCircle, Zap, Eye
} from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import API from '../api';

const AutomationBuilder = () => {
  const navigate = useNavigate();
  const { id } = useParams();
  const isEditing = Boolean(id);

  const [workflow, setWorkflow] = useState({
    name: '',
    trigger: 'welcome',
    trigger_conditions: {},
    target_segments: [],
    steps: [],
    active: false
  });

  const [templates, setTemplates] = useState([]);
  const [segments, setSegments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [validationErrors, setValidationErrors] = useState([]);

  useEffect(() => {
    fetchTemplatesAndSegments();
    if (isEditing) {
      fetchAutomation();
    }
  }, [id, isEditing]);

  const fetchTemplatesAndSegments = async () => {
    try {
      setLoading(true);
      setError(null);

      console.log('🔄 Fetching templates and segments...');

      const [templatesRes, segmentsRes] = await Promise.all([
        API.get('/automation/templates'),
        API.get('/automation/segments')
      ]);

      console.log('📦 Templates Response:', templatesRes);
      console.log('📦 Segments Response:', segmentsRes);

      // Extract data with multiple fallbacks
      let templatesData = [];
      if (templatesRes?.data?.templates) {
        templatesData = templatesRes.data.templates;
      } else if (Array.isArray(templatesRes?.data)) {
        templatesData = templatesRes.data;
      } else if (Array.isArray(templatesRes)) {
        templatesData = templatesRes;
      }

      let segmentsData = [];
      if (segmentsRes?.data?.segments) {
        segmentsData = segmentsRes.data.segments;
      } else if (Array.isArray(segmentsRes?.data)) {
        segmentsData = segmentsRes.data;
      } else if (Array.isArray(segmentsRes)) {
        segmentsData = segmentsRes;
      }

      setTemplates(Array.isArray(templatesData) ? templatesData : []);
      setSegments(Array.isArray(segmentsData) ? segmentsData : []);

      console.log(`✅ Loaded ${templatesData.length} templates`);
      console.log(`✅ Loaded ${segmentsData.length} segments`);

      if (templatesData.length > 0) {
        console.log('📧 Sample template:', templatesData[0]);
      }

    } catch (error) {
      console.error('❌ Failed to fetch templates/segments:', error);
      console.error('Error details:', error.response?.data);
      setError(`Failed to load data: ${error.message}`);
      setTemplates([]);
      setSegments([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchAutomation = async () => {
    try {
      setLoading(true);
      console.log('🔄 Fetching automation with ID:', id);

      const res = await API.get(`/automation/rules/${id}`);
      const actualData = res?.data || res;

      // Ensure steps have unique IDs for React keys
      if (actualData.steps && Array.isArray(actualData.steps)) {
        actualData.steps = actualData.steps.map(step => ({
          ...step,
          id: step.id || `step_${Date.now()}_${Math.random()}`
        }));
      }

      setWorkflow(actualData);
      console.log('✅ Automation loaded successfully');

    } catch (error) {
      console.error('❌ Failed to fetch automation rule:', error);
      setError('Failed to load automation rule');
    } finally {
      setLoading(false);
    }
  };

  // Validation
  const validateWorkflow = () => {
    const errors = [];

    if (!workflow.name || workflow.name.trim() === '') {
      errors.push('Automation name is required');
    }

    if (!workflow.trigger) {
      errors.push('Trigger event is required');
    }

    if (workflow.steps.length === 0) {
      errors.push('At least one email step is required');
    }

    workflow.steps.forEach((step, index) => {
      if (!step.template_id || step.template_id === '') {
        errors.push(`Email ${index + 1}: Template is required`);
      }
      if (step.delay_value < 0) {
        errors.push(`Email ${index + 1}: Delay cannot be negative`);
      }
    });

    setValidationErrors(errors);
    return errors.length === 0;
  };

  const addEmailStep = () => {
    const newStep = {
      id: `step_${Date.now()}_${Math.random()}`,
      template_id: '',
      delay_value: safeSteps.length === 0 ? 0 : 1,
      delay_type: safeSteps.length === 0 ? 'hours' : 'days'
    };
    setWorkflow(prev => ({
      ...prev,
      steps: [...safeSteps, newStep]
    }));
  };

  const removeEmailStep = (stepId) => {
    if (workflow.steps.length === 1) {
      if (!window.confirm('This will remove the last email step. Are you sure?')) {
        return;
      }
    }
    setWorkflow(prev => ({
      ...prev,
      steps: safeSteps.filter(step => step.id !== stepId)
    }));
  };

  const updateEmailStep = (stepId, field, value) => {
    setWorkflow(prev => ({
      ...prev,
      steps: safeSteps.map(step =>
        step.id === stepId ? { ...step, [field]: value } : step
      )
    }));
  };

  const toggleTargetSegment = (segmentId) => {
    setWorkflow(prev => ({
      ...prev,
      target_segments: safeTargetSegments.includes(segmentId)
        ? safeTargetSegments.filter(id => id !== segmentId)
        : [...safeTargetSegments, segmentId]
    }));
  };

  const saveWorkflow = async () => {
    // Validate
    if (!validateWorkflow()) {
      setError('Please fix the validation errors before saving');
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }

    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      console.log('💾 Saving workflow:', workflow);

      const payload = {
        ...workflow,
        steps: workflow.steps.map(step => ({
          template_id: step.template_id,
          delay_value: parseInt(step.delay_value) || 0,
          delay_type: step.delay_type
        }))
      };

      if (isEditing) {
        await API.put(`/automation/rules/${id}`, payload);
        setSuccess('Automation updated successfully!');
      } else {
        await API.post('/automation/rules', payload);
        setSuccess('Automation created successfully!');
      }

      console.log('✅ Automation saved successfully');

      // Navigate back after short delay
      setTimeout(() => {
        navigate('/automation');
      }, 1500);

    } catch (error) {
      console.error('❌ Failed to save automation:', error);
      setError(error.response?.data?.detail || `Failed to save automation: ${error.message}`);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } finally {
      setSaving(false);
    }
  };

  const [workflow, setWorkflow] = useState({
    name: '',
    trigger: 'welcome',
    trigger_conditions: {},
    target_segments: [],
    target_lists: [],
    steps: [],
    active: false,

    // ⭐ NEW FIELDS
    timezone: 'UTC',
    use_subscriber_timezone: false,
    allow_retrigger: false,
    retrigger_delay_hours: 24,
    cancel_previous_on_retrigger: true,
    exit_on_goal_achieved: true,
    exit_on_unsubscribe: true,
    max_emails_per_day: 3,
    respect_quiet_hours: true,
    quiet_hours_start: 22,
    quiet_hours_end: 8,
    skip_step_on_failure: false,
    notify_on_failure: true,
  });

  // Common timezones
  const commonTimezones = [
    { value: 'UTC', label: 'UTC (Coordinated Universal Time)' },
    { value: 'America/New_York', label: 'Eastern Time (US & Canada)' },
    { value: 'America/Chicago', label: 'Central Time (US & Canada)' },
    { value: 'America/Denver', label: 'Mountain Time (US & Canada)' },
    { value: 'America/Los_Angeles', label: 'Pacific Time (US & Canada)' },
    { value: 'Europe/London', label: 'London (GMT/BST)' },
    { value: 'Europe/Paris', label: 'Paris (CET/CEST)' },
    { value: 'Asia/Kolkata', label: 'India (IST)' },
    { value: 'Asia/Dubai', label: 'Dubai (GST)' },
    { value: 'Asia/Singapore', label: 'Singapore (SGT)' },
    { value: 'Asia/Tokyo', label: 'Tokyo (JST)' },
    { value: 'Australia/Sydney', label: 'Sydney (AEDT/AEST)' },
  ];

  // Safe array variables
  const safeSteps = Array.isArray(workflow.steps) ? workflow.steps : [];
  const safeTargetSegments = Array.isArray(workflow.target_segments) ? workflow.target_segments : [];
  const safeTemplates = Array.isArray(templates) ? templates : [];
  const safeSegments = Array.isArray(segments) ? segments : [];

  // Get template name for display
  const getTemplateName = (templateId) => {
    const template = safeTemplates.find(t => t.id === templateId);
    return template ? `${template.name} - ${template.subject}` : 'Select template...';
  };

  // Calculate estimated timeline
  const calculateTimeline = () => {
    let totalHours = 0;
    safeSteps.forEach(step => {
      const hours = step.delay_type === 'hours' ? step.delay_value :
        step.delay_type === 'days' ? step.delay_value * 24 :
          step.delay_value * 24 * 7;
      totalHours += hours;
    });

    if (totalHours < 24) return `${totalHours} hours`;
    if (totalHours < 168) return `${Math.floor(totalHours / 24)} days`;
    return `${Math.floor(totalHours / 168)} weeks`;
  };

  if (loading) {
    return (
      <div className="flex flex-col justify-center items-center p-8 min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mb-4"></div>
        <span className="text-gray-600">Loading automation builder...</span>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Success Message */}
      {success && (
        <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg mb-6 flex items-start animate-fade-in">
          <CheckCircle className="mr-3 flex-shrink-0 mt-0.5" size={20} />
          <div className="flex-1">
            <p className="font-medium">{success}</p>
            <p className="text-sm mt-1">Redirecting to dashboard...</p>
          </div>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6 flex items-start">
          <AlertCircle className="mr-3 flex-shrink-0 mt-0.5" size={20} />
          <div className="flex-1">
            <p className="font-medium">Error</p>
            <p className="text-sm mt-1">{error}</p>
          </div>
          <button
            onClick={() => setError(null)}
            className="text-red-600 hover:text-red-800 ml-4"
          >
            ✕
          </button>
        </div>
      )}

      {/* Validation Errors */}
      {validationErrors.length > 0 && (
        <div className="bg-yellow-50 border border-yellow-200 text-yellow-800 px-4 py-3 rounded-lg mb-6">
          <p className="font-medium mb-2">⚠️ Please fix the following issues:</p>
          <ul className="list-disc list-inside space-y-1 text-sm">
            {validationErrors.map((error, index) => (
              <li key={index}>{error}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-8 gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">
            {isEditing ? 'Edit' : 'Create'} Email Automation
          </h1>
          <p className="text-gray-600 mt-1">
            Build a multi-step email workflow to engage your subscribers
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => navigate('/automation')}
            disabled={saving}
            className="bg-gray-200 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-300 transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={saveWorkflow}
            disabled={saving || loading}
            className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            <Save size={20} />
            {saving ? 'Saving...' : (isEditing ? 'Update' : 'Save')} Automation
          </button>
        </div>
      </div>

      {/* Timeline Summary */}
      {safeSteps.length > 0 && (
        <div className="bg-gradient-to-r from-blue-50 to-purple-50 border border-blue-200 rounded-lg p-4 mb-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Clock className="text-blue-600" size={24} />
              <div>
                <p className="font-medium text-gray-900">Total Timeline</p>
                <p className="text-sm text-gray-600">{calculateTimeline()} from trigger to completion</p>
              </div>
            </div>
            <div className="text-right">
              <p className="text-2xl font-bold text-blue-600">{safeSteps.length}</p>
              <p className="text-sm text-gray-600">Email steps</p>
            </div>
          </div>
        </div>
      )}

      {/* Basic Settings */}
      <div className="bg-white rounded-lg shadow-sm border p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <Settings className="text-blue-600" size={22} />
          Basic Settings
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
          <div>
            <label className="block text-sm font-medium mb-2">
              Automation Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={workflow.name}
              onChange={(e) => setWorkflow(prev => ({ ...prev, name: e.target.value }))}
              className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="e.g., Welcome Series"
            />
            <p className="text-xs text-gray-500 mt-1">Give your automation a descriptive name</p>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">
              Trigger Event <span className="text-red-500">*</span>
            </label>
            <select
              value={workflow.trigger}
              onChange={(e) => setWorkflow(prev => ({ ...prev, trigger: e.target.value }))}
              className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="welcome">🎉 New Subscriber (Welcome)</option>
              <option value="birthday">🎂 Birthday</option>
              <option value="abandoned_cart">🛒 Abandoned Cart</option>
              <option value="purchase">✅ After Purchase</option>
              <option value="inactive_30_days">💤 Inactive 30 Days</option>
            </select>
            <p className="text-xs text-gray-500 mt-1">When should this automation start?</p>
          </div>
        </div>
        
        <div className="bg-white rounded-lg shadow-sm border p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <Clock className="text-blue-600" size={22} />
            Scheduling & Timing
          </h2>

          {/* Timezone Selection */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-4">
            <div>
              <label className="block text-sm font-medium mb-2">
                Automation Timezone
              </label>
              <select
                value={workflow.timezone}
                onChange={(e) => setWorkflow(prev => ({ ...prev, timezone: e.target.value }))}
                className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                {commonTimezones.map(tz => (
                  <option key={tz.value} value={tz.value}>{tz.label}</option>
                ))}
              </select>
              <p className="text-xs text-gray-500 mt-1">
                All emails will be scheduled in this timezone
              </p>
            </div>

            <div>
              <label className="flex items-center space-x-3 cursor-pointer mt-8">
                <input
                  type="checkbox"
                  checked={workflow.use_subscriber_timezone}
                  onChange={(e) => setWorkflow(prev => ({ ...prev, use_subscriber_timezone: e.target.checked }))}
                  className="w-5 h-5 rounded text-blue-600"
                />
                <div>
                  <div className="font-medium text-gray-900">Use Subscriber's Timezone</div>
                  <div className="text-sm text-gray-600">
                    If subscriber has timezone, use it instead
                  </div>
                </div>
              </label>
            </div>
          </div>

          {/* Quiet Hours */}
          <div className="border-t pt-4">
            <label className="flex items-center space-x-3 cursor-pointer mb-4">
              <input
                type="checkbox"
                checked={workflow.respect_quiet_hours}
                onChange={(e) => setWorkflow(prev => ({ ...prev, respect_quiet_hours: e.target.checked }))}
                className="w-5 h-5 rounded text-blue-600"
              />
              <div>
                <div className="font-medium text-gray-900">Respect Quiet Hours</div>
                <div className="text-sm text-gray-600">
                  Don't send emails during specified hours
                </div>
              </div>
            </label>

            {workflow.respect_quiet_hours && (
              <div className="grid grid-cols-2 gap-4 ml-8">
                <div>
                  <label className="block text-sm font-medium mb-2">Start (Evening)</label>
                  <input
                    type="number"
                    min="0"
                    max="23"
                    value={workflow.quiet_hours_start}
                    onChange={(e) => setWorkflow(prev => ({ ...prev, quiet_hours_start: parseInt(e.target.value) }))}
                    className="w-full p-2 border rounded"
                  />
                  <p className="text-xs text-gray-500">Hour (0-23)</p>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">End (Morning)</label>
                  <input
                    type="number"
                    min="0"
                    max="23"
                    value={workflow.quiet_hours_end}
                    onChange={(e) => setWorkflow(prev => ({ ...prev, quiet_hours_end: parseInt(e.target.value) }))}
                    className="w-full p-2 border rounded"
                  />
                  <p className="text-xs text-gray-500">Hour (0-23)</p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Advanced Settings */}
        <div className="bg-white rounded-lg shadow-sm border p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <Settings className="text-purple-600" size={22} />
            Advanced Settings
          </h2>

          {/* Re-trigger Settings */}
          <div className="mb-4">
            <label className="flex items-center space-x-3 cursor-pointer mb-2">
              <input
                type="checkbox"
                checked={workflow.allow_retrigger}
                onChange={(e) => setWorkflow(prev => ({ ...prev, allow_retrigger: e.target.checked }))}
                className="w-5 h-5 rounded text-blue-600"
              />
              <div>
                <div className="font-medium text-gray-900">Allow Re-triggering</div>
                <div className="text-sm text-gray-600">
                  Allow this automation to run multiple times for the same subscriber
                </div>
              </div>
            </label>

            {workflow.allow_retrigger && (
              <div className="ml-8 grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Minimum Hours Between Triggers</label>
                  <input
                    type="number"
                    min="1"
                    value={workflow.retrigger_delay_hours}
                    onChange={(e) => setWorkflow(prev => ({ ...prev, retrigger_delay_hours: parseInt(e.target.value) }))}
                    className="w-full p-2 border rounded"
                  />
                </div>
                <div>
                  <label className="flex items-center space-x-2 mt-7">
                    <input
                      type="checkbox"
                      checked={workflow.cancel_previous_on_retrigger}
                      onChange={(e) => setWorkflow(prev => ({ ...prev, cancel_previous_on_retrigger: e.target.checked }))}
                      className="rounded text-blue-600"
                    />
                    <span className="text-sm">Cancel previous workflow</span>
                  </label>
                </div>
              </div>
            )}
          </div>

          {/* Frequency Cap */}
          <div className="border-t pt-4 mb-4">
            <label className="block text-sm font-medium mb-2">Maximum Emails Per Day</label>
            <input
              type="number"
              min="0"
              max="10"
              value={workflow.max_emails_per_day}
              onChange={(e) => setWorkflow(prev => ({ ...prev, max_emails_per_day: parseInt(e.target.value) }))}
              className="w-full p-2 border rounded"
            />
            <p className="text-xs text-gray-500 mt-1">
              Set to 0 for unlimited (0 = no cap)
            </p>
          </div>

          {/* Exit Conditions */}
          <div className="border-t pt-4 space-y-2">
            <label className="flex items-center space-x-3 cursor-pointer">
              <input
                type="checkbox"
                checked={workflow.exit_on_unsubscribe}
                onChange={(e) => setWorkflow(prev => ({ ...prev, exit_on_unsubscribe: e.target.checked }))}
                className="w-5 h-5 rounded text-blue-600"
              />
              <div>
                <div className="font-medium text-gray-900">Cancel on Unsubscribe</div>
                <div className="text-sm text-gray-600">
                  Stop workflow if subscriber unsubscribes
                </div>
              </div>
            </label>

            <label className="flex items-center space-x-3 cursor-pointer">
              <input
                type="checkbox"
                checked={workflow.exit_on_goal_achieved}
                onChange={(e) => setWorkflow(prev => ({ ...prev, exit_on_goal_achieved: e.target.checked }))}
                className="w-5 h-5 rounded text-blue-600"
              />
              <div>
                <div className="font-medium text-gray-900">Cancel on Goal Achievement</div>
                <div className="text-sm text-gray-600">
                  Stop workflow when goal is reached (e.g., purchase made)
                </div>
              </div>
            </label>
          </div>

          {/* Failure Handling */}
          <div className="border-t pt-4 mt-4 space-y-2">
            <label className="flex items-center space-x-3 cursor-pointer">
              <input
                type="checkbox"
                checked={workflow.skip_step_on_failure}
                onChange={(e) => setWorkflow(prev => ({ ...prev, skip_step_on_failure: e.target.checked }))}
                className="w-5 h-5 rounded text-blue-600"
              />
              <div>
                <div className="font-medium text-gray-900">Skip Failed Steps</div>
                <div className="text-sm text-gray-600">
                  Continue to next step if email fails to send
                </div>
              </div>
            </label>

            <label className="flex items-center space-x-3 cursor-pointer">
              <input
                type="checkbox"
                checked={workflow.notify_on_failure}
                onChange={(e) => setWorkflow(prev => ({ ...prev, notify_on_failure: e.target.checked }))}
                className="w-5 h-5 rounded text-blue-600"
              />
              <div>
                <div className="font-medium text-gray-900">Notify on Failure</div>
                <div className="text-sm text-gray-600">
                  Send notification to admin when automation fails
                </div>
              </div>
            </label>
          </div>
        </div>

        
        {/* Status Toggle */}
        <div className="border-t pt-6">
          <label className="flex items-center space-x-3 cursor-pointer">
            <input
              type="checkbox"
              checked={workflow.active}
              onChange={(e) => setWorkflow(prev => ({ ...prev, active: e.target.checked }))}
              className="w-5 h-5 rounded text-blue-600 focus:ring-blue-500"
            />
            <div>
              <div className="font-medium text-gray-900">Activate Immediately</div>
              <div className="text-sm text-gray-600">
                {workflow.active
                  ? '✅ This automation will start running for matching subscribers'
                  : '⚠️ Save as draft - automation will not run until activated'}
              </div>
            </div>
          </label>
        </div>
      </div>

      {/* Target Segments */}
      <div className="bg-white rounded-lg shadow-sm border p-6 mb-6">
        <h2 className="text-xl font-semibold mb-3 flex items-center gap-2">
          <Target className="text-purple-600" size={22} />
          Target Audience
        </h2>
        <p className="text-sm text-gray-600 mb-4">
          Select specific segments to target, or leave empty to send to all active subscribers
        </p>

        {safeSegments.length === 0 ? (
          <div className="p-8 border-2 border-dashed border-gray-300 rounded-lg text-center">
            <Users className="mx-auto text-gray-300 mb-3" size={48} />
            <p className="text-gray-600 mb-2">No segments available</p>
            <p className="text-sm text-gray-500 mb-4">Create segments to target specific audiences</p>
            <button
              onClick={() => window.open('/segments/create', '_blank')}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 text-sm"
            >
              Create Segment
            </button>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
              {safeSegments.map((segment) => (
                <label
                  key={segment.id}
                  className={`flex items-start space-x-3 p-4 border-2 rounded-lg cursor-pointer transition-all ${safeTargetSegments.includes(segment.id)
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-200 hover:border-blue-300 hover:bg-gray-50'
                    }`}
                >
                  <input
                    type="checkbox"
                    checked={safeTargetSegments.includes(segment.id)}
                    onChange={() => toggleTargetSegment(segment.id)}
                    className="mt-1 rounded text-blue-600 focus:ring-blue-500"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-gray-900">{segment.name}</div>
                    <div className="text-sm text-gray-600 flex items-center gap-1 mt-1">
                      <Users size={14} />
                      {(segment.subscriber_count || 0).toLocaleString()} subscribers
                    </div>
                    {segment.description && (
                      <div className="text-xs text-gray-500 mt-1">{segment.description}</div>
                    )}
                  </div>
                </label>
              ))}
            </div>

            {safeTargetSegments.length > 0 && (
              <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <p className="text-sm text-blue-900">
                  <strong>🎯 Targeting:</strong> This automation will only send to subscribers in {safeTargetSegments.length} selected segment{safeTargetSegments.length > 1 ? 's' : ''}.
                </p>
              </div>
            )}

            {safeTargetSegments.length === 0 && (
              <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
                <p className="text-sm text-gray-700">
                  <strong>📢 All Subscribers:</strong> No segments selected - this automation will target all active subscribers.
                </p>
              </div>
            )}
          </>
        )}
      </div>

      {/* Email Sequence */}
      <div className="bg-white rounded-lg shadow-sm border p-6">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <Mail className="text-green-600" size={22} />
              Email Sequence
              {safeSteps.length > 0 && (
                <span className="text-sm font-normal text-gray-500">
                  ({safeSteps.length} step{safeSteps.length > 1 ? 's' : ''})
                </span>
              )}
            </h2>
            <p className="text-sm text-gray-600 mt-1">
              Build your multi-step email workflow
            </p>
          </div>
          <button
            onClick={addEmailStep}
            disabled={safeTemplates.length === 0}
            className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            <Plus size={18} />
            Add Email
          </button>
        </div>

        {safeTemplates.length === 0 && (
          <div className="p-8 border-2 border-dashed border-orange-300 rounded-lg text-center bg-orange-50 mb-6">
            <AlertCircle className="mx-auto text-orange-500 mb-3" size={48} />
            <p className="text-orange-800 font-medium mb-2">No email templates available</p>
            <p className="text-sm text-orange-700 mb-4">You need to create email templates before building automations</p>
            <button
              onClick={() => window.open('/templates/create', '_blank')}
              className="bg-orange-600 text-white px-4 py-2 rounded-lg hover:bg-orange-700 text-sm"
            >
              Create Template
            </button>
          </div>
        )}

        {safeSteps.length === 0 ? (
          <div className="text-center py-16 border-2 border-dashed border-gray-300 rounded-lg bg-gray-50">
            <div className="text-6xl mb-4">📧</div>
            <p className="text-lg font-medium text-gray-900 mb-2">No emails in sequence yet</p>
            <p className="text-sm text-gray-600 mb-6">
              Click "Add Email" to start building your automation workflow
            </p>
            {safeTemplates.length > 0 && (
              <button
                onClick={addEmailStep}
                className="bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700 inline-flex items-center gap-2"
              >
                <Plus size={20} />
                Add Your First Email
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-6">
            {safeSteps.map((step, index) => (
              <div key={step.id}>
                <div className="relative bg-gradient-to-r from-gray-50 to-white rounded-lg p-6 border-2 border-gray-200 hover:border-blue-300 transition-colors">
                  {/* Step Number Badge */}
                  <div className="absolute -left-3 -top-3 w-10 h-10 bg-blue-600 text-white rounded-full flex items-center justify-center font-bold text-lg shadow-lg">
                    {index + 1}
                  </div>

                  <div className="ml-4">
                    <div className="flex justify-between items-start mb-4">
                      <div>
                        <h3 className="font-semibold text-lg text-gray-900">
                          📧 Email Step {index + 1}
                        </h3>
                        {index === 0 && (
                          <p className="text-sm text-gray-600 mt-1">
                            <Zap size={14} className="inline" /> Trigger: Sent when {workflow.trigger.replace('_', ' ')} event occurs
                          </p>
                        )}
                      </div>
                      <button
                        onClick={() => removeEmailStep(step.id)}
                        className="text-red-600 hover:text-red-800 hover:bg-red-50 p-2 rounded-lg transition-colors"
                        title="Remove this email"
                      >
                        <Trash2 size={18} />
                      </button>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                      {/* Template Selection */}
                      <div>
                        <label className="block text-sm font-medium mb-2">
                          📄 Email Template <span className="text-red-500">*</span>
                        </label>
                        <select
                          value={step.template_id}
                          onChange={(e) => updateEmailStep(step.id, 'template_id', e.target.value)}
                          className={`w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent ${!step.template_id ? 'border-red-300 bg-red-50' : ''
                            }`}
                        >
                          <option value="">Select a template...</option>
                          {safeTemplates.map((template) => (
                            <option key={template.id} value={template.id}>
                              {template.name} {template.subject && `- ${template.subject}`}
                            </option>
                          ))}
                        </select>
                        {!step.template_id && (
                          <p className="text-xs text-red-600 mt-1">⚠️ Please select a template</p>
                        )}
                      </div>

                      {/* Delay Settings */}
                      <div>
                        <label className="block text-sm font-medium mb-2">
                          ⏰ {index === 0 ? 'Send After Trigger' : 'Wait Before Sending'}
                        </label>
                        <div className="flex gap-2">
                          <input
                            type="number"
                            min="0"
                            max="999"
                            value={step.delay_value}
                            onChange={(e) => updateEmailStep(step.id, 'delay_value', Math.max(0, parseInt(e.target.value) || 0))}
                            className="flex-1 p-3 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                            placeholder="0"
                          />
                          <select
                            value={step.delay_type}
                            onChange={(e) => updateEmailStep(step.id, 'delay_type', e.target.value)}
                            className="p-3 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent min-w-[120px]"
                          >
                            <option value="hours">Hours</option>
                            <option value="days">Days</option>
                            <option value="weeks">Weeks</option>
                          </select>
                        </div>
                        <p className="text-xs text-gray-500 mt-1">
                          {index === 0
                            ? step.delay_value === 0
                              ? '⚡ Sent immediately when triggered'
                              : `⏱️ Sent ${step.delay_value} ${step.delay_type} after trigger`
                            : `⏱️ Sent ${step.delay_value} ${step.delay_type} after previous email`
                          }
                        </p>
                      </div>
                    </div>

                    {/* Template Preview Button */}
                    {step.template_id && (
                      <div className="mt-4 pt-4 border-t">
                        <button
                          onClick={() => window.open(`/templates/preview/${step.template_id}`, '_blank')}
                          className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-2"
                        >
                          <Eye size={16} />
                          Preview template
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                {/* Arrow between steps */}
                {index < safeSteps.length - 1 && (
                  <div className="flex justify-center py-4">
                    <div className="flex flex-col items-center text-gray-400">
                      <ArrowDown size={24} className="animate-bounce" />
                      <span className="text-sm mt-1">Then wait and send</span>
                    </div>
                  </div>
                )}

                {/* Last step indicator */}
                {index === safeSteps.length - 1 && (
                  <div className="flex justify-center py-4">
                    <div className="px-4 py-2 bg-green-100 text-green-800 rounded-full text-sm font-medium flex items-center gap-2">
                      <CheckCircle size={16} />
                      Automation Complete
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Help Text */}
        {safeSteps.length > 0 && (
          <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
            <p className="text-sm text-blue-900">
              <strong>💡 Tip:</strong> Test your automation before activating it. Consider starting with a small segment to verify everything works correctly.
            </p>
          </div>
        )}
      </div>

      {/* Save Button (Bottom) */}
      <div className="mt-8 flex justify-end gap-3">
        <button
          onClick={() => navigate('/automation')}
          disabled={saving}
          className="bg-gray-200 text-gray-700 px-6 py-3 rounded-lg hover:bg-gray-300 transition-colors disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          onClick={saveWorkflow}
          disabled={saving || loading}
          className="bg-blue-600 text-white px-8 py-3 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2 text-lg font-medium"
        >
          <Save size={22} />
          {saving ? 'Saving...' : (isEditing ? 'Update Automation' : 'Create Automation')}
        </button>
      </div>
    </div>
  );
};

export default AutomationBuilder;