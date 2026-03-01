import { describe, expect, it } from 'vitest';

import { buildQueryString } from '../query';

describe('buildQueryString', () => {
  it('skips empty values and preserves numeric fields', () => {
    const query = buildQueryString({
      tenant_id: 'tenant-alpha',
      cursor: undefined,
      limit: 20,
      empty: '',
      score_min: 0
    });

    expect(query).toBe('?tenant_id=tenant-alpha&limit=20&score_min=0');
  });
});
