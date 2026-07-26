"use client";

import { useState } from "react";
import { TrendingDown, Landmark, ArrowRight } from "lucide-react";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Money } from "@/components/ui/money";
import { MoneyInput } from "@/components/ui/money-input";
import { useDebt, usePayoff } from "@/lib/api/portfolio";
import type { PayoffComparison } from "@/lib/api/types";

export default function DebtPage() {
  const { data, isLoading, isError } = useDebt();
  const payoff = usePayoff();
  const [extra, setExtra] = useState("");
  const [result, setResult] = useState<PayoffComparison | null>(null);

  const hasDebt = data && data.debts.length > 0;

  function runPayoff() {
    payoff.mutate(extra || "0", { onSuccess: setResult });
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-medium tracking-tight">Debt</h1>
        <p className="mt-1 text-sm text-fg-muted">Your payoff picture, snowball vs. avalanche.</p>
      </div>

      {isLoading && <div className="grid gap-4 sm:grid-cols-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-28 w-full" />)}</div>}
      {isError && <Panel className="text-sm text-fg-muted">Couldn&apos;t load your debt summary.</Panel>}

      {data && !hasDebt && (
        <Panel className="flex flex-col items-center py-16 text-center">
          <span className="grid size-12 place-items-center rounded-2xl bg-warning/10 ring-1 ring-warning/20">
            <TrendingDown className="size-6 text-warning" />
          </span>
          <h3 className="mt-4 text-lg font-medium">No debt accounts linked</h3>
          <p className="mt-1 max-w-sm text-sm text-fg-muted">
            Connect a bank with loans or credit cards and MoneyWealth AI will map a payoff path and the
            interest you could save.
          </p>
          <Button className="mt-5">
            <Landmark className="size-4" /> Connect a bank <ArrowRight className="size-4" />
          </Button>
        </Panel>
      )}

      {hasDebt && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <Stat label="Total debt" value={<Money value={data.total_debt} />} />
            <Stat label="Minimum / month" value={<Money value={data.total_minimum_payment} />} />
            <Stat
              label="Debt-to-income"
              value={data.debt_to_income != null ? `${Math.round(data.debt_to_income * 100)}%` : "—"}
            />
          </div>

          <Panel>
            <PanelHeader title="Your debts" />
            <div className="divide-y divide-line">
              {data.debts.map((d) => (
                <div key={d.debt_id} className="flex items-center justify-between gap-4 py-3">
                  <div>
                    <p className="text-sm font-medium capitalize">{d.debt_type ?? "Debt"}</p>
                    <p className="text-xs text-fg-subtle">
                      {d.apr ? `${(Number(d.apr) * 100).toFixed(1)}% APR` : "APR n/a"}
                      {d.minimum_payment ? <> · min <Money value={d.minimum_payment} /></> : null}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    {d.above_typical_rate && <Badge tone="warning">High rate</Badge>}
                    <span className="font-medium tabular-nums">{d.balance ? <Money value={d.balance} /> : "—"}</span>
                  </div>
                </div>
              ))}
            </div>
          </Panel>

          <Panel>
            <PanelHeader title="Payoff what-if" hint="Add an extra monthly payment to compare strategies" />
            <div className="flex flex-wrap items-end gap-3">
              <div className="w-44">
                <MoneyInput value={extra} onChange={setExtra} placeholder="0.00" />
              </div>
              <Button onClick={runPayoff} loading={payoff.isPending}>Compare</Button>
            </div>
            {result && (
              <div className="mt-5 grid gap-4 sm:grid-cols-2">
                <Method title="Avalanche" m={result.avalanche} highlight />
                <Method title="Snowball" m={result.snowball} />
                {Number(result.interest_saved_with_avalanche) > 0 && (
                  <p className="sm:col-span-2 text-sm text-positive">
                    Avalanche saves <Money value={result.interest_saved_with_avalanche} /> in interest.
                  </p>
                )}
              </div>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Panel>
      <p className="text-xs text-fg-subtle">{label}</p>
      <p className="mt-1 text-2xl font-medium tracking-tight tabular-nums">{value}</p>
    </Panel>
  );
}

function Method({ title, m, highlight }: { title: string; m: PayoffComparison["avalanche"]; highlight?: boolean }) {
  return (
    <div className={`rounded-[14px] border p-4 ${highlight ? "border-brand/30 ring-glow" : "border-line"}`}>
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">{title}</p>
        {highlight && <Badge tone="brand">Recommended</Badge>}
      </div>
      <p className="mt-2 text-2xl font-medium tracking-tight">{m.months_to_payoff} mo</p>
      <p className="mt-1 text-xs text-fg-subtle">
        <Money value={m.total_interest} /> total interest
      </p>
    </div>
  );
}
