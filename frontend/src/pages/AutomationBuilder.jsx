// src/pages/AutomationBuilder.jsx - FIXED WITH SUBJECT LINE SUPPORT
import React, { useState, useEffect } from 'react';
import {
  Save, Plus, Trash2, ArrowDown, Users, Target, Mail,
  Clock, Settings, AlertCircle, CheckCircle, Zap, Eye,
  GitBranch, TestTube, Clock3, TrendingUp, Webhook,
  Edit3, ChevronDown, ChevronUp, Info, Check, X
} from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import API from '../api';

const AutomationBuilder = () => {
  const navigate = useNavigate();
  const { id } = useParams();
  const isEditing = Boolean(id);

  // State management
  const [workflow, setWorkflow] = useState({
    name: '',
    trigger: 'welcome',
    trigger_conditions: {},
    target_segments: [],
    target_lists: [],
    steps: [],
    active: false,

    // Basic settings
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

    // Email config
    email_config: {
      sender_email: 'noreply@yourdomain.com',
      sender_name: 'Your Company',
      reply_to: ''
    },

    // Advanced features
    primary_goal: null,
    advanced_mode: false
  });

  const [templates, setTemplates] = useState([]);
  const [segments, setSegments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [validationErrors, setValidationErrors] = useState([]);
  const [expandedSections, setExpandedSections] = useState({
    basic: true,
    advanced: false,
    email: false,
    timing: false,
    goals: false
  });

  // Available fields from segments for field mapping
  const [availableFields, setAvailableFields] = useState({
    universal: ['email'],
    standard: [],
    custom: []
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

  // Safe array access
  const safeSteps = Array.isArray(workflow.steps) ? workflow.steps : [];
  const safeTargetSegments = Array.isArray(workflow.target_segments) ? workflow.target_segments : [];
  const safeTemplates = Array.isArray(templates) ? templates : [];
  const safeSegments = Array.isArray(segments) ? segments : [];

  useEffect(() => {
    fetchTemplatesAndSegments();
    if (isEditing) {
      fetchAutomation();
    }
  }, [id, isEditing]);

  // Fetch available fields when segments change
  useEffect(() => {
    if (workflow.target_segments && workflow.target_segments.length > 0) {
      getAllColumns().then(setAvailableFields).catch(console.error);
    } else {
      setAvailableFields({
        universal: ['email'],
        standard: ['first_name', 'last_name', 'phone', 'company', 'country', 'city', 'job_title'],
        custom: []
      });
    }
  }, [workflow.target_segments]);

  const fetchTemplatesAndSegments = async () => {
    try {
      setLoading(true);
      setError(null);

      const [templatesRes, segmentsRes] = await Promise.all([
        API.get('/automation/templates'),
        API.get('/automation/segments')
      ]);

      let templatesData = templatesRes?.data?.templates || templatesRes?.data || [];
      let segmentsData = segmentsRes?.data?.segments || segmentsRes?.data || [];

      setTemplates(Array.isArray(templatesData) ? templatesData : []);
      setSegments(Array.isArray(segmentsData) ? segmentsData : []);

    } catch (error) {
      console.error('Failed to fetch data:', error);
      setError(`Failed to load data: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const fetchAutomation = async () => {
    try {
      setLoading(true);
      const res = await API.get(`/automation/rules/${id}`);
      const data = res?.data || res;

      if (data.steps && Array.isArray(data.steps)) {
        data.steps = data.steps.map(step => ({
          ...step,
          id: step.id || `step_${Date.now()}_${Math.random()}`
        }));
      }

      if (!data.email_config) {
        data.email_config = {
          sender_email: 'noreply@yourdomain.com',
          sender_name: 'Your Company',
          reply_to: ''
        };
      }

      setWorkflow(data);
    } catch (error) {
      console.error('Failed to fetch automation:', error);
      setError('Failed to load automation rule');
    } finally {
      setLoading(false);
    }
  };

  const validateWorkflow = () => {
    const errors = [];

    if (!workflow.name?.trim()) errors.push('Automation name is required');
    if (!workflow.trigger) errors.push('Trigger event is required');
    if (!workflow.email_config?.sender_email?.trim()) errors.push('Sender email is required');
    if (!workflow.email_config?.sender_name?.trim()) errors.push('Sender name is required');
    if (workflow.steps.length === 0) errors.push('At least one step is required');

    workflow.steps.forEach((step, index) => {
      if (step.step_type === 'email' || !step.step_type) {
        // ⭐ Validate subject line
        if (!step.subject_line || step.subject_line.trim() === '') {
          errors.push(`Step ${index + 1}: Subject line is required for email steps`);
        }

        // Validate template
        if (!step.template_id || step.template_id === '') {
          errors.push(`Step ${index + 1}: Template is required for email steps`);
        }
      }

      // Validate A/B test subjects
      if (step.step_type === 'ab_split' && step.ab_test_config) {
        if (!step.ab_test_config.variant_a_subject || !step.ab_test_config.variant_a_subject.trim()) {
          errors.push(`Step ${index + 1}: Variant A subject line is required`);
        }
        if (!step.ab_test_config.variant_b_subject || !step.ab_test_config.variant_b_subject.trim()) {
          errors.push(`Step ${index + 1}: Variant B subject line is required`);
        }
      }

      // Validate delay
      if (step.delay_value < 0) {
        errors.push(`Step ${index + 1}: Delay cannot be negative`);
      }
    });

    setValidationErrors(errors);
    return errors.length === 0;
  };

  const saveWorkflow = async () => {
    if (!validateWorkflow()) {
      setError('Please fix validation errors');
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }

    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const payload = preparePayload();

      if (isEditing) {
        await API.put(`/automation/rules/${id}`, payload);
        setSuccess('Automation updated successfully!');
      } else {
        await API.post('/automation/rules', payload);
        setSuccess('Automation created successfully!');
      }

      setTimeout(() => navigate('/automation'), 1500);
    } catch (error) {
      console.error('Failed to save:', error);
      setError(error.response?.data?.detail || 'Failed to save automation');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } finally {
      setSaving(false);
    }
  };

  const preparePayload = () => {
    const payload = {
      ...workflow,
      steps: workflow.steps.map((step, index) => {
        const stepData = {
          step_type: step.step_type || 'email',
          step_order: index + 1,
          delay_value: parseInt(step.delay_value) || 0,
          delay_type: step.delay_type || 'hours'
        };

        // ⭐ Add subject_line for email steps
        if (step.step_type === 'email' || !step.step_type) {
          stepData.template_id = step.template_id;
          stepData.subject_line = step.subject_line;
        }

        if (step.conditional_branch) {
          stepData.conditional_branch = step.conditional_branch;
        }

        if (step.ab_test_config) {
          stepData.ab_test_config = step.ab_test_config;
        }

        if (step.wait_for_event) {
          stepData.wait_for_event = step.wait_for_event;
        }

        if (step.smart_send_time) {
          stepData.smart_send_time = step.smart_send_time;
        }

        if (step.webhook_url) {
          stepData.webhook_url = step.webhook_url;
          stepData.webhook_payload = step.webhook_payload || {};
        }

        if (step.field_updates) {
          stepData.field_updates = step.field_updates;
        }

        if (step.goal_tracking) {
          stepData.goal_tracking = step.goal_tracking;
        }

        return stepData;
      })
    };

    return payload;
  };

  // ⭐ FIXED: addStep function with subject_line
  const addStep = (stepType = 'email') => {
    const newStep = {
      id: `step_${Date.now()}_${Math.random()}`,
      step_type: stepType,
      step_order: safeSteps.length + 1,
      delay_value: safeSteps.length === 0 ? 0 : 1,
      delay_type: safeSteps.length === 0 ? 'hours' : 'days'
    };

    // ⭐ Add subject_line for email steps
    if (stepType === 'email') {
      newStep.template_id = '';
      newStep.subject_line = '';
    }

    setWorkflow(prev => ({
      ...prev,
      steps: [...safeSteps, newStep]
    }));
  };

  const removeStep = (stepId) => {
    if (workflow.steps.length === 1) {
      if (!window.confirm('Remove the last step?')) return;
    }
    setWorkflow(prev => ({
      ...prev,
      steps: safeSteps.filter(step => step.id !== stepId)
    }));
  };

  const updateStep = (stepId, field, value) => {
    console.log('🔄 updateStep called:', { stepId, field, value });
    setWorkflow(prev => {
      const updatedSteps = prev.steps.map(step =>
        step.id === stepId ? { ...step, [field]: value } : step
      );
      console.log('🔄 Updated steps:', updatedSteps);
      return {
        ...prev,
        steps: updatedSteps
      };
    });
  };

  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
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

  const calculateTimeline = () => {
    let totalHours = 0;
    safeSteps.forEach(step => {
      const hours = step.delay_type === 'hours' ? step.delay_value :
        step.delay_type === 'days' ? step.delay_value * 24 :
          step.delay_value * 24 * 7;
      totalHours += hours;
    });

    if (totalHours < 24) return `${totalHours} hours`;
    const days = Math.floor(totalHours / 24);
    const remainingHours = totalHours % 24;
    return remainingHours > 0 ? `${days} days ${remainingHours} hours` : `${days} days`;
  };

  const getTemplateName = (templateId) => {
    const template = safeTemplates.find(t => t.id === templateId);
    return template ? template.name : 'Select template...';
  };

  // ⭐ NEW: Extract dynamic fields from template
  const extractDynamicFields = (template) => {
    if (!template) return [];

    const fields = new Set();

    // 🔍 Try ALL possible content locations in your template
    const contentSources = [
      template.content_json?.html,
      template.content_json?.content,
      template.html_content,
      template.content,
      template.body,
      template.html,
      template.text_content,
      // If template has nested structure
      template.template?.html_content,
      template.template?.content,
    ];

    // Find first non-empty content
    let content = '';
    for (const source of contentSources) {
      if (source && String(source).trim().length > 0) {
        content = String(source);
        break;
      }
    }

    // If still no content, try stringifying the whole template
    if (!content) {
      content = JSON.stringify(template);
    }

    // Match {field_name} patterns (single braces)
    const regex1 = /\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g;
    // Also match {{field_name}} patterns (double braces - common in some systems)
    const regex2 = /\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}/g;

    let match;

    // Try single braces
    while ((match = regex1.exec(content)) !== null) {
      fields.add(match[1]);
    }

    // Try double braces
    while ((match = regex2.exec(content)) !== null) {
      fields.add(match[1]);
    }

    return Array.from(fields);
  };

  // ⭐ Get available fields from selected segments (like CreateCampaign)
  const getAllColumns = async () => {
    if (!workflow.target_segments || workflow.target_segments.length === 0) {
      return { universal: ['email'], standard: [], custom: [] };
    }

    try {
      const payload = { segmentIds: workflow.target_segments };
      const response = await API.post('/subscribers/analyze-fields', payload);
      return response.data;
    } catch (error) {
      console.error('Failed to analyze fields from segments:', error);
      return {
        universal: ['email'],
        standard: ['first_name', 'last_name', 'phone', 'company', 'country', 'city', 'job_title'],
        custom: []
      };
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-2">
            {workflow.advanced_mode && <Zap className="text-yellow-500" size={32} />}
            {isEditing ? 'Edit' : 'Create'} Email Automation
          </h1>
          <p className="text-gray-600 mt-1">
            {workflow.advanced_mode
              ? 'Advanced workflow with conditional logic and smart features'
              : 'Build a multi-step email workflow'}
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => navigate('/automation')}
            disabled={saving}
            className="bg-gray-200 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-300 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={saveWorkflow}
            disabled={saving || loading}
            className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
          >
            <Save size={20} />
            {saving ? 'Saving...' : isEditing ? 'Update' : 'Save'} Automation
          </button>
        </div>
      </div>

      {/* Messages */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6 flex items-center gap-2">
          <AlertCircle size={20} />
          {error}
        </div>
      )}

      {success && (
        <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg mb-6 flex items-center gap-2">
          <CheckCircle size={20} />
          {success}
        </div>
      )}

      {validationErrors.length > 0 && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-6">
          <h3 className="font-semibold text-yellow-800 mb-2 flex items-center gap-2">
            <AlertCircle size={20} />
            Please fix the following errors:
          </h3>
          <ul className="list-disc list-inside text-yellow-700 space-y-1">
            {validationErrors.map((err, idx) => (
              <li key={idx}>{err}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Advanced Mode Toggle */}
      <div className="bg-gradient-to-r from-yellow-50 to-orange-50 border-2 border-yellow-300 rounded-lg p-4 mb-6">
        <label className="flex items-center space-x-3 cursor-pointer">
          <input
            type="checkbox"
            checked={workflow.advanced_mode}
            onChange={(e) => setWorkflow(prev => ({ ...prev, advanced_mode: e.target.checked }))}
            className="w-6 h-6 rounded text-yellow-600"
          />
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <Zap className="text-yellow-600" size={24} />
              <div className="font-bold text-gray-900 text-lg">Enable Advanced Features</div>
            </div>
            <div className="text-sm text-gray-700 mt-1">
              Unlock conditional branching, A/B testing, wait-for-event, goal tracking, smart send times, webhooks, and more!
            </div>
          </div>
        </label>
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
              <p className="text-sm text-gray-600">Steps configured</p>
            </div>
          </div>
        </div>
      )}

      {/* Basic Settings Section */}
      <CollapsibleSection
        title="Basic Settings"
        icon={<Settings className="text-blue-600" size={22} />}
        isExpanded={expandedSections.basic}
        onToggle={() => toggleSection('basic')}
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium mb-2">
              Automation Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={workflow.name}
              onChange={(e) => setWorkflow(prev => ({ ...prev, name: e.target.value }))}
              className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
              placeholder="e.g., Welcome Series"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">
              Trigger Event <span className="text-red-500">*</span>
            </label>
            <select
              value={workflow.trigger}
              onChange={(e) => setWorkflow(prev => ({ ...prev, trigger: e.target.value }))}
              className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              <option value="welcome">New Subscriber (Welcome)</option>
              <option value="birthday">Birthday</option>
              <option value="abandoned_cart">Abandoned Cart</option>
              <option value="purchase">After Purchase</option>
              <option value="inactive">Inactive Subscriber</option>
              <option value="custom">Custom Event</option>
            </select>
          </div>
        </div>

        <div className="mt-6">
          <label className="block text-sm font-medium mb-2">Description</label>
          <textarea
            value={workflow.description || ''}
            onChange={(e) => setWorkflow(prev => ({ ...prev, description: e.target.value }))}
            className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
            rows="3"
            placeholder="Describe the purpose of this automation..."
          />
        </div>

        {/* Target Segments */}
        <div className="mt-6">
          <label className="block text-sm font-medium mb-3 flex items-center gap-2">
            <Target size={18} />
            Target Segments (Optional)
          </label>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {safeSegments.map(segment => (
              <label
                key={segment.id}
                className="flex items-center space-x-2 p-3 border rounded-lg cursor-pointer hover:bg-gray-50"
              >
                <input
                  type="checkbox"
                  checked={safeTargetSegments.includes(segment.id)}
                  onChange={() => toggleTargetSegment(segment.id)}
                  className="w-4 h-4 text-blue-600"
                />
                <span className="text-sm">{segment.name}</span>
              </label>
            ))}
          </div>
          {safeSegments.length === 0 && (
            <p className="text-sm text-gray-500 italic">No segments available</p>
          )}
        </div>
      </CollapsibleSection>

      {/* Email Configuration Section */}
      <CollapsibleSection
        title="Email Configuration"
        icon={<Mail className="text-green-600" size={22} />}
        isExpanded={expandedSections.email}
        onToggle={() => toggleSection('email')}
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium mb-2">
              Sender Email <span className="text-red-500">*</span>
            </label>
            <input
              type="email"
              value={workflow.email_config?.sender_email || ''}
              onChange={(e) => setWorkflow(prev => ({
                ...prev,
                email_config: { ...prev.email_config, sender_email: e.target.value }
              }))}
              className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
              placeholder="noreply@yourdomain.com"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">
              Sender Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={workflow.email_config?.sender_name || ''}
              onChange={(e) => setWorkflow(prev => ({
                ...prev,
                email_config: { ...prev.email_config, sender_name: e.target.value }
              }))}
              className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
              placeholder="Your Company"
            />
          </div>

          <div className="md:col-span-2">
            <label className="block text-sm font-medium mb-2">
              Reply-To Email (Optional)
            </label>
            <input
              type="email"
              value={workflow.email_config?.reply_to || ''}
              onChange={(e) => setWorkflow(prev => ({
                ...prev,
                email_config: { ...prev.email_config, reply_to: e.target.value }
              }))}
              className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
              placeholder="support@yourdomain.com"
            />
          </div>
        </div>
      </CollapsibleSection>

      {/* Timing & Schedule Section */}
      <CollapsibleSection
        title="Timing & Schedule"
        icon={<Clock className="text-purple-600" size={22} />}
        isExpanded={expandedSections.timing}
        onToggle={() => toggleSection('timing')}
      >
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium mb-2">Default Timezone</label>
              <select
                value={workflow.timezone}
                onChange={(e) => setWorkflow(prev => ({ ...prev, timezone: e.target.value }))}
                className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                {commonTimezones.map(tz => (
                  <option key={tz.value} value={tz.value}>{tz.label}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Max Emails Per Day</label>
              <input
                type="number"
                min="1"
                max="20"
                value={workflow.max_emails_per_day}
                onChange={(e) => setWorkflow(prev => ({ ...prev, max_emails_per_day: parseInt(e.target.value) }))}
                className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          <label className="flex items-center space-x-3 cursor-pointer">
            <input
              type="checkbox"
              checked={workflow.use_subscriber_timezone}
              onChange={(e) => setWorkflow(prev => ({ ...prev, use_subscriber_timezone: e.target.checked }))}
              className="w-4 h-4 text-blue-600"
            />
            <span className="text-sm">Use subscriber's timezone (if available)</span>
          </label>

          <label className="flex items-center space-x-3 cursor-pointer">
            <input
              type="checkbox"
              checked={workflow.respect_quiet_hours}
              onChange={(e) => setWorkflow(prev => ({ ...prev, respect_quiet_hours: e.target.checked }))}
              className="w-4 h-4 text-blue-600"
            />
            <span className="text-sm">Respect quiet hours (don't send during these times)</span>
          </label>

          {workflow.respect_quiet_hours && (
            <div className="ml-7 grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-2">Quiet Hours Start</label>
                <input
                  type="number"
                  min="0"
                  max="23"
                  value={workflow.quiet_hours_start}
                  onChange={(e) => setWorkflow(prev => ({ ...prev, quiet_hours_start: parseInt(e.target.value) }))}
                  className="w-full p-2 border rounded-lg"
                />
                <p className="text-xs text-gray-500 mt-1">Hour (0-23, e.g., 22 = 10 PM)</p>
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">Quiet Hours End</label>
                <input
                  type="number"
                  min="0"
                  max="23"
                  value={workflow.quiet_hours_end}
                  onChange={(e) => setWorkflow(prev => ({ ...prev, quiet_hours_end: parseInt(e.target.value) }))}
                  className="w-full p-2 border rounded-lg"
                />
                <p className="text-xs text-gray-500 mt-1">Hour (0-23, e.g., 8 = 8 AM)</p>
              </div>
            </div>
          )}
        </div>
      </CollapsibleSection>

      {/* Goal Tracking Section */}
      {workflow.advanced_mode && (
        <CollapsibleSection
          title="Goal Tracking"
          icon={<TrendingUp className="text-green-600" size={22} />}
          isExpanded={expandedSections.goals}
          onToggle={() => toggleSection('goals')}
          badge="Advanced"
        >
          <GoalTrackingConfig workflow={workflow} setWorkflow={setWorkflow} />
        </CollapsibleSection>
      )}

      {/* Workflow Steps */}
      <div className="bg-white rounded-lg shadow-sm border p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <Mail className="text-blue-600" size={22} />
            Workflow Steps
          </h2>
          <div className="flex gap-2">
            <button
              onClick={() => addStep('email')}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 flex items-center gap-2"
            >
              <Plus size={18} />
              Add Email
            </button>
            {workflow.advanced_mode && (
              <AdvancedStepMenu onSelectStepType={addStep} />
            )}
          </div>
        </div>

        {safeSteps.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <Mail size={48} className="mx-auto mb-3 opacity-50" />
            <p>No steps yet. Click "Add Email" to start building your workflow.</p>
          </div>
        ) : (
          <div className="space-y-4">
            {safeSteps.map((step, index) => (
              <StepCard
                key={step.id}
                step={step}
                index={index}
                templates={safeTemplates}
                segments={safeSegments}
                isAdvanced={workflow.advanced_mode}
                onUpdate={updateStep}
                onRemove={removeStep}
                getTemplateName={getTemplateName}
                extractDynamicFields={extractDynamicFields}
                availableFields={availableFields}
              />
            ))}
          </div>
        )}
      </div>

      {/* Status Toggle */}
      <div className="bg-white rounded-lg shadow-sm border p-6 mb-6">
        <label className="flex items-center space-x-3 cursor-pointer">
          <input
            type="checkbox"
            checked={workflow.active}
            onChange={(e) => setWorkflow(prev => ({ ...prev, active: e.target.checked }))}
            className="w-6 h-6 rounded text-blue-600"
          />
          <div>
            <div className="font-medium text-gray-900 text-lg">Activate Immediately</div>
            <div className="text-sm text-gray-600">
              {workflow.active
                ? '🟢 Automation will start immediately after saving'
                : '⚪ Automation will be saved as draft'}
            </div>
          </div>
        </label>
      </div>

      {/* Save Buttons */}
      <div className="flex justify-end gap-3">
        <button
          onClick={() => navigate('/automation')}
          disabled={saving}
          className="bg-gray-200 text-gray-700 px-6 py-3 rounded-lg hover:bg-gray-300 transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={saveWorkflow}
          disabled={saving || loading}
          className="bg-blue-600 text-white px-8 py-3 rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2 text-lg font-medium"
        >
          <Save size={22} />
          {saving ? 'Saving...' : isEditing ? 'Update Automation' : 'Create Automation'}
        </button>
      </div>
    </div>
  );
};

// ============================================
// COLLAPSIBLE SECTION COMPONENT
// ============================================
const CollapsibleSection = ({ title, icon, children, isExpanded, onToggle, badge }) => (
  <div className="bg-white rounded-lg shadow-sm border mb-6">
    <button
      onClick={onToggle}
      className="w-full p-6 flex items-center justify-between hover:bg-gray-50 transition-colors"
    >
      <div className="flex items-center gap-3">
        {icon}
        <h2 className="text-xl font-semibold">{title}</h2>
        {badge && (
          <span className="px-2 py-1 text-xs font-medium bg-yellow-100 text-yellow-800 rounded">
            {badge}
          </span>
        )}
      </div>
      {isExpanded ? <ChevronUp size={24} /> : <ChevronDown size={24} />}
    </button>
    {isExpanded && <div className="p-6 pt-0 border-t">{children}</div>}
  </div>
);

// ============================================
// GOAL TRACKING CONFIG COMPONENT
// ============================================
const GoalTrackingConfig = ({ workflow, setWorkflow }) => {
  const [goalEnabled, setGoalEnabled] = useState(!!workflow.primary_goal);

  const toggleGoal = (enabled) => {
    setGoalEnabled(enabled);
    if (!enabled) {
      setWorkflow(prev => ({ ...prev, primary_goal: null }));
    } else {
      setWorkflow(prev => ({
        ...prev,
        primary_goal: {
          goal_type: 'purchase',
          goal_value: null,
          tracking_window_days: 30,
          conversion_url: ''
        }
      }));
    }
  };

  return (
    <div className="space-y-4">
      <label className="flex items-center space-x-3 cursor-pointer">
        <input
          type="checkbox"
          checked={goalEnabled}
          onChange={(e) => toggleGoal(e.target.checked)}
          className="w-5 h-5 rounded text-green-600"
        />
        <div>
          <div className="font-medium text-gray-900">Enable Goal Tracking</div>
          <div className="text-sm text-gray-600">Track conversions and stop automation when goal is achieved</div>
        </div>
      </label>

      {goalEnabled && workflow.primary_goal && (
        <div className="ml-8 space-y-4 border-l-2 border-green-200 pl-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-2">Goal Type</label>
              <select
                value={workflow.primary_goal.goal_type}
                onChange={(e) => setWorkflow(prev => ({
                  ...prev,
                  primary_goal: { ...prev.primary_goal, goal_type: e.target.value }
                }))}
                className="w-full p-2 border rounded-lg"
              >
                <option value="purchase">Purchase</option>
                <option value="signup">Signup</option>
                <option value="download">Download</option>
                <option value="click">Click</option>
                <option value="open">Open</option>
                <option value="custom">Custom Event</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Tracking Window (Days)</label>
              <input
                type="number"
                min="1"
                max="365"
                value={workflow.primary_goal.tracking_window_days}
                onChange={(e) => setWorkflow(prev => ({
                  ...prev,
                  primary_goal: { ...prev.primary_goal, tracking_window_days: parseInt(e.target.value) }
                }))}
                className="w-full p-2 border rounded-lg"
              />
            </div>
          </div>

          {workflow.primary_goal.goal_type === 'purchase' && (
            <div>
              <label className="block text-sm font-medium mb-2">Goal Value ($)</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={workflow.primary_goal.goal_value || ''}
                onChange={(e) => setWorkflow(prev => ({
                  ...prev,
                  primary_goal: { ...prev.primary_goal, goal_value: parseFloat(e.target.value) }
                }))}
                className="w-full p-2 border rounded-lg"
                placeholder="99.99"
              />
            </div>
          )}

          <div>
            <label className="block text-sm font-medium mb-2">Conversion URL (Optional)</label>
            <input
              type="url"
              value={workflow.primary_goal.conversion_url || ''}
              onChange={(e) => setWorkflow(prev => ({
                ...prev,
                primary_goal: { ...prev.primary_goal, conversion_url: e.target.value }
              }))}
              className="w-full p-2 border rounded-lg"
              placeholder="https://example.com/thank-you"
            />
          </div>

          <label className="flex items-center space-x-3 cursor-pointer">
            <input
              type="checkbox"
              checked={workflow.exit_on_goal_achieved}
              onChange={(e) => setWorkflow(prev => ({ ...prev, exit_on_goal_achieved: e.target.checked }))}
              className="w-4 h-4 rounded text-green-600"
            />
            <div className="text-sm text-gray-700">Exit automation when goal is achieved</div>
          </label>
        </div>
      )}
    </div>
  );
};

// ============================================
// ADVANCED STEP MENU COMPONENT
// ============================================
const AdvancedStepMenu = ({ onSelectStepType }) => {
  const [isOpen, setIsOpen] = useState(false);

  const stepTypes = [
    { type: 'condition', label: 'Conditional Branch', icon: GitBranch, color: 'text-purple-600' },
    { type: 'ab_split', label: 'A/B Test', icon: TestTube, color: 'text-blue-600' },
    { type: 'wait_for_event', label: 'Wait for Event', icon: Clock3, color: 'text-orange-600' },
    { type: 'send_webhook', label: 'Send Webhook', icon: Webhook, color: 'text-green-600' },
    { type: 'update_field', label: 'Update Field', icon: Edit3, color: 'text-indigo-600' },
  ];

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="bg-purple-600 text-white px-4 py-2 rounded-lg hover:bg-purple-700 flex items-center gap-2"
      >
        <Zap size={18} />
        Advanced Step
        <ChevronDown size={16} />
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
          <div className="absolute right-0 mt-2 w-64 bg-white rounded-lg shadow-lg border z-20">
            {stepTypes.map(({ type, label, icon: Icon, color }) => (
              <button
                key={type}
                onClick={() => {
                  onSelectStepType(type);
                  setIsOpen(false);
                }}
                className="w-full px-4 py-3 flex items-center gap-3 hover:bg-gray-50 transition-colors first:rounded-t-lg last:rounded-b-lg"
              >
                <Icon className={color} size={20} />
                <span className="text-sm font-medium">{label}</span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
};

// ============================================
// STEP CARD COMPONENT
// ============================================
const StepCard = ({ step, index, templates, segments, isAdvanced, onUpdate, onRemove, getTemplateName, extractDynamicFields, availableFields }) => {
  const [showAdvanced, setShowAdvanced] = useState(false);

  const stepTypeLabels = {
    email: 'Email',
    condition: 'Conditional Branch',
    ab_split: 'A/B Test',
    wait_for_event: 'Wait for Event',
    send_webhook: 'Webhook',
    update_field: 'Update Field',
    delay: 'Delay'
  };

  const stepTypeIcons = {
    email: Mail,
    condition: GitBranch,
    ab_split: TestTube,
    wait_for_event: Clock3,
    send_webhook: Webhook,
    update_field: Edit3,
    delay: Clock
  };

  const Icon = stepTypeIcons[step.step_type] || Mail;

  return (
    <div className="border rounded-lg p-4 bg-gray-50">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="bg-blue-100 text-blue-700 font-bold w-8 h-8 rounded-full flex items-center justify-center">
            {index + 1}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <Icon size={18} className="text-gray-700" />
              <h3 className="font-semibold text-gray-900">
                {stepTypeLabels[step.step_type] || 'Email Step'}
              </h3>
            </div>
            {index > 0 && (
              <p className="text-sm text-gray-600 mt-1">
                Delay: {step.delay_value} {step.delay_type}
              </p>
            )}
          </div>
        </div>
        <button
          onClick={() => onRemove(step.id)}
          className="text-red-600 hover:bg-red-50 p-2 rounded-lg transition-colors"
        >
          <Trash2 size={18} />
        </button>
      </div>

      {/* Delay Configuration */}
      {index > 0 && (
        <div className="grid grid-cols-2 gap-3 mb-4">
          <div>
            <label className="block text-xs font-medium mb-1">Delay Amount</label>
            <input
              type="number"
              min="0"
              value={step.delay_value}
              onChange={(e) => onUpdate(step.id, 'delay_value', parseInt(e.target.value) || 0)}
              className="w-full p-2 border rounded text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Delay Unit</label>
            <select
              value={step.delay_type}
              onChange={(e) => onUpdate(step.id, 'delay_type', e.target.value)}
              className="w-full p-2 border rounded text-sm"
            >
              <option value="hours">Hours</option>
              <option value="days">Days</option>
              <option value="weeks">Weeks</option>
            </select>
          </div>
        </div>
      )}

      {/* ⭐ Email Step Configuration WITH SUBJECT LINE & FIELD MAPPING */}
      {step.step_type === 'email' && (
        <div className="space-y-3">
          {/* ⭐ Subject Line Field */}
          <div>
            <label className="block text-sm font-medium mb-2">
              Email Subject Line <span className="text-red-500">*</span>
              <span className="text-xs text-gray-500 ml-2">(Templates don't have subjects)</span>
            </label>
            <input
              type="text"
              value={step.subject_line || ''}
              onChange={(e) => onUpdate(step.id, 'subject_line', e.target.value)}
              className={`w-full p-2 border rounded-lg ${!step.subject_line || step.subject_line.trim() === ''
                  ? 'border-red-300 bg-red-50'
                  : 'border-gray-300'
                }`}
              placeholder="e.g., Welcome to our platform!"
            />
            {(!step.subject_line || step.subject_line.trim() === '') && (
              <p className="text-xs text-red-600 mt-1">⚠️ Subject line is required</p>
            )}
            <p className="text-xs text-gray-500 mt-1">
              💡 Use variables: {'{'}first_name{'}'}, {'{'}company{'}'},  {'{'}email{'}'}
            </p>
          </div>

          {/* Template Selection */}
          <div>
            <label className="block text-sm font-medium mb-2">
              Email Template <span className="text-red-500">*</span>
            </label>
            <select
              value={step.template_id || ''}
              onChange={async (e) => {
                const templateId = e.target.value;
                console.log('📧 EMAIL STEP - Template selected:', templateId);

                const selectedTemplate = templates?.find(t => t.id === templateId);
                console.log('📧 EMAIL STEP - Found template:', selectedTemplate);

                // Update template ID immediately
                onUpdate(step.id, 'template_id', templateId);

                // Fetch dynamic fields from backend API (like CreateCampaign does)
                if (templateId) {
                  try {
                    console.log('📧 EMAIL STEP - Fetching fields from API...');
                    const response = await API.get(`/templates/${templateId}/fields`);
                    const dynamicFields = response.data;
                    console.log('📧 EMAIL STEP - API returned fields:', dynamicFields);

                    onUpdate(step.id, 'dynamic_fields', dynamicFields);
                    onUpdate(step.id, 'field_map', step.field_map || {});
                    onUpdate(step.id, 'fallback_values', step.fallback_values || {});
                    console.log('📧 EMAIL STEP - Updated all field data from API');
                  } catch (error) {
                    console.error('📧 EMAIL STEP - API fetch failed, trying local extraction:', error);

                    // Fallback to local extraction if API fails
                    if (selectedTemplate && extractDynamicFields) {
                      const dynamicFields = extractDynamicFields(selectedTemplate);
                      console.log('📧 EMAIL STEP - Local extraction fields:', dynamicFields);
                      onUpdate(step.id, 'dynamic_fields', dynamicFields);
                      onUpdate(step.id, 'field_map', step.field_map || {});
                      onUpdate(step.id, 'fallback_values', step.fallback_values || {});
                    }
                  }
                }
              }}
              className={`w-full p-2 border rounded-lg ${!step.template_id ? 'border-red-300 bg-red-50' : 'border-gray-300'
                }`}
            >
              <option value="">-- Select Template --</option>
              {templates && Array.isArray(templates) ? (
                templates.map(template => (
                  <option key={template.id} value={template.id}>
                    {template.name}
                  </option>
                ))
              ) : (
                <option value="" disabled>No templates found</option>
              )}
            </select>
            {(!templates || templates.length === 0) && (
              <p className="text-xs text-red-600 mt-1">
                ⚠️ No templates available
              </p>
            )}
            <p className="text-xs text-gray-500 mt-1">
              Template provides email body content only
            </p>
          </div>

          {/* ⭐ NEW: Field Mapping Section */}
          {step.template_id && step.dynamic_fields && step.dynamic_fields.length > 0 && (
            <FieldMappingSection
              step={step}
              onUpdate={onUpdate}
              availableFields={availableFields}
            />
          )}
        </div>
      )}

      {/* Advanced Features for Email Steps */}
      {isAdvanced && step.step_type === 'email' && (
        <div className="mt-4">
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-sm text-purple-600 hover:text-purple-700 font-medium flex items-center gap-1"
          >
            <Zap size={14} />
            {showAdvanced ? 'Hide' : 'Show'} Advanced Options
            {showAdvanced ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>

          {showAdvanced && (
            <div className="mt-3 space-y-3 pl-4 border-l-2 border-purple-200">
              <AdvancedEmailOptions step={step} onUpdate={onUpdate} />
            </div>
          )}
        </div>
      )}

      {/* Conditional Branch Configuration */}
      {step.step_type === 'condition' && (
        <ConditionalBranchConfig step={step} onUpdate={onUpdate} segments={segments} />
      )}

      {/* A/B Test Configuration */}
      {step.step_type === 'ab_split' && (
        <ABTestConfig step={step} onUpdate={onUpdate} templates={templates} extractDynamicFields={extractDynamicFields} availableFields={availableFields} />
      )}

      {/* Wait for Event Configuration */}
      {step.step_type === 'wait_for_event' && (
        <WaitForEventConfig step={step} onUpdate={onUpdate} />
      )}

      {/* Webhook Configuration */}
      {step.step_type === 'send_webhook' && (
        <WebhookConfig step={step} onUpdate={onUpdate} />
      )}

      {/* Update Field Configuration */}
      {step.step_type === 'update_field' && (
        <UpdateFieldConfig step={step} onUpdate={onUpdate} />
      )}
    </div>
  );
};

// ============================================
// ADVANCED EMAIL OPTIONS COMPONENT
// ============================================
const AdvancedEmailOptions = ({ step, onUpdate }) => {
  const toggleSmartSendTime = (enabled) => {
    if (enabled) {
      onUpdate(step.id, 'smart_send_time', {
        enabled: true,
        optimize_for: 'opens',
        time_window_start: 8,
        time_window_end: 20,
        respect_timezone: true,
        fallback_time: 10
      });
    } else {
      onUpdate(step.id, 'smart_send_time', null);
    }
  };

  return (
    <>
      <label className="flex items-center space-x-2 cursor-pointer">
        <input
          type="checkbox"
          checked={!!step.smart_send_time?.enabled}
          onChange={(e) => toggleSmartSendTime(e.target.checked)}
          className="w-4 h-4 rounded text-purple-600"
        />
        <span className="text-sm font-medium">Smart Send Time Optimization</span>
      </label>

      {step.smart_send_time?.enabled && (
        <div className="ml-6 space-y-2 p-3 bg-purple-50 rounded border border-purple-200">
          <div>
            <label className="block text-xs font-medium mb-1">Optimize For</label>
            <select
              value={step.smart_send_time.optimize_for}
              onChange={(e) => onUpdate(step.id, 'smart_send_time', {
                ...step.smart_send_time,
                optimize_for: e.target.value
              })}
              className="w-full p-2 border rounded text-sm"
            >
              <option value="opens">Opens</option>
              <option value="clicks">Clicks</option>
              <option value="engagement">Overall Engagement</option>
            </select>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs font-medium mb-1">Send Window Start (Hour)</label>
              <input
                type="number"
                min="0"
                max="23"
                value={step.smart_send_time.time_window_start}
                onChange={(e) => onUpdate(step.id, 'smart_send_time', {
                  ...step.smart_send_time,
                  time_window_start: parseInt(e.target.value)
                })}
                className="w-full p-2 border rounded text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1">Send Window End (Hour)</label>
              <input
                type="number"
                min="0"
                max="23"
                value={step.smart_send_time.time_window_end}
                onChange={(e) => onUpdate(step.id, 'smart_send_time', {
                  ...step.smart_send_time,
                  time_window_end: parseInt(e.target.value)
                })}
                className="w-full p-2 border rounded text-sm"
              />
            </div>
          </div>
        </div>
      )}
    </>
  );
};

// ============================================
// CONDITIONAL BRANCH CONFIG
// ============================================
const ConditionalBranchConfig = ({ step, onUpdate, segments }) => {
  const initBranch = () => ({
    condition_type: 'opened_email',
    wait_time_hours: 24,
    true_path_step_ids: [],
    false_path_step_ids: [],
    timeout_path: 'false'
  });

  // ⭐ FIX: Initialize in useEffect instead of during render
  React.useEffect(() => {
    if (!step.conditional_branch) {
      onUpdate(step.id, 'conditional_branch', initBranch());
    }
  }, [step.id, step.conditional_branch]);

  return (
    <div className="space-y-3">
      <div>
        <label className="block text-sm font-medium mb-2">Condition Type</label>
        <select
          value={step.conditional_branch?.condition_type || 'opened_email'}
          onChange={(e) => onUpdate(step.id, 'conditional_branch', {
            ...step.conditional_branch,
            condition_type: e.target.value
          })}
          className="w-full p-2 border rounded-lg"
        >
          <option value="opened_email">Opened Email</option>
          <option value="clicked_link">Clicked Link</option>
          <option value="not_opened">Did Not Open</option>
          <option value="segment_match">In Segment</option>
          <option value="field_equals">Field Equals</option>
        </select>
      </div>

      {/* ⭐ Segment Selection UI */}
      {step.conditional_branch?.condition_type === 'segment_match' && segments && (
        <div className="p-3 bg-purple-50 border border-purple-200 rounded">
          <label className="block text-sm font-medium mb-2">
            Select Target Segments
          </label>
          <p className="text-xs text-purple-600 mb-3">
            Subscriber must be in at least ONE of these segments
          </p>

          <div className="space-y-2 max-h-48 overflow-y-auto">
            {segments && segments.length > 0 ? (
              segments.map(segment => (
                <label
                  key={segment.id}
                  className="flex items-center space-x-2 p-2 hover:bg-purple-100 rounded cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={(step.conditional_branch?.condition_value || []).includes(segment.id)}
                    onChange={(e) => {
                      const currentSegments = step.conditional_branch?.condition_value || [];
                      const newSegments = e.target.checked
                        ? [...currentSegments, segment.id]
                        : currentSegments.filter(s => s !== segment.id);

                      onUpdate(step.id, 'conditional_branch', {
                        ...step.conditional_branch,
                        condition_value: newSegments
                      });
                    }}
                    className="w-4 h-4 rounded text-purple-600"
                  />
                  <div className="flex-1">
                    <div className="text-sm font-medium">{segment.name}</div>
                    {segment.subscriber_count && (
                      <div className="text-xs text-gray-500">
                        {segment.subscriber_count} subscribers
                      </div>
                    )}
                  </div>
                </label>
              ))
            ) : (
              <div className="text-sm text-gray-500 italic text-center py-4">
                No segments available
              </div>
            )}
          </div>
        </div>
      )}

      {/* ⭐ NEW: Field Equals Configuration UI */}
      {step.conditional_branch?.condition_type === 'field_equals' && (
        <div className="p-3 bg-indigo-50 border border-indigo-200 rounded space-y-3">
          <div>
            <label className="block text-sm font-medium mb-2">
              Field Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={step.conditional_branch?.field_name || ''}
              onChange={(e) => onUpdate(step.id, 'conditional_branch', {
                ...step.conditional_branch,
                field_name: e.target.value
              })}
              className="w-full p-2 border rounded-lg"
              placeholder="e.g., status, tier, location"
            />
            <p className="text-xs text-gray-500 mt-1">
              The subscriber field to check (e.g., status, company, city)
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">
              Comparison Operator
            </label>
            <select
              value={step.conditional_branch?.operator || 'equals'}
              onChange={(e) => onUpdate(step.id, 'conditional_branch', {
                ...step.conditional_branch,
                operator: e.target.value
              })}
              className="w-full p-2 border rounded-lg"
            >
              <option value="equals">Equals (=)</option>
              <option value="not_equals">Not Equals (≠)</option>
              <option value="contains">Contains</option>
              <option value="not_contains">Does Not Contain</option>
              <option value="starts_with">Starts With</option>
              <option value="ends_with">Ends With</option>
              <option value="greater_than">Greater Than (&gt;)</option>
              <option value="less_than">Less Than (&lt;)</option>
              <option value="exists">Field Exists</option>
              <option value="not_exists">Field Does Not Exist</option>
            </select>
          </div>

          {step.conditional_branch?.operator !== 'exists' && step.conditional_branch?.operator !== 'not_exists' && (
            <div>
              <label className="block text-sm font-medium mb-2">
                Expected Value <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={step.conditional_branch?.condition_value || ''}
                onChange={(e) => onUpdate(step.id, 'conditional_branch', {
                  ...step.conditional_branch,
                  condition_value: e.target.value
                })}
                className="w-full p-2 border rounded-lg"
                placeholder="e.g., premium, active, USA"
              />
              <p className="text-xs text-gray-500 mt-1">
                The value to compare against
              </p>
            </div>
          )}

          <div className="p-2 bg-indigo-100 border border-indigo-300 rounded text-xs">
            <p className="font-medium text-indigo-900 mb-1">📝 Example Conditions:</p>
            <ul className="text-indigo-700 space-y-1">
              <li>• Field: "tier" | Equals | "premium"</li>
              <li>• Field: "last_purchase_days" | Less Than | "30"</li>
              <li>• Field: "country" | Equals | "USA"</li>
              <li>• Field: "vip_status" | Exists</li>
            </ul>
          </div>
        </div>
      )}

      <div>
        <label className="block text-sm font-medium mb-2">Wait Time (Hours)</label>
        <input
          type="number"
          min="1"
          value={step.conditional_branch?.wait_time_hours || 24}
          onChange={(e) => onUpdate(step.id, 'conditional_branch', {
            ...step.conditional_branch,
            wait_time_hours: parseInt(e.target.value)
          })}
          className="w-full p-2 border rounded-lg"
        />
        <p className="text-xs text-gray-500 mt-1">How long to wait before checking condition</p>
      </div>
    </div>
  );
};

// ============================================
// A/B TEST CONFIG - WITH SUBJECT LINES
// ============================================
const ABTestConfig = ({ step, onUpdate, templates, extractDynamicFields, availableFields }) => {
  const initABTest = () => ({
    variant_a_percentage: 50,
    variant_b_percentage: 50,
    variant_a_template_id: '',
    variant_a_subject: '',  // ⭐ REQUIRED
    variant_b_template_id: '',
    variant_b_subject: '',  // ⭐ REQUIRED
    winning_metric: 'open_rate',
    test_duration_hours: 48
  });

  // ⭐ FIX: Initialize in useEffect instead of during render
  React.useEffect(() => {
    if (!step.ab_test_config) {
      onUpdate(step.id, 'ab_test_config', initABTest());
    }
  }, [step.id, step.ab_test_config]);

  const config = step.ab_test_config || initABTest();

  return (
    <div className="space-y-4">
      <div className="p-3 bg-gradient-to-r from-blue-50 to-purple-50 border border-blue-200 rounded">
        <h4 className="font-semibold text-sm mb-2 text-blue-900">🧪 A/B Test Configuration</h4>
        <p className="text-xs text-blue-700">
          Test different email variations to find what works best
        </p>
      </div>

      {/* Traffic Split */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm font-medium mb-2">Variant A %</label>
          <input
            type="number"
            min="0"
            max="100"
            value={config.variant_a_percentage}
            onChange={(e) => {
              const valA = parseInt(e.target.value) || 0;
              onUpdate(step.id, 'ab_test_config', {
                ...config,
                variant_a_percentage: valA,
                variant_b_percentage: 100 - valA
              });
            }}
            className="w-full p-2 border rounded"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-2">Variant B %</label>
          <input
            type="number"
            value={config.variant_b_percentage}
            disabled
            className="w-full p-2 border rounded bg-gray-100"
          />
        </div>
      </div>

      {/* ⭐ Variant A Configuration WITH SUBJECT & FIELD MAPPING */}
      <div className="p-4 border-2 border-blue-300 rounded-lg bg-blue-50">
        <h5 className="font-semibold text-blue-900 mb-3">📧 Variant A</h5>

        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium mb-2">
              Subject Line <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={config.variant_a_subject}
              onChange={(e) => onUpdate(step.id, 'ab_test_config', {
                ...config,
                variant_a_subject: e.target.value
              })}
              className={`w-full p-2 border rounded ${!config.variant_a_subject ? 'border-red-300 bg-red-50' : 'border-gray-300'
                }`}
              placeholder="e.g., Unlock Your Free Trial Today"
            />
            {!config.variant_a_subject && (
              <p className="text-xs text-red-600 mt-1">⚠️ Subject is required</p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">
              Template <span className="text-red-500">*</span>
            </label>
            <select
              value={config.variant_a_template_id || ''}
              onChange={async (e) => {
                const templateId = e.target.value;
                onUpdate(step.id, 'ab_test_config', {
                  ...config,
                  variant_a_template_id: templateId
                });

                // Fetch dynamic fields from backend API
                if (templateId) {
                  try {
                    const response = await API.get(`/templates/${templateId}/fields`);
                    const dynamicFields = response.data;
                    onUpdate(step.id, 'ab_test_config', {
                      ...config,
                      variant_a_template_id: templateId,
                      variant_a_dynamic_fields: dynamicFields,
                      variant_a_field_map: config.variant_a_field_map || {},
                      variant_a_fallback_values: config.variant_a_fallback_values || {}
                    });
                  } catch (error) {
                    console.error('Failed to fetch fields from API, trying local extraction:', error);
                    // Fallback to local extraction
                    const selectedTemplate = templates?.find(t => t.id === templateId);
                    if (selectedTemplate && extractDynamicFields) {
                      const dynamicFields = extractDynamicFields(selectedTemplate);
                      onUpdate(step.id, 'ab_test_config', {
                        ...config,
                        variant_a_template_id: templateId,
                        variant_a_dynamic_fields: dynamicFields,
                        variant_a_field_map: config.variant_a_field_map || {},
                        variant_a_fallback_values: config.variant_a_fallback_values || {}
                      });
                    }
                  }
                }
              }}
              className={`w-full p-2 border rounded ${!config.variant_a_template_id ? 'border-red-300' : 'border-gray-300'
                }`}
            >
              <option value="">-- Select Template --</option>
              {templates && Array.isArray(templates) ? (
                templates.map(t => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))
              ) : null}
            </select>
          </div>

          {/* ⭐ NEW: Field Mapping for Variant A */}
          {config.variant_a_template_id && config.variant_a_dynamic_fields && config.variant_a_dynamic_fields.length > 0 && (
            <ABVariantFieldMapping
              variantLabel="A"
              dynamicFields={config.variant_a_dynamic_fields}
              fieldMap={config.variant_a_field_map || {}}
              fallbackValues={config.variant_a_fallback_values || {}}
              availableFields={availableFields}
              onFieldMapChange={(newMap) => onUpdate(step.id, 'ab_test_config', {
                ...config,
                variant_a_field_map: newMap
              })}
              onFallbackChange={(newFallback) => onUpdate(step.id, 'ab_test_config', {
                ...config,
                variant_a_fallback_values: newFallback
              })}
            />
          )}
        </div>
      </div>

      {/* ⭐ Variant B Configuration WITH SUBJECT & FIELD MAPPING */}
      <div className="p-4 border-2 border-purple-300 rounded-lg bg-purple-50">
        <h5 className="font-semibold text-purple-900 mb-3">📧 Variant B</h5>

        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium mb-2">
              Subject Line <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={config.variant_b_subject}
              onChange={(e) => onUpdate(step.id, 'ab_test_config', {
                ...config,
                variant_b_subject: e.target.value
              })}
              className={`w-full p-2 border rounded ${!config.variant_b_subject ? 'border-red-300 bg-red-50' : 'border-gray-300'
                }`}
              placeholder="e.g., Start Your Journey - Free Trial"
            />
            {!config.variant_b_subject && (
              <p className="text-xs text-red-600 mt-1">⚠️ Subject is required</p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">
              Template <span className="text-red-500">*</span>
            </label>
            <select
              value={config.variant_b_template_id || ''}
              onChange={async (e) => {
                const templateId = e.target.value;
                onUpdate(step.id, 'ab_test_config', {
                  ...config,
                  variant_b_template_id: templateId
                });

                // Fetch dynamic fields from backend API
                if (templateId) {
                  try {
                    const response = await API.get(`/templates/${templateId}/fields`);
                    const dynamicFields = response.data;
                    onUpdate(step.id, 'ab_test_config', {
                      ...config,
                      variant_b_template_id: templateId,
                      variant_b_dynamic_fields: dynamicFields,
                      variant_b_field_map: config.variant_b_field_map || {},
                      variant_b_fallback_values: config.variant_b_fallback_values || {}
                    });
                  } catch (error) {
                    console.error('Failed to fetch fields from API, trying local extraction:', error);
                    // Fallback to local extraction
                    const selectedTemplate = templates?.find(t => t.id === templateId);
                    if (selectedTemplate && extractDynamicFields) {
                      const dynamicFields = extractDynamicFields(selectedTemplate);
                      onUpdate(step.id, 'ab_test_config', {
                        ...config,
                        variant_b_template_id: templateId,
                        variant_b_dynamic_fields: dynamicFields,
                        variant_b_field_map: config.variant_b_field_map || {},
                        variant_b_fallback_values: config.variant_b_fallback_values || {}
                      });
                    }
                  }
                }
              }}
              className={`w-full p-2 border rounded ${!config.variant_b_template_id ? 'border-red-300' : 'border-gray-300'
                }`}
            >
              <option value="">-- Select Template --</option>
              {templates.map(t => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>

          {/* ⭐ NEW: Field Mapping for Variant B */}
          {config.variant_b_template_id && config.variant_b_dynamic_fields && config.variant_b_dynamic_fields.length > 0 && (
            <ABVariantFieldMapping
              variantLabel="B"
              dynamicFields={config.variant_b_dynamic_fields}
              fieldMap={config.variant_b_field_map || {}}
              fallbackValues={config.variant_b_fallback_values || {}}
              availableFields={availableFields}
              onFieldMapChange={(newMap) => onUpdate(step.id, 'ab_test_config', {
                ...config,
                variant_b_field_map: newMap
              })}
              onFallbackChange={(newFallback) => onUpdate(step.id, 'ab_test_config', {
                ...config,
                variant_b_fallback_values: newFallback
              })}
            />
          )}
        </div>
      </div>

      {/* Test Settings */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm font-medium mb-2">Winning Metric</label>
          <select
            value={config.winning_metric}
            onChange={(e) => onUpdate(step.id, 'ab_test_config', {
              ...config,
              winning_metric: e.target.value
            })}
            className="w-full p-2 border rounded"
          >
            <option value="open_rate">Open Rate</option>
            <option value="click_rate">Click Rate</option>
            <option value="conversion_rate">Conversion Rate</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Test Duration (hours)</label>
          <input
            type="number"
            min="1"
            value={config.test_duration_hours}
            onChange={(e) => onUpdate(step.id, 'ab_test_config', {
              ...config,
              test_duration_hours: parseInt(e.target.value) || 24
            })}
            className="w-full p-2 border rounded"
          />
        </div>
      </div>

      {/* Test Preview */}
      <div className="p-3 bg-white border border-gray-200 rounded">
        <h6 className="text-xs font-semibold mb-2">📊 Test Preview</h6>
        <div className="text-xs text-gray-600 space-y-1">
          <p>• {config.variant_a_percentage}% get: "{config.variant_a_subject || 'Subject A'}"</p>
          <p>• {config.variant_b_percentage}% get: "{config.variant_b_subject || 'Subject B'}"</p>
          <p>• Winner determined by: {config.winning_metric.replace('_', ' ')}</p>
          <p>• Test duration: {config.test_duration_hours} hours</p>
        </div>
      </div>
    </div>
  );
};

// ============================================
// WAIT FOR EVENT CONFIG
// ============================================
const WaitForEventConfig = ({ step, onUpdate }) => {
  const initWaitEvent = () => ({
    event_type: 'opened_email',
    max_wait_hours: 168,
    timeout_action: 'continue'
  });

  if (!step.wait_for_event) {
    onUpdate(step.id, 'wait_for_event', initWaitEvent());
  }

  return (
    <div className="space-y-3">
      <div>
        <label className="block text-sm font-medium mb-2">Event Type</label>
        <select
          value={step.wait_for_event?.event_type || 'opened_email'}
          onChange={(e) => onUpdate(step.id, 'wait_for_event', {
            ...step.wait_for_event,
            event_type: e.target.value
          })}
          className="w-full p-2 border rounded-lg"
        >
          <option value="opened_email">Email Opened</option>
          <option value="clicked_link">Link Clicked</option>
          <option value="made_purchase">Purchase Made</option>
          <option value="form_submitted">Form Submitted</option>
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium mb-2">Max Wait Time (Hours)</label>
        <input
          type="number"
          min="1"
          value={step.wait_for_event?.max_wait_hours || 168}
          onChange={(e) => onUpdate(step.id, 'wait_for_event', {
            ...step.wait_for_event,
            max_wait_hours: parseInt(e.target.value)
          })}
          className="w-full p-2 border rounded-lg"
        />
        <p className="text-xs text-gray-500 mt-1">Default: 168 hours (7 days)</p>
      </div>

      <div>
        <label className="block text-sm font-medium mb-2">Timeout Action</label>
        <select
          value={step.wait_for_event?.timeout_action || 'continue'}
          onChange={(e) => onUpdate(step.id, 'wait_for_event', {
            ...step.wait_for_event,
            timeout_action: e.target.value
          })}
          className="w-full p-2 border rounded-lg"
        >
          <option value="continue">Continue Workflow</option>
          <option value="exit">Exit Workflow</option>
          <option value="alternate_path">Take Alternate Path</option>
        </select>
      </div>
    </div>
  );
};

// ============================================
// WEBHOOK CONFIG
// ============================================
const WebhookConfig = ({ step, onUpdate }) => {
  return (
    <div className="space-y-3">
      <div>
        <label className="block text-sm font-medium mb-2">Webhook URL</label>
        <input
          type="url"
          value={step.webhook_url || ''}
          onChange={(e) => onUpdate(step.id, 'webhook_url', e.target.value)}
          className="w-full p-2 border rounded-lg"
          placeholder="https://your-app.com/webhook"
        />
      </div>

      <div>
        <label className="block text-sm font-medium mb-2">Payload (JSON)</label>
        <textarea
          value={JSON.stringify(step.webhook_payload || {}, null, 2)}
          onChange={(e) => {
            try {
              onUpdate(step.id, 'webhook_payload', JSON.parse(e.target.value));
            } catch (err) {
              // Invalid JSON, don't update
            }
          }}
          className="w-full p-2 border rounded-lg font-mono text-sm"
          rows="4"
          placeholder='{"event": "automation_step", "data": {}}'
        />
      </div>

      <div className="p-3 bg-green-50 border border-green-200 rounded text-sm">
        <Info size={14} className="inline mr-2 text-green-600" />
        Subscriber data will be automatically included in the webhook payload.
      </div>
    </div>
  );
};

// ============================================
// UPDATE FIELD CONFIG
// ============================================
const UpdateFieldConfig = ({ step, onUpdate }) => {
  const [fieldName, setFieldName] = useState('');
  const [fieldValue, setFieldValue] = useState('');

  const addField = () => {
    if (fieldName && fieldValue) {
      const updates = step.field_updates || {};
      updates[fieldName] = fieldValue;
      onUpdate(step.id, 'field_updates', updates);
      setFieldName('');
      setFieldValue('');
    }
  };

  const removeField = (key) => {
    const updates = { ...step.field_updates };
    delete updates[key];
    onUpdate(step.id, 'field_updates', updates);
  };

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <input
          type="text"
          value={fieldName}
          onChange={(e) => setFieldName(e.target.value)}
          className="p-2 border rounded-lg"
          placeholder="Field name"
        />
        <input
          type="text"
          value={fieldValue}
          onChange={(e) => setFieldValue(e.target.value)}
          className="p-2 border rounded-lg"
          placeholder="Field value"
        />
      </div>

      <button
        onClick={addField}
        className="w-full bg-indigo-600 text-white py-2 rounded-lg hover:bg-indigo-700 flex items-center justify-center gap-2"
      >
        <Plus size={16} />
        Add Field Update
      </button>

      {step.field_updates && Object.keys(step.field_updates).length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium">Fields to Update:</p>
          {Object.entries(step.field_updates).map(([key, value]) => (
            <div key={key} className="flex items-center justify-between p-2 bg-indigo-50 rounded border border-indigo-200">
              <span className="text-sm">
                <strong>{key}:</strong> {value}
              </span>
              <button
                onClick={() => removeField(key)}
                className="text-red-600 hover:text-red-700"
              >
                <X size={16} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ============================================
// FIELD MAPPING SECTION COMPONENT
// ============================================
const FieldMappingSection = ({ step, onUpdate, availableFields }) => {
  const dynamicFields = step.dynamic_fields || [];
  const fieldMap = step.field_map || {};
  const fallbackValues = step.fallback_values || {};

  // Use passed availableFields or fall back to defaults
  const fields = availableFields || {
    universal: ['email'],
    standard: ['first_name', 'last_name', 'phone', 'company', 'country', 'city', 'job_title'],
    custom: []
  };

  // Convert available fields from API format to dropdown format
  const fieldOptions = {
    universal: (fields.universal || ['email']).map(f => ({
      value: `universal.${f}`,
      label: `📧 ${f.charAt(0).toUpperCase() + f.slice(1).replace(/_/g, ' ')}`
    })),
    standard: (fields.standard || []).map(f => ({
      value: `standard.${f}`,
      label: `✨ ${f.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}`
    })),
    custom: (fields.custom || []).map(f => ({
      value: `custom.${f}`,
      label: `🔧 ${f.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}`
    }))
  };

  const handleFieldChange = (templateField, mapping) => {
    const newFieldMap = { ...fieldMap, [templateField]: mapping };
    onUpdate(step.id, 'field_map', newFieldMap);
  };

  const handleFallbackChange = (templateField, value) => {
    const newFallbackValues = { ...fallbackValues, [templateField]: value };
    onUpdate(step.id, 'fallback_values', newFallbackValues);
  };

  if (dynamicFields.length === 0) return null;

  return (
    <div className="mt-4 p-4 border-2 border-purple-200 rounded-lg bg-purple-50">
      <div className="flex items-center gap-2 mb-3">
        <Edit3 size={18} className="text-purple-600" />
        <h4 className="font-semibold text-purple-900">Field Mapping</h4>
      </div>

      <p className="text-sm text-purple-700 mb-4">
        Map template variables to subscriber data fields. Choose fallback values for missing data.
      </p>

      <div className="space-y-4">
        {dynamicFields.map(field => (
          <div key={field} className="p-3 bg-white rounded border border-purple-200">
            <label className="block font-medium text-gray-900 mb-2">
              {'{'}{field}{'}'}  <span className="text-red-500">*</span>
            </label>

            {/* Field Mapping Dropdown */}
            <div className="mb-2">
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Map to Subscriber Field:
              </label>
              <select
                value={fieldMap[field] || ''}
                onChange={(e) => handleFieldChange(field, e.target.value)}
                className={`w-full p-2 border rounded text-sm ${!fieldMap[field] ? 'border-red-300 bg-red-50' : 'border-gray-300'
                  }`}
              >
                <option value="">-- Select Field --</option>

                {/* Universal Fields */}
                <optgroup label="📋 Universal Fields">
                  {fieldOptions.universal.map(f => (
                    <option key={f.value} value={f.value}>{f.label}</option>
                  ))}
                </optgroup>

                {/* Standard Fields */}
                <optgroup label="✨ Standard Fields">
                  {fieldOptions.standard.map(f => (
                    <option key={f.value} value={f.value}>{f.label}</option>
                  ))}
                </optgroup>

                {/* Custom Fields */}
                <optgroup label="🔧 Custom Fields">
                  {fieldOptions.custom.map(f => (
                    <option key={f.value} value={f.value}>{f.label}</option>
                  ))}
                </optgroup>

                {/* Special Options */}
                <optgroup label="⚙️ Special">
                  <option value="__EMPTY__">Leave Empty</option>
                  <option value="__DEFAULT__">Use Fallback Value</option>
                </optgroup>
              </select>

              {!fieldMap[field] && (
                <p className="text-xs text-red-600 mt-1">⚠️ Please map this field</p>
              )}
            </div>

            {/* Fallback Value Input */}
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Fallback Value (if subscriber data is missing):
              </label>
              <input
                type="text"
                value={fallbackValues[field] || ''}
                onChange={(e) => handleFallbackChange(field, e.target.value)}
                className="w-full p-2 border border-gray-300 rounded text-sm"
                placeholder={`Default value for ${field}`}
              />
              <p className="text-xs text-gray-500 mt-1">
                Used when subscriber doesn't have this field
              </p>
            </div>

            {/* Field Mapping Preview */}
            {fieldMap[field] && (
              <div className="mt-2 p-2 bg-purple-100 rounded text-xs">
                <strong>Mapping:</strong> {'{'}{field}{'}'} → {fieldMap[field]}
                {fallbackValues[field] && (
                  <> | <strong>Fallback:</strong> "{fallbackValues[field]}"</>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Mapping Summary */}
      {Object.keys(fieldMap).length > 0 && (
        <div className="mt-4 p-3 bg-purple-100 border border-purple-300 rounded">
          <p className="text-xs font-semibold text-purple-900 mb-2">
            📊 Mapping Summary:
          </p>
          <div className="text-xs text-purple-800 space-y-1">
            {Object.entries(fieldMap).map(([field, mapping]) => (
              <div key={field} className="flex justify-between">
                <span className="font-medium">{field}:</span>
                <span className="text-purple-600">
                  {mapping === '__EMPTY__' ? 'Empty' :
                    mapping === '__DEFAULT__' ? 'Fallback' :
                      mapping}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

// ============================================
// A/B VARIANT FIELD MAPPING COMPONENT
// ============================================
const ABVariantFieldMapping = ({ variantLabel, dynamicFields, fieldMap, fallbackValues, onFieldMapChange, onFallbackChange, availableFields }) => {
  // Use passed availableFields or fall back to defaults
  const fields = availableFields || {
    universal: ['email'],
    standard: ['first_name', 'last_name', 'phone', 'company', 'country', 'city', 'job_title'],
    custom: []
  };

  // Convert to dropdown format
  const fieldOptions = {
    universal: (fields.universal || ['email']).map(f => ({
      value: `universal.${f}`,
      label: `📧 ${f.charAt(0).toUpperCase() + f.slice(1).replace(/_/g, ' ')}`
    })),
    standard: (fields.standard || []).map(f => ({
      value: `standard.${f}`,
      label: `✨ ${f.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}`
    })),
    custom: (fields.custom || []).map(f => ({
      value: `custom.${f}`,
      label: `🔧 ${f.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}`
    }))
  };

  const handleFieldChange = (templateField, mapping) => {
    const newFieldMap = { ...fieldMap, [templateField]: mapping };
    onFieldMapChange(newFieldMap);
  };

  const handleFallbackChange = (templateField, value) => {
    const newFallbackValues = { ...fallbackValues, [templateField]: value };
    onFallbackChange(newFallbackValues);
  };

  if (dynamicFields.length === 0) return null;

  const borderColor = variantLabel === 'A' ? 'border-blue-200' : 'border-purple-200';
  const bgColor = variantLabel === 'A' ? 'bg-blue-50' : 'bg-purple-50';
  const textColor = variantLabel === 'A' ? 'text-blue-900' : 'text-purple-900';

  return (
    <div className={`mt-3 p-3 border ${borderColor} rounded ${bgColor}`}>
      <div className="flex items-center gap-2 mb-2">
        <Edit3 size={16} className={textColor} />
        <h6 className={`font-semibold text-sm ${textColor}`}>
          Field Mapping for Variant {variantLabel}
        </h6>
      </div>

      <p className="text-xs text-gray-700 mb-3">
        Map template variables to subscriber data
      </p>

      <div className="space-y-3">
        {dynamicFields.map(field => (
          <div key={field} className="p-2 bg-white rounded border border-gray-200">
            <label className="block font-medium text-xs text-gray-900 mb-1">
              {'{'}{field}{'}'}
            </label>

            <select
              value={fieldMap[field] || ''}
              onChange={(e) => handleFieldChange(field, e.target.value)}
              className="w-full p-1.5 border rounded text-xs mb-1"
            >
              <option value="">-- Select Field --</option>
              <optgroup label="📋 Universal">
                {fieldOptions.universal.map(f => (
                  <option key={f.value} value={f.value}>{f.label}</option>
                ))}
              </optgroup>
              <optgroup label="✨ Standard">
                {fieldOptions.standard.map(f => (
                  <option key={f.value} value={f.value}>{f.label}</option>
                ))}
              </optgroup>
              <optgroup label="🔧 Custom">
                {fieldOptions.custom.map(f => (
                  <option key={f.value} value={f.value}>{f.label}</option>
                ))}
              </optgroup>
              <optgroup label="⚙️ Special">
                <option value="__EMPTY__">Leave Empty</option>
                <option value="__DEFAULT__">Use Fallback</option>
              </optgroup>
            </select>

            <input
              type="text"
              value={fallbackValues[field] || ''}
              onChange={(e) => handleFallbackChange(field, e.target.value)}
              className="w-full p-1.5 border rounded text-xs"
              placeholder="Fallback value"
            />
          </div>
        ))}
      </div>
    </div>
  );
};

export default AutomationBuilder;
