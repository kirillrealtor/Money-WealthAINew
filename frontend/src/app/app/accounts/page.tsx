"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Landmark, Trash2, RefreshCw, CircleAlert } from "lucide-react";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { Dot } from "@/components/ui/badge";
import { Money } from "@/components/ui/money";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { ConnectBankButton } from "@/components/plaid/connect-bank-button";
import { usePlaidItems, useDisconnectItem, type PlaidItem } from "@/lib/api/plaid";

export default function AccountsPage() {
  const { data: items, isLoading, isError } = usePlaidItems();

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-medium tracking-tight">Accounts</h1>
          <p className="mt-1 text-sm text-fg-muted">Securely connect your banks — read-only, via Plaid.</p>
        </div>
        {items && items.length > 0 && <ConnectBankButton size="sm" variant="secondary">Add a bank</ConnectBankButton>}
      </div>

      {isLoading && <div className="space-y-3">{[0, 1].map((i) => <div key={i} className="skeleton h-36 w-full" />)}</div>}
      {isError && <Panel className="text-sm text-fg-muted">Couldn&apos;t load your accounts.</Panel>}

      {items && items.length === 0 && (
        <Panel className="relative overflow-hidden py-14 text-center">
          <div className="absolute -right-10 -top-10 size-48 rounded-full bg-brand/15 blur-3xl" />
          <div className="relative">
            <span className="mx-auto grid size-12 place-items-center rounded-2xl bg-brand/10 ring-1 ring-brand/20">
              <Landmark className="size-6 text-brand" />
            </span>
            <h3 className="mt-4 text-lg font-medium">Connect your first bank</h3>
            <p className="mx-auto mt-1 max-w-sm text-sm text-fg-muted">
              Link an account through Plaid — encrypted and read-only — to bring your dashboard,
              budgets and advisor to life with real data.
            </p>
            <div className="mt-5 flex justify-center">
              <ConnectBankButton size="lg" />
            </div>
            <p className="mt-4 text-xs text-fg-subtle">
              Sandbox: search <span className="text-fg-muted">Platypus</span>, use{" "}
              <span className="text-fg-muted">user_good / pass_good</span>.
            </p>
          </div>
        </Panel>
      )}

      {items && items.length > 0 && (
        <div className="space-y-4">
          {items.map((item) => <ItemCard key={item.item_id} item={item} />)}
        </div>
      )}
    </div>
  );
}

function ItemCard({ item }: { item: PlaidItem }) {
  const disconnect = useDisconnectItem();
  const [confirm, setConfirm] = useState(false);
  const ok = item.item_status === "good";

  return (
    <Panel>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-hover ring-1 ring-line">
            <Landmark className="size-5 text-fg-muted" />
          </span>
          <div>
            <p className="font-medium">{item.institution_name ?? "Linked bank"}</p>
            <p className="mt-0.5 flex items-center gap-1.5 text-xs text-fg-subtle">
              {ok ? <Dot tone="positive" /> : <CircleAlert className="size-3.5 text-warning" />}
              {item.item_status === "synthetic" ? "Synthetic data - no Plaid connection" : ok ? "Connected" : "Needs attention"}
              {item.last_sync_at && <span>· synced {new Date(item.last_sync_at).toLocaleDateString()}</span>}
            </p>
          </div>
        </div>
        <button
          onClick={() => setConfirm(true)}
          aria-label="Disconnect bank"
          className="grid size-9 place-items-center rounded-lg text-fg-subtle hover:bg-negative/10 hover:text-negative"
        >
          <Trash2 className="size-4" />
        </button>
      </div>

      {item.accounts.length > 0 ? (
        <div className="mt-4 divide-y divide-line border-t border-line">
          {item.accounts.map((a) => (
            <div key={a.account_id} className="flex items-center justify-between py-2.5">
              <div className="min-w-0">
                <p className="truncate text-sm">{a.name ?? "Account"}</p>
                <p className="text-xs capitalize text-fg-subtle">{a.subtype ?? a.type ?? "—"}</p>
              </div>
              <span className="font-medium tabular-nums">
                {a.balance_current != null ? <Money value={a.balance_current} currency={a.currency_code ?? "USD"} /> : "—"}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-4 flex items-center gap-2 border-t border-line pt-4 text-sm text-fg-subtle">
          <RefreshCw className="size-4 animate-spin" /> Syncing accounts…
        </p>
      )}

      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent
          title="Disconnect this bank?"
          description="This revokes MoneyWealth AI's access at Plaid and permanently removes this bank's accounts and transactions. This can't be undone."
        >
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setConfirm(false)}>Keep connected</Button>
            <Button
              variant="danger"
              loading={disconnect.isPending}
              onClick={() =>
                disconnect.mutate(item.item_id, {
                  onSuccess: () => { toast.success("Bank disconnected"); setConfirm(false); },
                  onError: () => toast.error("Couldn't disconnect. Please retry."),
                })
              }
            >
              Disconnect
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Panel>
  );
}
