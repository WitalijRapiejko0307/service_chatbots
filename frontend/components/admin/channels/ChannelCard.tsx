"use client";

import type React from "react";
import { useState } from "react";
import { useTranslations } from "next-intl";
import {
  ChevronDown,
  ChevronUp,
  Settings,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Button } from "@/components/shared/Button";
import { ConfirmModal } from "@/components/shared/ConfirmModal";
import { TelegramBotCommandsPanel } from "@/components/admin/TelegramBotCommandsPanel";
import type { ChannelBinding } from "@/lib/types/channel";
import { BindingRow } from "./BindingRow";
import { ConnectForm } from "./ConnectForm";
import { StatusBadge } from "./StatusBadge";
import type { MessengerChannel } from "./utils";

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

export function ChannelCard({
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
    <div className="bg-surface border border-border rounded-sm overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-border">
        <div className="flex items-center gap-3">
          <span className="text-xl">{icon}</span>
          <span className="font-semibold text-foreground text-base">{title}</span>
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
              className={`p-1 transition-colors ${settingsOpen ? "text-foreground" : "text-muted hover:text-foreground"}`}
              title={t("appSettings")}
            >
              <Settings size={16} />
            </button>
          )}
        </div>
      </div>

      {banner}

      {actionError && (
        <div className="mx-5 mt-3 text-xs text-danger bg-danger/10 border border-danger/30 rounded-sm px-3 py-2">
          {actionError}
        </div>
      )}

      {settingsForm && settingsOpen && (
        <div className="px-5 py-4 border-b border-border bg-surface-hover">{settingsForm}</div>
      )}

      {bindings.length > 0 && (
        <div className="px-5 py-3 space-y-2 border-b border-border">
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
                        className={`w-full flex items-center justify-between px-3 py-2 text-xs font-medium text-foreground bg-surface-hover border-t border-border hover:bg-surface-hover transition-colors ${
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
        <p className="px-5 py-3 text-xs text-muted border-b border-border">
          {t("emptyBindingHint")}
        </p>
      )}

      <button
        type="button"
        onClick={() => setGuideOpen((o) => !o)}
        className="w-full flex items-center justify-between px-5 py-3 text-sm text-foreground hover:bg-surface-hover transition-colors"
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
                <p className="text-xs text-muted">{t("instagram.pathsHelp")}</p>
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
