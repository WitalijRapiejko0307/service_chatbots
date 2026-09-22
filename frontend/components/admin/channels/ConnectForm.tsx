"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/shared/Button";
import type { ChannelBinding, CreateChannelBindingRequest } from "@/lib/types/channel";
import { INPUT_CLASS, LABEL_CLASS } from "./constants";
import type { MessengerChannel } from "./utils";

interface ConnectFormProps {
  agentId: string;
  channelType: MessengerChannel;
  tiktokMessagingEnabled?: boolean;
  onSuccess: (binding: ChannelBinding) => void;
  onCancel: () => void;
}

export function ConnectForm({
  agentId,
  channelType,
  tiktokMessagingEnabled = true,
  onSuccess,
  onCancel,
}: ConnectFormProps) {
  const t = useTranslations("Channels");
  const [form, setForm] = useState<CreateChannelBindingRequest>({
    channel_type: channelType,
    channel_account_id: "",
    access_token: "",
    channel_username: "",
    metadata: {},
  });
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const firstInput = useRef<HTMLInputElement>(null);
  const tiktokPending = channelType === "tiktok" && tiktokMessagingEnabled === false;

  useEffect(() => {
    firstInput.current?.focus();
  }, []);

  const set = (field: keyof CreateChannelBindingRequest, value: string) =>
    setForm((prev) => ({ ...prev, [field]: value }));
  const setMeta = (key: string, value: string) =>
    setForm((prev) => ({ ...prev, metadata: { ...prev.metadata, [key]: value } }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setSubmitting(true);
    try {
      let channelAccountId = form.channel_account_id.trim();
      let accessToken = form.access_token.trim();
      const metadata: Record<string, unknown> = { ...(form.metadata ?? {}) };
      if (channelType === "instagram") {
        metadata.connected_via = "paste";
      }

      if (channelType === "telegram") {
        if (!channelAccountId) {
          const numericPart = accessToken.split(":")[0];
          channelAccountId =
            numericPart && /^\d+$/.test(numericPart) ? numericPart : "telegram";
        }
      } else if (channelType === "viber") {
        channelAccountId =
          channelAccountId || form.channel_username?.trim() || "viber";
      } else if (channelType === "tiktok") {
        if (tiktokPending) {
          channelAccountId = channelAccountId || "tiktok";
          accessToken = accessToken || "pending";
          metadata.pending_access = true;
        }
      }

      const payload: CreateChannelBindingRequest = {
        channel_type: channelType,
        channel_account_id: channelAccountId,
        access_token: accessToken,
        channel_username: form.channel_username?.trim() || undefined,
        metadata,
      };

      const binding = await api.createChannelBinding(agentId, payload);
      const autoVerify =
        channelType === "telegram" ||
        channelType === "viber" ||
        channelType === "instagram";
      if (autoVerify && binding.binding_id) {
        await api.verifyChannelBinding(binding.binding_id).catch(() => {});
      }
      onSuccess(binding);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : t("connectError"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-4 p-4 bg-[#FAF9F8] border border-[#BEBAB7] rounded-sm space-y-3"
    >
      {err && (
        <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-sm px-3 py-2">
          {err}
        </div>
      )}

      {channelType === "instagram" && (
        <>
          <p className="text-xs text-[#443C3C] bg-[#EEEAE7]/60 rounded-sm px-3 py-2">
            {t("instagram.pastePathActive")}
          </p>
          <div>
            <label className={LABEL_CLASS}>{t("instagram.accountId")}</label>
            <input
              ref={firstInput}
              className={INPUT_CLASS}
              value={form.channel_account_id}
              onChange={(e) => set("channel_account_id", e.target.value)}
              placeholder="17841458318357324"
              autoComplete="off"
            />
            <p className="text-xs text-[#9A9590] mt-1">{t("instagram.accountIdHint")}</p>
          </div>
          <div>
            <label className={LABEL_CLASS}>{t("instagram.pageToken")}</label>
            <input
              className={INPUT_CLASS}
              type="password"
              value={form.access_token}
              onChange={(e) => set("access_token", e.target.value)}
              placeholder="IGAAXjRiKjwKFBZA..."
              required
              autoComplete="new-password"
            />
          </div>
          <div>
            <label className={LABEL_CLASS}>{t("instagram.username")}</label>
            <input
              className={INPUT_CLASS}
              value={form.channel_username ?? ""}
              onChange={(e) => set("channel_username", e.target.value)}
              placeholder={t("instagram.usernamePlaceholder")}
            />
          </div>
          <div>
            <label className={LABEL_CLASS}>{t("instagram.appId")}</label>
            <input
              className={INPUT_CLASS}
              value={(form.metadata?.app_id as string) ?? ""}
              onChange={(e) => setMeta("app_id", e.target.value)}
              placeholder={t("instagram.appIdPlaceholder")}
            />
          </div>
        </>
      )}

      {channelType === "telegram" && (
        <>
          <div>
            <label className={LABEL_CLASS}>{t("telegram.botToken")}</label>
            <input
              ref={firstInput}
              className={INPUT_CLASS}
              type="password"
              value={form.access_token}
              onChange={(e) => {
                const token = e.target.value;
                const numericPart = token.split(":")[0];
                setForm((prev) => ({
                  ...prev,
                  access_token: token,
                  channel_account_id:
                    numericPart && /^\d+$/.test(numericPart) ? numericPart : "telegram",
                }));
              }}
              placeholder="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
              required
              autoComplete="new-password"
            />
            <p className="text-xs text-[#9A9590] mt-1">{t("telegram.botTokenHint")}</p>
          </div>
          <div>
            <label className={LABEL_CLASS}>{t("telegram.botUsername")}</label>
            <input
              className={INPUT_CLASS}
              value={form.channel_username ?? ""}
              onChange={(e) => set("channel_username", e.target.value)}
              placeholder={t("telegram.botUsernamePlaceholder")}
            />
          </div>
          <p className="text-xs text-[#9A9590]">{t("telegram.webhookAutoNote")}</p>
        </>
      )}

      {channelType === "viber" && (
        <>
          <div>
            <label className={LABEL_CLASS}>{t("viber.authToken")}</label>
            <input
              ref={firstInput}
              className={INPUT_CLASS}
              type="password"
              value={form.access_token}
              onChange={(e) => set("access_token", e.target.value)}
              placeholder="••••••••••••••••"
              required
              autoComplete="new-password"
            />
            <p className="text-xs text-[#9A9590] mt-1">{t("viber.authTokenHint")}</p>
          </div>
          <div>
            <label className={LABEL_CLASS}>{t("viber.accountName")}</label>
            <input
              className={INPUT_CLASS}
              value={form.channel_username ?? ""}
              onChange={(e) => {
                const name = e.target.value;
                setForm((prev) => ({
                  ...prev,
                  channel_username: name,
                  channel_account_id: name.trim() || "viber",
                }));
              }}
              placeholder={t("viber.accountNamePlaceholder")}
            />
          </div>
          <p className="text-xs text-[#443C3C] bg-[#EEEAE7]/60 rounded-sm px-3 py-2">
            {t("viber.httpsNote")}
          </p>
        </>
      )}

      {channelType === "tiktok" && (
        <>
          {tiktokPending && (
            <p className="text-xs text-[#443C3C] bg-[#EEEAE7]/60 rounded-sm px-3 py-2">
              {t("tiktok.pendingNote")}
            </p>
          )}
          <div>
            <label className={LABEL_CLASS}>
              {tiktokPending ? t("tiktok.businessId") : t("tiktok.businessIdRequired")}
            </label>
            <input
              ref={firstInput}
              className={INPUT_CLASS}
              value={form.channel_account_id}
              onChange={(e) => set("channel_account_id", e.target.value)}
              placeholder="open_id or business_id"
              required={!tiktokPending}
              autoComplete="off"
            />
            <p className="text-xs text-[#9A9590] mt-1">{t("tiktok.businessIdHint")}</p>
          </div>
          <div>
            <label className={LABEL_CLASS}>
              {tiktokPending ? t("tiktok.accessToken") : t("tiktok.accessTokenRequired")}
            </label>
            <input
              className={INPUT_CLASS}
              type="password"
              value={form.access_token}
              onChange={(e) => set("access_token", e.target.value)}
              placeholder="act.••••"
              required={!tiktokPending}
              autoComplete="new-password"
            />
            <p className="text-xs text-[#9A9590] mt-1">{t("tiktok.accessTokenHint")}</p>
          </div>
          {tiktokPending && (
            <p className="text-xs text-[#9A9590]">{t("tiktok.placeholderSaveNote")}</p>
          )}
        </>
      )}

      <div className="flex gap-2 pt-1">
        <Button type="submit" size="sm" disabled={submitting}>
          {submitting ? t("connecting") : t("connect")}
        </Button>
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-sm text-[#9A9590] hover:text-[#443C3C]"
        >
          {t("cancel")}
        </button>
      </div>
    </form>
  );
}
