"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Settings } from "lucide-react";
import { ApiError } from "@/lib/api";
import { Button } from "@/components/shared/Button";
import { INPUT_CLASS, LABEL_CLASS } from "./constants";

interface ChannelSettingsFormProps {
  title: string;
  currentVerifyToken: string;
  appSecretConfigured: boolean;
  verifyTokenHint?: string;
  onSave: (data: { verify_token?: string; app_secret?: string }) => Promise<void>;
}

export function ChannelSettingsForm({
  title,
  currentVerifyToken,
  appSecretConfigured,
  verifyTokenHint,
  onSave,
}: ChannelSettingsFormProps) {
  const t = useTranslations("Channels");
  const [verifyToken, setVerifyToken] = useState(currentVerifyToken);
  const [appSecret, setAppSecret] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setVerifyToken(currentVerifyToken);
  }, [currentVerifyToken]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setSaving(true);
    try {
      const payload: { verify_token?: string; app_secret?: string } = {};
      if (verifyToken.trim()) payload.verify_token = verifyToken.trim();
      if (appSecret.trim()) payload.app_secret = appSecret.trim();
      await onSave(payload);
      setSaved(true);
      setAppSecret("");
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : t("saveSettingsError"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSave} className="p-4 bg-surface-hover border border-border rounded-sm space-y-3">
      <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
        <Settings size={12} /> {t("appSettingsTitle", { title })}
      </div>
      {err && (
        <div className="text-xs text-danger bg-danger/10 border border-danger/30 rounded-sm px-3 py-2">
          {err}
        </div>
      )}
      <div>
        <label className={LABEL_CLASS}>{t("verifyToken")}</label>
        <input
          className={INPUT_CLASS}
          value={verifyToken}
          onChange={(e) => setVerifyToken(e.target.value)}
          placeholder={verifyTokenHint ?? t("verifyTokenHint")}
        />
        <p className="text-xs text-muted mt-1">{t("verifyTokenHelp")}</p>
      </div>
      <div>
        <label className={LABEL_CLASS}>
          {t("appSecret")}{" "}
          <span className="font-normal text-muted">{t("appSecretOptional")}</span>
        </label>
        <input
          className={INPUT_CLASS}
          type="password"
          value={appSecret}
          onChange={(e) => setAppSecret(e.target.value)}
          placeholder={
            appSecretConfigured ? t("appSecretPlaceholderSet") : t("appSecretPlaceholderUnset")
          }
          autoComplete="new-password"
        />
        <p className="text-xs text-muted mt-1">{t("appSecretHelp")}</p>
      </div>
      <Button type="submit" size="sm" disabled={saving}>
        {saving ? t("saving") : saved ? t("saved") : t("saveSettings")}
      </Button>
    </form>
  );
}
