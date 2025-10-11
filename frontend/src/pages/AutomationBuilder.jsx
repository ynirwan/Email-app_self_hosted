// src/pages/AutomationBuilder.jsx
import React, { useState, useEffect } from 'react';
import { Save, Plus, Trash2, ArrowDown, Users, Target } from 'lucide-react';
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
  const [automationLoading, setAutomationLoading] = useState(false); // ✅ Separate loading state
  const [error, setError] = useState(null);

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
      
      console.log('📧 Templates received:', templatesRes);
      console.log('🎯 Segments received:', segmentsRes);
      
      const actualTemplates = templatesRes?.data || templatesRes;
      const actualSegments = segmentsRes?.data || segmentsRes;
      
      setTemplates(Array.isArray(actualTemplates) ? actualTemplates : []);
      setSegments(Array.isArray(actualSegments) ? actualSegments : []);
      
      console.log(`✅ Templates loaded: ${Array.isArray(actualTemplates) ? actualTemplates.length : 0}`);
      console.log(`✅ Segments loaded: ${Array.isArray(actualSegments) ? actualSegments.length : 0}`);
      
    } catch (error) {
      console.error('❌ Failed to fetch templates/segments:', error);
      setError(`Failed to load data: ${error.message}`);
      setTemplates([]);
      setSegments([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchAutomation = async () => {
    try {
      setAutomationLoading(true); // ✅ Use separate loading state
      console.log('🔄 Fetching automation with ID:', id);
      
      const res = await API.get(`/automation/rules/${id}`);
      console.log('📥 Raw API response:', res);
      console.log('📧 Steps in response:', res.steps);
      console.log('🎯 Target segments in response:', res.target_segments);
      
      // ✅ Handle different response formats
      const actualData = res?.data || res;
      setWorkflow(actualData);
      
      console.log('✅ Workflow state should be updated now');
      
    } catch (error) {
      console.error('❌ Failed to fetch automation rule:', error);
      setError('Failed to load automation rule');
    } finally {
      setAutomationLoading(false); // ✅ Clear automation loading
    }
  };

  // ✅ Monitor workflow updates
  useEffect(() => {
    console.log('🔧 Workflow state updated:', workflow);
    console.log('🔧 Steps count:', workflow.steps?.length || 0);
    console.log('🔧 Target segments count:', workflow.target_segments?.length || 0);
  }, [workflow]);

  // Safe array variables
  const safeSteps = Array.isArray(workflow.steps) ? workflow.steps : [];
  const safeTargetSegments = Array.isArray(workflow.target_segments) ? workflow.target_segments : [];
  const safeTemplates = Array.isArray(templates) ? templates : [];
  const safeSegments = Array.isArray(segments) ? segments : [];

  console.log('🛡️ Safe steps:', safeSteps);
  console.log('🛡️ Safe target segments:', safeTargetSegments);

  const addEmailStep = () => {
    const newStep = {
      id: Date.now().toString(),
      template_id: '',
      delay_value: 1,
      delay_type: 'hours'
    };
    setWorkflow(prev => ({
      ...prev,
      steps: [...safeSteps, newStep]
    }));
  };

  const removeEmailStep = (stepId) => {
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
    setLoading(true);
    try {
      console.log('💾 Saving workflow:', workflow);
      
      if (isEditing) {
        await API.put(`/automation/rules/${id}`, workflow);
      } else {
        await API.post('/automation/rules', workflow);
      }
      
      console.log('✅ Automation saved successfully');
      navigate('/automation');
      
    } catch (error) {
      console.error('❌ Failed to save automation:', error);
      setError(`Failed to save automation: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  // ✅ FIXED: Better loading logic
  if (loading || automationLoading) {
    return (
      <div className="p-6 text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
        {loading ? 'Loading templates and segments...' : 'Loading automation data...'}
      </div>
    );
  }

  // ✅ Don't render main content if editing but no workflow data loaded yet
  if (isEditing && !workflow.id) {
    return (
      <div className="p-6 text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
        Waiting for automation data...
      </div>
    );
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* Error Display */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6">
          <div className="flex">
            <div className="flex-shrink-0">❌</div>
            <div className="ml-3">
              <h3 className="text-sm font-medium">Error</h3>
              <p className="text-sm mt-1">{error}</p>
              <button
                onClick={fetchTemplatesAndSegments}
                className="mt-2 text-sm bg-red-100 hover:bg-red-200 px-3 py-1 rounded"
              >
                Retry
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Enhanced Debug Info */}
      <div className="bg-blue-50 border border-blue-200 p-4 rounded-lg mb-6 text-sm">
        <h4 className="font-medium mb-2">🔍 Debug Info:</h4>
        <p>Templates loaded: {safeTemplates.length}</p>
        <p>Segments loaded: {safeSegments.length}</p>
        <p>Workflow ID: {workflow.id || 'Not loaded'}</p>
        <p>Workflow name: "{workflow.name}"</p>
        <p>Workflow steps: {safeSteps.length}</p>
        <p>Target segments: {safeTargetSegments.length}</p>
        <p>Loading: {loading ? 'Yes' : 'No'}</p>
        <p>Automation Loading: {automationLoading ? 'Yes' : 'No'}</p>
        <p>Is Editing: {isEditing ? 'Yes' : 'No'}</p>
        
        {/* Show raw data for debugging */}
        {safeSteps.length > 0 && (
          <details className="mt-2">
            <summary className="cursor-pointer text-blue-600">📧 View Steps Data</summary>
            <pre className="text-xs bg-gray-100 p-2 rounded mt-1 overflow-auto max-h-40">
              {JSON.stringify(safeSteps, null, 2)}
            </pre>
          </details>
        )}
        
        {safeTargetSegments.length > 0 && (
          <details className="mt-2">
            <summary className="cursor-pointer text-blue-600">🎯 View Target Segments</summary>
            <pre className="text-xs bg-gray-100 p-2 rounded mt-1">
              {JSON.stringify(safeTargetSegments, null, 2)}
            </pre>
          </details>
        )}
      </div>

      {/* Header */}
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold">{isEditing ? 'Edit' : 'Create'} Email Automation</h1>
        <div className="flex gap-3">
          <button
            onClick={() => navigate('/automation')}
            className="bg-gray-200 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-300"
          >
            Cancel
          </button>
          <button
            onClick={saveWorkflow}
            disabled={loading || automationLoading}
            className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            <Save size={20} className="inline mr-2" />
            {loading || automationLoading ? 'Saving...' : (isEditing ? 'Update' : 'Save')} Automation
          </button>
        </div>
      </div>

      {/* Basic Settings */}
      <div className="bg-white rounded-lg shadow-sm border p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Basic Settings</h2>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          <div>
            <label className="block text-sm font-medium mb-2">Name</label>
            <input
              type="text"
              value={workflow.name}
              onChange={(e) => setWorkflow(prev => ({...prev, name: e.target.value}))}
              className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
              placeholder="Welcome Series"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium mb-2">Trigger Event</label>
            <select
              value={workflow.trigger}
              onChange={(e) => setWorkflow(prev => ({...prev, trigger: e.target.value}))}
              className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              <option value="welcome">New Subscriber</option>
              <option value="birthday">Birthday</option>
              <option value="abandoned_cart">Abandoned Cart</option>
              <option value="purchase">After Purchase</option>
            </select>
          </div>
        </div>

        {/* Target Segments */}
        <div className="border-t pt-6">
          <h3 className="text-lg font-medium mb-3 flex items-center gap-2">
            <Target className="text-blue-600" size={20} />
            Target Audience (Optional)
          </h3>
          <p className="text-sm text-gray-600 mb-4">
            Choose which segments should receive this automation. Leave empty to target all active subscribers.
          </p>
          
          {safeSegments.length === 0 ? (
            <div className="p-6 border-2 border-dashed border-gray-300 rounded-lg text-center">
              <Users className="mx-auto text-gray-300 mb-2" size={32} />
              <p className="text-gray-500 mb-1">No segments available</p>
              <p className="text-sm text-gray-400">Create segments first to target specific audiences</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {safeSegments.map((segment) => (
                <label
                  key={segment.id}
                  className="flex items-start space-x-3 p-4 border rounded-lg cursor-pointer hover:bg-blue-50 hover:border-blue-300 transition-colors"
                >
                  <input
                    type="checkbox"
                    checked={safeTargetSegments.includes(segment.id)}
                    onChange={() => toggleTargetSegment(segment.id)}
                    className="mt-1 rounded text-blue-600 focus:ring-blue-500"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-gray-900">{segment.name}</div>
                    <div className="text-sm text-gray-500">
                      {segment.subscriber_count || 0} subscribers
                    </div>
                    {segment.description && (
                      <div className="text-xs text-gray-400 mt-1">{segment.description}</div>
                    )}
                  </div>
                </label>
              ))}
            </div>
          )}
          
          {safeTargetSegments.length > 0 && (
            <div className="mt-4 p-3 bg-blue-100 border border-blue-200 rounded text-sm">
              <strong>🎯 Selected:</strong> {safeTargetSegments.length} segment(s). 
              This automation will only target subscribers in these segments.
            </div>
          )}
        </div>
      </div>

      {/* Email Steps - Enhanced Debug */}
      <div className="bg-white rounded-lg shadow-sm border p-6">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-semibold">
            Email Sequence ({safeSteps.length} steps found)
          </h2>
          <button
            onClick={addEmailStep}
            className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 flex items-center gap-2"
          >
            <Plus size={16} />
            Add Email
          </button>
        </div>

        {safeSteps.length === 0 ? (
          <div className="text-center py-12 text-gray-500 border-2 border-dashed border-gray-300 rounded-lg">
            <div className="text-4xl mb-4">📧</div>
            <p className="text-lg mb-2">No emails in sequence yet</p>
            <p className="text-sm mb-4">Click "Add Email" to start building your automation workflow</p>
            
            {/* Enhanced debug info */}
            <div className="text-xs text-red-600 mt-4 p-2 bg-red-50 rounded">
              <p>Debug: workflow.steps = {JSON.stringify(workflow.steps)}</p>
              <p>Debug: safeSteps = {JSON.stringify(safeSteps)}</p>
              <p>Debug: workflow.id = {workflow.id}</p>
            </div>
          </div>
        ) : (
          <div>
            <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded text-sm text-green-700">
              ✅ Found {safeSteps.length} email step(s) in this automation!
            </div>
            
            {safeSteps.map((step, index) => (
              <div key={step.id} className="mb-6">
                <div className="bg-gray-50 rounded-lg p-6 border-l-4 border-blue-500">
                  <div className="flex justify-between items-center mb-4">
                    <h3 className="font-medium text-lg">📧 Email {index + 1}</h3>
                    <button
                      onClick={() => removeEmailStep(step.id)}
                      className="text-red-600 hover:text-red-900 p-2 hover:bg-red-50 rounded"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Template Selection */}
                    <div>
                      <label className="block text-sm font-medium mb-2">
                        📄 Email Template ({safeTemplates.length} available)
                      </label>
                      
                      {safeTemplates.length === 0 ? (
                        <div className="p-3 border-2 border-dashed border-gray-300 rounded-lg text-center text-gray-500">
                          No templates available
                        </div>
                      ) : (
                        <select
                          value={step.template_id}
                          onChange={(e) => updateEmailStep(step.id, 'template_id', e.target.value)}
                          className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
                        >
                          <option value="">Select template...</option>
                          {safeTemplates.map((template) => (
                            <option key={template.id} value={template.id}>
                              {template.name} - {template.subject}
                            </option>
                          ))}
                        </select>
                      )}
                    </div>

                    {/* Delay Settings */}
                    <div>
                      <label className="block text-sm font-medium mb-2">⏰ Send After</label>
                      <div className="flex gap-2">
                        <input
                          type="number"
                          min="0"
                          value={step.delay_value}
                          onChange={(e) => updateEmailStep(step.id, 'delay_value', parseInt(e.target.value) || 0)}
                          className="flex-1 p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
                        />
                        <select
                          value={step.delay_type}
                          onChange={(e) => updateEmailStep(step.id, 'delay_type', e.target.value)}
                          className="p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
                        >
                          <option value="hours">Hours</option>
                          <option value="days">Days</option>
                          <option value="weeks">Weeks</option>
                        </select>
                      </div>
                    </div>
                  </div>
                </div>

                {index < safeSteps.length - 1 && (
                  <div className="flex justify-center py-3">
                    <div className="flex items-center text-gray-400">
                      <ArrowDown size={20} />
                      <span className="ml-2 text-sm">Then send</span>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default AutomationBuilder;

