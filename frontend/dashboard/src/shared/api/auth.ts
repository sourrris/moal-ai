import { z } from 'zod';

import { requestJson } from './http';

const tokenResponseSchema = z.object({
  access_token: z.string(),
  token_type: z.string()
});

export async function login(username: string, password: string) {
  return requestJson(
    '/v1/auth/token',
    tokenResponseSchema,
    {
      method: 'POST',
      credentials: 'include',
      body: { username, password }
    }
  );
}
