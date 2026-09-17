/** Hook for managing conversation state in admin panel. */

import { useEffect, useState, useRef } from "react";
import { api, ApiError } from "@/lib/api";
import type { Conversation } from "@/lib/types/conversation";

export function useAdminConversation(conversationId: string | null) {
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isInitialLoadRef = useRef(true);

  const loadConversation = async (isPolling = false) => {
    if (!conversationId) {
      return;
    }

    try {
      // Only set isLoading for initial load, not for polling
      if (isInitialLoadRef.current && !isPolling) {
        setIsLoading(true);
      } else if (isPolling) {
        setIsRefreshing(true);
      }
      setError(null);
      const data = await api.getAdminConversation(conversationId);
      setConversation(data);
      isInitialLoadRef.current = false;
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to load conversation");
      }
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    if (!conversationId) {
      return;
    }

    isInitialLoadRef.current = true;
    loadConversation(false);
    
    // Poll for status updates every 10 seconds (less aggressive)
    const interval = setInterval(() => {
      loadConversation(true);
    }, 10000);

    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  return {
    conversation,
    isLoading,
    isRefreshing,
    error,
    refresh: () => loadConversation(false),
  };
}
