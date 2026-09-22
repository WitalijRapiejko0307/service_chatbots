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
