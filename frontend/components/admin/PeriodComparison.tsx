/** Period comparison component. */

import React from "react";
import { Toggle } from "@/components/shared/Toggle";
import type { StatsComparison } from "@/lib/types/stats";
import { formatChange, formatPercentageChange, calculatePercentageChange } from "@/lib/utils/statsHelpers";

interface PeriodComparisonProps {
  comparison?: StatsComparison;
  currentStats: {
    total_conversations: number;
    ai_active: number;
    needs_human: number;
    human_active: number;
    closed: number;
    marketing_new: number;
    marketing_booked: number;
    marketing_no_response: number;
    marketing_rejected: number;
  };
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}

export const PeriodComparison: React.FC<PeriodComparisonProps> = ({
  comparison,
  currentStats,
  enabled,
  onToggle,
}) => {
  if (!enabled || !comparison) {
    return (
      <div className="mb-6">
        <div className="flex items-center gap-2">
          <Toggle checked={enabled} onChange={onToggle} />
          <label className="text-sm font-medium text-gray-700">
            Show comparison with previous period
          </label>
        </div>
      </div>
    );
  }

  return (
    <div className="mb-6 bg-gray-50 rounded-sm border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-900">Period Comparison</h3>
        <div className="flex items-center gap-2">
          <Toggle checked={enabled} onChange={onToggle} />
          <label className="text-xs text-gray-600">Enabled</label>
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
        {[
          { key: "total_conversations", label: "Total" },
          { key: "ai_active", label: "AI Active" },
          { key: "needs_human", label: "Needs Human" },
          { key: "human_active", label: "Human Active" },
          { key: "closed", label: "Closed" },
          { key: "marketing_new", label: "New" },
          { key: "marketing_booked", label: "Booked" },
          { key: "marketing_no_response", label: "No Response" },
          { key: "marketing_rejected", label: "Rejected" },
        ].map(({ key, label }) => {
          const change = comparison[key as keyof StatsComparison];
          const current = currentStats[key as keyof typeof currentStats];
          const previous = current - change;
          const changeDisplay = formatChange(change);
          const percentageChange = calculatePercentageChange(current, previous);

          return (
            <div key={key} className="text-center">
              <p className="text-xs text-gray-600 mb-1">{label}</p>
              <p className="text-lg font-bold text-gray-900">{current}</p>
              <p className={`text-xs font-medium ${changeDisplay.colorClass}`}>
                {changeDisplay.text} ({formatPercentageChange(percentageChange)})
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
};
