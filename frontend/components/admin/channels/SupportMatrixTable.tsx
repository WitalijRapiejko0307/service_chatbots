"use client";

import { useTranslations } from "next-intl";
import type { ChannelSupportMatrix } from "@/lib/types/channel";

export function SupportMatrixTable({ matrix }: { matrix: ChannelSupportMatrix }) {
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
    if (value === "yes") return "text-success";
    if (value === "limited") return "text-warning";
    if (value === "no") return "text-muted";
    return "text-foreground";
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
    <div className="bg-surface border border-border rounded-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-border">
        <h2 className="font-semibold text-foreground text-base">{t("matrixTitle")}</h2>
        <p className="text-xs text-muted mt-1">{t("matrixSubtitle")}</p>
        <p className="text-xs text-muted mt-2">
          <span className="text-success font-medium">{t("matrixLegendYes")}</span>
          {" · "}
          <span className="text-warning font-medium">{t("matrixLegendLimited")}</span>
          {" · "}
          <span className="text-muted font-medium">{t("matrixLegendNo")}</span>
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs text-left min-w-[640px]">
          <thead>
            <tr className="bg-surface-hover border-b border-border">
              <th className="px-3 py-2 font-medium text-foreground" />
              {channels.map((ch) => (
                <th key={ch} className="px-3 py-2 font-semibold text-foreground whitespace-nowrap">
                  {channelLabel(ch)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {capabilities.map((cap) => (
              <tr key={cap} className="border-b border-border">
                <th className="px-3 py-2 font-medium text-foreground whitespace-nowrap">
                  {capLabel(cap)}
                  {cap === "restart_command" ? (
                    <span className="block font-normal text-[10px] text-muted">
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
      <ul className="px-5 py-3 space-y-1.5 text-xs text-foreground bg-surface-hover">
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
