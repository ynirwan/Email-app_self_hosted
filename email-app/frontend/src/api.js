// frontend/src/api.js
import axios from "axios";

const getBaseURL = () => {
  // Priority 1: Use VITE_API_BASE_URL from .env if configured
  if (import.meta.env.VITE_API_BASE_URL) {
    console.log("📡 Using configured API URL:", import.meta.env.VITE_API_BASE_URL);
    return import.meta.env.VITE_API_BASE_URL;
  }
  
  // Priority 2: For Replit environments, auto-detect and construct backend URL
  if (window.location.hostname.includes('replit.dev')) {
    const protocol = window.location.protocol;
    const host = window.location.hostname;
    // Remove port if present, keep only the hostname
    const baseHost = host.split(':')[0];
    // Replit routes :8000 through the same host automatically
    const backendUrl = `${protocol}//${baseHost}:8000/api`;
    console.log("🔗 Auto-detected Replit API URL:", backendUrl);
    return backendUrl;
  }
  
  // Priority 3: Fallback to localhost for development
  console.log("🏠 Using localhost API URL");
  return "http://localhost:8000/api";
};

const API = axios.create({
  baseURL: getBaseURL(),
});

// ✅ SIMPLIFIED - REMOVED all slash manipulation logic
API.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
      console.log("🔑 Token attached to request:", config.url);
    }
    return config;
  },
  (error) => Promise.reject(error),
);

// Response interceptor to handle 401 errors
API.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      console.warn("🚫 Unauthorized - clearing token and redirecting to login");
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  },
);

export default API;
