export type AuthMode = "password" | "magic_link";

/** Must match backend AUTH_MODE. Defaults to password for local dev. */
export function authMode(): AuthMode {
  const mode = process.env.NEXT_PUBLIC_AUTH_MODE ?? "password";
  return mode === "magic_link" ? "magic_link" : "password";
}

export function isMagicLinkAuth(): boolean {
  return authMode() === "magic_link";
}
