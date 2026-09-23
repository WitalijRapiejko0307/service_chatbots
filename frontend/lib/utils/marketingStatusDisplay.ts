/** Marketing status display utilities for consistent status formatting across the app. */

import type { MarketingStatus } from "@/lib/types/conversation";

export interface MarketingStatusDisplayConfig {
  label: string;
  icon: string;
  colorClasses: string;
  ariaLabel: string;
}

/**
 * Get human-readable label and icon for a marketing status.
 */
export function getMarketingStatusDisplay(
  status: MarketingStatus
): MarketingStatusDisplayConfig {
  const statusMap: Record<MarketingStatus, MarketingStatusDisplayConfig> = {
    NEW: {
      label: "New",
      icon: "🆕",
      colorClasses:
        "bg-accent/15 text-accent border border-accent/30",
      ariaLabel: "New conversation",
    },
    BOOKED: {
      label: "Booked",
      icon: "✅",
      colorClasses:
        "bg-success/15 text-success border border-success/30",
      ariaLabel: "Appointment booked",
    },
    NO_RESPONSE: {
      label: "No Response",
      icon: "⏸️",
      colorClasses:
        "bg-surface-hover text-muted border border-border",
      ariaLabel: "No response from patient",
    },
    REJECTED: {
      label: "Rejected",
      icon: "❌",
      colorClasses:
        "bg-danger/15 text-danger border border-danger/30",
      ariaLabel: "Lead rejected",
    },
  };

  return statusMap[status] || statusMap.NEW;
}

/**
 * Get color classes for a marketing status badge.
 */
export function getMarketingStatusColorClasses(
  status: MarketingStatus
): string {
  return getMarketingStatusDisplay(status).colorClasses;
}

/**
 * Get icon for a marketing status.
 */
export function getMarketingStatusIcon(status: MarketingStatus): string {
  return getMarketingStatusDisplay(status).icon;
}

/**
 * Get human-readable label for a marketing status.
 */
export function getMarketingStatusLabel(status: MarketingStatus): string {
  return getMarketingStatusDisplay(status).label;
}

/**
 * Get ARIA label for a marketing status.
 */
export function getMarketingStatusAriaLabel(status: MarketingStatus): string {
  return getMarketingStatusDisplay(status).ariaLabel;
}
