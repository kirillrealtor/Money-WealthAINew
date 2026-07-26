"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, Wallet } from "lucide-react";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Money } from "@/components/ui/money";
import { BudgetDialog } from "@/components/budgets/budget-dialog";
import {
  useBudgets,
  useDeleteBudget,
  useCreateBudget,
} from "@/lib/api/budgets";
import { categoryLabel, type Budget } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export default function BudgetsPage() {
  const { data: budgets, isLoading, isError } = useBudgets();
  const del = useDeleteBudget();
  const recreate = useCreateBudget();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Budget | null>(null);

  function openNew() {
    setEditing(null);
    setDialogOpen(true);
  }
  function openEdit(b: Budget) {
    setEditing(b);
    setDialogOpen(true);
  }

  async function onDelete(b: Budget) {
    await del.mutateAsync(b.budget_id);
    toast(`${categoryLabel(b.category)} budget deleted`, {
      action: {
        label: "Undo",
        onClick: () =>
          recreate.mutate({
            category: b.category,
            monthly_limit: String(Number(b.monthly_limit)),
            alert_at_pct: b.alert_at_pct,
          }),
      },
    });
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-medium tracking-tight">Budgets</h1>
          <p className="mt-1 text-sm text-fg-muted">Track spending against monthly limits.</p>
        </div>
        <Button onClick={openNew}>
          <Plus className="size-4" /> New budget
        </Button>
      </div>

      {isLoading && <SkeletonList />}

      {isError && (
        <Panel className="text-sm text-fg-muted">Couldn&apos;t load your budgets. Please retry.</Panel>
      )}

      {budgets && budgets.length === 0 && <EmptyState onNew={openNew} />}

      {budgets && budgets.length > 0 && (
        <div className="space-y-3">
          {budgets.map((b) => (
            <BudgetCard key={b.budget_id} budget={b} onEdit={openEdit} onDelete={onDelete} />
          ))}
        </div>
      )}

      <BudgetDialog open={dialogOpen} onOpenChange={setDialogOpen} editing={editing} />
    </div>
  );
}

function BudgetCard({
  budget: b,
  onEdit,
  onDelete,
}: {
  budget: Budget;
  onEdit: (b: Budget) => void;
  onDelete: (b: Budget) => void;
}) {
  const pct = Math.min(b.pct_used, 100);
  const over = b.pct_used > 100;
  const near = !over && b.pct_used >= b.alert_at_pct;
  return (
    <Panel className="group">
      <div className="flex items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-hover ring-1 ring-line">
            <Wallet className="size-5 text-fg-muted" />
          </span>
          <div className="min-w-0">
            <p className="truncate font-medium">{categoryLabel(b.category)}</p>
            <p className="text-xs text-fg-subtle">
              <Money value={b.spent} /> of <Money value={b.monthly_limit} /> spent
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {over ? (
            <Badge tone="negative">Over by <Money value={String(Math.abs(Number(b.remaining)))} /></Badge>
          ) : near ? (
            <Badge tone="warning">{Math.round(b.pct_used)}% used</Badge>
          ) : (
            <Badge tone="positive"><Money value={b.remaining} /> left</Badge>
          )}
          <div className="flex opacity-0 transition-opacity group-hover:opacity-100">
            <button
              onClick={() => onEdit(b)}
              aria-label="Edit budget"
              className="grid size-9 place-items-center rounded-lg text-fg-subtle hover:bg-hover hover:text-fg"
            >
              <Pencil className="size-4" />
            </button>
            <button
              onClick={() => onDelete(b)}
              aria-label="Delete budget"
              className="grid size-9 place-items-center rounded-lg text-fg-subtle hover:bg-negative/10 hover:text-negative"
            >
              <Trash2 className="size-4" />
            </button>
          </div>
        </div>
      </div>
      <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-hover">
        <div
          className={cn(
            "h-full rounded-full transition-all",
            over ? "bg-negative" : near ? "bg-warning" : "bg-gradient-to-r from-brand to-sky",
          )}
          style={{ width: `${Math.max(pct, 2)}%` }}
        />
      </div>
    </Panel>
  );
}

function EmptyState({ onNew }: { onNew: () => void }) {
  return (
    <Panel className="flex flex-col items-center py-14 text-center">
      <span className="grid size-12 place-items-center rounded-2xl bg-brand/10 ring-1 ring-brand/20">
        <Wallet className="size-6 text-brand" />
      </span>
      <h3 className="mt-4 text-lg font-medium">No budgets yet</h3>
      <p className="mt-1 max-w-xs text-sm text-fg-muted">
        Set a monthly limit for any category and MoneyWealth AI will track your pace.
      </p>
      <Button className="mt-5" onClick={onNew}>
        <Plus className="size-4" /> Create your first budget
      </Button>
    </Panel>
  );
}

function SkeletonList() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="skeleton h-[92px] w-full" />
      ))}
    </div>
  );
}
