/** Channel setup — Telegram, Viber, Instagram, TikTok. */

"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { api, ApiError } from "@/lib/api";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Button } from "@/components/shared/Button";
import { ConfirmModal } from "@/components/shared/ConfirmModal";
import { TelegramBotCommandsPanel } from "@/components/admin/TelegramBotCommandsPanel";
import {
  channelWebhookFromMetadata,
  isInstagramPendingReview,
  isPendingChannelAccess,
} from "@/lib/utils/channelDisplay";
import type {
  ChannelBinding,
  ChannelConfig,
  ChannelSupportMatrix,
  ChannelType,
  CreateChannelBindingRequest,
} from "@/lib/types/channel";
import {
  CheckCircle2,
  Circle,
  Copy,
  Check,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Trash2,
  ToggleLeft,
  ToggleRight,
  Settings,
  Eye,
  EyeOff,
} from "lucide-react";

type MessengerChannel = Exclude<ChannelType, "web_chat">;

function joinWebhook(base: string, bindingId?: string): string {
  if (!base) return "";
  const trimmed = base.replace(/\/$/, "");
  if (!bindingId) return trimmed;
  return `${trimmed}/${bindingId}`;
}

function webhookBaseFor(
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

function bindingWebhookUrl(
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

const INPUT_CLASS =
  "w-full text-sm px-3 py-2 border border-[#BEBAB7] rounded-sm outline-none focus:border-[#251D1C] bg-white placeholder:text-[#BEBAB7]";
const LABEL_CLASS = "block text-xs font-medium text-[#443C3C] mb-1";

function CopyButton({ value, label }: { value: string; label?: string }) {
  const t = useTranslations("Channels");
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    if (!value) return;
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      type="button"
      onClick={handleCopy}
      disabled={!value}
      className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-sm border transition-colors
        border-[#BEBAB7] text-[#443C3C] hover:border-[#251D1C] hover:text-[#251D1C]
        disabled:opacity-40 disabled:cursor-not-allowed"
      title={label ?? t("copyToClipboard")}
    >
      {copied ? <Check size={12} className="text-green-600" /> : <Copy size={12} />}
      {copied ? t("copied") : t("copy")}
    </button>
  );
}

function CopyField({ value, masked }: { value: string; masked?: boolean }) {
  const t = useTranslations("Channels");
  const [show, setShow] = useState(false);
  const display = masked && !show ? "•".repeat(Math.min(value.length, 24)) : value;
  return (
    <div className="flex items-center gap-2 mt-1.5">
      <code className="flex-1 min-w-0 bg-[#EEEAE7] border border-[#BEBAB7] rounded-sm px-3 py-1.5 text-xs font-mono text-[#251D1C] overflow-x-auto whitespace-nowrap block">
        {value ? display : <span className="text-[#9A9590]">{t("notConfigured")}</span>}
      </code>
      {masked && value && (
        <button
          type="button"
          onClick={() => setShow((s) => !s)}
          className="text-[#9A9590] hover:text-[#443C3C]"
          title={show ? t("hide") : t("show")}
        >
          {show ? <EyeOff size={14} /> : <Eye size={14} />}
        </button>
      )}
      {value && <CopyButton value={value} />}
    </div>
  );
}

function StatusBadge({
  binding,
  pendingAccess,
  channelType,
}: {
  binding?: ChannelBinding;
  pendingAccess?: boolean;
  channelType?: MessengerChannel;
}) {
  const t = useTranslations("Channels");
  const pending = pendingAccess || isPendingChannelAccess(binding?.metadata);
  const pendingReview = isInstagramPendingReview(channelType, binding);

  if (!binding) {
    if (pending) {
      return (
        <span className="flex items-center gap-1.5 text-xs text-[#443C3C]">
          <Circle size={10} className="fill-[#BEBAB7]" /> {t("statusPendingAccess")}
        </span>
      );
    }
    return (
      <span className="flex items-center gap-1.5 text-xs text-[#9A9590]">
        <Circle size={10} /> {t("statusNotConnected")}
      </span>
    );
  }
  if (!binding.is_active) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-amber-600">
        <Circle size={10} className="fill-amber-400" /> {t("statusInactive")}
      </span>
    );
  }
  if (pending) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-[#443C3C]">
        <Circle size={10} className="fill-[#BEBAB7]" /> {t("statusPendingAccess")}
      </span>
    );
  }
  if (pendingReview) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-amber-700">
        <Circle size={10} className="fill-amber-400" /> {t("statusPendingReview")}
      </span>
    );
  }
  if (!binding.is_verified) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-amber-600">
        <Circle size={10} className="fill-amber-400" /> {t("statusUnverified")}
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1.5 text-xs text-green-600 font-medium">
      <CheckCircle2 size={12} className="fill-green-100" /> {t("statusConnected")}
    </span>
  );
}

