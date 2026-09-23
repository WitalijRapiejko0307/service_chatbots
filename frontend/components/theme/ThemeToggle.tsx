/** Theme switcher — cycles Light -> Dark -> System, persisted via next-themes. */

"use client";

import React, { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { Sun, Moon, Monitor } from "lucide-react";
import { useTranslations } from "next-intl";

type ThemeOption = "light" | "dark" | "system";

const ORDER: ThemeOption[] = ["light", "dark", "system"];

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const t = useTranslations("Theme");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // Standard next-themes hydration-safe mount flag: theme/resolvedTheme is
    // undefined on the server and only becomes available after mount.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true);
  }, []);

  // Avoid hydration mismatch: render a stable placeholder until mounted.
  const current: ThemeOption = mounted ? ((theme as ThemeOption) ?? "system") : "system";

  const handleClick = () => {
    const nextIndex = (ORDER.indexOf(current) + 1) % ORDER.length;
    setTheme(ORDER[nextIndex]);
  };

  const icons: Record<ThemeOption, React.ReactNode> = {
    light: <Sun size={16} aria-hidden />,
    dark: <Moon size={16} aria-hidden />,
    system: <Monitor size={16} aria-hidden />,
  };

  const labels: Record<ThemeOption, string> = {
    light: t("light"),
    dark: t("dark"),
    system: t("system"),
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className="flex items-center gap-1.5 sm:gap-2 text-xs sm:text-sm text-foreground px-2 sm:px-3 py-1.5 rounded-sm border border-border hover:bg-surface-hover hover:border-border-strong transition-colors"
      aria-label={t("switchTo", { mode: labels[current] })}
      title={t("switchTo", { mode: labels[current] })}
    >
      {icons[current]}
      <span className="font-medium hidden sm:inline">{labels[current]}</span>
    </button>
  );
}
