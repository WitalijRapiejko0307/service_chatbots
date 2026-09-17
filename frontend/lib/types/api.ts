/** Types for API requests and responses. */

export interface ErrorResponse {
  error: {
    code: string;
    message: string;
    details?: Record<string, any>;
    request_id?: string;
  };
}

export interface SuccessResponse<T = any> {
  success?: boolean;
  message?: string;
  data?: T;
}

export interface PaginationParams {
  limit?: number;
  offset?: number;
}








