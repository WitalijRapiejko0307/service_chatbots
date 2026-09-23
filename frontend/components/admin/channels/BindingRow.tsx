"use client";

import type React from "react";
import { useTranslations } from "next-intl";
import {
  ToggleLeft,
  ToggleRight,
  Trash2,
} from "lucide-react";
import { isPendingChannelAccess } from "@/lib/utils/channelDisplay";
import type { ChannelBinding } from "@/lib/types/channel";
import { CopyField } from "./CopyField";
import { StatusBadge } from "./StatusBadge";
import type { MessengerChannel } from "./utils";

export function BindingRow({
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
    <div className="rounded-sm border border-border bg-surface text-sm overflow-hidden">
      <div className="flex items-center gap-3 p-3">
        <div className="flex-1 min-w-0">
          <div className="font-medium text-foreground truncate">
            {binding.channel_username || binding.channel_account_id}
          </div>
          <div className="text-xs text-muted">
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
              className="text-xs text-accent hover:opacity-80 px-2 py-1 rounded-sm border border-border-strong hover:border-accent"
            >
              {t("verify")}
            </button>
          )}
          <button
            type="button"
            onClick={onToggle}
            className="text-muted hover:text-foreground"
            title={binding.is_active ? t("deactivate") : t("activate")}
          >
            {binding.is_active ? (
              <ToggleRight size={18} className="text-success" />
            ) : (
              <ToggleLeft size={18} />
            )}
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="text-muted hover:text-danger"
            title={t("removeConnection")}
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>
      {webhookUrl && (
        <div className="px-3 pb-3">
          <div className="text-xs font-medium text-foreground">{t("webhookUrl")}</div>
          <CopyField value={webhookUrl} />
        </div>
      )}
      {bottomSlot}
    </div>
  );
}
