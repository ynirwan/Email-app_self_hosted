// frontend/src/api.js
import axios from "axios";

const API = axios.create({
  baseURL:
    "https://5474f674-6074-4eb8-8818-15946bef35a1-00-1y8lhfj74gqcq.pike.replit.dev:8000/api",
});

// Fix 307 Redirects by ensuring trailing slashes for ALL requests (GET, POST, PUT, DELETE)
API.interceptors.request.use(
  (config) => {
    // Check if the URL already has a trailing slash or is an absolute URL with a path that looks like a file
    const hasTrailingSlash = config.url.endsWith('/');
    const isFilePath = config.url.split('/').pop().includes('.');
    
    // TEMPLATE EXCEPTION: The templates endpoint MUST have a trailing slash due to backend routing structure
    const isTemplatesEndpoint = config.url.includes('/templates');

    if (isTemplatesEndpoint && !hasTrailingSlash) {
        config.url += '/';
    } else if (!isTemplatesEndpoint && hasTrailingSlash && config.url !== '/') {
        // REMOVE trailing slash for non-template endpoints to avoid 307 redirects on standard routes
        config.url = config.url.slice(0, -1);
    }
    
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
      console.log("🔑 Token attached to request:", config.url);
    }
    return config;
  },
  (error) => Promise.reject(error)
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
