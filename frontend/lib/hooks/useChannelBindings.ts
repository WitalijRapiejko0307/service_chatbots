/** Hook for loading and refreshing channel bindings on the admin channels page. */

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { api, ApiError } from "@/lib/api";
import type {
  ChannelBinding,
  ChannelConfig,
  ChannelSupportMatrix,
} from "@/lib/types/channel";
import { bindingWebhookUrl, type MessengerChannel } from "@/components/admin/channels/utils";

export function useChannelBindings(agentId: string) {
  const t = useTranslations("Channels");
  const [bindings, setBindings] = useState<ChannelBinding[]>([]);
  const [config, setConfig] = useState<ChannelConfig | null>(null);
  const [matrix, setMatrix] = useState<ChannelSupportMatrix | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const appBase =
    config?.app_url || (typeof window !== "undefined" ? window.location.origin : "");

  const tiktokMessagingEnabled = config?.tiktok_messaging_enabled === true;
  const tiktokPendingAccess = !tiktokMessagingEnabled;

  const reload = useCallback(async () => {
    try {
      setError(null);
      const [bindingsData, configData, matrixData] = await Promise.all([
        api.listChannelBindings(agentId, undefined, false),
        api.getChannelConfig().catch(() => null),
        api.getChannelSupportMatrix().catch(() => null),
      ]);
      setBindings(bindingsData);
      setConfig(configData);
      setMatrix(matrixData);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("loadError"));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t is next-intl translator
  }, [agentId]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const hasTikTokError = params.has("tiktok_error");
    const hasTikTokBinding = params.has("tiktok_binding");
    const hasInstagramError = params.has("instagram_error");
    const hasInstagramBinding = params.has("instagram_binding");

    void (async () => {
      await reload();
      // Apply after reload() so its opening setError(null) cannot wipe the banner.
      if (hasTikTokError) {
        setError(t("oauthReturnError"));
      } else if (hasInstagramError) {
        setError(t("instagram.oauthReturnError"));
      }
    })();

    if (hasTikTokError || hasTikTokBinding || hasInstagramError || hasInstagramBinding) {
      params.delete("tiktok_error");
      params.delete("tiktok_binding");
      params.delete("instagram_error");
      params.delete("instagram_binding");
      const query = params.toString();
      const next = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
      window.history.replaceState(null, "", next);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t is next-intl translator
  }, [reload]);

  const byType = useCallback(
    (type: MessengerChannel) => bindings.filter((b) => b.channel_type === type),
    [bindings]
  );

  const webhookFor = useCallback(
    (type: MessengerChannel) => (binding?: ChannelBinding) =>
      bindingWebhookUrl(type, binding, config, appBase),
    [config, appBase]
  );

  return {
    bindings,
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
  };
}
