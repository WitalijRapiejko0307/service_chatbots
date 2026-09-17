/** Utility functions for displaying channel information. */

/**
 * Get display text for a channel.
 * @param channel - Channel identifier (e.g., "instagram", "telegram", "viber", "tiktok", "web_chat")
 * @returns Formatted channel display string with emoji
 */
export function getChannelDisplay(channel?: string | null): string {
  if (!channel) return "-";
  if (channel === "instagram") return "📷 Instagram";
  if (channel === "telegram") return "💬 Telegram";
  if (channel === "viber") return "💜 Viber";
  if (channel === "tiktok") return "🎵 TikTok";
  if (channel === "web_chat") return "🌐 Web Chat";
  return channel;
}

/**
 * Get short label for a channel (without emoji), suitable for badges.
 */
export function getChannelLabel(channel?: string | null): string {
  if (!channel) return "-";
  if (channel === "instagram") return "Instagram";
  if (channel === "telegram") return "Telegram";
  if (channel === "viber") return "Viber";
  if (channel === "tiktok") return "TikTok";
  if (channel === "web_chat") return "Web Chat";
  return channel;
}

export function isInstagramChannel(channel?: string | null): boolean {
  return channel === "instagram";
}

export function isWebChatChannel(channel?: string | null): boolean {
  return channel === "web_chat";
}

export function isTelegramChannel(channel?: string | null): boolean {
  return channel === "telegram";
}

export function isViberChannel(channel?: string | null): boolean {
  return channel === "viber";
}

export function isTikTokChannel(channel?: string | null): boolean {
  return channel === "tiktok";
}

/** Phone-number style channels (show +external_user_id). */
export function isPhoneChannel(channel?: string | null): boolean {
  return channel === "telegram" || channel === "viber";
}

/** TikTok (and similar) placeholder connections waiting on partner API access. */
export function isPendingChannelAccess(
  metadata?: Record<string, unknown> | null
): boolean {
  return Boolean(metadata?.pending_access);
}

/** Instagram App Review / unverified connected account. */
export function isInstagramPendingReview(
  channelType: string | undefined,
  binding?: { is_verified?: boolean; metadata?: Record<string, unknown> | null } | null
): boolean {
  if (channelType !== "instagram" || !binding) return false;
  if (Boolean(binding.metadata?.app_review_pending)) return true;
  return binding.is_verified === false;
}

/** Webhook URL stored on a binding after verify (never includes tokens). */
export function channelWebhookFromMetadata(
  metadata?: Record<string, unknown> | null
): string {
  const url = metadata?.webhook_url;
  return typeof url === "string" ? url : "";
}
