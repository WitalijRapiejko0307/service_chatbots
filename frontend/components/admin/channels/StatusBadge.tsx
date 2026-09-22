"use client";

import { useTranslations } from "next-intl";
import { CheckCircle2, Circle } from "lucide-react";
import {
  isInstagramPendingReview,
  isPendingChannelAccess,
} from "@/lib/utils/channelDisplay";
import type { ChannelBinding } from "@/lib/types/channel";
import type { MessengerChannel } from "./utils";

export function StatusBadge({
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
