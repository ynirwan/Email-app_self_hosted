// src/pages/AutomationBuilder.jsx - COMPLETE FIXED VERSION
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


  // ✅ SINGLE workflow state declaration
  const [workflow, setWorkflow] = useState({
    name: '',
    trigger: 'welcome',
    trigger_conditions: {},
    target_segments: [],
    target_lists: [],
    steps: [],
    active: false,

    // ⭐ NEW FIELDS FROM PHASE 1-3
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
    
    // ⭐ FIX: Email config with required fields
    email_config: {
      sender_email: 'noreply@yourdomain.com',
      sender_name: 'Your Company',
      reply_to: ''
    }
  });


  const [templates, setTemplates] = useState([]);
  const [segments, setSegments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [validationErrors, setValidationErrors] = useState([]);


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

      // ⭐ Ensure email_config exists when loading
      if (!actualData.email_config) {
        actualData.email_config = {
          sender_email: 'noreply@yourdomain.com',
          sender_name: 'Your Company',
          reply_to: ''
        };
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


  // ⭐ UPDATED: Validation with email config check
  const validateWorkflow = () => {
    const errors = [];

    if (!workflow.name || workflow.name.trim() === '') {
      errors.push('Automation name is required');
    }

    if (!workflow.trigger) {
      errors.push('Trigger event is required');
    }

    // ⭐ Validate email config
    if (!workflow.email_config?.sender_email || workflow.email_config.sender_email.trim() === '') {
      errors.push('Sender email is required');
    }

    if (!workflow.email_config?.sender_name || workflow.email_config.sender_name.trim() === '') {
      errors.push('Sender name is required');
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
      
      // ⭐ Better error message extraction
      let errorMessage = 'Failed to save automation';
      
      if (error.response?.data?.detail) {
        if (typeof error.response.data.detail === 'string') {
          errorMessage = error.response.data.detail;
        } else if (Array.isArray(error.response.data.detail)) {
          // Handle validation errors array
          errorMessage = error.response.data.detail
            .map(err => err.msg || JSON.stringify(err))
            .join(', ');
        }
      } else if (error.response?.data?.message) {
        errorMessage = error.response.data.message;
      } else if (error.message) {
        errorMessage = error.message;
      }
      
      setError(errorMessage);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } finally {
      setSaving(false);
    }
  };


  // Get template name for display
  const getTemplateName = (templateId) => {
    const template = safeTemplates.find(t => (t.id || t._id) === templateId);
    return template ? `${template.name} - ${template.subject || ''}` : 'Select template...';
  };


  // Calculate estimated timeline
  const calculateTimeline = () => {
    let totalHours = 0;
    safeSteps.forEach(step => {
      const hours = step.delay_type === 'hours' ? step.delay_value :
        step.delay_type === 'days' ? step.delay_value * 24 :
          step.delay_type === 'weeks' ? step.delay_value * 168 : 0;
      totalHours += hours;
    });

    if (totalHours < 24) {
      return `${totalHours} hours`;
    } else if (totalHours < 168) {
      return `${Math.floor(totalHours / 24)} days`;
    } else {
      return `${Math.floor(totalHours / 168)} weeks`;
    }
  };


  return (
    <div className="max-w-6xl mx-auto p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-3">
            <Zap className="text-blue-600" size={32} />
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


      {/* Error/Success Messages */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6 flex items-center gap-2">
          <AlertCircle size={20} />
          <div className="flex-1">{error}</div>
        </div>
      )}


      {success && (
        <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg mb-6 flex items-center gap-2">
          <CheckCircle size={20} />
          {success}
        </div>
      )}


      {/* Validation Errors */}
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


        {/* ⭐ Email Configuration Section */}
        <div className="border-t pt-6 mb-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Mail className="text-blue-600" size={20} />
            Email Configuration
          </h3>


          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
              <p className="text-xs text-gray-500 mt-1">Email address that will send the automation emails</p>
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
              <p className="text-xs text-gray-500 mt-1">Name that will appear in the "From" field</p>
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
              <p className="text-xs text-gray-500 mt-1">Email address for replies (optional)</p>
            </div>
          </div>
        </div>


        {/* Scheduling & Timing */}
        <div className="border-t pt-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Clock className="text-blue-600" size={20} />
            Scheduling & Timing
          </h3>


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
          <div className="text-center py-8 border-2 border-dashed border-gray-300 rounded-lg bg-gray-50">
            <Users className="mx-auto text-gray-400 mb-2" size={48} />
            <p className="text-gray-600">No segments available yet.</p>
            <p className="text-sm text-gray-500 mt-1">Create segments first to target specific audiences.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {safeSegments.map(segment => (
              <label
                key={segment.id || segment._id}
                className="flex items-center space-x-3 p-3 border rounded-lg hover:bg-gray-50 cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={safeTargetSegments.includes(segment.id || segment._id)}
                  onChange={() => toggleTargetSegment(segment.id || segment._id)}
                  className="w-5 h-5 rounded text-blue-600"
                />
                <div className="flex-1">
                  <div className="font-medium text-gray-900">{segment.name}</div>
                  <div className="text-sm text-gray-600">{segment.description || 'No description'}</div>
                </div>
                <div className="text-sm text-gray-500">
                  {segment.subscriber_count || 0} subscribers
                </div>
              </label>
            ))}
          </div>
        )}
      </div>


      {/* Email Steps */}
      <div className="bg-white rounded-lg shadow-sm border p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <Mail className="text-green-600" size={22} />
              Email Sequence
            </h2>
            <p className="text-sm text-gray-600 mt-1">
              Add emails to create your automation workflow
            </p>
          </div>
          <button
            onClick={addEmailStep}
            disabled={safeTemplates.length === 0}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <Plus size={20} />
            Add Email
          </button>
        </div>


        {safeTemplates.length === 0 && (
          <div className="bg-yellow-50 border border-yellow-200 text-yellow-700 px-4 py-3 rounded-lg mb-4">
            <p>⚠️ No templates available. Create email templates first before building automations.</p>
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
                        className="text-red-600 hover:text-red-800 hover:bg-red-50 p-2 rounded"
                        title="Remove this step"
                      >
                        <Trash2 size={20} />
                      </button>
                    </div>


                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      {/* Template Selection */}
                      <div className="md:col-span-2">
                        <label className="block text-sm font-medium mb-2">
                          Email Template <span className="text-red-500">*</span>
                        </label>
                        <select
                          value={step.template_id}
                          onChange={(e) => updateEmailStep(step.id, 'template_id', e.target.value)}
                          className="w-full p-2 border rounded focus:ring-2 focus:ring-blue-500"
                        >
                          <option value="">Select template...</option>
                          {safeTemplates.map(template => (
                            <option key={template.id || template._id} value={template.id || template._id}>
                              {template.name} {template.subject ? `- ${template.subject}` : ''}
                            </option>
                          ))}
                        </select>
                      </div>


                      {/* Delay */}
                      {index > 0 && (
                        <>
                          <div>
                            <label className="block text-sm font-medium mb-2">Delay Value</label>
                            <input
                              type="number"
                              min="0"
                              value={step.delay_value}
                              onChange={(e) => updateEmailStep(step.id, 'delay_value', parseInt(e.target.value) || 0)}
                              className="w-full p-2 border rounded focus:ring-2 focus:ring-blue-500"
                            />
                          </div>
                          <div className="md:col-span-2">
                            <label className="block text-sm font-medium mb-2">Delay Unit</label>
                            <select
                              value={step.delay_type}
                              onChange={(e) => updateEmailStep(step.id, 'delay_type', e.target.value)}
                              className="w-full p-2 border rounded focus:ring-2 focus:ring-blue-500"
                            >
                              <option value="hours">Hours</option>
                              <option value="days">Days</option>
                              <option value="weeks">Weeks</option>
                            </select>
                          </div>
                        </>
                      )}
                    </div>


                    {/* Delay Info */}
                    {index > 0 && (
                      <p className="text-xs text-gray-500 mt-2">
                        ⏱️ This email will be sent {step.delay_value} {step.delay_type} after the previous email
                      </p>
                    )}
                  </div>
                </div>


                {/* Arrow between steps */}
                {index < safeSteps.length - 1 && (
                  <div className="flex justify-center my-2">
                    <ArrowDown className="text-gray-400" size={24} />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>


      {/* Test Mode Warning */}
      {workflow.active && (
        <div className="bg-blue-50 border border-blue-200 text-blue-700 px-4 py-3 rounded-lg mb-6">
          <p className="font-medium">⚡ Active Automation</p>
          <p className="text-sm mt-1">
            This automation will start processing immediately for matching subscribers.
            Consider starting with a small segment to verify everything works correctly.
          </p>
        </div>
      )}


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
