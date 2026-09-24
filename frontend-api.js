/**
 * GeoIntel Frontend API Client
 * Handles all communication with backend REST API
 */

// Use Vercel proxy (/api) in production to avoid CORS — Vercel forwards to Railway.
// Use localhost directly in development.
const API_BASE = window.GEOINTEL_API_BASE
  || (window.location.hostname === 'localhost' ? 'http://localhost:5000/api' : '/api');

class GeoIntelAPI {
  /**
   * Fetch all active crises
   */
  static async getCrises(options = {}) {
    const params = new URLSearchParams();
    if (options.type) params.append('type', options.type);
    if (options.min_severity) params.append('min_severity', options.min_severity);
    if (options.days) params.append('days', options.days);

    try {
      const response = await fetch(`${API_BASE}/crises?${params}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching crises:', error);
      return { crises: [], count: 0, error: error.message };
    }
  }

  /**
   * Build the URL for the bulk crisis export endpoint (CSV/JSON download of
   * whatever filters are passed) — public and rate-limited (see backend's
   * GET /api/crises/export), not fetched here since the caller triggers a
   * browser download from the URL directly rather than reading the body.
   */
  static getExportUrl(options = {}) {
    const params = new URLSearchParams();
    params.append('format', options.format || 'csv');
    if (options.type) params.append('type', options.type);
    if (options.min_severity) params.append('min_severity', options.min_severity);
    if (options.country) params.append('country', options.country);
    if (options.status) params.append('status', options.status);
    return `${API_BASE}/crises/export?${params}`;
  }

  /**
   * Fetch detailed info on specific crisis
   */
  static async getCrisisDetail(crisisId) {
    try {
      const response = await fetch(`${API_BASE}/crises/${crisisId}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (error) {
      console.error(`Error fetching crisis ${crisisId}:`, error);
      return null;
    }
  }

  /**
   * Update crisis (admin)
   */
  static async updateCrisis(crisisId, data) {
    try {
      const response = await fetch(`${API_BASE}/crises/${crisisId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (error) {
      console.error(`Error updating crisis ${crisisId}:`, error);
      return null;
    }
  }

  /**
   * Fetch all geopolitical actors
   */
  static async getActors() {
    try {
      const response = await fetch(`${API_BASE}/actors`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching actors:', error);
      return { actors: [], count: 0, error: error.message };
    }
  }

  /**
   * Fetch specific actor details
   */
  static async getActor(actorId) {
    try {
      const response = await fetch(`${API_BASE}/actors/${actorId}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (error) {
      console.error(`Error fetching actor ${actorId}:`, error);
      return null;
    }
  }

  /**
   * Fetch all actor relationships
   */
  static async getRelationships(options = {}) {
    const params = new URLSearchParams();
    if (options.type) params.append('type', options.type);

    try {
      const response = await fetch(`${API_BASE}/relationships?${params}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching relationships:', error);
      return { relationships: [], count: 0, error: error.message };
    }
  }

  /**
   * Fetch forecasts for a crisis
   */
  static async getForecasts(crisisId) {
    try {
      const response = await fetch(`${API_BASE}/forecasts/${crisisId}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (error) {
      console.error(`Error fetching forecasts for ${crisisId}:`, error);
      return { forecasts: [], count: 0, error: error.message };
    }
  }

  /**
   * Fetch source reliability analysis for a crisis
   */
  static async getReliability(crisisId) {
    try {
      const response = await fetch(`${API_BASE}/crises/${crisisId}/reliability`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (error) {
      console.error(`Error fetching reliability for ${crisisId}:`, error);
      return { error: error.message };
    }
  }

  /**
   * Fetch news articles
   */
  static async getNews(options = {}) {
    const params = new URLSearchParams();
    if (options.crisis_id) params.append('crisis_id', options.crisis_id);
    if (options.days) params.append('days', options.days);
    if (options.limit) params.append('limit', options.limit);

    try {
      const response = await fetch(`${API_BASE}/news?${params}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching news:', error);
      return { articles: [], count: 0, error: error.message };
    }
  }

  /**
   * Fetch economic data for country
   */
  static async getEconomicData(countryCode) {
    try {
      const response = await fetch(`${API_BASE}/economic/${countryCode}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (error) {
      console.error(`Error fetching economic data for ${countryCode}:`, error);
      return { data: [], count: 0, error: error.message };
    }
  }

  /**
   * Trigger manual data sync (admin)
   */
  static async triggerSync() {
    try {
      const response = await fetch(`${API_BASE}/admin/sync`, {
        method: 'POST',
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (error) {
      console.error('Error triggering sync:', error);
      return { error: error.message };
    }
  }

  /**
   * Get database statistics (admin)
   */
  static async getStats() {
    try {
      const response = await fetch(`${API_BASE}/admin/stats`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching stats:', error);
      return { error: error.message };
    }
  }

  /**
   * Health check
   */
  static async healthCheck() {
    try {
      const response = await fetch(`${API_BASE}/health`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (error) {
      console.error('Health check failed:', error);
      return { status: 'error', error: error.message };
    }
  }

  /**
   * Check if backend is available
   */
  static async isBackendAvailable() {
    const result = await this.healthCheck();
    return result.status === 'ok';
  }
}

// Export for use in other files
if (typeof module !== 'undefined' && module.exports) {
  module.exports = GeoIntelAPI;
}
