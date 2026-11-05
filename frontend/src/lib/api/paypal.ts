"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useApiClient } from "./client";

export type Purchase = {
  purchase_id: string;
  description: string;
  amount: string;
  currency: "USD";
  sandbox: true;
  status: "ASSESSED" | "CREATED" | "PENDING" | "COMPLETED";
  order_id: string | null;
  approval_url: string | null;
  capture_id: string | null;
  assessment: {
    recommendation: "ok" | "caution" | "insufficient_data";
    liquid_assets: string;
    monthly_spend: string;
    post_purchase_liquid: string;
    emergency_fund_flag: boolean;
    note: string;
  };
};

export function usePayPalConfig() {
  const api = useApiClient();
  return useQuery({ queryKey: ["paypal", "config"],
    queryFn: () => api.get<{ configured: boolean; sandbox: true }>("/paypal/config") });
}

export function useAssessPurchase() {
  const api = useApiClient();
  return useMutation({ mutationFn: (body: { description: string; amount: string }) =>
    api.post<Purchase>("/paypal/assess", body) });
}

export function useCreatePayPalOrder() {
  const api = useApiClient();
  return useMutation({ mutationFn: (purchase_id: string) =>
    api.post<Purchase>("/paypal/orders", { purchase_id, acknowledge: true }) });
}

export function usePurchase(id: string | null) {
  const api = useApiClient();
  return useQuery({ queryKey: ["paypal", "purchase", id], enabled: !!id,
    queryFn: () => api.get<Purchase>(`/paypal/purchases/${encodeURIComponent(id!)}`) });
}

export function useCapturePayPalOrder() {
  const api = useApiClient();
  return useMutation({ mutationFn: (id: string) =>
    api.post<Purchase>(`/paypal/purchases/${encodeURIComponent(id)}/capture`, {}) });
}
