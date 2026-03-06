// src/pages/AutomationAnalytics.jsx - FIXED VERSION
import React, { useState, useEffect } from 'react';
import { BarChart3, TrendingUp, Mail, Users, ArrowLeft, Calendar } from 'lucide-react';
import { useParams, useNavigate } from 'react-router-dom';
import API from '../api';

const AutomationAnalytics = () => {
  const { id } = useParams();
  const navigate = useNavigate();

  const [analytics, setAnalytics] = useState(null);
  const [automationName, setAutomationName] = useState('');
  const [dateRange, setDateRange] = useState('30d');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (id) {
      fetchAnalytics();
    }
  }, [id, dateRange]);

  const fetchAnalytics = async () => {
    try {
      setLoading(true);
      setError(null);

      console.log('🔄 Fetching analytics for automation:', id);

      const response = await API.get(`/automation/rules/${id}/analytics`);
      console.log('📊 Analytics response:', response);

      // Handle response structure
      const data = response?.data || response;
      setAnalytics(data);
      setAutomationName(data.rule_name || 'Automation Analytics');

      console.log('✅ Analytics loaded successfully');

    } catch (error) {
      console.error('❌ Failed to fetch analytics:', error);
      setError('Failed to load analytics data');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading analytics...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 max-w-6xl mx-auto">
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          <p className="font-medium">Error</p>
          <p className="text-sm mt-1">{error}</p>
        </div>
        <button
          onClick={() => navigate('/automation')}
          className="mt-4 text-blue-600 hover:underline flex items-center gap-2"
        >
          <ArrowLeft size={16} />
          Back to Automations
        </button>
      </div>
    );
  }

  if (!analytics) {
    return (
      <div className="p-6 max-w-6xl mx-auto">
        <div className="text-center py-12">
          <BarChart3 size={64} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-600">No analytics data available</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex justify-between items-center mb-8">
        <div>
          <button
            onClick={() => navigate('/automation')}
            className="text-blue-600 hover:underline flex items-center gap-2 mb-2"
          >
            <ArrowLeft size={16} />
            Back to Automations
          </button>
          <h1 className="text-3xl font-bold text-gray-900">{automationName}</h1>
          <p className="text-gray-600 mt-1">Performance analytics and insights</p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={fetchAnalytics}
            className="bg-gray-100 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-200 transition-colors"
          >
            🔄 Refresh
          </button>

          <select
            value={dateRange}
            onChange={(e) => setDateRange(e.target.value)}
            className="p-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
          >
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
            <option value="90d">Last 90 days</option>
          </select>
        </div>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        {/* Emails Sent */}
        <div className="bg-white p-6 rounded-lg shadow-sm border hover:shadow-md transition-shadow">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-blue-100 rounded-lg">
              <Mail className="text-blue-600" size={24} />
            </div>
            <div>
              <p className="text-gray-600 text-sm">Emails Sent</p>
              <p className="text-2xl font-bold">{(analytics.emails_sent || 0).toLocaleString()}</p>
            </div>
          </div>
        </div>

        {/* Open Rate */}
        <div className="bg-white p-6 rounded-lg shadow-sm border hover:shadow-md transition-shadow">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-green-100 rounded-lg">
              <TrendingUp className="text-green-600" size={24} />
            </div>
            <div>
              <p className="text-gray-600 text-sm">Open Rate</p>
              <p className="text-2xl font-bold">{(analytics.open_rate || 0).toFixed(1)}%</p>
              <p className="text-xs text-gray-500 mt-1">{(analytics.emails_opened || 0).toLocaleString()} opens</p>
            </div>
          </div>
        </div>

        {/* Click Rate */}
        <div className="bg-white p-6 rounded-lg shadow-sm border hover:shadow-md transition-shadow">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-purple-100 rounded-lg">
              <BarChart3 className="text-purple-600" size={24} />
            </div>
            <div>
              <p className="text-gray-600 text-sm">Click Rate</p>
              <p className="text-2xl font-bold">{(analytics.click_rate || 0).toFixed(1)}%</p>
              <p className="text-xs text-gray-500 mt-1">{(analytics.emails_clicked || 0).toLocaleString()} clicks</p>
            </div>
          </div>
        </div>

        {/* Subscribers */}
        <div className="bg-white p-6 rounded-lg shadow-sm border hover:shadow-md transition-shadow">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-orange-100 rounded-lg">
              <Users className="text-orange-600" size={24} />
            </div>
            <div>
              <p className="text-gray-600 text-sm">Subscribers Entered</p>
              <p className="text-2xl font-bold">{(analytics.subscribers_entered || 0).toLocaleString()}</p>
              <p className="text-xs text-gray-500 mt-1">
                {(analytics.subscribers_completed || 0).toLocaleString()} completed
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Execution Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <div className="flex items-center justify-between mb-2">
            <p className="text-gray-600 text-sm">Total Executions</p>
            <span className="text-2xl">📊</span>
          </div>
          <p className="text-3xl font-bold text-gray-900">{analytics.total_executions || 0}</p>
        </div>

        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <div className="flex items-center justify-between mb-2">
            <p className="text-gray-600 text-sm">Completed</p>
            <span className="text-2xl">✅</span>
          </div>
          <p className="text-3xl font-bold text-green-600">{analytics.completed_executions || 0}</p>
        </div>

        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <div className="flex items-center justify-between mb-2">
            <p className="text-gray-600 text-sm">Failed</p>
            <span className="text-2xl">❌</span>
          </div>
          <p className="text-3xl font-bold text-red-600">{analytics.failed_executions || 0}</p>
        </div>
      </div>

      {/* Summary Info */}
      <div className="bg-gradient-to-r from-blue-50 to-purple-50 border border-blue-200 rounded-lg p-6 mb-8">
        <h3 className="font-semibold text-gray-900 mb-3">📈 Performance Summary</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-gray-600">Rule ID</p>
            <p className="font-medium text-gray-900">{analytics.rule_id}</p>
          </div>
          <div>
            <p className="text-gray-600">Rule Name</p>
            <p className="font-medium text-gray-900">{analytics.rule_name}</p>
          </div>
        </div>
      </div>

      {/* Email Performance Table (if available) */}
      {analytics.email_performance && analytics.email_performance.length > 0 && (
        <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">Email Step Performance</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Email Step
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Sent
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Opens
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Clicks
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Open Rate
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Click Rate
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 bg-white">
                {analytics.email_performance.map((email, index) => (
                  <tr key={index} className="hover:bg-gray-50">
                    <td className="px-6 py-4 font-medium text-gray-900">
                      {email.subject || `Email Step ${index + 1}`}
                    </td>
                    <td className="px-6 py-4 text-gray-900">
                      {(email.sent || 0).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 text-gray-900">
                      {(email.opens || 0).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 text-gray-900">
                      {(email.clicks || 0).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 text-gray-900">
                      {(email.open_rate || 0).toFixed(1)}%
                    </td>
                    <td className="px-6 py-4 text-gray-900">
                      {(email.click_rate || 0).toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* No detailed data message */}
      {(!analytics.email_performance || analytics.email_performance.length === 0) && (
        <div className="bg-gray-50 rounded-lg p-8 text-center border border-dashed">
          <BarChart3 size={48} className="mx-auto text-gray-300 mb-3" />
          <p className="text-gray-600">No detailed email performance data available yet</p>
          <p className="text-sm text-gray-500 mt-2">Data will appear once emails are sent</p>
        </div>
      )}
    </div>
  );
};

export default AutomationAnalytics;