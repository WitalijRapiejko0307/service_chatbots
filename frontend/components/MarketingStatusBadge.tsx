/** Marketing status badge component for displaying marketing status consistently. */

import React from "react";
import type { MarketingStatus } from "@/lib/types/conversation";
import {
  getMarketingStatusDisplay,
  getMarketingStatusAriaLabel,
} from "@/lib/utils/marketingStatusDisplay";

interface MarketingStatusBadgeProps {
  status: MarketingStatus;
  size?: "sm" | "md";
  showIcon?: boolean;
  className?: string;
}

export const MarketingStatusBadge: React.FC<MarketingStatusBadgeProps> = ({
  status,
  size = "md",
  showIcon = true,
  className = "",
}) => {
  const statusDisplay = getMarketingStatusDisplay(status);
  const ariaLabel = getMarketingStatusAriaLabel(status);

  const sizeClasses = {
    sm: "px-2 py-0.5 text-xs",
    md: "px-2 py-1 text-xs",
  };

  return (
    <span
      className={`inline-flex items-center gap-1 leading-5 font-semibold rounded-sm ${statusDisplay.colorClasses} ${sizeClasses[size]} ${className}`}
      aria-label={ariaLabel}
      role="status"
    >
      {showIcon && <span aria-hidden="true">{statusDisplay.icon}</span>}
      <span>{statusDisplay.label}</span>
    </span>
  );
};
