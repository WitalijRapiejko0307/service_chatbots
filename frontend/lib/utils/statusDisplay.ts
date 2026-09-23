/** Status display utilities for consistent status formatting across the app. */

import type { ConversationStatus } from "@/lib/types/conversation";

export interface StatusDisplayConfig {
  label: string;
  icon: string;
  colorClasses: string;
  ariaLabel: string;
}

/**
 * Get human-readable label and icon for a conversation status.
 */
export function getStatusDisplay(status: ConversationStatus): StatusDisplayConfig {
  const statusMap: Record<ConversationStatus, StatusDisplayConfig> = {
    AI_ACTIVE: {
      label: "AI Responding",
      icon: "🤖",
      colorClasses: "bg-surface-hover text-foreground border border-border-strong/30",
      ariaLabel: "AI is currently responding",
    },
    NEEDS_HUMAN: {
      label: "Needs Attention",
      icon: "⚠️",
      colorClasses: "bg-warning/15 text-warning border border-warning/30",
      ariaLabel: "Requires human attention",
    },
    HUMAN_ACTIVE: {
      label: "Admin Active",
      icon: "👤",
      colorClasses: "bg-accent/15 text-accent border border-accent/30",
      ariaLabel: "Administrator is actively responding",
    },
    CLOSED: {
      label: "Closed",
      icon: "✅",
      colorClasses: "bg-surface-hover text-muted border border-border",
      ariaLabel: "Conversation is closed",
    },
  };

  return statusMap[status] || statusMap.CLOSED;
}

/**
 * Get color classes for a status badge.
 */
export function getStatusColorClasses(status: ConversationStatus): string {
  return getStatusDisplay(status).colorClasses;
}

/**
 * Get icon for a status.
 */
export function getStatusIcon(status: ConversationStatus): string {
  return getStatusDisplay(status).icon;
}

/**
 * Get human-readable label for a status.
 */
export function getStatusLabel(status: ConversationStatus): string {
  return getStatusDisplay(status).label;
}

/**
 * Get ARIA label for a status.
 */
export function getStatusAriaLabel(status: ConversationStatus): string {
  return getStatusDisplay(status).ariaLabel;
}
