/** Types for channel bindings. */

export type ChannelType = "web_chat" | "telegram" | "viber" | "instagram" | "tiktok";

export interface ChannelConfig {
  app_url: string;
  instagram_webhook_url: string;
  instagram_verify_token: string;
  instagram_app_secret_configured: boolean;
  /** Base webhook URL for Telegram bindings. Append `/{binding_id}`. */
  telegram_webhook_base: string;
  /** Base webhook URL for Viber bindings. Append `/{binding_id}`. */
  viber_webhook_base: string;
  /** Base webhook URL for TikTok bindings. Append `/{binding_id}`. */
  tiktok_webhook_base: string;
  /** When false, TikTok is pending partner / API access — not an error. */
  tiktok_messaging_enabled?: boolean;
  /** True when INSTAGRAM_APP_ID is set (OAuth button). Paste-token remains. */
  instagram_oauth_available?: boolean;
  /** True when TIKTOK_APP_ID is set (OAuth button), including while messaging is pending. */
  tiktok_oauth_available?: boolean;
}

export type SupportLevel = "yes" | "limited" | "no";

export interface ChannelSupportRow {
  text_in: string;
  text_out: string;
  images: string;
  media_other: string;
  quick_replies: string;
  typing: string;
  restart_command: string;
  proactive_first_message: string;
  response_window: string;
  human_handoff: string;
  notes: string;
}

export interface ChannelSupportMatrix {
  channels: string[];
  capabilities: string[];
  matrix: Record<string, ChannelSupportRow>;
  tiktok_messaging_enabled?: boolean;
  legend?: string[];
}

export interface ChannelBinding {
  binding_id: string;
  agent_id: string;
  channel_type: ChannelType;
  channel_account_id: string;
  channel_username?: string;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  updated_at: string;
  created_by?: string;
  /** May include `webhook_url` and `pending_access`. Tokens are never echoed. */
  metadata: Record<string, unknown>;
}

export interface CreateChannelBindingRequest {
  channel_type: ChannelType;
  channel_account_id: string;
  access_token: string;
  channel_username?: string;
  metadata?: Record<string, unknown>;
}

export interface UpdateChannelBindingRequest {
  is_active?: boolean;
  access_token?: string;
  metadata?: Record<string, unknown>;
}

/** A single bot command entry returned by GET /channel-bindings/{id}/commands */
export interface TelegramCommand {
  key: string;
  command: string;
  /** Effective description shown in Telegram menu (may be overridden in admin). */
  description: string;
  /** Catalog default before admin override. */
  default_description?: string;
  enabled: boolean;
  /** supportproject / feedback — admin can set menu label + reply body */
  supports_custom_content?: boolean;
  menu_description?: string | null;
  message?: string;
}
