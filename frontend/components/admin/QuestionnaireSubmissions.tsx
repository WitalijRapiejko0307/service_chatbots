/** Submissions tab: table of fill/edit sessions and per-submission timeline. */

"use client";

import React, { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Input } from "@/components/shared/Input";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Select } from "@/components/shared/Select";
import { SegmentedControl } from "@/components/shared/SegmentedControl";
import { getChannelDisplay } from "@/lib/utils/channelDisplay";
import type {
  QuestionnaireTemplate,
  QuestionnaireSubmissionListItem,
  QuestionnaireSubmissionDetail,
  QuestionnaireResponseItem,
  QuestionnaireSubmissionSort,
} from "@/lib/types/questionnaire";

const DEFAULT_SORT: QuestionnaireSubmissionSort = "started_at_desc";

const SORT_OPTIONS: { value: QuestionnaireSubmissionSort; label: string }[] = [
  { value: "started_at_desc", label: "Started: newest first" },
  { value: "started_at_asc", label: "Started: oldest first" },
  { value: "completed_at_desc", label: "Completed: newest first" },
  { value: "completed_at_asc", label: "Completed: oldest first" },
];

interface Props {
  agentId: string;
  template: QuestionnaireTemplate;
}

const STATUS_LABEL: Record<string, string> = {
  in_progress: "In progress",
  completed: "Completed",
  cancelled: "Cancelled",
};

const SOURCE_LABEL: Record<string, string> = {
  fill: "Fill",
  edit: "Edit",
};

type SubmissionsViewMode = "compact" | "table";

const VIEW_MODE_SEGMENTS: { value: SubmissionsViewMode; label: string }[] = [
  { value: "compact", label: "Compact list" },
  { value: "table", label: "Table with answers" },
];

const CONTROL_BORDER = "border-border";

/** Column keys: template order first, then orphan keys from snapshots (sorted). */
function tableColumnKeys(
  fields: QuestionnaireTemplate["fields"],
  items: QuestionnaireSubmissionListItem[]
): string[] {
  const ordered = [...fields].sort((a, b) => a.order - b.order).map((f) => f.key);
  const known = new Set(ordered);
  const extras = new Set<string>();
  for (const row of items) {
    const snap = row.field_snapshot ?? {};
    for (const k of Object.keys(snap)) {
      if (!known.has(k)) extras.add(k);
    }
  }
  return [...ordered, ...Array.from(extras).sort((a, b) => a.localeCompare(b))];
}

