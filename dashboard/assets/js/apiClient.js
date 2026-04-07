/**
 * Mories Central API Client (v2)
 * - Auto-detects API base URL from current origin/port
 * - Safe URL joining (handles trailing/leading slashes)
 * - Centralized auth token injection (Bearer JWT)
 * - Standardized error handling with status-specific behaviors
 */

class ApiClient {
  constructor() {
    this.baseUrl = this._detectBaseUrl();
    this.tokenKey = 'mories_access_token';
  }

  /** Auto-detect API base URL based on current page origin */
  _detectBaseUrl() {
    if (window.API_BASE) return window.API_BASE;
    const origin = window.location.origin;
    const port = window.location.port;
    // If served from the API server itself, standard ports, or nginx proxy (8080), use same origin
    if (port === '5001' || port === '' || port === '8080' || port === '80') {
      return `${origin}/api`;
    }
    // Otherwise, assume API is on localhost:5001
    return 'http://localhost:5001/api';
  }

  /** Join base URL and endpoint safely, avoiding double slashes */
  _joinUrl(endpoint) {
    if (endpoint.startsWith('http')) return endpoint;
    const base = this.baseUrl.replace(/\/+$/, '');
    const path = endpoint.replace(/^\/+/, '');
    return `${base}/${path}`;
  }

  getHeaders(customHeaders = {}) {
    const headers = {
      'Content-Type': 'application/json',
      ...customHeaders
    };
    
    const token = localStorage.getItem(this.tokenKey);
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    
    return headers;
  }

  async _request(method, endpoint, body = null, options = {}) {
    const url = this._joinUrl(endpoint);
    
    const fetchOptions = {
      method,
      headers: this.getHeaders(options.headers || {}),
    };

    if (body) {
      fetchOptions.body = typeof body === 'string' ? body : JSON.stringify(body);
    }

    try {
      const response = await fetch(url, fetchOptions);
      
      let data = null;
      // Handle 204 No Content safely
      if (response.status !== 204) {
        const contentType = response.headers.get("content-type");
        if (contentType && contentType.indexOf("application/json") !== -1) {
          data = await response.json();
        } else {
          data = await response.text();
        }
      }

      if (!response.ok) {
        this._handleError(response.status, data);
        const errorMsg = data && data.message ? data.message : `API request failed with status ${response.status}`;
        throw new Error(errorMsg);
      }
      
      return data;
      
    } catch (error) {
      console.error(`[ApiClient Error] ${method} ${url}:`, error);
      throw error;
    }
  }

  _handleError(status, data) {
    if (status === 401) {
      console.warn("[ApiClient] 401 Unauthorized — token may be expired or missing.");
    }
    if (status === 403) {
      console.warn("[ApiClient] 403 Forbidden.", data);
    }
    if (status === 429) {
      console.warn("[ApiClient] 429 Rate limit exceeded.");
    }
  }

  async rawRequest(method, endpoint, body = null, options = {}) {
    const url = this._joinUrl(endpoint);
    const fetchOptions = {
      method,
      headers: this.getHeaders(options.headers || {}),
    };
    if (body) {
      fetchOptions.body = typeof body === 'string' ? body : JSON.stringify(body);
    }
    return fetch(url, fetchOptions);
  }

  async get(endpoint, options = {}) {
    return this._request('GET', endpoint, null, options);
  }

  async post(endpoint, body, options = {}) {
    return this._request('POST', endpoint, body, options);
  }

  async put(endpoint, body, options = {}) {
    return this._request('PUT', endpoint, body, options);
  }

  async delete(endpoint, options = {}) {
    return this._request('DELETE', endpoint, null, options);
  }
}

// Export singleton instance
window.moriesApi = new ApiClient();
