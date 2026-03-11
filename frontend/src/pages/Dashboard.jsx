import { useEffect, useState } from 'react'
import API from '../api'
import { useNavigate } from 'react-router-dom'
import { useUser } from '../contexts/UserContext'

export default function Dashboard() {
  const { user, userLoading } = useUser()
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState({
    total_subscribers: 0,
    active_subscribers: 0,
    total_campaigns: 0,
    draft_campaigns: 0,
    completed_campaigns: 0,
    summary: { active_rate: 0 },
    lists: []
  })
  const [error, setError] = useState(null)

  const navigate = useNavigate()

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) {
      navigate('/login', { replace: true })
      return
    }
    fetchStats()
  }, [navigate])

  const fetchStats = async () => {
    try {
      const statsResponse = await API.get('/stats/summary')
      setStats(statsResponse.data)
    } catch (err) {
      console.error('❌ Error fetching dashboard stats:', err)
      if (err.response?.status === 401) {
        localStorage.removeItem('token')
        navigate('/login', { replace: true })
      } else {
        setError('Failed to load dashboard data')
      }
    } finally {
      setLoading(false)
    }
  }

  const refreshStats = async () => {
    try {
      setError(null)
      const statsResponse = await API.get('/stats/summary')
      setStats(statsResponse.data)
    } catch (err) {
      console.error('Error refreshing stats:', err)
      setError('Failed to refresh statistics')
    }
  }

  if (loading || userLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600 text-lg">Loading dashboard...</p>
        </div>
      </div>
    )
  }

  // ✅ Show error screen if something went wrong
  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center max-w-md">
          <div className="bg-red-100 border border-red-400 text-red-700 px-6 py-4 rounded-lg">
            <p className="font-semibold mb-2">⚠️ Error Loading Dashboard</p>
            <p className="mb-4">{error}</p>
            <button
              onClick={refreshStats}
              className="bg-red-600 text-white px-6 py-2 rounded-lg hover:bg-red-700 transition-colors"
            >
              🔄 Try Again
            </button>
          </div>
        </div>
      </div>
    )
  }
  
  return (
    <div className="space-y-10">
      {/* User Welcome Section */}
      {user && (
      <div>
        <h2 className="text-2xl font-bold mb-2">Welcome, {user?.name} 👋</h2>
        <p className="text-gray-600">Email: {user?.email}</p>
      </div>
      )}


      {/* Error Display */}
      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          {error}
          <button
            onClick={refreshStats}
            className="ml-2 underline hover:no-underline"
          >
            Try Again
          </button>
        </div>
      )}

      {/* Main Stats Cards */}
      {stats && (

      <div>
        <h3 className="text-xl font-semibold mb-4">📊 Your Stats</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 gap-6">
          {/* Subscribers Card */}
          <div className="bg-blue-100 p-6 rounded-xl shadow-sm border hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-3">
              <div className="text-sm font-medium text-gray-700">Subscribers</div>
              <span className="text-2xl">👥</span>
            </div>
            <div className="space-y-1">
              <p className="text-gray-800">
                <span className="font-semibold">{stats.total_subscribers}</span>{' '}
                Total
              </p>
              <p className="text-green-700">
                <span className="font-semibold">{stats.active_subscribers}</span>{' '}
                Active
              </p>
              <p className="text-yellow-700">
                Engagement Rate:{' '}
                <span className="font-semibold">
                  {stats.summary?.active_rate?.toFixed(1) || 0}%
                </span>
              </p>
            </div>
          </div>
      
          {/* Campaigns Card */}
          <div className="bg-purple-100 p-6 rounded-xl shadow-sm border hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-3">
              <div className="text-sm font-medium text-gray-700">Campaigns</div>
              <span className="text-2xl">📧</span>
            </div>
            <div className="space-y-1">
              <p className="text-gray-800">
                <span className="font-semibold">{stats.total_campaigns}</span>{' '}
                Total
              </p>
              <p className="text-blue-700">
                <span className="font-semibold">{stats.draft_campaigns || 0}</span>{' '}
                Draft
              </p>
              <p className="text-green-700">
                <span className="font-semibold">{stats.completed_campaigns || 0}</span>{' '}
                Completed
              </p>
            </div>
          </div>
        </div>
      </div>
      )}


      {/* Subscribers by List Breakdown */}
      {stats.lists && stats.lists.length > 0 && (
        <div>
          <h3 className="text-xl font-semibold mb-4">📋 Subscribers by List</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {stats.lists.map((list) => (
              <div
                key={list._id}
                className="bg-gray-50 p-4 rounded-lg shadow-sm border"
              >
                <div className="text-sm text-gray-600 capitalize font-medium">
                  {list._id || 'Unknown List'}
                </div>
                <div className="text-2xl font-bold text-gray-800">
                  {list.count}
                </div>
                <div className="text-xs text-gray-500">subscribers</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quick Actions */}
      <div>
        <h3 className="text-xl font-semibold mb-4">🚀 Quick Actions</h3>
        <div className="flex flex-wrap gap-4">
          <button
            onClick={() => navigate('/subscribers')}
            className="bg-blue-500 text-white px-6 py-2 rounded-lg hover:bg-blue-600 transition-colors"
          >
            👥 Manage Subscribers
          </button>
          <button
            onClick={() => navigate('/campaigns')}
            className="bg-green-500 text-white px-6 py-2 rounded-lg hover:bg-green-600 transition-colors"
          >
            📧 Create Campaign
          </button>
          <button
            onClick={() => navigate('/ab-testing')}
            className="bg-yellow-500 text-white px-6 py-2 rounded-lg hover:bg-yellow-600 transition-colors"
          >
            🧪 A/B Testing
          </button>
          <button
            onClick={() => navigate('/settings/email')}
            className="bg-gray-700 text-white px-6 py-2 rounded-lg hover:bg-gray-800 transition-colors"
          >
            ⚙ Settings
          </button>
        </div>
      </div>
    </div>
  )
}