function Step({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-[#EEEAE7] text-[#443C3C] text-xs font-bold flex items-center justify-center mt-0.5">
        {n}
      </span>
      <div className="flex-1 min-w-0 text-sm text-[#443C3C] leading-relaxed break-words">{children}</div>
    </div>
  );
}

function ExtLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-[#251D1C] font-medium underline underline-offset-2 hover:opacity-70"
    >
      {children} <ExternalLink size={11} />
    </a>
  );
}

function AppUrlWarning() {
  const t = useTranslations("Channels");
  return (
    <div className="text-xs bg-amber-50 border border-amber-200 rounded-sm px-3 py-2 space-y-1">
      <div className="font-medium text-amber-800">{t("appUrlMissingTitle")}</div>
      <div className="text-amber-700">{t("appUrlMissingBody")}</div>
    </div>
  );
}

function richMarks(extra?: Record<string, (chunks: React.ReactNode) => React.ReactNode>) {
  return {
    strong: (chunks: React.ReactNode) => <strong>{chunks}</strong>,
    em: (chunks: React.ReactNode) => <em>{chunks}</em>,
    code: (chunks: React.ReactNode) => (
      <code className="bg-[#EEEAE7] px-1 rounded-sm text-xs">{chunks}</code>
    ),
    ...extra,
  };
}

interface ConnectFormProps {
  agentId: string;
  channelType: MessengerChannel;
  tiktokMessagingEnabled?: boolean;
  onSuccess: (binding: ChannelBinding) => void;
  onCancel: () => void;
}

