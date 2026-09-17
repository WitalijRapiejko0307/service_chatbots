/** Audit log display utilities for consistent formatting. */

export interface ActionDisplayConfig {
  label: string;
  icon: string;
  colorClasses: string;
}

/**
 * Get human-readable label and icon for audit log action.
 */
export function getActionDisplay(action: string): ActionDisplayConfig {
  const actionMap: Record<string, ActionDisplayConfig> = {
    handoff: {
      label: "Handoff to Human",
      icon: "👤",
      colorClasses: "bg-blue-100 text-blue-800 border border-blue-200",
    },
    return_to_ai: {
      label: "Return to AI",
      icon: "🤖",
      colorClasses: "bg-green-100 text-green-800 border border-green-200",
    },
    send_message: {
      label: "Send Message",
      icon: "💬",
      colorClasses: "bg-purple-100 text-purple-800 border border-purple-200",
    },
    update_marketing_status: {
      label: "Update Marketing Status",
      icon: "📊",
      colorClasses: "bg-yellow-100 text-yellow-800 border border-yellow-200",
    },
    create_conversation: {
      label: "Create Conversation",
      icon: "➕",
      colorClasses: "bg-gray-100 text-gray-800 border border-gray-200",
    },
    update_conversation: {
      label: "Update Conversation",
      icon: "✏️",
      colorClasses: "bg-indigo-100 text-indigo-800 border border-indigo-200",
    },
  };

  return (
    actionMap[action] || {
      label: action.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase()),
      icon: "📝",
      colorClasses: "bg-gray-100 text-gray-800 border border-gray-200",
    }
  );
}

/**
 * Get human-readable label for resource type.
 */
export function getResourceTypeLabel(resourceType: string): string {
  const typeMap: Record<string, string> = {
    conversation: "Conversation",
    agent: "Agent",
    channel_binding: "Channel Binding",
  };

  return (
    typeMap[resourceType] ||
    resourceType.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase())
  );
}
