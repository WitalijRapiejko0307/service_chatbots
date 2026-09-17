/** Helper functions for status validation and type safety. */

import type { ConversationStatus } from "@/lib/types/conversation";

/**
 * Check if a string is a valid ConversationStatus.
 */
export function isValidConversationStatus(status: string): status is ConversationStatus {
  return (
    status === "AI_ACTIVE" ||
    status === "NEEDS_HUMAN" ||
    status === "HUMAN_ACTIVE" ||
    status === "CLOSED"
  );
}

/**
 * Safely convert a string to ConversationStatus with fallback.
 */
export function toConversationStatus(status: string | ConversationStatus): ConversationStatus {
  if (isValidConversationStatus(status)) {
    return status;
  }
  // Default fallback for invalid statuses
  return "CLOSED";
}
