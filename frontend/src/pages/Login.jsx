// frontend/src/pages/Login.jsx
import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import API from '../api'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  const handleLogin = async (e) => {
    e.preventDefault()
    
    // Prevent multiple submissions
    if (loading) return
    
    setError(null)
    setLoading(true)
    
    try {
      console.log('🔐 Attempting login for:', email)
      const res = await API.post('/auth/login', { email, password })
      console.log('✅ Login successful, received token')
      
      // ✅ Store token
      localStorage.setItem('token', res.data.token)
      
      // ✅ CRITICAL: Wait for localStorage to sync (especially in slower browsers)
      await new Promise(resolve => setTimeout(resolve, 150))
      
      // ✅ Verify token is actually stored
      const storedToken = localStorage.getItem('token')
      if (!storedToken) {
        throw new Error('Failed to store authentication token')
      }
      
      console.log('✅ Token verified, navigating to dashboard...')
      
      // ✅ Force a hard refresh to ensure all context and state is clean
      window.location.assign('/');
      
    } catch (err) {
      console.error('❌ Login failed:', err)
      setError(err.response?.data?.detail || err.response?.data?.message || 'Login failed')
      setLoading(false)
    }
    // Don't set loading false on success - let navigation unmount component
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-100 px-4">
      <div className="max-w-md w-full bg-white p-8 rounded-xl shadow-lg space-y-6">
        {/* Header */}
        <div className="text-center">
          <h2 className="text-2xl font-bold">Welcome Back 👋</h2>
          <p className="text-gray-600">Log in to access your dashboard</p>
        </div>

        {/* Error Block */}
        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative">
            <span className="block sm:inline">{error}</span>
            <button 
              onClick={() => setError(null)}
              className="absolute top-0 bottom-0 right-0 px-4 py-3"
            >
              <span className="text-2xl">&times;</span>
            </button>
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleLogin} className="space-y-4">
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-400 outline-none disabled:bg-gray-100 disabled:cursor-not-allowed"
            required
            disabled={loading}
            autoComplete="email"
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-400 outline-none disabled:bg-gray-100 disabled:cursor-not-allowed"
            required
            disabled={loading}
            autoComplete="current-password"
          />

          <button
            type="submit"
            disabled={loading}
            className={`w-full px-4 py-2 rounded-lg text-white font-medium transition-all duration-200 ${
              loading
                ? 'bg-blue-400 cursor-not-allowed'
                : 'bg-blue-600 hover:bg-blue-700 active:scale-95'
            }`}
          >
            {loading ? (
              <span className="flex items-center justify-center">
                <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Logging in...
              </span>
            ) : (
              'Login'
            )}
          </button>
        </form>

        {/* Register Redirect */}
        <div className="text-sm text-gray-500 text-center">
          Don't have an account?{' '}
          <Link to="/register" className="text-blue-600 hover:text-blue-700 hover:underline font-medium">
            Register
          </Link>
        </div>
      </div>
    </div>
  )
}
