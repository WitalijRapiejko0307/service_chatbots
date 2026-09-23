/** Audit log row component with expandable details. */

import React, { useState } from "react";
import Link from "next/link";
import { getActionDisplay, getResourceTypeLabel } from "@/lib/utils/auditDisplay";
import { formatRelativeTimeDetailed, formatDateTime } from "@/lib/utils/timeFormat";
import type { AuditLog } from "@/lib/types/api";

export type { AuditLog };

interface AuditLogRowProps {
  log: AuditLog;
}

export const AuditLogRow: React.FC<AuditLogRowProps> = ({ log }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const actionDisplay = getActionDisplay(log.action);
  const hasMetadata = log.metadata && Object.keys(log.metadata).length > 0;

  const getResourceLink = () => {
    if (log.resource_type === "conversation") {
      return `/admin/conversations/${log.resource_id}`;
    }
    return null;
  };

  const resourceLink = getResourceLink();

  return (
    <>
      <tr
        className="hover:bg-surface-hover transition-colors duration-150 cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <td className="px-6 py-4 whitespace-nowrap text-sm text-muted">
          <div className="flex items-center gap-2">
            <span className="text-xs">{actionDisplay.icon}</span>
            <span
              className={`px-2 py-1 rounded text-xs font-medium ${actionDisplay.colorClasses}`}
            >
              {actionDisplay.label}
            </span>
          </div>
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm text-foreground">
          {formatRelativeTimeDetailed(log.timestamp)}
          <div className="text-xs text-muted mt-1">
            {formatDateTime(log.timestamp)}
          </div>
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm text-foreground">
          {log.admin_id}
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm text-muted">
          {getResourceTypeLabel(log.resource_type)}
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm">
          {resourceLink ? (
            <Link
              href={resourceLink}
              onClick={(e) => e.stopPropagation()}
              className="text-foreground hover:text-foreground hover:underline"
            >
              {log.resource_id.substring(0, 8)}...
            </Link>
          ) : (
            <span className="text-muted">
              {log.resource_id.substring(0, 8)}...
            </span>
          )}
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
          {hasMetadata && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setIsExpanded(!isExpanded);
              }}
              className="text-foreground hover:text-foreground"
            >
              {isExpanded ? "▼" : "▶"}
            </button>
          )}
        </td>
      </tr>
      {isExpanded && hasMetadata && (
        <tr>
          <td colSpan={6} className="px-6 py-4 bg-surface-hover">
            <div className="text-sm">
              <h4 className="font-medium text-muted mb-2">Metadata</h4>
              <pre className="bg-surface p-3 rounded border border-border overflow-x-auto text-xs">
                {JSON.stringify(log.metadata, null, 2)}
              </pre>
            </div>
          </td>
        </tr>
      )}
    </>
  );
};
