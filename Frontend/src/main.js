import './assets/main.css'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'

import { createApp } from 'vue'
import App from './App.vue'
import { sessionManager, setupCleanup } from './services/sessionManager.js'

const app = createApp(App)

/**
 * Initialize session before mounting app
 * This ensures every user gets a unique session ID
 */
async function initializeApp() {
  try {
    console.log('🚀 Initializing app...');
    
    // Create/restore session
    const sessionId = await sessionManager.init();
    console.log('📍 Session ID:', sessionId);
    
    // Setup cleanup handlers
    setupCleanup();
    
    // Provide session manager to all components
    app.provide('sessionManager', sessionManager);
    
    // Mount the app
    app.mount('#app');
    console.log('✅ App mounted successfully');
    
  } catch (error) {
    console.error('❌ Failed to initialize app:', error);
    // Show error to user
    document.body.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: center; height: 100vh; background: #f5f5f5; font-family: Arial, sans-serif;">
        <div style="text-align: center; background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
          <h1 style="color: #d32f2f; margin-bottom: 16px;">Connection Error</h1>
          <p style="color: #666; margin-bottom: 16px;">Failed to initialize session. Please check your connection.</p>
          <button onclick="location.reload()" style="padding: 10px 20px; background: #1976d2; color: white; border: none; border-radius: 4px; cursor: pointer;">
            Retry
          </button>
        </div>
      </div>
    `;
  }
}

// Start the app
initializeApp();

