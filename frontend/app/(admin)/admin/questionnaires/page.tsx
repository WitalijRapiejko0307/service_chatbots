/** Questionnaires section — list of agents with a link to per-agent editor. */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { linkButtonSecondarySmClassName } from "@/components/shared/Button";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import type { Agent } from "@/lib/types";
import type { QuestionnaireResponsePayload } from "@/lib/types/questionnaire";

interface AgentRow {
  agent: Agent;
  fields_count: number;
  submissions_count: number;
  welcome_preview: string;
}

export default function QuestionnairesIndexPage() {
  const [rows, setRows] = useState<AgentRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void load();
  }, []);

  const load = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const agents = await api.listAgents();
      const enriched = await Promise.all(
        agents.map(async (agent) => {
          try {
            const data: QuestionnaireResponsePayload = await api.getQuestionnaireTemplate(
              agent.agent_id
            );
            const preview = (data.template.welcome_message || "").slice(0, 120);
            return {
              agent,
              fields_count: data.template.fields.length,
              submissions_count: data.submissions_count,
              welcome_preview: preview,
            };
          } catch {
            return {
              agent,
              fields_count: 0,
              submissions_count: 0,
              welcome_preview: "",
            };
          }
        })
      );
      setRows(enriched);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Failed to load questionnaires");
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">Questionnaires</h1>
        <p className="text-muted mt-1">
          Edit each agent’s questionnaire and review user submissions. The bot can start the
          questionnaire from chat when the user asks to fill it in.
        </p>
      </div>

      {error && (
        <div className="bg-danger/10 border-l-4 border-danger p-4 mb-6 rounded-sm">
          <p className="text-sm text-danger">{error}</p>
        </div>
      )}

      {rows.length === 0 ? (
        <div className="bg-surface border border-border rounded-sm p-8 text-center text-muted">
          No agents yet. Create an agent to set up a questionnaire.
        </div>
      ) : (
        <div className="bg-surface border border-border rounded-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-surface-hover text-left text-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">Agent</th>
                <th className="px-4 py-3 font-medium">Fields</th>
                <th className="px-4 py-3 font-medium">Submissions</th>
                <th className="px-4 py-3 font-medium">Welcome</th>
                <th className="px-4 py-3 font-medium text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.agent.agent_id}
                  className="border-t border-border hover:bg-surface-hover"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium text-foreground">
                      {row.agent.config?.profile?.agent_display_name ||
                        row.agent.config?.profile?.doctor_display_name ||
                        row.agent.agent_id}
                    </div>
                    <div className="text-xs text-muted">{row.agent.agent_id}</div>
                  </td>
                  <td className="px-4 py-3">{row.fields_count}</td>
                  <td className="px-4 py-3">{row.submissions_count}</td>
                  <td className="px-4 py-3 text-muted max-w-xs truncate">
                    {row.welcome_preview || <span className="italic text-muted-foreground">not set</span>}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/admin/agents/${row.agent.agent_id}/questionnaire`}
                      className={linkButtonSecondarySmClassName}
                    >
                      Open
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
