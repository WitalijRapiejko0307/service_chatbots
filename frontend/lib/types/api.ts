/** Types for API requests and responses. */

export interface ErrorResponse {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    request_id?: string;
  };
}

export interface SuccessResponse<T = unknown> {
  success?: boolean;
  message?: string;
  data?: T;
}

export interface PaginationParams {
  limit?: number;
  offset?: number;
}

export interface AuditLog {
  log_id: string;
  admin_id: string;
  action: string;
  resource_type: string;
  resource_id: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}








