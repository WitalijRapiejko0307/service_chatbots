/** Channel setup — Telegram, Viber, Instagram, TikTok. */

"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { RefreshCw } from "lucide-react";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { InstagramChannelSection } from "@/components/admin/channels/InstagramChannelSection";
import { SupportMatrixTable } from "@/components/admin/channels/SupportMatrixTable";
import { TelegramChannelSection } from "@/components/admin/channels/TelegramChannelSection";
import { TikTokChannelSection } from "@/components/admin/channels/TikTokChannelSection";
import { ViberChannelSection } from "@/components/admin/channels/ViberChannelSection";
import { useChannelBindings } from "@/lib/hooks/useChannelBindings";

export default function AgentChannelsPage() {
  const params = useParams<{ agentId: string }>();
  const agentId = params?.agentId as string;
  const t = useTranslations("Channels");

  const {
    config,
    matrix,
    loading,
    error,
    reload,
    setConfig,
    appBase,
    tiktokMessagingEnabled,
    tiktokPendingAccess,
    byType,
    webhookFor,
  } = useChannelBindings(agentId);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  const igWebhookUrl = webhookFor("instagram")();
  const telegramBindings = byType("telegram");
  const viberBindings = byType("viber");
  const tiktokBindings = byType("tiktok");
  const telegramWebhook = webhookFor("telegram")(telegramBindings[0]);
  const viberWebhook = webhookFor("viber")(viberBindings[0]);
  const tiktokWebhook = webhookFor("tiktok")(tiktokBindings[0]);

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <Link
            href="/admin/agents"
            className="text-sm text-muted hover:text-foreground mb-1 inline-block"
          >
            ← {t("backToAgents")}
          </Link>
          <h1 className="text-2xl font-bold text-foreground">{t("title")}</h1>
          <p className="text-sm text-muted mt-1">{t("subtitle", { agentId })}</p>
        </div>
        <button
          type="button"
          onClick={() => void reload()}
          className="flex items-center gap-1.5 text-sm text-muted hover:text-foreground border border-border px-3 py-1.5 rounded-sm hover:border-border-strong transition-colors"
        >
          <RefreshCw size={13} /> {t("refresh")}
        </button>
      </div>

      {error && (
        <div className="mb-4 bg-danger/10 border-l-4 border-danger px-4 py-3 rounded-sm text-sm text-danger">
          {error}
        </div>
      )}

      <div className="space-y-4">
        <TelegramChannelSection
          agentId={agentId}
          bindings={telegramBindings}
          telegramWebhook={telegramWebhook}
          webhookFor={webhookFor("telegram")}
          onBindingsChange={reload}
        />

        <ViberChannelSection
          agentId={agentId}
          bindings={viberBindings}
          viberWebhook={viberWebhook}
          appBase={appBase}
          webhookFor={webhookFor("viber")}
          onBindingsChange={reload}
        />

        <InstagramChannelSection
          agentId={agentId}
          bindings={byType("instagram")}
          config={config}
          igWebhookUrl={igWebhookUrl}
          webhookFor={webhookFor("instagram")}
          onBindingsChange={reload}
          onConfigUpdate={setConfig}
        />

        <TikTokChannelSection
          agentId={agentId}
          bindings={tiktokBindings}
          tiktokWebhook={tiktokWebhook}
          tiktokPendingAccess={tiktokPendingAccess}
          tiktokMessagingEnabled={tiktokMessagingEnabled}
          oauthAvailable={config?.tiktok_oauth_available === true}
          webhookFor={webhookFor("tiktok")}
          onBindingsChange={reload}
        />
      </div>

      {matrix && (
        <div className="mt-6">
          <SupportMatrixTable matrix={matrix} />
        </div>
      )}
    </div>
  );
}
