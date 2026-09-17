/** Hook for managing admin WebSocket connection. */

import { useEffect, useRef, useState, useCallback } from "react";
import { AdminWebSocketClient, type AdminWebSocketMessage } from "@/lib/adminWebSocket";
import { getAdminToken } from "@/lib/auth";

export function useAdminWebSocket() {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const wsClientRef = useRef<AdminWebSocketClient | null>(null);
  const conversationUpdateHandlersRef = useRef<Set<(conversation: any) => void>>(
    new Set()
  );
  const escalationHandlersRef = useRef<Set<(conversation: any, reason?: string) => void>>(
    new Set()
  );
  const statsUpdateHandlersRef = useRef<Set<(stats: any) => void>>(new Set());

  useEffect(() => {
    // Check if we have a token before attempting connection
    const token = getAdminToken();
    
    if (!token) {
      // No token available, skip WebSocket connection
      console.warn("useAdminWebSocket: No admin token, skipping WebSocket connection");
      return;
    }

    const client = new AdminWebSocketClient();
    wsClientRef.current = client;

    const unsubscribeConnection = client.onConnectionStateChange(setIsConnected);
    const unsubscribeError = client.onError((err) => {
      // Only set error if it's not a missing token issue
      if (!err.message.includes("No token")) {
        setError(err);
      }
    });

    // Handle different message types
    const unsubscribeMessage = client.onMessage((message: AdminWebSocketMessage) => {
      if (message.type === "conversation_updated" && message.conversation) {
        conversationUpdateHandlersRef.current.forEach((handler) => {
          try {
            handler(message.conversation!);
          } catch (err) {
            console.error("Error in conversation update handler:", err);
          }
        });
      } else if (
        message.type === "conversation_escalated" &&
        message.conversation
      ) {
        escalationHandlersRef.current.forEach((handler) => {
          try {
            handler(message.conversation!, message.escalation_reason);
          } catch (err) {
            console.error("Error in escalation handler:", err);
          }
        });
      } else if (message.type === "stats_updated" && message.stats) {
        statsUpdateHandlersRef.current.forEach((handler) => {
          try {
            handler(message.stats!);
          } catch (err) {
            console.error("Error in stats update handler:", err);
          }
        });
      }
    });

    client.connect().catch((err) => {
      // Don't set error for missing token cases
      if (!err.message?.includes("No token")) {
        setError(err);
      }
    });

    return () => {
      unsubscribeConnection();
      unsubscribeError();
      unsubscribeMessage();
      client.disconnect();
    };
  }, []);

  const onConversationUpdate = useCallback(
    (callback: (conversation: any) => void) => {
      conversationUpdateHandlersRef.current.add(callback);
      return () => {
        conversationUpdateHandlersRef.current.delete(callback);
      };
    },
    []
  );

  const onNewEscalation = useCallback(
    (callback: (conversation: any, reason?: string) => void) => {
      escalationHandlersRef.current.add(callback);
      return () => {
        escalationHandlersRef.current.delete(callback);
      };
    },
    []
  );

  const onStatsUpdate = useCallback((callback: (stats: any) => void) => {
    statsUpdateHandlersRef.current.add(callback);
    return () => {
      statsUpdateHandlersRef.current.delete(callback);
    };
  }, []);

  return {
    isConnected,
    error,
    onConversationUpdate,
    onNewEscalation,
    onStatsUpdate,
  };
}

