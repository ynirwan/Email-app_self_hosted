// frontend/src/api.js
import axios from "axios";

const getBaseURL = () => {
  // Priority 1: Use VITE_API_BASE_URL from .env if explicitly configured
  if (import.meta.env.VITE_API_BASE_URL) {
    console.log("📡 Using configured API URL:", import.meta.env.VITE_API_BASE_URL);
    return import.meta.env.VITE_API_BASE_URL;
  }
  
  // Priority 2: Use current hostname with backend port
  // This works for: Replit environments, custom domains, and localhost
  const protocol = window.location.protocol;
  const hostname = window.location.hostname;
  const backendUrl = `${protocol}//${hostname}:8000/api`;
  console.log("🔗 Using current hostname for backend:", backendUrl);
  return backendUrl;
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
