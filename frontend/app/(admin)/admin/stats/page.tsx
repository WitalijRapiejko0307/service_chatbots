/** Statistics page with dynamic CRM pipeline metrics and period filter. */

"use client";

import { useEffect, useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import { api, ApiError } from "@/lib/api";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { StatCardGroup } from "@/components/admin/StatCardGroup";
import { PeriodComparison } from "@/components/admin/PeriodComparison";
import { Select } from "@/components/shared/Select";
import type { Stats, Period, CRMStageStat } from "@/lib/types/stats";

export default function StatsPage() {
  const t = useTranslations("Stats");
  const [stats, setStats] = useState<Stats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState<Period>("today");
  const [includeComparison, setIncludeComparison] = useState(false);

  const loadStats = useCallback(async () => {
    try {
      setIsLoading(true);
      const statsData = await api.getStats({
        period,
        include_comparison: includeComparison,
      });
      setStats(statsData);
      setError(null);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(t("failedToLoad"));
      }
    } finally {
      setIsLoading(false);
    }
  }, [period, includeComparison]);

  useEffect(() => {
    loadStats();
    // Refresh every 10 seconds
    const interval = setInterval(loadStats, 10000);
    return () => clearInterval(interval);
  }, [loadStats]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="bg-danger/10 border-l-4 border-danger p-4">
        <p className="text-sm text-danger">{error || t("failedToLoad")}</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <h1 className="text-2xl font-bold text-foreground">{t("title")}</h1>
        <div className="w-full sm:w-48">
          <Select
            value={period}
            onChange={(e) => setPeriod(e.target.value as Period)}
            options={[
              { value: "today", label: t("today") },
              { value: "last_7_days", label: t("last7Days") },
              { value: "last_30_days", label: t("last30Days") },
            ]}
          />
        </div>
      </div>

      {includeComparison && stats.comparison && (
        <PeriodComparison
          comparison={stats.comparison}
          currentStats={{
            total_conversations: stats.total_conversations,
            ai_active: stats.ai_active,
            needs_human: stats.needs_human,
            human_active: stats.human_active,
            closed: stats.closed,
            marketing_new: stats.marketing_new,
            marketing_booked: stats.marketing_booked,
            marketing_no_response: stats.marketing_no_response,
            marketing_rejected: stats.marketing_rejected,
          }}
          enabled={includeComparison}
          onToggle={setIncludeComparison}
        />
      )}

      {!includeComparison && (
        <div className="mb-6">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="comparison-toggle"
              checked={includeComparison}
              onChange={(e) => setIncludeComparison(e.target.checked)}
              className="h-4 w-4 text-accent focus:ring-accent border-border rounded"
            />
            <label htmlFor="comparison-toggle" className="text-sm font-medium text-muted">
              {t("showComparison")}
            </label>
          </div>
        </div>
      )}

      <StatCardGroup
        title={t("overview")}
        cards={[
          {
            label: t("totalConversations"),
            value: stats.total_conversations,
            change: stats.comparison?.total_conversations,
            icon: "💬",
            colorClass: "bg-surface-hover text-foreground border-border",
          },
          {
            label: t("uniqueEndUsers"),
            value: stats.unique_end_users ?? 0,
            icon: "👥",
            colorClass: "bg-success/10 text-foreground border-success/30",
            href: "/admin/stats/users",
          },
        ]}
        columns={2}
      />
      <p className="text-xs text-muted -mt-6 mb-8 max-w-3xl">{t("uniqueEndUsersHint")}</p>

      <StatCardGroup
        title={t("technicalStatuses")}
        cards={[
          {
            label: t("aiActive"),
            value: stats.ai_active,
            change: stats.comparison?.ai_active,
            icon: "🤖",
            colorClass: "bg-surface-hover text-foreground border-border",
          },
          {
            label: t("needsHuman"),
            value: stats.needs_human,
            change: stats.comparison?.needs_human,
            icon: "👤",
            colorClass: "bg-warning/10 text-warning border-warning/30",
          },
          {
            label: t("humanActive"),
            value: stats.human_active,
            change: stats.comparison?.human_active,
            icon: "✋",
            colorClass: "bg-accent/10 text-accent border-accent/30",
          },
          {
            label: t("closed"),
            value: stats.closed,
            change: stats.comparison?.closed,
            icon: "✅",
            colorClass: "bg-surface-hover text-muted border-border",
          },
        ]}
        columns={4}
      />

      {/* Dynamic CRM Pipeline stats */}
      {stats.crm_stage_stats && stats.crm_stage_stats.length > 0 && (
        <div className="mb-6">
          <h2 className="text-base font-semibold text-foreground mb-3">{t("crmPipeline")}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {stats.crm_stage_stats.map((stage: CRMStageStat) => (
              <div
                key={stage.id}
                className="bg-surface rounded-sm border p-4 flex flex-col gap-1"
                style={{ borderColor: stage.color, borderLeftWidth: 4 }}
              >
                <div className="flex items-center gap-2">
                  <span
                    className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0"
                    style={{ backgroundColor: stage.color }}
                  />
                  <span className="text-xs font-medium text-foreground uppercase tracking-wide truncate">
                    {stage.name}
                  </span>
                </div>
                <span className="text-2xl font-bold text-foreground">{stage.count}</span>
                <span className="text-xs text-muted">{t("conversations")}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