export const QuestionnaireSubmissions: React.FC<Props> = ({ agentId, template }) => {
  const [items, setItems] = useState<QuestionnaireSubmissionListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [fieldKeyFilter, setFieldKeyFilter] = useState<string>("");
  const [valueSearchDraft, setValueSearchDraft] = useState("");
  const [valueSearch, setValueSearch] = useState("");
  const [sort, setSort] = useState<QuestionnaireSubmissionSort>(DEFAULT_SORT);
  const [historicFieldKeys, setHistoricFieldKeys] = useState<string[]>([]);
  const [viewMode, setViewMode] = useState<SubmissionsViewMode>("compact");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<QuestionnaireSubmissionDetail | null>(null);

  const labelByKey = useMemo(() => {
    const acc: Record<string, string> = {};
    for (const f of template.fields) acc[f.key] = f.label;
    return acc;
  }, [template.fields]);

  const fieldKeySelectOptions = useMemo(() => {
    const s = new Set<string>();
    for (const f of template.fields) s.add(f.key);
    for (const k of historicFieldKeys) s.add(k);
    return Array.from(s).sort((a, b) => a.localeCompare(b));
  }, [template.fields, historicFieldKeys]);

  const statusSelectOptions = useMemo(
    () => [
      { value: "", label: "All" },
      { value: "in_progress", label: STATUS_LABEL.in_progress },
      { value: "completed", label: STATUS_LABEL.completed },
      { value: "cancelled", label: STATUS_LABEL.cancelled },
    ],
    []
  );

  const fieldFilterSelectOptions = useMemo(() => {
    const rows = [{ value: "", label: "All fields" }];
    for (const key of fieldKeySelectOptions) {
      const lab = labelByKey[key];
      rows.push({
        value: key,
        label: lab ? `${key} — ${lab}` : `${key} (not in template)`,
      });
    }
    return rows;
  }, [fieldKeySelectOptions, labelByKey]);

  const sortSelectOptions = useMemo(
    () => SORT_OPTIONS.map((o) => ({ value: o.value, label: o.label })),
    []
  );

  useEffect(() => {
    let cancelled = false;
    void api
      .listQuestionnaireResponseFieldKeys(agentId)
      .then((keys) => {
        if (!cancelled) setHistoricFieldKeys(keys);
      })
      .catch(() => {
        if (!cancelled) setHistoricFieldKeys([]);
      });
    return () => {
      cancelled = true;
    };
  }, [agentId]);

  useEffect(() => {
    const t = setTimeout(() => setValueSearch(valueSearchDraft.trim()), 400);
    return () => clearTimeout(t);
  }, [valueSearchDraft]);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, statusFilter, fieldKeyFilter, valueSearch, sort, viewMode]);

  const hasResponseFilters = Boolean(fieldKeyFilter || valueSearch);

  const tableColumns = useMemo(
    () => tableColumnKeys(template.fields, items),
    [template.fields, items]
  );

  const load = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const params: Parameters<typeof api.listQuestionnaireSubmissions>[1] = {
        limit: 100,
        sort,
        include_field_snapshot: viewMode === "table",
      };
      if (statusFilter) {
        params.status = statusFilter as typeof params.status;
      }
      if (fieldKeyFilter) params.field_key = fieldKeyFilter;
      if (valueSearch) params.value_search = valueSearch;
      const rows = await api.listQuestionnaireSubmissions(agentId, params);
      setItems(rows);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Failed to load submissions");
    } finally {
      setIsLoading(false);
    }
  };

  const openDetail = async (submissionId: string) => {
    setSelectedId(submissionId);
    setSelectedDetail(null);
    try {
      const detail = await api.getQuestionnaireSubmission(submissionId);
      setSelectedDetail(detail);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-4 bg-surface border border-border rounded-sm p-4 shadow-sm">
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
          <Select
            label="Status"
            options={statusSelectOptions}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className={CONTROL_BORDER}
          />
          <Select
            label="Field"
            options={fieldFilterSelectOptions}
            value={fieldKeyFilter}
            onChange={(e) => setFieldKeyFilter(e.target.value)}
            className={CONTROL_BORDER}
          />
          <Input
            label="Search by value"
            type="search"
            value={valueSearchDraft}
            onChange={(e) => setValueSearchDraft(e.target.value)}
            placeholder="Substring in the latest answer…"
            className={CONTROL_BORDER}
          />
          <Select
            label="Sort"
            options={sortSelectOptions}
            value={sort}
            onChange={(e) => setSort(e.target.value as QuestionnaireSubmissionSort)}
            className={CONTROL_BORDER}
          />
        </div>
        <SegmentedControl
          label="View"
          options={VIEW_MODE_SEGMENTS}
          value={viewMode}
          onChange={(v) => setViewMode(v as SubmissionsViewMode)}
          aria-label="Submissions list view"
        />
        <details className="group text-sm text-muted border-t border-border pt-3">
          <summary className="cursor-pointer text-foreground font-medium list-none flex items-center gap-1 [&::-webkit-details-marker]:hidden">
            <span className="select-none">How filters work</span>
            <span className="text-xs text-muted group-open:hidden">(show)</span>
          </summary>
          <p className="mt-2 text-xs leading-relaxed text-muted pl-0.5">
            Value search looks at the latest answer in the session for each field. Keys that are no
            longer in the current questionnaire are loaded from saved answers — pick them in the
            Field list to search the archive.
          </p>
        </details>
      </div>

      {error && (
        <div className="bg-danger/10 border-l-4 border-danger p-3 rounded-sm">
          <p className="text-sm text-danger">{error}</p>
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-10">
          <LoadingSpinner />
        </div>
      ) : items.length === 0 ? (
        <div className="bg-surface border border-border rounded-sm p-6 text-center text-muted">
          {statusFilter || hasResponseFilters
            ? "No sessions match the selected filters."
            : "No one has filled this questionnaire yet."}
        </div>
      ) : viewMode === "compact" ? (
        <div className="bg-surface border border-border rounded-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-surface-hover text-left text-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">User</th>
                <th className="px-4 py-3 font-medium">Channel</th>
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Answers</th>
                <th className="px-4 py-3 font-medium">Started</th>
                <th className="px-4 py-3 font-medium">Completed</th>
              </tr>
            </thead>
            <tbody>
              {items.map(({ submission, answers_count }) => (
                <tr
                  key={submission.submission_id}
                  className="border-t border-border hover:bg-surface-hover cursor-pointer"
                  onClick={() => openDetail(submission.submission_id)}
                >
                  <td className="px-4 py-3 font-mono text-xs text-muted">
                    {submission.external_user_id}
                  </td>
                  <td className="px-4 py-3">{getChannelDisplay(submission.channel)}</td>
                  <td className="px-4 py-3">{SOURCE_LABEL[submission.source] || submission.source}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={submission.status} />
                  </td>
                  <td className="px-4 py-3">{answers_count}</td>
                  <td className="px-4 py-3 text-muted">{formatTime(submission.started_at)}</td>
                  <td className="px-4 py-3 text-muted">
                    {submission.completed_at
                      ? formatTime(submission.completed_at)
                      : submission.cancelled_at
                      ? formatTime(submission.cancelled_at)
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded-sm border border-border bg-surface overflow-x-auto">
          <table className="text-sm min-w-max w-full border-collapse">
            <thead className="bg-surface-hover text-left text-foreground">
              <tr>
                <th className="sticky left-0 z-30 px-3 py-3 font-medium min-w-[9rem] max-w-[9rem] bg-surface-hover shadow-[2px_0_4px_rgba(0,0,0,0.06)]">
                  User
                </th>
                <th className="sticky left-[9rem] z-20 px-3 py-3 font-medium min-w-[10rem] bg-surface-hover shadow-[2px_0_4px_rgba(0,0,0,0.04)]">
                  Started
                </th>
                <th className="sticky left-[19rem] z-10 px-3 py-3 font-medium min-w-[10rem] bg-surface-hover shadow-[2px_0_4px_rgba(0,0,0,0.04)]">
                  Completed
                </th>
                <th className="px-3 py-3 font-medium whitespace-nowrap">Channel</th>
                <th className="px-3 py-3 font-medium whitespace-nowrap">Type</th>
                <th className="px-3 py-3 font-medium whitespace-nowrap">Status</th>
                <th className="px-3 py-3 font-medium whitespace-nowrap">Answers</th>
                {tableColumns.map((key) => (
                  <th
                    key={key}
                    className="px-3 py-3 font-medium min-w-[8rem] max-w-[14rem] align-top whitespace-normal"
                    title={labelByKey[key] ? `${key} — ${labelByKey[key]}` : key}
                  >
                    <span className="line-clamp-2">{labelByKey[key] || `${key} (archive)`}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.map(({ submission, answers_count, field_snapshot }) => {
                const snap = field_snapshot ?? {};
                return (
                  <tr
                    key={submission.submission_id}
                    className="border-t border-border hover:bg-surface-hover cursor-pointer align-top"
                    onClick={() => openDetail(submission.submission_id)}
                  >
                    <td className="sticky left-0 z-20 px-3 py-2.5 font-mono text-xs text-foreground min-w-[9rem] max-w-[9rem] bg-surface shadow-[2px_0_4px_rgba(0,0,0,0.06)]">
                      {submission.external_user_id}
                    </td>
                    <td className="sticky left-[9rem] z-10 px-3 py-2.5 text-muted text-xs bg-surface whitespace-nowrap">
                      {formatTime(submission.started_at)}
                    </td>
                    <td className="sticky left-[19rem] z-10 px-3 py-2.5 text-muted text-xs bg-surface whitespace-nowrap">
                      {submission.completed_at
                        ? formatTime(submission.completed_at)
                        : submission.cancelled_at
                        ? formatTime(submission.cancelled_at)
                        : "—"}
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">{getChannelDisplay(submission.channel)}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      {SOURCE_LABEL[submission.source] || submission.source}
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <StatusBadge status={submission.status} />
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">{answers_count}</td>
                    {tableColumns.map((key) => {
                      const raw = snap[key] ?? "";
                      return (
                        <td
                          key={key}
                          className="px-3 py-2.5 text-foreground max-w-[14rem] align-top"
                          title={raw || undefined}
                        >
                          <span className="line-clamp-3 break-words">{raw || "—"}</span>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selectedId && (
        <SubmissionDrawer
          detail={selectedDetail}
          labelByKey={labelByKey}
          onClose={() => {
            setSelectedId(null);
            setSelectedDetail(null);
          }}
        />
      )}
    </div>
  );
};

function StatusBadge({ status }: { status: string }) {
  const color =
    status === "completed"
      ? "bg-success/15 text-success"
      : status === "cancelled"
      ? "bg-surface-hover text-muted"
      : "bg-warning/15 text-warning";
  return (
    <span className={`inline-block px-2 py-0.5 rounded-sm text-xs font-medium ${color}`}>
      {STATUS_LABEL[status] || status}
    </span>
  );
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

interface DrawerProps {
  detail: QuestionnaireSubmissionDetail | null;
  labelByKey: Record<string, string>;
  onClose: () => void;
}

const SubmissionDrawer: React.FC<DrawerProps> = ({ detail, labelByKey, onClose }) => {
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-overlay" onClick={onClose}>
      <aside
        className="w-full md:w-[520px] bg-surface h-full overflow-y-auto shadow-xl border-l border-border"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-surface border-b border-border px-5 py-3 flex items-center justify-between">
          <div className="font-semibold text-foreground">Submission details</div>
          <button
            onClick={onClose}
            className="text-muted hover:text-foreground"
            aria-label="Close"
          >
            ✕
          </button>
        </div>
        <div className="p-5">
          {!detail ? (
            <div className="flex justify-center py-10">
              <LoadingSpinner />
            </div>
          ) : detail.responses.length === 0 ? (
            <div className="text-sm text-muted">No answers yet.</div>
          ) : (
            <SubmissionTimeline responses={detail.responses} labelByKey={labelByKey} />
          )}
        </div>
      </aside>
    </div>
  );
};

function SubmissionTimeline({
  responses,
  labelByKey,
}: {
  responses: QuestionnaireResponseItem[];
  labelByKey: Record<string, string>;
}) {
  return (
    <ul className="space-y-3">
      {responses.map((r) => (
        <li key={r.response_id} className="border border-border rounded-sm p-3">
          <div className="text-sm font-medium text-foreground">
            {labelByKey[r.field_key] || r.field_key}
          </div>
          <div className="mt-1 text-sm text-muted whitespace-pre-wrap">{r.value}</div>
          <div className="mt-1 text-xs text-muted">{formatTime(r.created_at)}</div>
        </li>
      ))}
    </ul>
  );
}
