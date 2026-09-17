/** Centralized error handling for frontend. */

import { ApiError } from "./api";

export interface ErrorInfo {
  code: string;
  message: string;
  details?: Record<string, any>;
  requestId?: string;
}

export function handleApiError(error: unknown): ErrorInfo {
  if (error instanceof ApiError) {
    return {
      code: error.code,
      message: error.message,
      details: error.details,
      requestId: error.requestId,
    };
  }

  if (error instanceof Error) {
    return {
      code: "UNKNOWN_ERROR",
      message: error.message,
    };
  }

  return {
    code: "UNKNOWN_ERROR",
    message: "An unexpected error occurred",
  };
}

export function getUserFriendlyMessage(error: ErrorInfo): string {
  const errorMessages: Record<string, string> = {
    AGENT_NOT_FOUND: "Agent not found. Please check the agent ID.",
    CONVERSATION_NOT_FOUND: "Conversation not found.",
    INVALID_AGENT_CONFIG: "Invalid agent configuration.",
    NETWORK_ERROR: "Network error. Please check your connection and try again.",
    VALIDATION_ERROR: "Invalid input. Please check your data and try again.",
  };

  return (
    errorMessages[error.code] ||
    error.message ||
    "An error occurred. Please try again."
  );
}

export function logError(error: ErrorInfo, context?: string): void {
  console.error(`[${context || "Error"}]`, {
    code: error.code,
    message: error.message,
    details: error.details,
    requestId: error.requestId,
  });
}








