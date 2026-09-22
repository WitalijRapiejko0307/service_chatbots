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
