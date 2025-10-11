// ABTestingPage.jsx
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import API from '../api';

const ABTestingPage = () => {
  const [abTests, setAbTests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const fetchABTests = async () => {
    try {
      setLoading(true);
      const response = await API.get('/ab-tests');
      const testsData = response.data.tests || response.data || [];
      setAbTests(Array.isArray(testsData) ? testsData : []);
    } catch (error) {
      console.error('Failed to fetch A/B tests:', error);
      setError('Failed to load A/B tests');
    } finally {
      setLoading(false);
    }
  };

  const startTest = async (testId) => {
    try {
      await API.post(`/ab-tests/${testId}/start`);
      alert('A/B test started successfully!');
      fetchABTests();
    } catch (error) {
      alert('Failed to start A/B test: ' + (error.response?.data?.detail || error.message));
    }
  };

  const stopTest = async (testId) => {
    if (!confirm('Are you sure you want to stop this A/B test?')) return;
    
    try {
      await API.post(`/ab-tests/${testId}/stop`);
      alert('A/B test stopped successfully!');
      fetchABTests();
    } catch (error) {
      alert('Failed to stop A/B test: ' + (error.response?.data?.detail || error.message));
    }
  };

  const deleteTest = async (testId) => {
    if (!confirm('Are you sure you want to delete this A/B test?')) return;
    
    try {
      await API.delete(`/ab-tests/${testId}`);
      alert('A/B test deleted successfully!');
      fetchABTests();
    } catch (error) {
      alert('Failed to delete A/B test: ' + (error.response?.data?.detail || error.message));
    }
  };

  const viewResults = (testId) => {
    navigate(`/ab-tests/${testId}/results`);
  };

  useEffect(() => {
    fetchABTests();
  }, []);

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto mt-10 p-6">
        <p className="text-center">Loading A/B tests...</p>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto mt-10 p-6">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold">🧪 A/B Tests</h2>
        <button
          onClick={() => navigate('/campaigns')}
          className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700"
        >
          ← Back to Campaigns
        </button>
      </div>

      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-6">
          {error}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">
        <div className="bg-purple-50 p-6 rounded-lg border">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-purple-600 font-medium">Total Tests</p>
              <p className="text-3xl font-bold text-purple-800">{abTests.length}</p>
            </div>
            <span className="text-4xl">🧪</span>
          </div>
        </div>
        
        <div className="bg-yellow-50 p-6 rounded-lg border">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-yellow-600 font-medium">Draft</p>
              <p className="text-3xl font-bold text-yellow-800">
                {abTests.filter(t => t.status === 'draft').length}
              </p>
            </div>
            <span className="text-4xl">📝</span>
          </div>
        </div>
        
        <div className="bg-blue-50 p-6 rounded-lg border">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-blue-600 font-medium">Running</p>
              <p className="text-3xl font-bold text-blue-800">
                {abTests.filter(t => t.status === 'running').length}
              </p>
            </div>
            <span className="text-4xl">🏃</span>
          </div>
        </div>
        
        <div className="bg-green-50 p-6 rounded-lg border">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-green-600 font-medium">Completed</p>
              <p className="text-3xl font-bold text-green-800">
                {abTests.filter(t => t.status === 'completed').length}
              </p>
            </div>
            <span className="text-4xl">✅</span>
          </div>
        </div>
      </div>

      {/* A/B Tests List */}
      <div className="bg-white shadow rounded">
        <div className="p-4 border-b">
          <h3 className="text-lg font-semibold">📋 Your A/B Tests ({abTests.length})</h3>
        </div>

        {abTests.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            <p className="text-lg mb-2">🧪 No A/B tests yet</p>
            <p>Create a draft campaign and click "A/B Test" to get started!</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full table-auto text-sm">
              <thead>
                <tr className="bg-gray-100 text-left">
                  <th className="p-3 font-semibold">Test Name</th>
                  <th className="p-3 font-semibold">Type</th>
                  <th className="p-3 font-semibold">Status</th>
                  <th className="p-3 font-semibold">Sample Size</th>
                  <th className="p-3 font-semibold">Created</th>
                  <th className="p-3 font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody>
                {abTests.map(test => (
                  <tr key={test._id} className="border-t hover:bg-gray-50">
                    <td className="p-3 font-medium">{test.test_name}</td>
                    <td className="p-3">
                      <span className="bg-gray-100 px-2 py-1 rounded text-xs">
                        {test.test_type.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="p-3">
                      <span className={`px-2 py-1 rounded text-xs font-medium ${
                        test.status === 'completed'
                          ? 'bg-green-100 text-green-800'
                          : test.status === 'running'
                          ? 'bg-blue-100 text-blue-800'
                          : test.status === 'paused'
                          ? 'bg-yellow-100 text-yellow-800'
                          : 'bg-gray-100 text-gray-800'
                      }`}>
                        {test.status}
                      </span>
                    </td>
                    <td className="p-3">{test.sample_size}</td>
                    <td className="p-3 text-gray-600">
                      {test.created_at ? new Date(test.created_at).toLocaleDateString() : '-'}
                    </td>
                    <td className="p-3">
                      <div className="flex gap-3 flex-wrap">
                        {test.status === 'draft' && (
                          <button
                            onClick={() => startTest(test._id)}
                            className="text-green-600 hover:text-green-800 hover:underline"
                          >
                            ▶️ Start
                          </button>
                        )}
                        
                        {test.status === 'running' && (
                          <button
                            onClick={() => stopTest(test._id)}
                            className="text-red-600 hover:text-red-800 hover:underline"
                          >
                            ⏹️ Stop
                          </button>
                        )}
                        
                        {(test.status === 'running' || test.status === 'completed') && (
                          <button
                            onClick={() => viewResults(test._id)}
                            className="text-purple-600 hover:text-purple-800 hover:underline"
                          >
                            📊 Results
                          </button>
                        )}
                        
                        <button
                          onClick={() => deleteTest(test._id)}
                          className="text-red-600 hover:text-red-800 hover:underline"
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
    </div>
  );
};

export default ABTestingPage;

