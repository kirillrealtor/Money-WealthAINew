import type { NextConfig } from "next";

/**
 * Defense-in-depth HTTP headers applied to every response (static + dynamic).
 * The per-request, nonce-based Content-Security-Policy lives in `src/proxy.ts`
 * (it needs a fresh nonce per request, which static headers can't provide).
 */
const securityHeaders = [
  // Stop MIME sniffing (drive-by script execution from mistyped responses).
  { key: "X-Content-Type-Options", value: "nosniff" },
  // Clickjacking: CSP frame-ancestors is the modern guard; this covers old UAs.
  { key: "X-Frame-Options", value: "DENY" },
  // Never leak the URL (could carry tokens/ids) to third parties.
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "X-DNS-Prefetch-Control", value: "off" },
  { key: "X-Permitted-Cross-Domain-Policies", value: "none" },
  // Force HTTPS for 2y incl. subdomains (ignored by browsers over http/localhost).
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  },
  // Drop powerful APIs we never use.
  {
    key: "Permissions-Policy",
    value:
      "camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()",
  },
  // Cross-origin isolation hardening.
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
];

const nextConfig: NextConfig = {
  // Don't advertise the framework/version (info disclosure).
  poweredByHeader: false,
  reactStrictMode: true,
  turbopack: {
    root: process.cwd(),
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
