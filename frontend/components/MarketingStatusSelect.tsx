/** Marketing status select component with rejection reason input. */

"use client";

import React, { useState, useEffect } from "react";
import { Select } from "./Select";
import { Textarea } from "./Textarea";
import type { MarketingStatus } from "@/lib/types/conversation";

interface MarketingStatusSelectProps {
  value: MarketingStatus | null | undefined;
  onChange: (status: MarketingStatus, rejectionReason?: string) => void;
  disabled?: boolean;
  className?: string;
  showRejectionReason?: boolean;
  currentRejectionReason?: string | null;
}

export const MarketingStatusSelect: React.FC<MarketingStatusSelectProps> = ({
  value,
  onChange,
  disabled = false,
  className = "",
  showRejectionReason = true,
  currentRejectionReason,
}) => {
  const [selectedStatus, setSelectedStatus] = useState<MarketingStatus>(
    value || "NEW"
  );
  const [rejectionReason, setRejectionReason] = useState<string>(
    currentRejectionReason || ""
  );
  const [error, setError] = useState<string>("");

  useEffect(() => {
    if (value) {
      setSelectedStatus(value);
    }
  }, [value]);

  useEffect(() => {
    if (currentRejectionReason !== undefined) {
      setRejectionReason(currentRejectionReason || "");
    }
  }, [currentRejectionReason]);

  const handleStatusChange = (newStatus: string) => {
    const status = newStatus as MarketingStatus;
    setSelectedStatus(status);
    setError("");

    // If status is not REJECTED, clear rejection reason and call onChange
    if (status !== "REJECTED") {
      setRejectionReason("");
      onChange(status);
    }
  };

  const handleRejectionReasonChange = (reason: string) => {
    setRejectionReason(reason);
    setError("");
    // Call onChange with updated reason
    if (selectedStatus === "REJECTED") {
      onChange(selectedStatus, reason);
    }
  };

  const handleBlur = () => {
    // Validate rejection reason when status is REJECTED
    if (selectedStatus === "REJECTED" && !rejectionReason.trim()) {
      setError("Rejection reason is required");
    } else {
      setError("");
    }
  };

  const statusOptions = [
    { value: "NEW", label: "New" },
    { value: "BOOKED", label: "Booked" },
    { value: "NO_RESPONSE", label: "No Response" },
    // Only show REJECTED if rejection reason input is enabled
    ...(showRejectionReason
      ? [{ value: "REJECTED", label: "Rejected" }]
      : []),
  ];

  return (
    <div className={`space-y-2 ${className}`}>
      <Select
        value={selectedStatus}
        onChange={(e) => handleStatusChange(e.target.value)}
        options={statusOptions}
        disabled={disabled}
        className="w-full"
      />
      {showRejectionReason && selectedStatus === "REJECTED" && (
        <Textarea
          label="Rejection Reason *"
          value={rejectionReason}
          onChange={(e) => handleRejectionReasonChange(e.target.value)}
          onBlur={handleBlur}
          placeholder="Enter reason for rejection..."
          disabled={disabled}
          error={error}
          helperText="Required when status is Rejected"
          rows={3}
          maxLength={1000}
        />
      )}
    </div>
  );
};
