import { z } from 'zod';

import { API_BASE_URL } from '../lib/constants';
import { buildQueryString } from '../lib/query';

type HttpOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  token?: string;
  query?: Record<string, string | number | undefined | null>;
  body?: unknown;
  credentials?: RequestCredentials;
  retries?: number;
  headers?: Record<string, string>;
};

class RequestError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'RequestError';
    this.status = status;
  }
}

async function delay(ms: number) {
  await new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

export async function requestJson<T>(
  path: string,
  schema: z.ZodSchema<T>,
  options: HttpOptions = {}
): Promise<T> {
  const method = options.method ?? 'GET';
  const query = buildQueryString(options.query ?? {});
  const url = `${API_BASE_URL}${path}${query}`;
  const retries = options.retries ?? (method === 'GET' ? 2 : 0);

  let attempt = 0;
  while (true) {
    const response = await fetch(url, {
      method,
      credentials: options.credentials,
      headers: {
        'Content-Type': 'application/json',
        ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
        ...(options.headers ?? {})
      },
      body: options.body ? JSON.stringify(options.body) : undefined
    });

    if (!response.ok) {
      if (attempt < retries && response.status >= 500) {
        attempt += 1;
        await delay(250 * 2 ** attempt);
        continue;
      }
      let message = `Request failed (${response.status}): ${response.statusText}`;
      try {
        const payload = await response.json();
        if (typeof payload?.detail === 'string' && payload.detail.trim().length > 0) {
          message = payload.detail;
        }
      } catch {
        // Preserve the default message when the response is not JSON.
      }
      throw new RequestError(response.status, message);
    }

    const payload = await response.json();
    return schema.parse(payload);
  }
}
