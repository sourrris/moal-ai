import { describe, expect, it } from 'vitest';

import { wsEnvelopeSchema } from '../websocket';

describe('wsEnvelopeSchema', () => {
  it('parses ALERT_CREATED envelopes', () => {
    const parsed = wsEnvelopeSchema.parse({
      type: 'ALERT_CREATED',
      occurred_at: '2026-01-01T00:00:00Z',
      data: {
        alert_id: 'abc-123',
        event_id: 'evt-1',
        tenant_id: 'tenant-alpha',
        severity: 'critical',
        model_name: 'risk_autoencoder',
        model_version: '20260101000000',
        anomaly_score: 3.2,
        threshold: 1.8,
        created_at: '2026-01-01T00:00:00Z'
      }
    });

    expect(parsed.type).toBe('ALERT_CREATED');
    expect(parsed.data.severity).toBe('critical');
  });
});
