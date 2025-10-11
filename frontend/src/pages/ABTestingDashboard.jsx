import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import ABTestCreator from './ABTestCreator';
import API from '../api'; // ← Keep this import

const ABTestingDashboard = () => {
  const [campaigns, setCampaigns] = useState([]);
  const [abTests, setAbTests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedCampaign, setSelectedCampaign] = useState(null);
  const navigate = useNavigate();

  // ✅ Fixed: Use API instead of api
  const fetchData = async () => {
    try {
      setLoading(true);
      
      const campaignsRes = await API.get('/draft-campaigns');
      setCampaigns(campaignsRes.data.campaigns || []);
      
      const testsRes = await API.get('/ab-tests');
      setAbTests(testsRes.data.tests || testsRes.data || []);
      
    } catch (error) {
      console.error('Failed to fetch data:', error);
      setAbTests([]);
      setCampaigns([]);
    } finally {
      setLoading(false);
    }
  };

  const openCreateModal = (campaign) => {
    setSelectedCampaign(campaign);
    setShowCreateModal(true);
  };

  const closeCreateModal = () => {
    setShowCreateModal(false);
    setSelectedCampaign(null);
    fetchData();
  };

  // ✅ Fixed: Use API instead of api
  const startTest = async (testId) => {
    try {
      const response = await API.post(`/ab-tests/${testId}/start`);
      alert('A/B test started successfully!');
      fetchData();
    } catch (error) {
      alert('Failed to start test: ' + (error.response?.data?.detail || error.message));
    }
  };

  // ✅ Fixed: Use API instead of api
  const stopTest = async (testId) => {
    if (!window.confirm('Are you sure you want to stop this test?')) return;
    
    try {
      await API.post(`/ab-tests/${testId}/stop`);
      alert('A/B test stopped successfully!');
      fetchData();
    } catch (error) {
      alert('Failed to stop test: ' + (error.response?.data?.detail || error.message));
    }
  };

  // ✅ Fixed: Use API instead of api
  const deleteTest = async (testId) => {
    if (!window.confirm('Are you sure you want to delete this test?')) return;
    
    try {
      await API.delete(`/ab-tests/${testId}`);
      alert('A/B test deleted successfully!');
      fetchData();
    } catch (error) {
      alert('Failed to delete test: ' + (error.response?.data?.detail || error.message));
    }
  };

  // ✅ Fixed: Use API instead of api
  const viewResults = async (testId) => {
    try {
      const response = await API.get(`/ab-tests/${testId}/results`);
      const results = response.data;
      
      // Simple results display - you can enhance this later
      const message = `
A/B Test Results:

Variant A:
- Sent: ${results.results.variant_a.sent}
- Opened: ${results.results.variant_a.opened} (${results.results.variant_a.open_rate.toFixed(2)}%)
- Clicked: ${results.results.variant_a.clicked} (${results.results.variant_a.click_rate.toFixed(2)}%)

Variant B:
- Sent: ${results.results.variant_b.sent}
- Opened: ${results.results.variant_b.opened} (${results.results.variant_b.open_rate.toFixed(2)}%)
- Clicked: ${results.results.variant_b.clicked} (${results.results.variant_b.click_rate.toFixed(2)}%)

Winner: Variant ${results.winner.winner} (${results.winner.improvement.toFixed(2)}% improvement)
      `;
      
      alert(message);
    } catch (error) {
      alert('Error fetching results: ' + (error.response?.data?.detail || error.message));
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto mt-10 p-6">
        <div className="text-center">Loading A/B testing dashboard...</div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto mt-10 p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">🧪 A/B Testing Dashboard</h1>
        <button
          onClick={() => navigate('/campaigns')}
          className="bg-gray-600 text-white px-4 py-2 rounded-lg hover:bg-gray-700"
        >
          ← Back to Campaigns
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="bg-blue-50 p-6 rounded-lg border">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-blue-600 font-medium">Draft Campaigns</p>
              <p className="text-3xl font-bold text-blue-800">{campaigns.length}</p>
              <p className="text-xs text-blue-500">Available for A/B testing</p>
            </div>
            <span className="text-4xl">📝</span>
          </div>
        </div>

        <div className="bg-purple-50 p-6 rounded-lg border">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-purple-600 font-medium">Active A/B Tests</p>
              <p className="text-3xl font-bold text-purple-800">
                {abTests.filter(t => t.status === 'running').length}
              </p>
            </div>
            <span className="text-4xl">🏃</span>
          </div>
        </div>

        <div className="bg-green-50 p-6 rounded-lg border">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-green-600 font-medium">Total A/B Tests</p>
              <p className="text-3xl font-bold text-green-800">{abTests.length}</p>
            </div>
            <span className="text-4xl">🧪</span>
          </div>
        </div>
      </div>

      {/* Draft Campaigns */}
      <div className="mb-8">
        <h2 className="text-xl font-semibold mb-4">📋 Draft Campaigns Available for A/B Testing</h2>
        {campaigns.length === 0 ? (
          <div className="bg-gray-50 p-8 text-center rounded-lg">
            <p className="text-gray-600 mb-2">No draft campaigns available</p>
            <button
              onClick={() => navigate('/campaigns/create')}
              className="text-blue-600 hover:underline"
            >
              Create a new campaign first
            </button>
          </div>
        ) : (
          <div className="bg-white shadow rounded-lg overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Campaign</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Subject</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Target Count</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {campaigns.map(campaign => (
                  <tr key={campaign._id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 font-medium text-gray-900">{campaign.title}</td>
                    <td className="px-6 py-4 text-gray-600">{campaign.subject}</td>
                    <td className="px-6 py-4 text-gray-600">{campaign.target_list_count || 0}</td>
                    <td className="px-6 py-4">
                      <button
                        onClick={() => openCreateModal(campaign)}
                        className="bg-purple-600 text-white px-4 py-2 rounded hover:bg-purple-700"
                      >
                        🧪 Create A/B Test
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* A/B Tests */}
      <div>
        <h2 className="text-xl font-semibold mb-4">📊 Your A/B Tests</h2>
        {abTests.length === 0 ? (
          <div className="bg-gray-50 p-8 text-center rounded-lg">
            <p className="text-gray-600">No A/B tests created yet</p>
          </div>
        ) : (
          <div className="bg-white shadow rounded-lg overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Test Name</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Sample Size</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {abTests.map(test => (
                  <tr key={test._id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 font-medium text-gray-900">{test.test_name}</td>
                    <td className="px-6 py-4">
                      <span className="bg-gray-100 px-2 py-1 rounded text-sm">
                        {test.test_type.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 rounded text-sm font-medium ${
                        test.status === 'running' ? 'bg-blue-100 text-blue-800' :
                        test.status === 'completed' ? 'bg-green-100 text-green-800' :
                        'bg-gray-100 text-gray-800'
                      }`}>
                        {test.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-gray-600">{test.sample_size}</td>
                    <td className="px-6 py-4">
                      <div className="flex space-x-2">
                        {test.status === 'draft' && (
                          <button
                            onClick={() => startTest(test._id)}
                            className="text-green-600 hover:underline text-sm"
                          >
                            ▶️ Start
                          </button>
                        )}
                        
                        {test.status === 'running' && (
                          <button
                            onClick={() => stopTest(test._id)}
                            className="text-red-600 hover:underline text-sm"
                          >
                            ⏹️ Stop
                          </button>
                        )}
                        
                        {(test.status === 'running' || test.status === 'completed') && (
                          <button
                            onClick={() => viewResults(test._id)}
                            className="text-purple-600 hover:underline text-sm"
                          >
                            📊 Results
                          </button>
                        )}
                        
                        <button
                          onClick={() => deleteTest(test._id)}
                          className="text-red-600 hover:underline text-sm"
                        >
                          🗑️ Delete
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

      {showCreateModal && selectedCampaign && (
        <ABTestCreator 
          campaign={selectedCampaign}
          onClose={closeCreateModal}
        />
      )}
    </div>
  );
};

export default ABTestingDashboard;
