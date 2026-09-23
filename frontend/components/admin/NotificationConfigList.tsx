/** List component for notification configs. */

"use client";

import type { NotificationConfig } from "@/lib/types/notification";

interface NotificationConfigListProps {
  configs: NotificationConfig[];
  onDelete: (configId: string) => void;
  onToggleActive: (configId: string, isActive: boolean) => void;
  onTest: (configId: string) => void;
  onEdit: (config: NotificationConfig) => void;
}

export function NotificationConfigList({
  configs,
  onDelete,
  onToggleActive,
  onTest,
  onEdit,
}: NotificationConfigListProps) {
  if (configs.length === 0) {
    return (
      <div className="text-center py-16 bg-surface rounded-sm shadow border border-border">
        <div className="max-w-md mx-auto">
          <div className="text-6xl mb-4">🔔</div>
          <h2 className="text-xl font-semibold text-foreground mb-2">
            No notification configs yet
          </h2>
          <p className="text-muted">
            Add a notification configuration to receive alerts when conversations are escalated.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-surface rounded-sm shadow border border-border overflow-hidden">
      <table className="min-w-full divide-y divide-border">
        <thead className="bg-surface-hover">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium text-foreground uppercase tracking-wider">
              Type
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-foreground uppercase tracking-wider">
              Chat ID
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-foreground uppercase tracking-wider">
              Description
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-foreground uppercase tracking-wider">
              Status
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-foreground uppercase tracking-wider">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="bg-surface divide-y divide-border">
          {configs.map((config) => (
            <tr
              key={config.config_id}
              className="hover:bg-surface-hover transition-colors duration-150"
            >
              <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-foreground">
                {config.notification_type === "telegram" ? "Telegram" : config.notification_type}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-muted">
                {config.chat_id}
              </td>
              <td className="px-6 py-4 text-sm text-muted">
                {config.description || "-"}
              </td>
              <td className="px-6 py-4 whitespace-nowrap">
                <span
                  className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-sm ${
                    config.is_active
                      ? "bg-surface-hover text-foreground border border-border"
                      : "bg-surface-hover text-foreground"
                  }`}
                >
                  {config.is_active ? "Active" : "Inactive"}
                </span>
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                <div className="flex gap-2">
                  <button
                    onClick={() => onEdit(config)}
                    className="text-accent hover:text-accent/80 transition-colors duration-200 cursor-pointer"
                    title="Edit config"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => onTest(config.config_id)}
                    className="text-success hover:text-success/80 transition-colors duration-200 cursor-pointer"
                    title="Send test notification"
                  >
                    Test
                  </button>
                  <button
                    onClick={() => onToggleActive(config.config_id, config.is_active)}
                    className={`text-sm ${
                      config.is_active
                        ? "text-warning hover:text-warning/80"
                        : "text-success hover:text-success/80"
                    } transition-colors duration-200 cursor-pointer`}
                    title={config.is_active ? "Deactivate" : "Activate"}
                  >
                    {config.is_active ? "Deactivate" : "Activate"}
                  </button>
                  <button
                    onClick={() => onDelete(config.config_id)}
                    className="text-danger hover:text-danger transition-colors duration-200 cursor-pointer"
                    title="Delete config"
                  >
                    Delete
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
