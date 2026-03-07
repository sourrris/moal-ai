export type AegisWsOptions = {
  url: string;
  getJwt: () => string | null;
  channels?: string[];
  onMessage: (event: MessageEvent<string>) => void;
  onError?: (error: Event) => void;
  maxBackoffMs?: number;
};

export class AegisWebSocketClient {
  private readonly options: AegisWsOptions;
  private socket: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private backoffMs = 500;

  constructor(options: AegisWsOptions) {
    this.options = options;
  }

  connect(): void {
    const jwt = this.options.getJwt();
    if (!jwt) {
      throw new Error('JWT is required for websocket connection');
    }

    const channels = (this.options.channels ?? ['alerts']).join(',');
    const url = new URL(this.options.url);
    url.searchParams.set('token', jwt);
    url.searchParams.set('channels', channels);

    this.socket = new WebSocket(url.toString());
    this.socket.onmessage = this.options.onMessage;
    this.socket.onerror = (event) => this.options.onError?.(event);
    this.socket.onopen = () => {
      this.backoffMs = 500;
    };
    this.socket.onclose = () => {
      this.scheduleReconnect();
    };
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.socket?.close();
    this.socket = null;
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) {
      return;
    }

    const maxBackoff = this.options.maxBackoffMs ?? 30_000;
    const jitter = Math.floor(Math.random() * 250);
    const waitMs = Math.min(this.backoffMs + jitter, maxBackoff);

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, waitMs);

    this.backoffMs = Math.min(this.backoffMs * 2, maxBackoff);
  }
}
