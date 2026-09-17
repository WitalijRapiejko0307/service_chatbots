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
        "bg-blue-100 text-blue-800 border border-blue-300",
      ariaLabel: "New conversation",
    },
    BOOKED: {
      label: "Booked",
      icon: "✅",
      colorClasses:
        "bg-green-100 text-green-800 border border-green-300",
      ariaLabel: "Appointment booked",
    },
    NO_RESPONSE: {
      label: "No Response",
      icon: "⏸️",
      colorClasses:
        "bg-gray-100 text-gray-800 border border-gray-300",
      ariaLabel: "No response from patient",
    },
    REJECTED: {
      label: "Rejected",
      icon: "❌",
      colorClasses:
        "bg-red-100 text-red-800 border border-red-300",
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