function ConnectForm({
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

interface ChannelSettingsFormProps {
  title: string;
  currentVerifyToken: string;
  appSecretConfigured: boolean;
  verifyTokenHint?: string;
  onSave: (data: { verify_token?: string; app_secret?: string }) => Promise<void>;
}

function ChannelSettingsForm({
  title,
  currentVerifyToken,
  appSecretConfigured,
  verifyTokenHint,
  onSave,
}: ChannelSettingsFormProps) {
  const t = useTranslations("Channels");
  const [verifyToken, setVerifyToken] = useState(currentVerifyToken);
  const [appSecret, setAppSecret] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setVerifyToken(currentVerifyToken);
  }, [currentVerifyToken]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setSaving(true);
    try {
      const payload: { verify_token?: string; app_secret?: string } = {};
      if (verifyToken.trim()) payload.verify_token = verifyToken.trim();
      if (appSecret.trim()) payload.app_secret = appSecret.trim();
      await onSave(payload);
      setSaved(true);
      setAppSecret("");
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : t("saveSettingsError"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSave} className="p-4 bg-[#FAF9F8] border border-[#BEBAB7] rounded-sm space-y-3">
      <div className="text-xs font-semibold text-[#443C3C] flex items-center gap-1.5">
        <Settings size={12} /> {t("appSettingsTitle", { title })}
      </div>
      {err && (
        <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-sm px-3 py-2">
          {err}
        </div>
      )}
      <div>
        <label className={LABEL_CLASS}>{t("verifyToken")}</label>
        <input
          className={INPUT_CLASS}
          value={verifyToken}
          onChange={(e) => setVerifyToken(e.target.value)}
          placeholder={verifyTokenHint ?? t("verifyTokenHint")}
        />
        <p className="text-xs text-[#9A9590] mt-1">{t("verifyTokenHelp")}</p>
      </div>
      <div>
        <label className={LABEL_CLASS}>
          {t("appSecret")}{" "}
          <span className="font-normal text-[#9A9590]">{t("appSecretOptional")}</span>
        </label>
        <input
          className={INPUT_CLASS}
          type="password"
          value={appSecret}
          onChange={(e) => setAppSecret(e.target.value)}
          placeholder={
            appSecretConfigured ? t("appSecretPlaceholderSet") : t("appSecretPlaceholderUnset")
          }
          autoComplete="new-password"
        />
        <p className="text-xs text-[#9A9590] mt-1">{t("appSecretHelp")}</p>
      </div>
      <Button type="submit" size="sm" disabled={saving}>
        {saving ? t("saving") : saved ? t("saved") : t("saveSettings")}
      </Button>
    </form>
  );
}

function BindingRow({
  binding,
  webhookUrl,
  pendingAccess,
  channelType,
  onToggle,
  onDelete,
  onVerify,
  bottomSlot,
}: {
  binding: ChannelBinding;
  webhookUrl?: string;
  pendingAccess?: boolean;
  channelType?: MessengerChannel;
  onToggle: () => void;
  onDelete: () => void;
  onVerify: () => void;
  bottomSlot?: React.ReactNode;
}) {
  const t = useTranslations("Channels");
  return (
    <div className="rounded-sm border border-[#BEBAB7] bg-white text-sm overflow-hidden">
      <div className="flex items-center gap-3 p-3">
        <div className="flex-1 min-w-0">
          <div className="font-medium text-[#251D1C] truncate">
            {binding.channel_username || binding.channel_account_id}
          </div>
          <div className="text-xs text-[#9A9590]">
            {t("idLabel", { id: binding.channel_account_id })}
            {channelType === "instagram" && binding.metadata?.connected_via === "oauth"
              ? ` · ${t("instagram.pathOauth")}`
              : channelType === "instagram"
                ? ` · ${t("instagram.pathPaste")}`
                : ""}
          </div>
        </div>
        <StatusBadge binding={binding} pendingAccess={pendingAccess} channelType={channelType} />
        <div className="flex items-center gap-1.5">
          {!binding.is_verified && !isPendingChannelAccess(binding.metadata) && (
            <button
              type="button"
              onClick={onVerify}
              className="text-xs text-blue-600 hover:text-blue-800 px-2 py-1 rounded-sm border border-blue-200 hover:border-blue-400"
            >
              {t("verify")}
            </button>
          )}
          <button
            type="button"
            onClick={onToggle}
            className="text-[#9A9590] hover:text-[#443C3C]"
            title={binding.is_active ? t("deactivate") : t("activate")}
          >
            {binding.is_active ? (
              <ToggleRight size={18} className="text-green-500" />
            ) : (
              <ToggleLeft size={18} />
            )}
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="text-[#9A9590] hover:text-red-500"
            title={t("removeConnection")}
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>
      {webhookUrl && (
        <div className="px-3 pb-3">
          <div className="text-xs font-medium text-[#443C3C]">{t("webhookUrl")}</div>
          <CopyField value={webhookUrl} />
        </div>
      )}
      {bottomSlot}
    </div>
  );
}

interface ChannelCardProps {
  title: string;
  icon: string;
  bindings: ChannelBinding[];
  agentId: string;
  channelType: MessengerChannel;
  pendingAccess?: boolean;
  tiktokMessagingEnabled?: boolean;
  oauthAvailable?: boolean;
  webhookFor: (binding?: ChannelBinding) => string;
  onBindingsChange: () => void;
  guide: React.ReactNode;
  settingsForm?: React.ReactNode;
  banner?: React.ReactNode;
}

function ChannelCard({
  title,
  icon,
  bindings,
  agentId,
  channelType,
  pendingAccess,
  tiktokMessagingEnabled,
  oauthAvailable,
  webhookFor,
  onBindingsChange,
  guide,
  settingsForm,
  banner,
}: ChannelCardProps) {
  const t = useTranslations("Channels");
  const tCommon = useTranslations("Common");
  const [formOpen, setFormOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(bindings.length === 0);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [telegramCommandsOpenId, setTelegramCommandsOpenId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [oauthBusy, setOauthBusy] = useState(false);

  const activeBinding = bindings.find((b) => b.is_active) ?? bindings[0];
  const showOauth = Boolean(oauthAvailable);

  const handleDelete = async (bindingId: string) => {
    setBusyId(bindingId);
    setActionError(null);
    try {
      await api.deleteChannelBinding(bindingId);
      onBindingsChange();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : t("actionError"));
    }
    setBusyId(null);
    setPendingDelete(null);
  };

  const handleToggle = async (binding: ChannelBinding) => {
    setBusyId(binding.binding_id);
    setActionError(null);
    try {
      await api.updateChannelBinding(binding.binding_id, { is_active: !binding.is_active });
      onBindingsChange();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : t("actionError"));
    }
    setBusyId(null);
  };

  const handleVerify = async (bindingId: string) => {
    setBusyId(bindingId);
    setActionError(null);
    try {
      await api.verifyChannelBinding(bindingId);
      onBindingsChange();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : t("actionError"));
    }
    setBusyId(null);
  };

  const handleOAuth = async () => {
    setOauthBusy(true);
    setActionError(null);
    try {
      const result =
        channelType === "instagram"
          ? await api.startInstagramOAuth(agentId)
          : await api.startTikTokOAuth(agentId);
      if (result.authorization_url) {
        window.location.assign(result.authorization_url);
        return;
      }
      setActionError(t("oauthError"));
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : t("oauthError"));
    }
    setOauthBusy(false);
  };

  return (
    <div className="bg-white border border-[#BEBAB7] rounded-sm overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-[#BEBAB7]">
        <div className="flex items-center gap-3">
          <span className="text-xl">{icon}</span>
          <span className="font-semibold text-[#251D1C] text-base">{title}</span>
          {busyId && <LoadingSpinner size="sm" />}
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge
            binding={activeBinding}
            pendingAccess={pendingAccess}
            channelType={channelType}
          />
          {settingsForm && (
            <button
              type="button"
              onClick={() => setSettingsOpen((o) => !o)}
              className={`p-1 transition-colors ${settingsOpen ? "text-[#251D1C]" : "text-[#9A9590] hover:text-[#443C3C]"}`}
              title={t("appSettings")}
            >
              <Settings size={16} />
            </button>
          )}
        </div>
      </div>

      {banner}

      {actionError && (
        <div className="mx-5 mt-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded-sm px-3 py-2">
          {actionError}
        </div>
      )}

      {settingsForm && settingsOpen && (
        <div className="px-5 py-4 border-b border-[#BEBAB7] bg-[#FAF9F8]">{settingsForm}</div>
      )}

      {bindings.length > 0 && (
        <div className="px-5 py-3 space-y-2 border-b border-[#BEBAB7]">
          {bindings.map((b) => {
            const isTg = channelType === "telegram";
            const commandsOpen = telegramCommandsOpenId === b.binding_id;
            return (
              <BindingRow
                key={b.binding_id}
                binding={b}
                webhookUrl={webhookFor(b)}
                pendingAccess={pendingAccess}
                channelType={channelType}
                onToggle={() => handleToggle(b)}
                onDelete={() => setPendingDelete(b.binding_id)}
                onVerify={() => handleVerify(b.binding_id)}
                bottomSlot={
                  isTg ? (
                    <>
                      <button
                        type="button"
                        onClick={() =>
                          setTelegramCommandsOpenId((id) =>
                            id === b.binding_id ? null : b.binding_id
                          )
                        }
                        className={`w-full flex items-center justify-between px-3 py-2 text-xs font-medium text-[#443C3C] bg-[#FAF9F8] border-t border-[#BEBAB7] hover:bg-[#EEEAE7]/60 transition-colors ${
                          !commandsOpen ? "rounded-b-sm" : ""
                        }`}
                      >
                        <span>{t("commandsTitle")}</span>
                        {commandsOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </button>
                      {commandsOpen && <TelegramBotCommandsPanel binding={b} embedded />}
                    </>
                  ) : undefined
                }
              />
            );
          })}
        </div>
      )}

      {bindings.length === 0 && (
        <p className="px-5 py-3 text-xs text-[#9A9590] border-b border-[#BEBAB7]">
          {t("emptyBindingHint")}
        </p>
      )}

      <button
        type="button"
        onClick={() => setGuideOpen((o) => !o)}
        className="w-full flex items-center justify-between px-5 py-3 text-sm text-[#443C3C] hover:bg-[#FAF9F8] transition-colors"
      >
        <span className="font-medium">{t("setupGuide")}</span>
        {guideOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>

      {guideOpen && (
        <div className="px-5 pb-5 space-y-4">
          {guide}

          {!formOpen ? (
            <div className="space-y-2">
              {channelType === "instagram" && (
                <p className="text-xs text-[#9A9590]">{t("instagram.pathsHelp")}</p>
              )}
              <div className="flex flex-wrap gap-2">
              <Button type="button" size="sm" onClick={() => setFormOpen(true)}>
                {bindings.length > 0
                  ? t("addAnother", { title })
                  : channelType === "instagram"
                    ? t("instagram.connectPaste")
                    : t("connectChannel", { title })}
              </Button>
              {showOauth && (
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => void handleOAuth()}
                  disabled={oauthBusy}
                >
                  {oauthBusy
                    ? t("connecting")
                    : channelType === "instagram"
                      ? t("instagram.oauthOptional")
                      : t("oauthTikTok")}
                </Button>
              )}
              </div>
            </div>
          ) : (
            <ConnectForm
              agentId={agentId}
              channelType={channelType}
              tiktokMessagingEnabled={tiktokMessagingEnabled}
              onSuccess={() => {
                setFormOpen(false);
                onBindingsChange();
              }}
              onCancel={() => setFormOpen(false)}
            />
          )}
        </div>
      )}

      <ConfirmModal
        isOpen={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        onConfirm={() => pendingDelete && void handleDelete(pendingDelete)}
        title={t("confirmRemoveTitle")}
        message={t("confirmRemoveMessage")}
        confirmText={tCommon("delete")}
        cancelText={tCommon("cancel")}
        variant="danger"
        isLoading={pendingDelete !== null && busyId === pendingDelete}
      />
    </div>
  );
}

function InlineTokenSetup({
  channel,
  onSave,
}: {
  channel: "instagram";
  onSave: (token: string) => Promise<void>;
}) {
  const t = useTranslations("Channels");
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSave = async () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    setSaving(true);
    try {
      await onSave(trimmed);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mt-2 p-3 bg-[#EEEAE7]/50 border border-[#BEBAB7] rounded-sm space-y-2">
      <p className="text-xs text-[#443C3C]">{t("inlineTokenIntro")}</p>
      <div className="flex gap-2">
        <input
          className="flex-1 text-sm px-2.5 py-1.5 border border-[#BEBAB7] rounded-sm outline-none focus:border-[#251D1C] bg-white"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={t("inlineTokenPlaceholder", { channel })}
          onKeyDown={(e) => e.key === "Enter" && handleSave()}
        />
        <Button type="button" size="sm" onClick={handleSave} disabled={!value.trim() || saving}>
          {saving ? t("saving") : saved ? t("savedCheck") : t("save")}
        </Button>
      </div>
    </div>
  );
}

function SupportMatrixTable({ matrix }: { matrix: ChannelSupportMatrix }) {
  const t = useTranslations("Channels");
  const channels = matrix.channels.filter((c) => c in (matrix.matrix || {}));
  const capabilities = matrix.capabilities.filter((c) => c !== "notes");

  const cellLabel = (key: string, value: string) => {
    if (value === "yes") return t("matrixLegendYes");
    if (value === "limited") return t("matrixLegendLimited");
    if (value === "no") return t("matrixLegendNo");
    if (key === "response_window") {
      if (value === "none") return t("matrixWindow.none");
      if (value === "24h") return t("matrixWindow.24h");
      if (value === "48h_10") return t("matrixWindow.48h_10");
    }
    return value;
  };

  const cellClass = (value: string) => {
    if (value === "yes") return "text-green-700";
    if (value === "limited") return "text-amber-700";
    if (value === "no") return "text-[#9A9590]";
    return "text-[#443C3C]";
  };

  const capLabel = (key: string) => {
    try {
      return t(`matrixCap.${key}` as "matrixCap.text_in");
    } catch {
      return key;
    }
  };

  const channelLabel = (key: string) => {
    try {
      return t(`matrixChannel.${key}` as "matrixChannel.telegram");
    } catch {
      return key;
    }
  };

  const noteLabel = (key: string) => {
    try {
      return t(`matrixNote.${key}` as "matrixNote.telegram_media_and_commands");
    } catch {
      return key;
    }
  };

  return (
    <div className="bg-white border border-[#BEBAB7] rounded-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-[#BEBAB7]">
        <h2 className="font-semibold text-[#251D1C] text-base">{t("matrixTitle")}</h2>
        <p className="text-xs text-[#9A9590] mt-1">{t("matrixSubtitle")}</p>
        <p className="text-xs text-[#9A9590] mt-2">
          <span className="text-green-700 font-medium">{t("matrixLegendYes")}</span>
          {" · "}
          <span className="text-amber-700 font-medium">{t("matrixLegendLimited")}</span>
          {" · "}
          <span className="text-[#9A9590] font-medium">{t("matrixLegendNo")}</span>
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs text-left min-w-[640px]">
          <thead>
            <tr className="bg-[#FAF9F8] border-b border-[#BEBAB7]">
              <th className="px-3 py-2 font-medium text-[#443C3C]" />
              {channels.map((ch) => (
                <th key={ch} className="px-3 py-2 font-semibold text-[#251D1C] whitespace-nowrap">
                  {channelLabel(ch)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {capabilities.map((cap) => (
              <tr key={cap} className="border-b border-[#EEEAE7]">
                <th className="px-3 py-2 font-medium text-[#443C3C] whitespace-nowrap">
                  {capLabel(cap)}
                  {cap === "restart_command" ? (
                    <span className="block font-normal text-[10px] text-[#9A9590]">
                      {t("commandsTelegramOnly")}
                    </span>
                  ) : null}
                </th>
                {channels.map((ch) => {
                  const value = matrix.matrix[ch]?.[cap as keyof ChannelSupportMatrix["matrix"][string]] ?? "";
                  return (
                    <td key={ch} className={`px-3 py-2 ${cellClass(String(value))}`}>
                      {cellLabel(cap, String(value))}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="px-5 py-3 space-y-1.5 text-xs text-[#443C3C] bg-[#FAF9F8]">
        {channels.map((ch) => {
          const noteKey = matrix.matrix[ch]?.notes;
          if (!noteKey) return null;
          return (
            <li key={ch}>
              <span className="font-medium">{channelLabel(ch)}:</span> {noteLabel(noteKey)}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default function AgentChannelsPage() {
  const params = useParams<{ agentId: string }>();
  const agentId = params?.agentId as string;
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

  const load = useCallback(async () => {
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
      await load();
      // Apply after load() so its opening setError(null) cannot wipe the banner.
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
  }, [load]);

  const byType = (type: MessengerChannel) =>
    bindings.filter((b) => b.channel_type === type);

  const webhookFor = (type: MessengerChannel) => (binding?: ChannelBinding) =>
    bindingWebhookUrl(type, binding, config, appBase);

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

  const telegramGuide = (
    <div className="space-y-4">
      <div className="text-xs text-[#9A9590] bg-[#EEEAE7]/60 rounded-sm p-3 space-y-1">
        <div className="font-semibold text-[#443C3C] mb-1.5">{t("needTitle")}</div>
        <div>• {t("telegram.needItem")}</div>
      </div>
      <div className="space-y-3">
        <Step n={1}>
          {t.rich("telegram.step1", {
            ...richMarks({
              botFather: (chunks) => (
                <ExtLink href="https://t.me/BotFather">{chunks}</ExtLink>
              ),
            }),
          })}
        </Step>
        <Step n={2}>{t("telegram.step2")}</Step>
        <Step n={3}>
          {t("telegram.step3")}
          {telegramWebhook ? <CopyField value={telegramWebhook} /> : (
            <p className="text-xs text-[#9A9590] mt-1">{t("webhookAppearsAfterConnect")}</p>
          )}
        </Step>
      </div>
    </div>
  );

  const viberGuide = (
    <div className="space-y-4">
      <div className="text-xs text-[#9A9590] bg-[#EEEAE7]/60 rounded-sm p-3 space-y-1">
        <div className="font-semibold text-[#443C3C] mb-1.5">{t("needTitle")}</div>
        <div>• {t("viber.needItem1")}</div>
        <div>• {t("viber.needItem2")}</div>
        <div>• {t("viber.needItem3")}</div>
      </div>
      <p className="text-xs text-[#443C3C] bg-[#EEEAE7]/60 rounded-sm px-3 py-2">
        {t("viber.httpsNote")}
      </p>
      {!appBase && <AppUrlWarning />}
      <div className="space-y-3">
        <Step n={1}>
          {t.rich("viber.step1", {
            ...richMarks({
              adminPanel: (chunks) => (
                <ExtLink href="https://partners.viber.com">{chunks}</ExtLink>
              ),
            }),
          })}
        </Step>
        <Step n={2}>{t.rich("viber.step2", richMarks())}</Step>
        <Step n={3}>
          {t("viber.step3")}
          {viberWebhook ? (
            <CopyField value={viberWebhook} />
          ) : appBase ? (
            <p className="text-xs text-[#9A9590] mt-1">{t("webhookAppearsAfterConnect")}</p>
          ) : (
            <AppUrlWarning />
          )}
        </Step>
      </div>
    </div>
  );

  const instagramGuide = (
    <div className="space-y-4">
      <div className="text-xs text-[#9A9590] bg-[#EEEAE7]/60 rounded-sm p-3 space-y-1">
        <div className="font-semibold text-[#443C3C] mb-1.5">{t("needTitle")}</div>
        <div>• {t("instagram.needItem1")}</div>
        <div>• {t("instagram.needItem2")}</div>
        <div>• {t("instagram.needItem3")}</div>
      </div>
      <p className="text-xs text-[#9A9590]">{t("instagram.intro")}</p>
      <div className="text-xs text-[#443C3C] bg-[#EEEAE7]/60 rounded-sm px-3 py-2">
        {t("instagram.appReviewNote")}
      </div>
      <div className="space-y-3">
        <Step n={1}>
          {t.rich("instagram.step1", {
            ...richMarks({
              metaDev: (chunks) => (
                <ExtLink href="https://developers.facebook.com/apps">{chunks}</ExtLink>
              ),
            }),
          })}
        </Step>
        <Step n={2}>{t.rich("instagram.step2", richMarks())}</Step>
        <Step n={3}>
          <div className="font-medium">{t("instagram.step3Title")}</div>
          <div className="text-xs text-[#9A9590] mt-0.5 mb-2">{t("instagram.step3Help")}</div>
          <div className="space-y-1 mb-3">
            <div className="text-xs font-medium text-[#443C3C]">
              {t("instagram.callbackUrl")}{" "}
              <span className="font-normal text-[#9A9590]">{t("instagram.callbackUrlHint")}</span>
            </div>
            {igWebhookUrl ? <CopyField value={igWebhookUrl} /> : <AppUrlWarning />}
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium text-[#443C3C]">
              {t("instagram.verifyTokenLabel")}{" "}
              <span className="font-normal text-[#9A9590]">
                {t("instagram.verifyTokenHintLabel")}
              </span>
            </div>
            {config?.instagram_verify_token ? (
              <>
                <CopyField value={config.instagram_verify_token} masked />
                <div className="text-xs text-[#9A9590]">{t("instagram.verifyTokenSameValue")}</div>
              </>
            ) : (
              <InlineTokenSetup
                channel="instagram"
                onSave={async (token) => {
                  await api.updateInstagramSettings({ verify_token: token });
                  const updated = await api.getChannelConfig();
                  setConfig(updated);
                }}
              />
            )}
          </div>
          <div className="text-xs text-[#9A9590] mt-3 bg-[#EEEAE7]/60 rounded-sm px-3 py-2">
            {t.rich("instagram.verifyAfterSave", richMarks())}
          </div>
        </Step>
        <Step n={4}>{t.rich("instagram.step4", richMarks())}</Step>
        <Step n={5}>{t("instagram.step5")}</Step>
        <p className="text-xs text-[#9A9590]">{t("instagram.oauthPathNote")}</p>
        <p className="text-xs text-[#9A9590]">{t("instagram.tokenExpiryNote")}</p>
      </div>
    </div>
  );

  const tiktokGuide = (
    <div className="space-y-4">
      <div className="text-xs text-[#9A9590] bg-[#EEEAE7]/60 rounded-sm p-3 space-y-1">
        <div className="font-semibold text-[#443C3C] mb-1.5">{t("needTitle")}</div>
        <div>• {t("tiktok.needItem1")}</div>
        <div>• {t("tiktok.needItem2")}</div>
        <div>• {t("tiktok.needItem3")}</div>
      </div>
      <p className="text-xs text-[#9A9590]">
        {tiktokPendingAccess ? t("tiktok.introPending") : t("tiktok.introEnabled")}
      </p>
      <div className="space-y-3">
        <Step n={1}>
          {t.rich("tiktok.step1", {
            ...richMarks({
              docs: (chunks) => (
                <ExtLink href="https://developers.tiktok.com/doc/app-review-guidelines">
                  {chunks}
                </ExtLink>
              ),
            }),
          })}
        </Step>
        <Step n={2}>{t("tiktok.step2")}</Step>
        <Step n={3}>
          {t("tiktok.step3")}
          {tiktokWebhook ? (
            <CopyField value={tiktokWebhook} />
          ) : (
            <p className="text-xs text-[#9A9590] mt-1">{t("webhookAppearsAfterConnect")}</p>
          )}
        </Step>
      </div>
    </div>
  );

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <Link
            href="/admin/agents"
            className="text-sm text-[#6B6560] hover:text-[#251D1C] mb-1 inline-block"
          >
            ← {t("backToAgents")}
          </Link>
          <h1 className="text-2xl font-bold text-[#251D1C]">{t("title")}</h1>
          <p className="text-sm text-[#9A9590] mt-1">{t("subtitle", { agentId })}</p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="flex items-center gap-1.5 text-sm text-[#9A9590] hover:text-[#443C3C] border border-[#BEBAB7] px-3 py-1.5 rounded-sm hover:border-[#443C3C] transition-colors"
        >
          <RefreshCw size={13} /> {t("refresh")}
        </button>
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border-l-4 border-red-500 px-4 py-3 rounded-sm text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="space-y-4">
        <ChannelCard
          title={t("telegram.title")}
          icon="✈️"
          bindings={telegramBindings}
          agentId={agentId}
          channelType="telegram"
          webhookFor={webhookFor("telegram")}
          onBindingsChange={load}
          guide={telegramGuide}
        />

        <ChannelCard
          title={t("viber.title")}
          icon="💜"
          bindings={viberBindings}
          agentId={agentId}
          channelType="viber"
          webhookFor={webhookFor("viber")}
          onBindingsChange={load}
          guide={viberGuide}
        />

        <ChannelCard
          title={t("instagram.title")}
          icon="📷"
          bindings={byType("instagram")}
          agentId={agentId}
          channelType="instagram"
          oauthAvailable={config?.instagram_oauth_available === true}
          webhookFor={webhookFor("instagram")}
          onBindingsChange={load}
          guide={instagramGuide}
          settingsForm={
            config ? (
              <ChannelSettingsForm
                title={t("instagram.title")}
                currentVerifyToken={config.instagram_verify_token}
                appSecretConfigured={config.instagram_app_secret_configured}
                verifyTokenHint={t("verifyTokenHint")}
                onSave={async (data) => {
                  await api.updateInstagramSettings(data);
                  const updated = await api.getChannelConfig();
                  setConfig(updated);
                }}
              />
            ) : undefined
          }
        />

        <ChannelCard
          title={t("tiktok.title")}
          icon="🎵"
          bindings={tiktokBindings}
          agentId={agentId}
          channelType="tiktok"
          pendingAccess={
            tiktokPendingAccess ||
            tiktokBindings.some((b) => isPendingChannelAccess(b.metadata))
          }
          tiktokMessagingEnabled={tiktokMessagingEnabled}
          oauthAvailable={config?.tiktok_oauth_available === true}
          webhookFor={webhookFor("tiktok")}
          onBindingsChange={load}
          guide={tiktokGuide}
          banner={
            tiktokPendingAccess ? (
              <div className="px-5 py-3 text-xs text-[#443C3C] bg-[#FAF9F8] border-b border-[#BEBAB7]">
                {t("tiktok.pendingBanner")}
              </div>
            ) : undefined
          }
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
