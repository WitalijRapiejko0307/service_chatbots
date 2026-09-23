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
        <span className="flex items-center gap-1.5 text-xs text-foreground">
          <Circle size={10} className="fill-border" /> {t("statusPendingAccess")}
        </span>
      );
    }
    return (
      <span className="flex items-center gap-1.5 text-xs text-muted">
        <Circle size={10} /> {t("statusNotConnected")}
      </span>
    );
  }
  if (!binding.is_active) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-warning">
        <Circle size={10} className="fill-warning/60" /> {t("statusInactive")}
      </span>
    );
  }
  if (pending) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-foreground">
        <Circle size={10} className="fill-border" /> {t("statusPendingAccess")}
      </span>
    );
  }
  if (pendingReview) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-warning">
        <Circle size={10} className="fill-warning/60" /> {t("statusPendingReview")}
      </span>
    );
  }
  if (!binding.is_verified) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-warning">
        <Circle size={10} className="fill-warning/60" /> {t("statusUnverified")}
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1.5 text-xs text-success font-medium">
      <CheckCircle2 size={12} className="fill-success/20" /> {t("statusConnected")}
    </span>
  );
}
