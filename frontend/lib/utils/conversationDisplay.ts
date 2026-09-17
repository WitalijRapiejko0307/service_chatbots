/** Conversation display utilities for consistent conversation formatting across the app. */

import type { Conversation } from "@/lib/types/conversation";
import { formatRelativeTime } from "./timeFormat";

/**
 * Get display ID for a conversation.
 * In list view: shows relative time or short description.
 * In detail view: shows full ID.
 */
export function getConversationDisplayId(
  conversation: Conversation | null | undefined,
  view: "list" | "detail" = "list"
): string {
  if (!conversation) {
    return "Unknown";
  }

  if (view === "detail") {
    return conversation.conversation_id;
  }

  // In list view, show relative time since creation
  const relativeTime = formatRelativeTime(conversation.created_at);
  return `Started ${relativeTime}`;
}

/**
 * Format conversation time for display.
 * Returns relative time for recent conversations, absolute for older ones.
 */
export function formatConversationTime(timestamp: string): string {
  return formatRelativeTime(timestamp);
}

/**
 * Get preview of last message in conversation (max 50 characters).
 * Returns null if no preview available.
 */
export function getConversationPreview(
  lastMessage: string | null | undefined
): string | null {
  if (!lastMessage || lastMessage.trim().length === 0) {
    return null;
  }

  const trimmed = lastMessage.trim();
  if (trimmed.length <= 50) {
    return trimmed;
  }

  return `${trimmed.substring(0, 47)}...`;
}

/**
 * Get priority indicator for a conversation.
 * Returns priority level based on status and waiting time.
 */
export function getPriorityIndicator(
  conversation: Conversation | null | undefined
): "high" | "medium" | "low" {
  if (!conversation) {
    return "low";
  }

  // High priority: NEEDS_HUMAN with long waiting time
  if (conversation.status === "NEEDS_HUMAN") {
    const updatedAt = new Date(conversation.updated_at);
    const now = new Date();
    const waitingMinutes = (now.getTime() - updatedAt.getTime()) / (1000 * 60);

    if (waitingMinutes > 30) {
      return "high";
    }
    if (waitingMinutes > 10) {
      return "medium";
    }
    return "medium";
  }

  // Medium priority: HUMAN_ACTIVE
  if (conversation.status === "HUMAN_ACTIVE") {
    return "medium";
  }

  // Low priority: AI_ACTIVE or CLOSED
  return "low";
}

/**
 * Check if conversation needs urgent attention.
 */
export function needsUrgentAttention(conversation: Conversation | null | undefined): boolean {
  return getPriorityIndicator(conversation) === "high";
}
