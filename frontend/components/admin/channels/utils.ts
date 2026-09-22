import { channelWebhookFromMetadata } from "@/lib/utils/channelDisplay";
import type { ChannelBinding, ChannelConfig, ChannelType } from "@/lib/types/channel";

export type MessengerChannel = Exclude<ChannelType, "web_chat">;

export function joinWebhook(base: string, bindingId?: string): string {
  if (!base) return "";
  const trimmed = base.replace(/\/$/, "");
  if (!bindingId) return trimmed;
  return `${trimmed}/${bindingId}`;
}

export function webhookBaseFor(
  type: MessengerChannel,
  config: ChannelConfig | null,
  appBase: string
): string {
  if (type === "telegram") {
    return config?.telegram_webhook_base || (appBase ? `${appBase}/api/v1/telegram/webhook` : "");
  }
  if (type === "viber") {
    return config?.viber_webhook_base || (appBase ? `${appBase}/api/v1/viber/webhook` : "");
  }
  if (type === "instagram") {
    return (
      config?.instagram_webhook_url || (appBase ? `${appBase}/api/v1/instagram/webhook` : "")
    );
  }
  return config?.tiktok_webhook_base || (appBase ? `${appBase}/api/v1/tiktok/webhook` : "");
}

export function bindingWebhookUrl(
  type: MessengerChannel,
  binding: ChannelBinding | undefined,
  config: ChannelConfig | null,
  appBase: string
): string {
  const fromMeta = channelWebhookFromMetadata(binding?.metadata);
  if (fromMeta) return fromMeta;
  const base = webhookBaseFor(type, config, appBase);
  if (type === "instagram") return base;
  return binding ? joinWebhook(base, binding.binding_id) : "";
}
