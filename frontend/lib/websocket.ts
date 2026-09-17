/** WebSocket client for real-time communication. */

import { getWebSocketBaseUrl } from "./backendUrls";
import type { WebSocketMessage } from "./types/message";

type MessageHandler = (message: WebSocketMessage) => void;
type ErrorHandler = (error: Error) => void;
type ConnectionStateHandler = (connected: boolean) => void;


export class WebSocketClient {
  private ws: WebSocket | null = null;
  private conversationId: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private heartbeatInterval: NodeJS.Timeout | null = null;
  private messageHandlers: MessageHandler[] = [];
  private errorHandlers: ErrorHandler[] = [];
  private connectionStateHandlers: ConnectionStateHandler[] = [];
  private isConnecting = false;
  private isConnected = false;

  constructor(conversationId: string) {
    this.conversationId = conversationId;
  }

  connect(): Promise<void> {
    if (this.isConnecting || this.isConnected) {
      return Promise.resolve();
    }

    return new Promise((resolve, reject) => {
      this.isConnecting = true;
      const wsUrl = `${getWebSocketBaseUrl()}/ws/${this.conversationId}`;

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
            const message: WebSocketMessage = JSON.parse(event.data);
            this.handleMessage(message);
          } catch (error) {
            console.error("Failed to parse WebSocket message:", error);
          }
        };

        this.ws.onerror = (error) => {
          this.isConnecting = false;
          this.notifyError(new Error("WebSocket connection error"));
          reject(error);
        };

        this.ws.onclose = () => {
          this.isConnected = false;
          this.isConnecting = false;
          this.stopHeartbeat();
          this.notifyConnectionState(false);

          // Attempt to reconnect
          if (this.reconnectAttempts < this.maxReconnectAttempts) {
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

  sendMessage(content: string): void {
    if (!this.isConnected || !this.ws) {
      throw new Error("WebSocket is not connected");
    }

    this.ws.send(
      JSON.stringify({
        type: "message",
        content,
        timestamp: new Date().toISOString(),
      })
    );
  }

  sendTyping(): void {
    if (!this.isConnected || !this.ws) {
      return;
    }

    this.ws.send(
      JSON.stringify({
        type: "typing",
      })
    );
  }

  onMessage(handler: MessageHandler): () => void {
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

  private handleMessage(message: WebSocketMessage): void {
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
        console.error("Error in message handler:", error);
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








