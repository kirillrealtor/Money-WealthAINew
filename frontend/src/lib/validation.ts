import { z } from "zod";
import { MONEY_MAX } from "@/lib/api/types";

/**
 * Shared client-side validation schemas. These mirror the backend's contracts
 * so users get inline feedback before the round-trip — the backend remains the
 * source of truth and re-validates everything.
 */

export const emailSchema = z
  .string()
  .trim()
  .min(1, "Email is required")
  .email("Enter a valid email address");

// Mirrors the backend minimum (≥8 chars). Kept deliberately non-prescriptive on
// composition — length is the dominant strength factor and avoids user friction.
export const passwordSchema = z
  .string()
  .min(8, "Password must be at least 8 characters")
  .max(200, "Password is too long");

export const loginSchema = z.object({
  email: emailSchema,
  password: z.string().min(1, "Password is required"),
});

export const signupSchema = z.object({
  email: emailSchema,
  password: passwordSchema,
});

/** A money amount as a decimal string (never a float), matching MoneyInput. */
export const amountSchema = z
  .string()
  .min(1, "Enter an amount")
  .refine((v) => /^\d+(\.\d{1,2})?$/.test(v), "Use a valid amount (max 2 decimals)")
  .refine((v) => Number(v) > 0, "Amount must be greater than zero")
  .refine((v) => Number(v) <= MONEY_MAX, "Amount is too large");

/**
 * Validate a value against a schema and return a flat field→message map.
 * Framework-agnostic so it works with the existing hand-rolled forms without a
 * full react-hook-form migration.
 */
export function validate<T>(
  schema: z.ZodType<T>,
  value: unknown,
): { ok: true; data: T } | { ok: false; errors: Record<string, string> } {
  const res = schema.safeParse(value);
  if (res.success) return { ok: true, data: res.data };
  const errors: Record<string, string> = {};
  for (const issue of res.error.issues) {
    const key = issue.path.join(".") || "_";
    if (!errors[key]) errors[key] = issue.message;
  }
  return { ok: false, errors };
}
