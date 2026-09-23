/** Sidebar navigation — operator desk: inbox, CRM, questionnaires, stats. */

"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useAdminWebSocket } from "@/lib/hooks/useAdminWebSocket";
import { api } from "@/lib/api";
import {
  Bot,
  MessageSquare,
  Bell,
  ClipboardList,
  BarChart3,
  Kanban,
  FileText,
  X,
} from "lucide-react";
import { LanguageSwitcher } from "@/components/shared/LanguageSwitcher";

function useNavItems() {
  const t = useTranslations("Nav");
  return [
    { name: t("agents"), href: "/admin/agents", icon: <Bot size={20} /> },
    { name: t("conversations"), href: "/admin/conversations", icon: <MessageSquare size={20} /> },
    { name: t("crm"), href: "/admin/crm", icon: <Kanban size={20} /> },
    { name: t("questionnaires"), href: "/admin/questionnaires", icon: <FileText size={20} /> },
    { name: t("notifications"), href: "/admin/notifications", icon: <Bell size={20} /> },
    { name: t("audit"), href: "/admin/audit", icon: <ClipboardList size={20} /> },
    { name: t("statistics"), href: "/admin/stats", icon: <BarChart3 size={20} /> },
  ];
}

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isOpen, onClose }) => {
  const pathname = usePathname();
  const t = useTranslations("Nav");
  const [needsHumanCount, setNeedsHumanCount] = useState(0);
  const { onStatsUpdate, onNewEscalation } = useAdminWebSocket();
  const navigation = useNavItems();

  useEffect(() => {
    const loadStats = async () => {
      try {
        const stats = await api.getStats();
        setNeedsHumanCount(stats.needs_human || 0);
      } catch (err) {
        console.error("Failed to load stats:", err);
      }
    };
    loadStats();
  }, []);

  useEffect(() => {
    const unsubscribeStats = onStatsUpdate((stats) => {
      if (stats.needs_human !== undefined) {
        setNeedsHumanCount(stats.needs_human);
      }
    });

    const unsubscribeEscalation = onNewEscalation(() => {
      api
        .getStats()
        .then((stats) => {
          setNeedsHumanCount(stats.needs_human || 0);
        })
        .catch((err) => {
          console.error("Failed to reload stats:", err);
        });
    });

    return () => {
      unsubscribeStats();
      unsubscribeEscalation();
    };
  }, [onStatsUpdate, onNewEscalation]);

  return (
    <aside
      className={[
        "fixed inset-y-0 left-0 z-50 w-64 bg-surface border-r border-border",
        "flex flex-col flex-shrink-0",
        "transition-transform duration-300 ease-in-out",
        isOpen ? "translate-x-0" : "-translate-x-full",
        "md:static md:translate-x-0 md:z-auto",
      ].join(" ")}
      aria-label={t("adminNav")}
    >
      <div className="relative flex items-center h-[72px] px-6 border-b border-border flex-shrink-0">
        <Link
          href="/admin/agents"
          className="text-lg font-semibold text-foreground hover:opacity-80"
          onClick={() => onClose()}
        >
          Service ChatBot
        </Link>
        <button
          onClick={onClose}
          className="absolute right-4 top-1/2 -translate-y-1/2 md:hidden p-1.5 rounded-sm text-muted-foreground hover:text-muted hover:bg-surface-hover transition-colors"
          aria-label={t("closeMenu")}
        >
          <X size={20} />
        </button>
      </div>

      <nav className="flex-1 p-4 space-y-1 overflow-y-auto" aria-label={t("mainNav")}>
        {navigation.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
          const isConversations = item.href === "/admin/conversations";
          const showBadge = isConversations && needsHumanCount > 0;

          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onClose}
              className={`group flex items-center justify-between gap-3 px-4 py-3 md:py-2 rounded-sm transition-all duration-200 ${
                isActive
                  ? "bg-surface-hover text-foreground font-medium border-l-2 border-border-strong"
                  : "text-foreground hover:bg-surface-hover/50 hover:text-foreground"
              }`}
              aria-current={isActive ? "page" : undefined}
              aria-label={
                showBadge
                  ? t("navigateTo", { name: item.name }) +
                    ` (${t("requireAttention", { count: needsHumanCount })})`
                  : t("navigateTo", { name: item.name })
              }
            >
              <div className="flex items-center gap-3">
                <span
                  className={`flex items-center justify-center transition-colors duration-200 group-hover:text-foreground ${isActive ? "text-foreground" : "text-muted"}`}
                  aria-hidden="true"
                >
                  {item.icon}
                </span>
                <span>{item.name}</span>
              </div>
              {showBadge && (
                <span
                  className="bg-warning text-white text-xs font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center"
                  aria-label={t("requireAttention", { count: needsHumanCount })}
                >
                  {needsHumanCount > 99 ? "99+" : needsHumanCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="flex-shrink-0 p-4 border-t border-border [&_button]:w-full [&_button]:justify-center">
        <LanguageSwitcher />
      </div>
    </aside>
  );
};
