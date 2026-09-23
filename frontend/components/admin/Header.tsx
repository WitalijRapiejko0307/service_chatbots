/** Header component for admin panel. */

"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Menu } from "lucide-react";
import { removeAdminToken, getCurrentUserEmail } from "@/lib/auth";
import { ThemeToggle } from "@/components/theme/ThemeToggle";

interface HeaderProps {
  onSidebarToggle: () => void;
}

export const Header: React.FC<HeaderProps> = ({ onSidebarToggle }) => {
  const router = useRouter();
  const t = useTranslations("Header");
  const [email] = useState<string | null>(() => getCurrentUserEmail());

  const handleLogout = () => {
    removeAdminToken();
    router.push("/admin/login");
  };

  return (
      <header className="flex items-center h-[72px] bg-surface border-b border-border px-3 sm:px-4 md:px-6" role="banner">
      <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          {/* Hamburger — mobile only */}
          <button
            onClick={onSidebarToggle}
            className="md:hidden shrink-0 p-2 -ml-1 rounded-sm hover:bg-surface-hover text-foreground transition-colors"
            aria-label={t("toggleMenu")}
          >
            <Menu size={20} />
          </button>
          <h2 className="min-w-0 truncate text-base font-semibold text-foreground sm:text-lg">
            {t("adminDashboard")}
          </h2>
        </div>

        <div className="flex shrink-0 items-center gap-2 sm:gap-3 md:gap-4">
          {email && (
            <span
              className="text-sm text-muted hidden sm:block truncate max-w-[160px] md:max-w-[200px]"
              title={email}
            >
              {email}
            </span>
          )}
          <ThemeToggle />
          <button
            onClick={handleLogout}
            className="text-sm text-foreground px-3 py-1.5 rounded-sm border border-border hover:bg-surface-hover hover:border-border-strong active:bg-surface transition-all duration-150 cursor-pointer whitespace-nowrap"
            aria-label={t("logoutAria")}
          >
            {t("logout")}
          </button>
        </div>
      </div>
    </header>
  );
};
