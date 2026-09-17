/** Admin WebSocket client for real-time admin dashboard updates. */

import { getWebSocketBaseUrl } from "./backendUrls";
import { getAdminToken } from "./auth";
import type { Conversation } from "./types/conversation";

type AdminMessageHandler = (message: AdminWebSocketMessage) => void;
type ErrorHandler = (error: Error) => void;
type ConnectionStateHandler = (connected: boolean) => void;


export interface AdminWebSocketMessage {
  type:
    | "connected"
    | "conversation_updated"
    | "conversation_escalated"
    | "stats_updated"
    | "ping"
    | "pong"
    | "error";
  conversation?: Conversation;
  escalation_reason?: string;
  stats?: {
    total_conversations: number;
    needs_human: number;
    human_active: number;
    ai_active: number;
    closed: number;
  };
  admin_id?: string;
  message?: string;
  timestamp?: string;
}

export class AdminWebSocketClient {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private heartbeatInterval: NodeJS.Timeout | null = null;
  private messageHandlers: AdminMessageHandler[] = [];
  private errorHandlers: ErrorHandler[] = [];
  private connectionStateHandlers: ConnectionStateHandler[] = [];
  private isConnecting = false;
  private isConnected = false;

  connect(): Promise<void> {
    if (this.isConnecting || this.isConnected) {
      return Promise.resolve();
    }

    const token = getAdminToken();
    // Don't attempt connection if token is missing
    if (!token) {
      console.warn("Admin WebSocket: No token available, skipping connection");
      return Promise.resolve();
    }

    return new Promise((resolve, reject) => {
      this.isConnecting = true;
      const wsUrl = `${getWebSocketBaseUrl()}/ws/admin?token=${encodeURIComponent(token)}`;

      try {
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
          this.isConnecting = false;
          this.isConnected = true;
          this.reconnectAttempts = 0;
          this.notifyConnectionState(true);
          this.startHeartbeat();
          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            const message: AdminWebSocketMessage = JSON.parse(event.data);
            this.handleMessage(message);
          } catch (error) {
            console.error("Failed to parse Admin WebSocket message:", error);
          }
        };

        this.ws.onerror = (error) => {
          this.isConnecting = false;
          this.notifyError(new Error("Admin WebSocket connection error"));
          reject(error);
        };

        this.ws.onclose = (event) => {
          this.isConnected = false;
          this.isConnecting = false;
          this.stopHeartbeat();
          this.notifyConnectionState(false);

          // Only attempt to reconnect if we have a token and it wasn't a normal closure
          const token = getAdminToken();
          if (token && event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            setTimeout(() => {
              this.connect().catch(() => {
                // Reconnection failed, will retry
              });
            }, this.reconnectDelay * this.reconnectAttempts);
          }
        };
      } catch (error) {
        this.isConnecting = false;
        reject(error);
      }
    });
  }

  disconnect(): void {
    this.stopHeartbeat();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.isConnected = false;
    this.notifyConnectionState(false);
  }

  onMessage(handler: AdminMessageHandler): () => void {
    this.messageHandlers.push(handler);
    return () => {
      const index = this.messageHandlers.indexOf(handler);
      if (index > -1) {
        this.messageHandlers.splice(index, 1);
      }
    };
  }

  onError(handler: ErrorHandler): () => void {
    this.errorHandlers.push(handler);
    return () => {
      const index = this.errorHandlers.indexOf(handler);
      if (index > -1) {
        this.errorHandlers.splice(index, 1);
      }
    };
  }

  onConnectionStateChange(handler: ConnectionStateHandler): () => void {
    this.connectionStateHandlers.push(handler);
    return () => {
      const index = this.connectionStateHandlers.indexOf(handler);
      if (index > -1) {
        this.connectionStateHandlers.splice(index, 1);
      }
    };
  }

  private handleMessage(message: AdminWebSocketMessage): void {
    // Handle ping/pong
    if (message.type === "ping") {
      if (this.ws && this.isConnected) {
        this.ws.send(JSON.stringify({ type: "pong" }));
      }
      return;
    }

    // Notify all handlers
    this.messageHandlers.forEach((handler) => {
      try {
        handler(message);
      } catch (error) {
        console.error("Error in admin message handler:", error);
      }
    });
  }

  private notifyError(error: Error): void {
    this.errorHandlers.forEach((handler) => {
      try {
        handler(error);
      } catch (err) {
        console.error("Error in error handler:", err);
      }
    });
  }

  private notifyConnectionState(connected: boolean): void {
    this.connectionStateHandlers.forEach((handler) => {
      try {
        handler(connected);
      } catch (error) {
        console.error("Error in connection state handler:", error);
      }
    });
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    // Heartbeat is handled by server ping/pong
  }

  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  get connected(): boolean {
    return this.isConnected;
  }
}

