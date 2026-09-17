/** Statistics calculation and formatting utilities. */

import type { StatsComparison } from "@/lib/types/stats";

/**
 * Format change indicator with color.
 */
export function formatChange(change: number): {
  text: string;
  colorClass: string;
} {
  if (change === 0) {
    return { text: "0", colorClass: "text-gray-500" };
  }
  if (change > 0) {
    return {
      text: `+${change}`,
      colorClass: "text-green-600",
    };
  }
  return {
    text: `${change}`,
    colorClass: "text-red-600",
  };
}

/**
 * Calculate percentage change.
 */
export function calculatePercentageChange(current: number, previous: number): number {
  if (previous === 0) {
    return current > 0 ? 100 : 0;
  }
  return Math.round(((current - previous) / previous) * 100);
}

/**
 * Format percentage change.
 */
export function formatPercentageChange(change: number): string {
  if (change === 0) {
    return "0%";
  }
  const sign = change > 0 ? "+" : "";
  return `${sign}${change}%`;
}
