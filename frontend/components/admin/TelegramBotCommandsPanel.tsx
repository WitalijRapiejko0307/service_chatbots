/** Telegram bot menu commands (/restart, etc.) — loads toggles from API. */

"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { api, ApiError } from "@/lib/api";
import type { ChannelBinding, TelegramCommand } from "@/lib/types/channel";

type Props = {
  binding: ChannelBinding;
  /** When true, styles match embedded card footer (channels page). */
  embedded?: boolean;
};

type Draft = { menu: string; body: string };

const PAYMENT_COMMAND_KEYS = new Set(["paysupport", "pay", "payment", "paysupportproject"]);

function isPaymentCommand(cmd: TelegramCommand): boolean {
  const key = cmd.key.toLowerCase();
  const command = cmd.command.replace(/^\//, "").toLowerCase();
  if (PAYMENT_COMMAND_KEYS.has(key) || PAYMENT_COMMAND_KEYS.has(command)) return true;
  if (key.includes("pay") || command.includes("pay")) return true;
  return false;
}

export function TelegramBotCommandsPanel({ binding, embedded }: Props) {
  const t = useTranslations("Channels");
  const [commands, setCommands] = useState<TelegramCommand[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [savingSettingsKey, setSavingSettingsKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getTelegramCommands(binding.binding_id);
      setCommands(data.filter((cmd) => !isPaymentCommand(cmd)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("commandsLoadError"));
    } finally {
      setLoading(false);
    }
    // t is stable enough for error copy; omit from deps to avoid reload loops
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [binding.binding_id]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const next: Record<string, Draft> = {};
    for (const c of commands) {
      if (!c.supports_custom_content) continue;
      next[c.key] = {
        menu: c.menu_description ?? "",
        body: c.message ?? "",
      };
    }
    setDrafts(next);
  }, [commands]);

  const toggleCommand = async (key: string, currentEnabled: boolean) => {
    setSavingKey(key);
    setError(null);
    try {
      const updated = await api.updateTelegramCommands(binding.binding_id, {
        [key]: !currentEnabled,
      });
      setCommands(updated.filter((cmd) => !isPaymentCommand(cmd)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("commandsSaveError"));
    } finally {
      setSavingKey(null);
    }
  };

  const saveCommandSettings = async (key: string) => {
    const draft = drafts[key];
    if (!draft) return;
    setSavingSettingsKey(key);
    setError(null);
    try {
      const updated = await api.patchTelegramCommandSettings(binding.binding_id, {
        [key]: {
          menu_description: draft.menu,
          message: draft.body,
        },
      });
      setCommands(updated.filter((cmd) => !isPaymentCommand(cmd)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("commandsSaveTextError"));
    } finally {
      setSavingSettingsKey(null);
    }
  };

  const shell = embedded
    ? "px-4 py-3 bg-background border-t border-border rounded-b-sm"
    : "px-6 py-4 bg-surface-hover border-t border-border";

  if (loading) {
    return <div className={`${shell} text-sm text-muted`}>{t("commandsLoading")}</div>;
  }

  return (
    <div className={shell}>
      <p
        className={`text-xs font-semibold uppercase tracking-wider mb-3 ${
          embedded ? "text-muted" : "text-muted"
        }`}
      >
        {t("commandsPanelTitle")}
        <span className="ml-2 normal-case tracking-normal font-medium text-muted">
          · {t("commandsTelegramOnly")}
        </span>
      </p>
      {commands.length === 0 ? (
        <p className={`text-sm ${embedded ? "text-muted" : "text-muted-foreground"}`}>
          {t("commandsEmpty")}
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {commands.map((cmd) => {
            const isSavingToggle = savingKey === cmd.key;
            const isSavingForm = savingSettingsKey === cmd.key;
            const catalogDefault = cmd.default_description ?? cmd.description;
            const draft = drafts[cmd.key];
            return (
              <div
                key={cmd.key}
                className={`rounded-sm border p-3 ${
                  embedded ? "border-border bg-surface" : "border-border bg-surface"
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-mono font-semibold text-foreground">
                        {cmd.command}
                      </span>
                      {cmd.enabled && (
                        <span className="text-xs bg-success/15 text-success px-1.5 py-0.5 rounded-sm font-medium">
                          {t("commandsEnabled")}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted mt-0.5">{cmd.description}</p>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={cmd.enabled}
                    aria-label={
                      cmd.enabled
                        ? t("commandsDisable", { command: cmd.command })
                        : t("commandsEnable", { command: cmd.command })
                    }
                    disabled={isSavingToggle}
                    onClick={() => void toggleCommand(cmd.key, cmd.enabled)}
                    className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 disabled:opacity-60 ${
                      cmd.enabled ? "bg-accent" : "bg-surface-hover"
                    }`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-surface shadow ring-0 transition duration-200 ${
                        cmd.enabled ? "translate-x-5" : "translate-x-0"
                      }`}
                    />
                  </button>
                </div>

                {cmd.supports_custom_content && draft && (
                  <div className="mt-3 pt-3 border-t border-border space-y-2">
                    <label className="block">
                      <span className="text-xs font-medium text-foreground">
                        {t("commandsMenuLabel")}
                      </span>
                      <span className="block text-[11px] text-muted mt-0.5 mb-1">
                        {t("commandsMenuHint", { fallback: catalogDefault })}
                      </span>
                      <input
                        type="text"
                        maxLength={256}
                        value={draft.menu}
                        disabled={isSavingForm}
                        onChange={(e) =>
                          setDrafts((prev) => ({
                            ...prev,
                            [cmd.key]: { ...prev[cmd.key]!, menu: e.target.value },
                          }))
                        }
                        className="mt-1 w-full rounded-sm border border-border px-2 py-1.5 text-sm text-foreground bg-surface"
                      />
                    </label>
                    <label className="block">
                      <span className="text-xs font-medium text-foreground">
                        {t("commandsMessageLabel")}
                      </span>
                      <textarea
                        rows={5}
                        maxLength={4096}
                        value={draft.body}
                        disabled={isSavingForm}
                        onChange={(e) =>
                          setDrafts((prev) => ({
                            ...prev,
                            [cmd.key]: { ...prev[cmd.key]!, body: e.target.value },
                          }))
                        }
                        className="mt-1 w-full rounded-sm border border-border px-2 py-1.5 text-sm text-foreground bg-surface resize-y min-h-[80px]"
                      />
                    </label>
                    <button
                      type="button"
                      disabled={isSavingForm}
                      onClick={() => void saveCommandSettings(cmd.key)}
                      className="text-xs font-medium px-3 py-1.5 rounded-sm bg-accent text-accent-foreground hover:opacity-90 disabled:opacity-60"
                    >
                      {isSavingForm ? t("commandsSavingText") : t("commandsSaveText")}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
      <p className={`mt-3 text-xs ${embedded ? "text-muted" : "text-muted-foreground"}`}>
        {t("commandsFooter")}
      </p>
    </div>
  );
}
