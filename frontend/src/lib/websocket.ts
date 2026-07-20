import type {
  WebSocketMessage,
  WebSocketMessageType,
  QueryProgressPayload,
  QueryResultPayload,
  NotificationPayload,
} from "@/types";

// ============================================================
// WebSocket Client with auto-reconnect & event emitter
// ============================================================

type EventCallback<T = unknown> = (payload: T) => void;

interface EventEmitter {
  on<T = unknown>(event: string, callback: EventCallback<T>): void;
  off<T = unknown>(event: string, callback: EventCallback<T>): void;
  emit<T = unknown>(event: string, payload: T): void;
}

function createEventEmitter(): EventEmitter {
  const listeners = new Map<string, Set<EventCallback>>();

  return {
    on<T = unknown>(event: string, callback: EventCallback<T>) {
      if (!listeners.has(event)) {
        listeners.set(event, new Set());
      }
      listeners.get(event)!.add(callback as EventCallback);
    },
    off<T = unknown>(event: string, callback: EventCallback<T>) {
      listeners.get(event)?.delete(callback as EventCallback);
    },
    emit<T = unknown>(event: string, payload: T) {
      listeners.get(event)?.forEach((cb) => {
        try {
          cb(payload);
        } catch (error) {
          console.error(`[WS] Error in event handler for "${event}":`, error);
        }
      });
    },
  };
}

export type ConnectionState =
  | "disconnected"
  | "connecting"
  | "connected"
  | "reconnecting";

export class WebSocketClient {
  private ws: WebSocket | null = null;
  private emitter: EventEmitter;
  private url: string;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 10;
  private baseReconnectDelay: number = 1000;
  private maxReconnectDelay: number = 30000;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private heartbeatInterval: number = 30000;
  private _state: ConnectionState = "disconnected";

  constructor(url?: string) {
    this.url = url || this.buildUrl();
    this.emitter = createEventEmitter();
  }

  private buildUrl(): string {
    if (typeof window === "undefined") return "";
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/api/v1/ws`;
  }

  // ---- Connection state ----
  get state(): ConnectionState {
    return this._state;
  }

  private setState(state: ConnectionState): void {
    this._state = state;
    this.emitter.emit("state_change", state);
  }

  // ---- Connect ----
  connect(): void {
    if (
      this.ws?.readyState === WebSocket.OPEN ||
      this.ws?.readyState === WebSocket.CONNECTING
    ) {
      return;
    }

    this.setState("connecting");

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this.setState("connected");
        this.reconnectAttempts = 0;
        this.startHeartbeat();
        this.emitter.emit("connected", null);
        console.log("[WS] Connected to", this.url);
      };

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          this.handleMessage(message);
        } catch {
          console.warn("[WS] Failed to parse message:", event.data);
        }
      };

      this.ws.onclose = (event) => {
        this.stopHeartbeat();
        this.setState("disconnected");
        this.emitter.emit("disconnected", { code: event.code, reason: event.reason });

        if (!event.wasClean) {
          this.scheduleReconnect();
        }
      };

      this.ws.onerror = (error) => {
        console.error("[WS] Error:", error);
        this.emitter.emit("error", error);
      };
    } catch (error) {
      console.error("[WS] Connection failed:", error);
      this.setState("disconnected");
      this.scheduleReconnect();
    }
  }

  // ---- Disconnect ----
  disconnect(): void {
    this.clearReconnectTimer();
    this.stopHeartbeat();

    if (this.ws) {
      this.ws.onclose = null; // Prevent auto-reconnect
      this.ws.close(1000, "Client disconnect");
      this.ws = null;
    }

    this.setState("disconnected");
  }

  // ---- Send message ----
  send(type: WebSocketMessageType, payload: unknown): void {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      console.warn("[WS] Cannot send, not connected");
      return;
    }

    const message: WebSocketMessage = {
      type,
      payload,
      timestamp: new Date().toISOString(),
      id: crypto.randomUUID(),
    };

    this.ws.send(JSON.stringify(message));
  }

  // ---- Message handler ----
  private handleMessage(message: WebSocketMessage): void {
    switch (message.type) {
      case "query_progress":
        this.emitter.emit(
          "query_progress",
          message.payload as QueryProgressPayload
        );
        break;

      case "query_result":
        this.emitter.emit(
          "query_result",
          message.payload as QueryResultPayload
        );
        break;

      case "notification":
        this.emitter.emit(
          "notification",
          message.payload as NotificationPayload
        );
        break;

      case "connection_established":
        console.log("[WS] Connection established:", message.payload);
        break;

      case "pong":
        // Heartbeat response
        break;

      default:
        this.emitter.emit("message", message);
    }
  }

  // ---- Reconnection with exponential backoff ----
  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error(
        `[WS] Max reconnect attempts (${this.maxReconnectAttempts}) reached`
      );
      this.emitter.emit("reconnect_failed", null);
      return;
    }

    this.setState("reconnecting");

    const delay = Math.min(
      this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts) +
        Math.random() * 1000,
      this.maxReconnectDelay
    );

    console.log(
      `[WS] Reconnecting in ${Math.round(delay)}ms (attempt ${this.reconnectAttempts + 1}/${this.maxReconnectAttempts})`
    );

    this.reconnectTimer = setTimeout(() => {
      this.reconnectAttempts++;
      this.connect();
    }, delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  // ---- Heartbeat ----
  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      this.send("ping", {});
    }, this.heartbeatInterval);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  // ---- Event subscription ----
  onQueryProgress(callback: EventCallback<QueryProgressPayload>): () => void {
    this.emitter.on("query_progress", callback);
    return () => this.emitter.off("query_progress", callback);
  }

  onQueryResult(callback: EventCallback<QueryResultPayload>): () => void {
    this.emitter.on("query_result", callback);
    return () => this.emitter.off("query_result", callback);
  }

  onNotification(callback: EventCallback<NotificationPayload>): () => void {
    this.emitter.on("notification", callback);
    return () => this.emitter.off("notification", callback);
  }

  onStateChange(callback: EventCallback<ConnectionState>): () => void {
    this.emitter.on("state_change", callback);
    return () => this.emitter.off("state_change", callback);
  }

  onConnected(callback: EventCallback<null>): () => void {
    this.emitter.on("connected", callback);
    return () => this.emitter.off("connected", callback);
  }

  onDisconnected(
    callback: EventCallback<{ code: number; reason: string }>
  ): () => void {
    this.emitter.on("disconnected", callback);
    return () => this.emitter.off("disconnected", callback);
  }

  onError(callback: EventCallback<unknown>): () => void {
    this.emitter.on("error", callback);
    return () => this.emitter.off("error", callback);
  }
}

// Singleton instance
let wsInstance: WebSocketClient | null = null;

export function getWebSocketClient(): WebSocketClient {
  if (!wsInstance) {
    wsInstance = new WebSocketClient();
  }
  return wsInstance;
}

export function connectWebSocket(): WebSocketClient {
  const client = getWebSocketClient();
  client.connect();
  return client;
}

export function disconnectWebSocket(): void {
  if (wsInstance) {
    wsInstance.disconnect();
  }
}
