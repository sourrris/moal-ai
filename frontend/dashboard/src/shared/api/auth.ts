import { z } from 'zod';

import { requestJson } from './http';

const tokenResponseSchema = z.object({
  access_token: z.string(),
  token_type: z.string()
});

export async function login(username: string, password: string) {
  return requestJson('/api/auth/token', tokenResponseSchema, {
    method: 'POST',
    body: { username, password }
  });
}

export async function register(username: string, password: string) {
  return requestJson('/api/auth/register', tokenResponseSchema, {
    method: 'POST',
    body: { username, password }
  });
}
