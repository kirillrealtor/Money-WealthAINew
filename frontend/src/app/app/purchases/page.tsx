"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ShoppingBag, Sparkles } from "lucide-react";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { MoneyInput } from "@/components/ui/money-input";
import { Money } from "@/components/ui/money";
import { ChatMarkdown } from "@/components/advisor/chat-markdown";
import { useSendMessage } from "@/lib/api/advisor";
import { useAssessPurchase, useCapturePayPalOrder, useCreatePayPalOrder,
  usePayPalConfig, usePurchase, type Purchase } from "@/lib/api/paypal";

export default function PurchasesPage() {
  return <Suspense fallback={<p>Loading purchase...</p>}><Purchases /></Suspense>;
}

function Purchases() {
  const params = useSearchParams();
  const returnedId = params.get("purchase_id");
  const returned = usePurchase(returnedId);
  const config = usePayPalConfig();
  const assess = useAssessPurchase();
  const create = useCreatePayPalOrder();
  const capture = useCapturePayPalOrder();
  const advisor = useSendMessage();
  const [description, setDescription] = useState("Noise-cancelling headphones");
  const [amount, setAmount] = useState("149.00");
  const [local, setLocal] = useState<Purchase | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const purchase = capture.data ?? local ?? returned.data;
  const error = assess.error ?? create.error ?? capture.error ?? returned.error ?? config.error;
  const insufficient = purchase?.assessment.recommendation === "insufficient_data";
  const cancelled = params.get("cancelled") === "1";

  function check(e: React.FormEvent) {
    e.preventDefault();
    advisor.reset(); capture.reset(); create.reset(); setAcknowledged(false); setLocal(null);
    assess.mutate({ description, amount }, { onSuccess: setLocal });
  }

  function explain() {
    if (!purchase) return;
    advisor.mutate({ message: `I am considering a one-time USD ${purchase.amount} purchase: ${purchase.description}. ` +
      "Use my linked financial data and the affordability tool to explain the effect on my emergency fund. " +
      "Explain the tradeoffs and any missing data. This is a sandbox checkout; do not initiate any payment." });
  }

  function checkout() {
    if (!purchase) return;
    create.mutate(purchase.purchase_id, { onSuccess: (order) => {
      if (order.approval_url) window.location.assign(order.approval_url);
    } });
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-medium"><ShoppingBag /> Purchase planner</h1>
        <p className="mt-2 text-sm text-fg-muted">Understand the tradeoff before you pay.</p>
      </div>
      <Panel className="border border-brand/30 text-sm">
        <strong>PayPal sandbox demo</strong>
        <p className="mt-1 text-fg-muted">Test purchases only. No real money moves and no goods are delivered.
          Your bank connection remains read-only. Only you approve checkout.</p>
      </Panel>
      {config.data && !config.data.configured && <Panel role="status">
        PayPal sandbox checkout is awaiting configuration. You can still check affordability and ask the advisor.
      </Panel>}
      {error && <Panel role="alert" className="text-negative">{error.message}</Panel>}
      {returnedId && returned.isLoading && <p role="status">Retrieving your saved order...</p>}
      {cancelled && !capture.data && <Panel role="status">Checkout was cancelled. No payment has been confirmed.</Panel>}
      {!returnedId && <Panel>
        <PanelHeader title="1. Check a purchase" hint="Based on your linked USD accounts and recent spending." />
        <form onSubmit={check} className="grid gap-4 sm:max-w-lg">
          <Field label="Demo purchase" htmlFor="purchase-description">
            <Input id="purchase-description" value={description} maxLength={127} required
              onChange={(e) => { setDescription(e.target.value); setLocal(null); advisor.reset(); }} />
          </Field>
          <Field label="Price (USD)" htmlFor="purchase-amount">
            <MoneyInput id="purchase-amount" value={amount}
              onChange={(v) => { setAmount(v); setLocal(null); advisor.reset(); }} />
          </Field>
          <Button type="submit" loading={assess.isPending} disabled={!description.trim() || !amount}>Check affordability</Button>
        </form>
      </Panel>}
      {purchase && <>
        <Panel>
          <PanelHeader title={`${purchase.description} - $${purchase.amount}`} hint="Saved assessment at the time you checked." />
          <p className="font-medium">{insufficient ? "More financial data needed" :
            purchase.assessment.recommendation === "caution" ? "This purchase needs a closer look" : "Within the estimated cash buffer"}</p>
          <dl className="mt-4 grid gap-4 sm:grid-cols-3">
            <div><dt className="text-xs text-fg-muted">Linked liquid assets</dt><dd><Money value={purchase.assessment.liquid_assets} /></dd></div>
            <div><dt className="text-xs text-fg-muted">Average monthly spending</dt><dd><Money value={purchase.assessment.monthly_spend} /></dd></div>
            <div><dt className="text-xs text-fg-muted">Cash after purchase</dt><dd><Money value={purchase.assessment.post_purchase_liquid} /></dd></div>
          </dl>
          <p className="mt-4 text-sm text-fg-muted">{purchase.assessment.note}</p>
          {insufficient ? <Link className="mt-4 inline-block text-brand underline" href="/app/accounts">Connect USD accounts with transaction history</Link> :
            purchase.assessment.emergency_fund_flag && <p className="mt-3 text-sm text-warning">This would leave less than three months of estimated expenses in cash.</p>}
        </Panel>
        {!returnedId && <Panel>
          <PanelHeader title="2. Ask your AI advisor" hint="The advisor reads your financial tools to explain the tradeoffs." />
          <Button onClick={explain} loading={advisor.isPending} variant="secondary"><Sparkles /> Explain this purchase</Button>
          {advisor.error && <p role="alert" className="mt-3 text-negative">{advisor.error.message}</p>}
          {advisor.data && <div className="mt-4 space-y-3">
            {advisor.data.provider === "mock" && <p role="status" className="text-sm text-warning">
              Simulated advisor response for development. No live AI model was called.
            </p>}
            <ChatMarkdown>{advisor.data.response}</ChatMarkdown>
            <p className="text-xs text-fg-muted">Provider: {advisor.data.provider}. Tools: {advisor.data.tool_calls_made.join(", ") || "None"}.</p>
          </div>}
        </Panel>}
        <Panel>
          <PanelHeader title="3. Your decision" />
          {purchase.status === "COMPLETED" ? <div role="status">
            <p className="font-medium text-brand">Sandbox payment confirmed: <Money value={purchase.amount} /></p>
            <p className="mt-2 break-all text-sm">PayPal order: {purchase.order_id}<br />Capture: {purchase.capture_id}</p>
          </div> : returnedId ? <>
            <p className="mb-4 text-sm text-fg-muted">After approving in PayPal, confirm below to complete the sandbox payment.
              A pending payment is not a confirmed payment.</p>
            {purchase.status === "PENDING" && <p role="status" className="mb-3">PayPal is processing this payment. Check again shortly.</p>}
            <Button onClick={() => capture.mutate(purchase.purchase_id)} loading={capture.isPending}>Confirm sandbox payment</Button>
            {purchase.approval_url && <a className="ml-4 text-sm text-brand underline" href={purchase.approval_url}>Return to PayPal</a>}
          </> : <>
            <label className="mb-4 flex items-start gap-3 text-sm">
              <input type="checkbox" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} className="mt-1" />
              I reviewed the estimate and understand this is a test purchase, not a guarantee of affordability.
            </label>
            <Button onClick={checkout} loading={create.isPending}
              disabled={!acknowledged || insufficient || !config.data?.configured}>Continue to PayPal sandbox</Button>
          </>}
        </Panel>
      </>}
      {returnedId && <Link className="inline-block text-brand underline" href="/app/purchases">Plan another purchase</Link>}
    </div>
  );
}
