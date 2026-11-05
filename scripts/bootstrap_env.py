"""Create missing local configuration and append missing keys without replacing existing values."""
from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def configure_backend() -> None:
    target = ROOT / "backend" / ".env"
    template = ROOT / "backend" / ".env.example"
    existing = dotenv_values(target) if target.exists() else {}
    defaults = dotenv_values(template)
    defaults.update({"JWT_ACCESS_SECRET": secrets.token_urlsafe(48),
                     "JWT_REFRESH_SECRET": secrets.token_urlsafe(48),
                     "PLAID_ENC_KEY": base64.b64encode(os.urandom(32)).decode(),
                     "DEMO_PASSWORD": secrets.token_urlsafe(24),
                     "ADVISOR_PROVIDER": "mock", "MAIL_TRANSPORT": "console"})
    missing = {key: value for key, value in defaults.items() if key not in existing}
    if not target.exists():
        content = template.read_text(encoding="utf-8")
        for key, value in defaults.items():
            lines = content.splitlines()
            replacement = f'{key}="{value or ""}"'
            found = any(line.startswith(key + "=") for line in lines)
            content = "\n".join(replacement if line.startswith(key + "=") else line for line in lines) + "\n"
            if not found:
                content += replacement + "\n"
        target.write_text(content, encoding="utf-8")
    elif missing:
        with target.open("a", encoding="utf-8") as output:
            output.write("\n# Missing settings added by local setup; existing settings preserved.\n")
            for key, value in missing.items():
                output.write(f'{key}="{value or ""}"\n')
    print("backend/.env ready; existing values preserved. No secrets printed.")


def main() -> None:
    configure_backend()
    frontend = ROOT / "frontend" / ".env.local"
    if not frontend.exists():
        frontend.write_text((ROOT / "frontend" / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")
    print("frontend/.env.local ready. Local simulated AI is used only for newly created backend configuration.")


if __name__ == "__main__":
    main()
