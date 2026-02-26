const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

type TokenResponse = {
  access_token: string;
  token_type: string;
};

export async function login(username: string, password: string): Promise<TokenResponse> {
  const response = await fetch(`${API_BASE}/v1/auth/token`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ username, password })
  });

  if (!response.ok) {
    throw new Error('Authentication failed');
  }

  return (await response.json()) as TokenResponse;
}

export async function ingestSyntheticEvent(token: string): Promise<void> {
  const features = Array.from({ length: 8 }, () => Math.random() * 2 - 1);
  const payload = {
    tenant_id: 'tenant-alpha',
    source: 'dashboard',
    event_type: 'transaction',
    payload: {
      channel: 'web',
      amount: Math.floor(Math.random() * 10000)
    },
    features
  };

  const response = await fetch(`${API_BASE}/v1/events/ingest`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    throw new Error('Event ingestion failed');
  }
}
