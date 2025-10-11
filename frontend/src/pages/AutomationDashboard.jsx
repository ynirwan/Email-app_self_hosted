// src/pages/AutomationDashboard.jsx
import React, { useState, useEffect } from 'react';
import { Plus, Play, Pause, BarChart3, Mail, Users, Trash2, Edit, TrendingUp } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import API from '../api';

const AutomationDashboard = () => {
  const navigate = useNavigate();
  const [automations, setAutomations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // ✅ FIXED: Always fetch fresh data when component mounts
  useEffect(() => {
    console.log('🏠 AutomationDashboard mounted, fetching automations...');
    fetchAutomations();
  }, []); // This ensures fresh data every time you navigate to dashboard

  const fetchAutomations = async () => {
    try {
      setLoading(true);
      setError(null);
      console.log('🔄 Fetching automations from dashboard...');
      
      const data = await API.get('/automation/rules');
      console.log('📋 Raw automations response:', data);
      
      // Handle different response formats
      let actualAutomations = [];
      if (Array.isArray(data)) {
        actualAutomations = data;
      } else if (data?.data && Array.isArray(data.data)) {
        actualAutomations = data.data;
      } else {
        console.warn('⚠️ Unexpected response format:', data);
        actualAutomations = [];
      }
      
      setAutomations(actualAutomations);
      console.log(`✅ Loaded ${actualAutomations.length} automations in dashboard`);
      
    } catch (error) {
      setError('Failed to fetch automations');
      console.error('❌ Failed to fetch automations:', error);
      setAutomations([]);
    } finally {
      setLoading(false);
    }
  };

  const toggleAutomation = async (id, currentStatus) => {
    const newStatus = currentStatus === 'active' ? 'paused' : 'active';
    try {
      console.log(`🔄 Toggling automation ${id} from ${currentStatus} to ${newStatus}`);
      await API.put(`/automation/rules/${id}/status`, { status: newStatus });
      await fetchAutomations(); // Refresh list after update
      console.log('✅ Automation status updated successfully');
    } catch (error) {
      console.error('❌ Failed to toggle automation:', error);
      setError('Failed to update automation status');
    }
  };

  const deleteAutomation = async (id) => {
    if (!window.confirm('Are you sure you want to delete this automation?')) return;
    
    try {
      console.log(`🗑️ Deleting automation ${id}`);
      await API.delete(`/automation/rules/${id}`);
      await fetchAutomations(); // Refresh list after delete
      console.log('✅ Automation deleted successfully');
    } catch (error) {
      console.error('❌ Failed to delete automation:', error);
      setError('Failed to delete automation');
    }
  };

  const safeAutomations = Array.isArray(automations) ? automations : [];

  if (loading) {
    return (
      <div className="flex justify-center p-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <span className="ml-2">Loading automations...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-red-600 p-4 text-center">
        <p>{error}</p>
        <button 
          onClick={fetchAutomations}
          className="mt-2 bg-red-100 hover:bg-red-200 px-4 py-2 rounded"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Debug Info */}
      <div className="bg-green-50 border border-green-200 p-4 rounded-lg mb-6 text-sm">
        <h4 className="font-medium mb-2">🔍 Dashboard Debug Info:</h4>
        <p>Automations loaded: {safeAutomations.length}</p>
        <p>Loading: {loading ? 'Yes' : 'No'}</p>
        <p>Last refresh: {new Date().toLocaleTimeString()}</p>
      </div>

      {/* Header */}
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Email Automation</h1>
          <p className="text-gray-600 mt-1">Automate your email workflows and engage subscribers</p>
        </div>
        <button 
          onClick={() => navigate('/automation/create')}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg flex items-center gap-2 hover:bg-blue-700 transition-colors"
        >
          <Plus size={20} />
          Create Automation
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded-lg">
              <Mail className="text-blue-600" size={24} />
            </div>
            <div>
              <p className="text-gray-600 text-sm">Active Automations</p>
              <p className="text-2xl font-bold">
                {safeAutomations.filter(a => a.status === 'active').length}
              </p>
            </div>
          </div>
        </div>
        
        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-100 rounded-lg">
              <Users className="text-green-600" size={24} />
            </div>
            <div>
              <p className="text-gray-600 text-sm">Total Emails Sent</p>
              <p className="text-2xl font-bold">
                {safeAutomations.reduce((sum, a) => sum + (a.emails_sent || 0), 0).toLocaleString()}
              </p>
            </div>
          </div>
        </div>
        
        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-100 rounded-lg">
              <TrendingUp className="text-purple-600" size={24} />
            </div>
            <div>
              <p className="text-gray-600 text-sm">Avg Open Rate</p>
              <p className="text-2xl font-bold">
                {safeAutomations.length > 0 ? 
                  (safeAutomations.reduce((sum, a) => sum + (a.open_rate || 0), 0) / safeAutomations.length).toFixed(1) : 
                  '0.0'
                }%
              </p>
            </div>
          </div>
        </div>
        
        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-orange-100 rounded-lg">
              <BarChart3 className="text-orange-600" size={24} />
            </div>
            <div>
              <p className="text-gray-600 text-sm">Avg Click Rate</p>
              <p className="text-2xl font-bold">
                {safeAutomations.length > 0 ? 
                  (safeAutomations.reduce((sum, a) => sum + (a.click_rate || 0), 0) / safeAutomations.length).toFixed(1) : 
                  '0.0'
                }%
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Automations Table */}
      <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
          <h2 className="text-lg font-semibold text-gray-900">Your Automations</h2>
          <button 
            onClick={fetchAutomations}
            className="text-sm bg-gray-100 hover:bg-gray-200 px-3 py-1 rounded"
          >
            🔄 Refresh
          </button>
        </div>
        
        {safeAutomations.length === 0 ? (
          <div className="text-center py-12">
            <Mail size={48} className="mx-auto text-gray-300 mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No automations yet</h3>
            <p className="text-gray-600 mb-6">Create your first email automation to engage subscribers automatically</p>
            <button 
              onClick={() => navigate('/automation/create')}
              className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700"
            >
              Create Your First Automation
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Trigger</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Emails Sent</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Performance</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {safeAutomations.map((automation) => (
                  <tr key={automation.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4">
                      <div className="font-medium text-gray-900">{automation.name}</div>
                      <div className="text-sm text-gray-500">
                        Created {new Date(automation.created_at).toLocaleDateString()}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className="capitalize text-sm text-gray-900">
                        {automation.trigger?.replace('_', ' ') || 'Unknown'}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-3 py-1 text-xs rounded-full font-medium ${
                        automation.status === 'active' ? 'bg-green-100 text-green-800' :
                        automation.status === 'paused' ? 'bg-yellow-100 text-yellow-800' :
                        'bg-gray-100 text-gray-800'
                      }`}>
                        {automation.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">
                      {(automation.emails_sent || 0).toLocaleString()}
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-sm">
                        <div className="text-gray-900">{(automation.open_rate || 0).toFixed(1)}% opens</div>
                        <div className="text-gray-500">{(automation.click_rate || 0).toFixed(1)}% clicks</div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <button
                          onClick={() => toggleAutomation(automation.id, automation.status)}
                          className="text-blue-600 hover:text-blue-900"
                          title={automation.status === 'active' ? 'Pause' : 'Activate'}
                        >
                          {automation.status === 'active' ? <Pause size={16} /> : <Play size={16} />}
                        </button>
                        <button
                          onClick={() => navigate(`/automation/edit/${automation.id}`)}
                          className="text-gray-600 hover:text-gray-900"
                          title="Edit"
                        >
                          <Edit size={16} />
                        </button>
                        <button
                          onClick={() => navigate(`/automation/analytics/${automation.id}`)}
                          className="text-purple-600 hover:text-purple-900"
                          title="Analytics"
                        >
                          <BarChart3 size={16} />
                        </button>
                        <button
                          onClick={() => deleteAutomation(automation.id)}
                          className="text-red-600 hover:text-red-900"
                          title="Delete"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default AutomationDashboard;

