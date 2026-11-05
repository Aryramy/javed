/**
 * Provider client service for JAVED Multi-Provider Inference Registry.
 */

import type { ProviderBindingResponse, ProviderSelectionRequest, ProvidersResponse } from '../types/chat';

const getBaseUrl = (): string => {
  if (typeof window !== 'undefined' && window.location?.origin && window.location.origin !== 'null') {
    return window.location.origin;
  }
  return 'http://localhost:5173';
};

export const providerService = {
  /**
   * Fetch sanitized provider list, health status, and configured models.
   */
  async getProviders(): Promise<ProvidersResponse> {
    const res = await fetch(`${getBaseUrl()}/api/v1/providers`, {
      headers: {
        Accept: 'application/json',
      },
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Failed to load providers (HTTP ${res.status}): ${errText}`);
    }

    return (await res.json()) as ProvidersResponse;
  },

  /**
   * Atomically validate provider, resolve effective backend model, and bind thread.
   */
  async bindProvider(payload: ProviderSelectionRequest): Promise<ProviderBindingResponse> {
    const res = await fetch(`${getBaseUrl()}/api/v1/providers/bind-thread`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      let errDetail = `Provider bind failed (HTTP ${res.status})`;
      try {
        const json = await res.json();
        if (json?.detail) errDetail = json.detail;
      } catch {
        // ignore
      }
      throw new Error(errDetail);
    }

    return (await res.json()) as ProviderBindingResponse;
  },
};

