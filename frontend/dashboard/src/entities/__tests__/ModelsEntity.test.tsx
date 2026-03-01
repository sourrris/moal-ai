import { describe, expect, it } from 'vitest';

import { modelsListResponseSchema } from '../models';

describe('modelsListResponseSchema', () => {
  it('accepts numeric-like anomaly rates and coerces them to numbers', () => {
    const parsed = modelsListResponseSchema.parse({
      active_model: {
        model_name: 'risk_autoencoder',
        model_version: '20260301054634',
        feature_dim: 8,
        threshold: 0.95
      },
      items: [
        {
          model_name: 'risk_autoencoder',
          model_version: '20260227160612',
          threshold: 0.5,
          updated_at: '2026-03-01T05:46:34.194083Z',
          inference_count: 3,
          anomaly_rate: '0E-20',
          active: false,
          activate_capable: false,
          source: 'inference_only'
        }
      ]
    });

    expect(parsed.items[0].anomaly_rate).toBe(0);
  });
});
