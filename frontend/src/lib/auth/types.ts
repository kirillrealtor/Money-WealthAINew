export type User = {
  is_demo?: boolean;
  user_id: string;
  email: string;
  full_name: string | null;
  tier: "free" | "plus" | "premium";
  advisor_persona: string;
  is_verified: boolean;
  onboarding_step: number;
};

/** The backend's standardized error contract. */
export type ApiError = {
  code: string;
  message: string;
  request_id?: string;
  details?: Array<{ loc?: (string | number)[]; type?: string; msg?: string }>;
};

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";
