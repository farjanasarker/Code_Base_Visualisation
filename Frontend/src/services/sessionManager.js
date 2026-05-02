/**
 * Session Manager for Multi-User Code Analysis
 * Handles session creation, tracking, and cleanup for 500+ concurrent users
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const SESSION_ID_KEY = 'bmad_session_id';
const SESSION_CREATED_AT = 'bmad_session_created';

class SessionManager {
  constructor() {
    this.sessionId = null;
    this.isInitialized = false;
  }

  /**
   * Initialize session on app startup
   * Creates new session or restores from sessionStorage
   */
  async init() {
    try {
      // Try to restore existing session from sessionStorage
      let existingSessionId = sessionStorage.getItem(SESSION_ID_KEY);
      
      if (existingSessionId) {
        console.log('✅ Restored session:', existingSessionId);
        this.sessionId = existingSessionId;
        this.isInitialized = true;
        return existingSessionId;
      }

      // Create new session
      const response = await fetch(`${API_BASE}/start-session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      this.sessionId = data.session_id;

      // Store in sessionStorage (automatically cleared when browser closes)
      sessionStorage.setItem(SESSION_ID_KEY, this.sessionId);
      sessionStorage.setItem(SESSION_CREATED_AT, new Date().toISOString());

      console.log('✅ New session created:', this.sessionId);
      this.isInitialized = true;
      
      return this.sessionId;
    } catch (error) {
      console.error('❌ Failed to initialize session:', error);
      throw error;
    }
  }

  /**
   * Get current session ID
   */
  getSessionId() {
    return this.sessionId || sessionStorage.getItem(SESSION_ID_KEY);
  }

  /**
   * Make API call with session ID header
   * All requests to backend should use this method
   */
  async apiCall(endpoint, options = {}) {
    const sessionId = this.getSessionId();
    
    if (!sessionId) {
      throw new Error('No session ID available. Call init() first.');
    }

    // Build headers - don't set Content-Type for FormData (browser will set it)
    const headers = {
      'X-Session-ID': sessionId,
      ...options.headers,
    };

    // Only set Content-Type if not FormData
    if (!(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    // Handle common HTTP errors
    if (!response.ok) {
      if (response.status === 401) {
        // Unauthorized - session expired or missing header
        this.clearSession();
        throw new Error('Session expired. Please refresh the page.');
      }
      if (response.status === 404) {
        throw new Error('Session not found. Starting new session...');
      }
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return response;
  }

  /**
   * Upload file with session tracking
   */
  async uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await this.apiCall('/upload', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();
      console.log('✅ File uploaded successfully:', data);
      return data;
    } catch (error) {
      console.error('❌ Upload failed:', error);
      throw error;
    }
  }

  /**
   * Fetch tier1 graph for current session
   */
  async fetchTier1() {
    try {
      const response = await this.apiCall('/graph/tier1');
      return await response.json();
    } catch (error) {
      console.error('❌ Failed to fetch tier1:', error);
      throw error;
    }
  }

  /**
   * Fetch tier2 graph for a module
   */
  async fetchTier2(moduleName) {
    try {
      const response = await this.apiCall(`/graph/tier2/${encodeURIComponent(moduleName)}`);
      return await response.json();
    } catch (error) {
      console.error('❌ Failed to fetch tier2:', error);
      throw error;
    }
  }

  /**
   * Fetch tier3 graph for a file
   */
  async fetchTier3(filePath) {
    try {
      const response = await this.apiCall(`/graph/tier3?file_path=${encodeURIComponent(filePath)}`);
      return await response.json();
    } catch (error) {
      console.error('❌ Failed to fetch tier3:', error);
      throw error;
    }
  }

  /**
   * Get session info
   */
  async getSessionInfo() {
    try {
      const response = await this.apiCall('/sessions/info');
      return await response.json();
    } catch (error) {
      console.error('❌ Failed to get session info:', error);
      throw error;
    }
  }

  /**
   * End session and cleanup
   * Called when browser closes or user logs out
   */
  async endSession() {
    try {
      const sessionId = this.getSessionId();
      
      if (!sessionId) {
        console.warn('⚠️ No session to end');
        return;
      }

      // Use sendBeacon for reliable delivery even if page is closing
      const beaconData = JSON.stringify({ session_id: sessionId });
      navigator.sendBeacon(`${API_BASE}/end-session`, beaconData);
      
      console.log('✅ Session end signal sent:', sessionId);
      this.clearSession();
    } catch (error) {
      console.error('❌ Error ending session:', error);
      // Still clear local session even if server call fails
      this.clearSession();
    }
  }

  /**
   * Clear local session data
   */
  clearSession() {
    this.sessionId = null;
    this.isInitialized = false;
    sessionStorage.removeItem(SESSION_ID_KEY);
    sessionStorage.removeItem(SESSION_CREATED_AT);
    console.log('✅ Local session cleared');
  }

  /**
   * Check if session is still valid
   */
  isSessionValid() {
    return this.isInitialized && this.sessionId !== null;
  }
}

// Create singleton instance
const sessionManager = new SessionManager();

/**
 * Setup beforeunload handler to cleanup on browser close
 * This ensures server cleanup even if user closes browser abruptly
 */
function setupCleanup() {
  window.addEventListener('beforeunload', () => {
    if (sessionManager.isSessionValid()) {
      sessionManager.endSession();
    }
  });

  // Also handle page visibility changes
  document.addEventListener('visibilitychange', () => {
    if (document.hidden === false) {
      // Page became visible again - session still valid
      console.log('Page visible again, session:', sessionManager.getSessionId());
    }
  });
}

export { sessionManager, setupCleanup };
