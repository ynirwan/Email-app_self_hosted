import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import API from '../api'; // ← Keep this import

const ABTestCreator = ({ campaign, onClose }) => {
  const navigate = useNavigate();
  const [testConfig, setTestConfig] = useState({
    test_name: '',
    test_type: 'subject_line',
    variants: [
      {
        name: 'Variant A (Control)',
        subject: '',
        sender_name: '',
        sender_email: '',
        reply_to: ''
      },
      {
        name: 'Variant B (Test)',
        subject: '',
        sender_name: '',
        sender_email: '',
        reply_to: ''
      }
    ],
    split_percentage: 50,
    sample_size: 1000,
    winner_criteria: 'open_rate'
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [campaignStats, setCampaignStats] = useState(null);

  useEffect(() => {
    if (campaign) {
      setTestConfig(prev => ({
        ...prev,
        variants: [
          {
            name: 'Variant A (Control)',
            subject: campaign.subject || '',
            sender_name: campaign.sender_name || '',
            sender_email: campaign.sender_email || '',
            reply_to: campaign.reply_to || ''
          },
          {
            name: 'Variant B (Test)',
            subject: '',
            sender_name: campaign.sender_name || '',
            sender_email: campaign.sender_email || '',
            reply_to: campaign.reply_to || ''
          }
        ]
      }));
    }
  }, [campaign]);

  useEffect(() => {
    if (campaign?._id) {
      fetchCampaignStats();
    }
  }, [campaign]);

  // ✅ Fixed: Use API instead of api
  const fetchCampaignStats = async () => {
    try {
      const response = await API.get(`/campaigns/${campaign._id}/stats`);
      setCampaignStats(response.data);
      
      const recommendedSize = Math.min(1000, Math.max(100, Math.floor(response.data.current_target_count * 0.2)));
      setTestConfig(prev => ({
        ...prev,
        sample_size: recommendedSize
      }));
    } catch (error) {
      console.error('Failed to load campaign stats:', error);
    }
  };

  const handleTestTypeChange = (newType) => {
    setTestConfig(prev => {
      const updatedVariants = [...prev.variants];
      
      if (newType === 'subject_line') {
        updatedVariants[1] = { ...updatedVariants[1], subject: '' };
      } else if (newType === 'sender_name') {
        updatedVariants[1] = { ...updatedVariants[1], sender_name: '' };
      } else if (newType === 'sender_email') {
        updatedVariants[1] = { ...updatedVariants[1], sender_email: '' };
      } else if (newType === 'reply_to') {
        updatedVariants[1] = { ...updatedVariants[1], reply_to: '' };
      }
      
      return {
        ...prev,
        test_type: newType,
        variants: updatedVariants
      };
    });
  };

  const handleVariantChange = (variantIndex, field, value) => {
    setTestConfig(prev => {
      const newVariants = [...prev.variants];
      newVariants[variantIndex] = {
        ...newVariants[variantIndex],
        [field]: value
      };
      return { ...prev, variants: newVariants };
    });
  };

  const validateTest = () => {
    if (!testConfig.test_name.trim()) {
      return 'Test name is required';
    }
    
    if (testConfig.test_type === 'subject_line') {
      if (!testConfig.variants[1].subject.trim()) {
        return 'Variant B subject line is required';
      }
    } else if (testConfig.test_type === 'sender_name') {
      if (!testConfig.variants[1].sender_name.trim()) {
        return 'Variant B sender name is required';
      }
    } else if (testConfig.test_type === 'sender_email') {
      if (!testConfig.variants[1].sender_email.trim()) {
        return 'Variant B sender email is required';
      }
    } else if (testConfig.test_type === 'reply_to') {
      if (!testConfig.variants[1].reply_to.trim()) {
        return 'Variant B reply-to address is required';
      }
    }
    
    if (testConfig.sample_size < 100) {
      return 'Sample size must be at least 100';
    }
    
    return null;
  };

  // ✅ Fixed: Use API instead of api
  const handleCreateTest = async () => {
    setError('');
    const validationError = validateTest();
    if (validationError) {
      setError(validationError);
      return;
    }

    setLoading(true);
    
    try {
      const response = await API.post('/ab-tests', {
        ...testConfig,
        campaign_id: campaign._id
      });

      navigate(`/ab-testing`);
      onClose();
    } catch (error) {
      setError(error.response?.data?.detail || 'Failed to create A/B test');
    } finally {
      setLoading(false);
    }
  };

  const renderVariantField = (variantIndex, isControl = false) => {
    const variant = testConfig.variants[variantIndex];
    const variantLabel = isControl ? 'Variant A (Control)' : 'Variant B (Test)';
    
    return (
      <div className={`border rounded-lg p-4 ${isControl ? 'bg-blue-50 border-blue-200' : 'bg-orange-50 border-orange-200'}`}>
        <h4 className="text-lg font-semibold mb-3 text-gray-800">{variantLabel}</h4>
        
        {testConfig.test_type === 'subject_line' && (
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-700">Subject Line</label>
            <input
              type="text"
              value={variant.subject}
              onChange={(e) => handleVariantChange(variantIndex, 'subject', e.target.value)}
              placeholder={isControl ? "Current subject line" : "Enter test subject line"}
              readOnly={isControl}
              className={`w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
                isControl
                  ? 'bg-gray-100 text-gray-600 cursor-not-allowed'
                  : 'bg-white text-gray-900'
              }`}
            />
          </div>
        )}
        
        {testConfig.test_type === 'sender_name' && (
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-700">Sender Name</label>
            <input
              type="text"
              value={variant.sender_name}
              onChange={(e) => handleVariantChange(variantIndex, 'sender_name', e.target.value)}
              placeholder={isControl ? "Current sender name" : "Enter test sender name"}
              readOnly={isControl}
              className={`w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
                isControl
                  ? 'bg-gray-100 text-gray-600 cursor-not-allowed'
                  : 'bg-white text-gray-900'
              }`}
            />
          </div>
        )}
        
        {testConfig.test_type === 'sender_email' && (
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-700">Sender Email</label>
            <input
              type="email"
              value={variant.sender_email}
              onChange={(e) => handleVariantChange(variantIndex, 'sender_email', e.target.value)}
              placeholder={isControl ? "Current sender email" : "Enter test sender email"}
              readOnly={isControl}
              className={`w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
                isControl
                  ? 'bg-gray-100 text-gray-600 cursor-not-allowed'
                  : 'bg-white text-gray-900'
              }`}
            />
          </div>
        )}
        
        {testConfig.test_type === 'reply_to' && (
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-700">Reply-To Address</label>
            <input
              type="email"
              value={variant.reply_to}
              onChange={(e) => handleVariantChange(variantIndex, 'reply_to', e.target.value)}
              placeholder={isControl ? "Current reply-to address" : "Enter test reply-to address"}
              readOnly={isControl}
              className={`w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
                isControl
                  ? 'bg-gray-100 text-gray-600 cursor-not-allowed'
                  : 'bg-white text-gray-900'
              }`}
            />
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6">
          <div className="flex justify-between items-center mb-6 pb-4 border-b border-gray-200">
            <h2 className="text-2xl font-bold text-gray-900">Create A/B Test: {campaign?.title}</h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 text-2xl font-bold w-8 h-8 flex items-center justify-center"
            >
              ×
            </button>
          </div>

          {campaignStats && (
            <div className="bg-gray-50 rounded-lg p-4 mb-6">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <p><span className="font-semibold">Target Subscribers:</span> {campaignStats.current_target_count}</p>
                <p><span className="font-semibold">Target Lists:</span> {campaignStats.target_lists.join(', ')}</p>
              </div>
            </div>
          )}

          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Test Name</label>
              <input
                type="text"
                placeholder="e.g., Subject Line Test #1"
                value={testConfig.test_name}
                onChange={(e) => setTestConfig({...testConfig, test_name: e.target.value})}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Test Type</label>
              <select
                value={testConfig.test_type}
                onChange={(e) => handleTestTypeChange(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="subject_line">Subject Line</option>
                <option value="sender_name">Sender Name</option>
                <option value="sender_email">Sender Email</option>
                <option value="reply_to">Reply-To Address</option>
              </select>
            </div>

            <div>
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Variants</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {renderVariantField(0, true)}
                {renderVariantField(1, false)}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Split: {testConfig.split_percentage}% / {100 - testConfig.split_percentage}%
                </label>
                <input
                  type="range"
                  min="10"
                  max="90"
                  value={testConfig.split_percentage}
                  onChange={(e) => setTestConfig({...testConfig, split_percentage: parseInt(e.target.value)})}
                  className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer slider"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Sample Size</label>
                <input
                  type="number"
                  value={testConfig.sample_size}
                  onChange={(e) => setTestConfig({...testConfig, sample_size: parseInt(e.target.value)})}
                  min="100"
                  max={campaignStats?.current_target_count || 10000}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Winner Criteria</label>
                <select
                  value={testConfig.winner_criteria}
                  onChange={(e) => setTestConfig({...testConfig, winner_criteria: e.target.value})}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="open_rate">Open Rate</option>
                  <option value="click_rate">Click Rate</option>
                </select>
              </div>
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 rounded-md p-3">
                <p className="text-sm text-red-800">{error}</p>
              </div>
            )}

            <div className="flex justify-end space-x-3 pt-4 border-t border-gray-200">
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 border border-gray-300 rounded-md hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-500"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateTest}
                disabled={loading}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Creating...' : 'Create A/B Test'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ABTestCreator;

