/**
 * GeoIntel Frontend API Client
 * Handles all communication with backend REST API
 */

const API_BASE = 'http://localhost:5000/api';

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
