/** Hook for managing WebSocket connection. */

import { useEffect, useRef, useState, useCallback } from "react";
import { WebSocketClient } from "@/lib/websocket";
import type { WebSocketMessage } from "@/lib/types/message";

export function useWebSocket(conversationId: string | null) {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const wsClientRef = useRef<WebSocketClient | null>(null);

  useEffect(() => {
    if (!conversationId) {
      return;
    }

    const client = new WebSocketClient(conversationId);
    wsClientRef.current = client;

    const unsubscribeConnection = client.onConnectionStateChange(setIsConnected);
    const unsubscribeError = client.onError(setError);

    client.connect().catch((err) => {
      setError(err);
    });

    return () => {
      unsubscribeConnection();
      unsubscribeError();
      client.disconnect();
    };
  }, [conversationId]);

  const sendMessage = useCallback((content: string) => {
    if (wsClientRef.current) {
      wsClientRef.current.sendMessage(content);
    }
  }, []);

  const sendTyping = useCallback(() => {
    if (wsClientRef.current) {
      wsClientRef.current.sendTyping();
    }
  }, []);

  return {
    isConnected,
    error,
    sendMessage,
    sendTyping,
  };
}








