/** Notification configuration types. */

export type NotificationType = "telegram";

export interface NotificationConfig {
  config_id: string;
  notification_type: NotificationType;
  chat_id: string;
  is_active: boolean;
  description?: string;
  created_at: string;
  updated_at: string;
  created_by?: string;
}

export interface CreateNotificationConfigRequest {
  notification_type: NotificationType;
  bot_token: string;
  chat_id: string;
  description?: string;
}

export interface UpdateNotificationConfigRequest {
  is_active?: boolean;
  bot_token?: string;
  chat_id?: string;
  description?: string;
}
