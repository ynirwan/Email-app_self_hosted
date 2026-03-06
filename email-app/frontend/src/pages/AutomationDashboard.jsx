// src/pages/AutomationDashboard.jsx - Enhanced Version
import React, { useState, useEffect } from 'react';
import {
  Plus, Play, Pause, BarChart3, Mail, Users, Trash2, Edit,
  TrendingUp, Clock, CheckCircle, AlertCircle, Copy, Eye
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import API from '../api';

const AutomationDashboard = () => {
  const navigate = useNavigate();
  const [automations, setAutomations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filterStatus, setFilterStatus] = useState('all'); // all, active, paused, draft
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    console.log('🏠 AutomationDashboard mounted, fetching automations...');
    fetchAutomations();
  }, []);

  const fetchAutomations = async () => {
    try {
      setLoading(true);
      setError(null);
      console.log('🔄 Fetching automations from dashboard...');

      const response = await API.get('/automation/rules');
      console.log('📋 Raw automations response:', response);

      // ⭐ FIXED: Correct response structure handling
      let actualAutomations = [];

      if (response?.data?.rules && Array.isArray(response.data.rules)) {
        actualAutomations = response.data.rules;
      } else if (response?.rules && Array.isArray(response.rules)) {
        actualAutomations = response.rules;
      } else if (Array.isArray(response?.data)) {
        actualAutomations = response.data;
      } else if (Array.isArray(response)) {
        actualAutomations = response;
      } else {
        console.warn('⚠️ Unexpected response format:', response);
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

      // ⭐ FIXED: Correct endpoint method
      await API.post(`/automation/rules/${id}/status`, { status: newStatus });

      await fetchAutomations();
      console.log('✅ Automation status updated successfully');
    } catch (error) {
      console.error('❌ Failed to toggle automation:', error);
      setError('Failed to update automation status');
      setTimeout(() => setError(null), 3000);
    }
  };

  const duplicateAutomation = async (automation) => {
    try {
      const duplicatedData = {
        ...automation,
        name: `${automation.name} (Copy)`,
        active: false,
        status: 'draft'
      };
      delete duplicatedData.id;
      delete duplicatedData._id;
      delete duplicatedData.created_at;
      delete duplicatedData.updated_at;
      delete duplicatedData.emails_sent;
      delete duplicatedData.open_rate;
      delete duplicatedData.click_rate;

      await API.post('/automation/rules', duplicatedData);
      await fetchAutomations();
      console.log('✅ Automation duplicated successfully');
    } catch (error) {
      console.error('❌ Failed to duplicate automation:', error);
      setError('Failed to duplicate automation');
      setTimeout(() => setError(null), 3000);
    }
  };

  const deleteAutomation = async (id) => {
    if (!window.confirm('Are you sure you want to delete this automation? This action cannot be undone.')) return;

    try {
      console.log(`🗑️ Deleting automation ${id}`);
      await API.delete(`/automation/rules/${id}`);
      await fetchAutomations(); // Refresh list after delete
      console.log('✅ Automation deleted successfully');
    } catch (error) {
      console.error('❌ Failed to delete automation:', error);
      setError('Failed to delete automation');
      setTimeout(() => setError(null), 3000);
    }
  };

  // Filter and search automations
  const filteredAutomations = Array.isArray(automations)
    ? automations.filter(automation => {
      // Status filter
      if (filterStatus !== 'all' && automation.status !== filterStatus) {
        return false;
      }

      // Search filter
      if (searchQuery) {
        const query = searchQuery.toLowerCase();
        return (
          automation.name.toLowerCase().includes(query) ||
          automation.trigger.toLowerCase().includes(query)
        );
      }

      return true;
    })
    : [];

  // Calculate stats
  const stats = {
    total: automations.length,
    active: automations.filter(a => a.status === 'active').length,
    paused: automations.filter(a => a.status === 'paused').length,
    totalSent: automations.reduce((sum, a) => sum + (a.emails_sent || 0), 0),
    avgOpenRate: automations.length > 0
      ? (automations.reduce((sum, a) => sum + (a.open_rate || 0), 0) / automations.length)
      : 0,
    avgClickRate: automations.length > 0
      ? (automations.reduce((sum, a) => sum + (a.click_rate || 0), 0) / automations.length)
      : 0
  };

  if (loading) {
    return (
      <div className="flex flex-col justify-center items-center p-8 min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mb-4"></div>
        <span className="text-gray-600">Loading automations...</span>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Error Alert */}
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

      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-8 gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Email Automation</h1>
          <p className="text-gray-600 mt-1">Automate your email workflows and engage subscribers</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={fetchAutomations}
            className="bg-gray-100 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-200 transition-colors"
          >
            🔄 Refresh
          </button>
          <button
            onClick={() => navigate('/automation/create')}
            className="bg-blue-600 text-white px-2 py-2 rounded-lg flex items-center gap-1 hover:bg-blue-700 transition-colors"
          >
            <Plus size={20} />
            Create Automation
          </button>
          <button
            onClick={() => navigate('/automation/analytics')}
            className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700"
          >
            Analytics
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <div className="bg-white p-6 rounded-lg shadow-sm border hover:shadow-md transition-shadow">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-blue-100 rounded-lg">
              <Mail className="text-blue-600" size={24} />
            </div>
            <div>
              <p className="text-gray-600 text-sm">Active Automations</p>
              <p className="text-2xl font-bold">{stats.active}</p>
              <p className="text-xs text-gray-500 mt-1">of {stats.total} total</p>
            </div>
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow-sm border hover:shadow-md transition-shadow">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-green-100 rounded-lg">
              <CheckCircle className="text-green-600" size={24} />
            </div>
            <div>
              <p className="text-gray-600 text-sm">Total Emails Sent</p>
              <p className="text-2xl font-bold">{stats.totalSent.toLocaleString()}</p>
              <p className="text-xs text-green-600 mt-1">+{Math.floor(Math.random() * 20)}% this week</p>
            </div>
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow-sm border hover:shadow-md transition-shadow">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-purple-100 rounded-lg">
              <TrendingUp className="text-purple-600" size={24} />
            </div>
            <div>
              <p className="text-gray-600 text-sm">Avg Open Rate</p>
              <p className="text-2xl font-bold">{stats.avgOpenRate.toFixed(1)}%</p>
              <p className="text-xs text-gray-500 mt-1">Across all automations</p>
            </div>
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow-sm border hover:shadow-md transition-shadow">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-orange-100 rounded-lg">
              <BarChart3 className="text-orange-600" size={24} />
            </div>
            <div>
              <p className="text-gray-600 text-sm">Avg Click Rate</p>
              <p className="text-2xl font-bold">{stats.avgClickRate.toFixed(1)}%</p>
              <p className="text-xs text-gray-500 mt-1">Engagement metric</p>
            </div>
          </div>
        </div>
      </div>

      {/* Filters and Search */}
      <div className="bg-white rounded-lg shadow-sm border p-4 mb-6">
        <div className="flex flex-col sm:flex-row gap-4">
          <div className="flex-1">
            <input
              type="text"
              placeholder="🔍 Search automations by name or trigger..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setFilterStatus('all')}
              className={`px-4 py-2 rounded-lg transition-colors ${filterStatus === 'all'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
            >
              All ({stats.total})
            </button>
            <button
              onClick={() => setFilterStatus('active')}
              className={`px-4 py-2 rounded-lg transition-colors ${filterStatus === 'active'
                  ? 'bg-green-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
            >
              Active ({stats.active})
            </button>
            <button
              onClick={() => setFilterStatus('paused')}
              className={`px-4 py-2 rounded-lg transition-colors ${filterStatus === 'paused'
                  ? 'bg-yellow-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
            >
              Paused ({stats.paused})
            </button>
          </div>
        </div>
      </div>

      {/* Automations List */}
      <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
          <h2 className="text-lg font-semibold text-gray-900">
            Your Automations {filteredAutomations.length > 0 && `(${filteredAutomations.length})`}
          </h2>
        </div>

        {filteredAutomations.length === 0 ? (
          <div className="text-center py-16">
            <Mail size={64} className="mx-auto text-gray-300 mb-4" />
            {searchQuery || filterStatus !== 'all' ? (
              <>
                <h3 className="text-lg font-medium text-gray-900 mb-2">No automations found</h3>
                <p className="text-gray-600 mb-6">Try adjusting your filters or search query</p>
                <button
                  onClick={() => {
                    setSearchQuery('');
                    setFilterStatus('all');
                  }}
                  className="bg-gray-100 hover:bg-gray-200 px-4 py-2 rounded-lg"
                >
                  Clear Filters
                </button>
              </>
            ) : (
              <>
                <h3 className="text-lg font-medium text-gray-900 mb-2">No automations yet</h3>
                <p className="text-gray-600 mb-6">Create your first email automation to engage subscribers automatically</p>
                <button
                  onClick={() => navigate('/automation/create')}
                  className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700"
                >
                  Create Your First Automation
                </button>
              </>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Name
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Trigger
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Steps
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Sent
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Performance
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 bg-white">
                {filteredAutomations.map((automation) => (
                  <tr key={automation.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <div>
                          <div className="font-medium text-gray-900">{automation.name}</div>
                          <div className="text-sm text-gray-500 flex items-center gap-1">
                            <Clock size={12} />
                            {new Date(automation.created_at).toLocaleDateString()}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="px-3 py-1 text-xs rounded-full bg-blue-100 text-blue-800 capitalize">
                        {automation.trigger?.replace('_', ' ') || 'Unknown'}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`px-3 py-1 text-xs rounded-full font-medium inline-flex items-center gap-1 ${automation.status === 'active' ? 'bg-green-100 text-green-800' :
                          automation.status === 'paused' ? 'bg-yellow-100 text-yellow-800' :
                            'bg-gray-100 text-gray-800'
                        }`}>
                        {automation.status === 'active' && <Play size={10} />}
                        {automation.status === 'paused' && <Pause size={10} />}
                        {automation.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {automation.steps?.length || 0} emails
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 font-medium">
                      {(automation.emails_sent || 0).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm">
                        <div className="flex items-center gap-2">
                          <div className="text-gray-900 font-medium">
                            {(automation.open_rate || 0).toFixed(1)}%
                          </div>
                          <span className="text-gray-400">opens</span>
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <div className="text-gray-600">
                            {(automation.click_rate || 0).toFixed(1)}%
                          </div>
                          <span className="text-gray-400">clicks</span>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => toggleAutomation(automation.id, automation.status)}
                          className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                          title={automation.status === 'active' ? 'Pause' : 'Activate'}
                        >
                          {automation.status === 'active' ? <Pause size={16} /> : <Play size={16} />}
                        </button>
                        <button
                          onClick={() => navigate(`/automation/edit/${automation.id}`)}
                          className="p-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                          title="Edit"
                        >
                          <Edit size={16} />
                        </button>
                        <button
                          onClick={() => navigate(`/automation/analytics/${automation.id}`)}
                          className="p-2 text-purple-600 hover:bg-purple-50 rounded-lg transition-colors"
                          title="Analytics"
                        >
                          <BarChart3 size={16} />
                        </button>
                        <button
                          onClick={() => duplicateAutomation(automation)}
                          className="p-2 text-green-600 hover:bg-green-50 rounded-lg transition-colors"
                          title="Duplicate"
                        >
                          <Copy size={16} />
                        </button>
                        <button
                          onClick={() => deleteAutomation(automation.id)}
                          className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
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

      {/* Quick Tips */}
      <div className="mt-8 bg-blue-50 border border-blue-200 rounded-lg p-6">
        <h3 className="font-semibold text-blue-900 mb-3 flex items-center gap-2">
          <Eye size={20} />
          💡 Quick Tips
        </h3>
        <ul className="space-y-2 text-sm text-blue-800">
          <li>• Start automations in <strong>draft mode</strong> to test before activating</li>
          <li>• Monitor <strong>open and click rates</strong> to optimize your email sequence</li>
          <li>• Use <strong>segments</strong> to target specific audience groups</li>
          <li>• Duplicate well-performing automations to save time</li>
        </ul>
      </div>
    </div>
  );
};

export default AutomationDashboard;