import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import API from '../api';

const ABTestResultsView = ({ testId, onClose }) => {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(true);
  const [completing, setCompleting] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    fetchResults();
    const interval = setInterval(fetchResults, 10000); // Refresh every 10s
    return () => clearInterval(interval);
  }, [testId]);

  const fetchResults = async () => {
    try {
      const response = await API.get(`/ab-tests/${testId}/results`);
      setResults(response.data);
      setLoading(false);
    } catch (error) {
      console.error('Failed to fetch results:', error);
      setLoading(false);
    }
  };

  const handleCompleteTest = async (applyWinner = true) => {
    if (!window.confirm(
      applyWinner 
        ? `Complete test and apply Variant ${results.winner.winner} to campaign?`
        : 'Complete test without applying winner to campaign?'
    )) {
      return;
    }

    setCompleting(true);
    try {
      const response = await API.post(`/ab-tests/${testId}/complete`, {
        apply_to_campaign: applyWinner
      });
      
      alert(response.data.message);
      fetchResults();
    } catch (error) {
      alert(error.response?.data?.detail || 'Failed to complete test');
    } finally {
      setCompleting(false);
    }
  };

  const handleSendCampaign = async () => {
    if (!results.campaign_id) return;
    
    if (!window.confirm(
      'Send campaign to remaining subscribers? ' +
      '(A/B test participants will be automatically excluded)'
    )) {
      return;
    }

    try {
      await API.post(`/campaigns/${results.campaign_id}/send`);
      alert('Campaign send initiated!');
      navigate('/campaigns');
    } catch (error) {
      alert(error.response?.data?.detail || 'Failed to send campaign');
    }
  };

  if (loading) {
    return <div className="p-6 text-center">Loading results...</div>;
  }

  if (!results) {
    return <div className="p-6 text-center text-red-600">Failed to load results</div>;
  }

  const { variant_a, variant_b } = results.results;
  const { winner, winner_info } = results;
  const significance = results.statistical_significance;
  const isCompleted = results.status === 'completed';

  return (
    <div className="bg-white rounded-lg shadow-lg p-6">
      <div className="flex justify-between items-start mb-6">
        <div>
          <h2 className="text-2xl font-bold">{results.test_name}</h2>
          <p className="text-gray-600">Test Type: {results.test_type}</p>
          <span className={`inline-block px-3 py-1 rounded-full text-sm font-medium mt-2 ${
            isCompleted ? 'bg-green-100 text-green-800' : 'bg-blue-100 text-blue-800'
          }`}>
            {results.status.toUpperCase()}
          </span>
        </div>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-700 text-2xl">
          ×
        </button>
      </div>

      {/* Statistical Significance Badge */}
      {significance && (
        <div className={`mb-6 p-4 rounded-lg border-2 ${
          significance.is_significant 
            ? 'bg-green-50 border-green-300' 
            : 'bg-yellow-50 border-yellow-300'
        }`}>
          <h3 className="font-semibold mb-2">📊 Statistical Analysis</h3>
          <p className="text-sm mb-2">{significance.interpretation}</p>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="font-medium">Confidence:</span> {significance.confidence_level}
            </div>
            {significance.p_value && (
              <div>
                <span className="font-medium">P-value:</span> {significance.p_value}
              </div>
            )}
            <div>
              <span className="font-medium">Sample Size:</span> {significance.total_samples}
            </div>
            <div>
              <span className="font-medium">Effect Size:</span> {significance.effect_size_percentage}%
            </div>
          </div>
          <div className="mt-3 p-2 bg-white rounded border">
            <p className="text-xs font-medium text-gray-700">
              💡 {significance.recommendation}
            </p>
          </div>
        </div>
      )}

      {/* Results Comparison */}
      <div className="grid md:grid-cols-2 gap-6 mb-6">
        {/* Variant A */}
        <div className={`border rounded-lg p-4 ${
          winner_info.winner === 'A' ? 'border-green-500 bg-green-50' : 'border-gray-300'
        }`}>
          <div className="flex justify-between items-center mb-3">
            <h3 className="text-lg font-bold">Variant A (Control)</h3>
            {winner_info.winner === 'A' && (
              <span className="bg-green-500 text-white px-2 py-1 rounded text-sm font-bold">
                🏆 WINNER
              </span>
            )}
          </div>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span>Sent:</span>
              <span className="font-semibold">{variant_a.sent}</span>
            </div>
            <div className="flex justify-between">
              <span>Opened:</span>
              <span className="font-semibold">{variant_a.opened}</span>
            </div>
            <div className="flex justify-between">
              <span>Open Rate:</span>
              <span className="font-semibold text-blue-600">{variant_a.open_rate}%</span>
            </div>
            <div className="flex justify-between">
              <span>Click Rate:</span>
              <span className="font-semibold text-purple-600">{variant_a.click_rate}%</span>
            </div>
          </div>
        </div>

        {/* Variant B */}
        <div className={`border rounded-lg p-4 ${
          winner_info.winner === 'B' ? 'border-green-500 bg-green-50' : 'border-gray-300'
        }`}>
          <div className="flex justify-between items-center mb-3">
            <h3 className="text-lg font-bold">Variant B (Test)</h3>
            {winner_info.winner === 'B' && (
              <span className="bg-green-500 text-white px-2 py-1 rounded text-sm font-bold">
                🏆 WINNER
              </span>
            )}
          </div>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span>Sent:</span>
              <span className="font-semibold">{variant_b.sent}</span>
            </div>
            <div className="flex justify-between">
              <span>Opened:</span>
              <span className="font-semibold">{variant_b.opened}</span>
            </div>
            <div className="flex justify-between">
              <span>Open Rate:</span>
              <span className="font-semibold text-blue-600">{variant_b.open_rate}%</span>
            </div>
            <div className="flex justify-between">
              <span>Click Rate:</span>
              <span className="font-semibold text-purple-600">{variant_b.click_rate}%</span>
            </div>
          </div>
        </div>
      </div>

      {/* Winner Summary */}
      {winner_info.winner !== 'TIE' && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
          <h3 className="font-semibold mb-2">🎯 Performance Summary</h3>
          <p className="text-sm">
            <strong>Variant {winner_info.winner}</strong> performed better by{' '}
            <strong>{winner_info.improvement_percentage}%</strong> based on{' '}
            <strong>{winner_info.criteria}</strong>
          </p>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex gap-3">
        {!isCompleted ? (
          <>
            <button
              onClick={() => handleCompleteTest(true)}
              disabled={completing}
              className="flex-1 bg-green-600 hover:bg-green-700 text-white py-3 px-6 rounded-lg font-semibold disabled:opacity-50"
            >
              {completing ? 'Completing...' : `Complete Test & Apply Winner`}
            </button>
            <button
              onClick={() => handleCompleteTest(false)}
              disabled={completing}
              className="flex-1 bg-gray-600 hover:bg-gray-700 text-white py-3 px-6 rounded-lg font-semibold disabled:opacity-50"
            >
              Complete Without Applying
            </button>
          </>
        ) : (
          <button
            onClick={handleSendCampaign}
            className="flex-1 bg-blue-600 hover:bg-blue-700 text-white py-3 px-6 rounded-lg font-semibold"
          >
            📤 Send Campaign to Remaining Subscribers
          </button>
        )}
      </div>

      {/* Info Notice */}
      <div className="mt-4 p-3 bg-gray-50 border border-gray-200 rounded text-sm text-gray-600">
        ℹ️ {isCompleted 
          ? 'Test completed. Sending campaign will exclude all A/B test participants automatically.'
          : 'Complete the test to apply the winning variant and send to remaining subscribers.'
        }
      </div>
    </div>
  );
};

export default ABTestResultsView;