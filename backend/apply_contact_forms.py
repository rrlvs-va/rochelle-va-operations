from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

SOURCES = {
    "index.html": "homepage",
    "about.html": "about",
    "faq.html": "faq",
    "service-policies.html": "service-policies",
    "privacy.html": "privacy",
}

COPY_REPLACEMENTS = {
    "about.html": {
        "It will open your email app with the details ready to send.":
            "Your inquiry will be sent securely to my client requests inbox for review.",
    },
    "faq.html": {
        "It will prepare an email in your email app for you to review and send.":
            "Your question will be sent securely to my client requests inbox for review.",
    },
    "privacy.html": {
        "It prepares an email to me using your email application.":
            "Your privacy question or request will be sent securely to my client requests inbox for review.",
    },
}

FORM_TAG = '<form class="form" onsubmit="sendMail(event)">'
SENDMAIL_SCRIPT = re.compile(
    r"\n?<script>\s*function sendMail\(e\)\{.*?\n\}\s*</script>\s*",
    re.DOTALL,
)


def normalize_endpoint(value: str) -> str:
    value = value.strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SystemExit("Endpoint URL must be a full https:// URL")
    return value


def add_name_attribute(text: str, field_id: str, field_name: str) -> str:
    pattern = re.compile(rf'(<(?:input|textarea)\b[^>]*\bid="{re.escape(field_id)}"\b)([^>]*>)')

    def repl(match: re.Match[str]) -> str:
        before, after = match.group(1), match.group(2)
        whole = before + after
        if re.search(r'\bname=', whole):
            return whole
        return before + f' name="{field_name}"' + after

    updated, count = pattern.subn(repl, text, count=1)
    if count != 1:
        raise RuntimeError(f"Could not uniquely add name= to field #{field_id}")
    return updated


def update_file(path: Path, source: str, endpoint: str) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text

    if FORM_TAG not in text:
        # Already wired forms are allowed when rerunning the script.
        if 'method="POST"' in text and 'name="source"' in text:
            return False
        raise RuntimeError(f"Expected contact form was not found in {path.name}")

    action = f"{endpoint}/api/inquiry"
    replacement = (
        f'<form class="form" action="{action}" method="POST">\n'
        f'      <input type="hidden" name="source" value="{source}">\n'
        '      <div aria-hidden="true" style="position:absolute;left:-10000px;top:auto;width:1px;height:1px;overflow:hidden">\n'
        '        <label>Leave this field empty <input type="text" name="website" tabindex="-1" autocomplete="off"></label>\n'
        '      </div>'
    )
    text = text.replace(FORM_TAG, replacement, 1)

    for field_id, field_name in (
        ("name", "name"),
        ("company", "company"),
        ("email", "email"),
        ("phone", "phone"),
        ("message", "message"),
    ):
        text = add_name_attribute(text, field_id, field_name)

    text = SENDMAIL_SCRIPT.sub("\n", text, count=1)

    for old, new in COPY_REPLACEMENTS.get(path.name, {}).items():
        if old in text:
            text = text.replace(old, new, 1)

    if text == original:
        return False

    path.write_text(text, encoding="utf-8")
    return True


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: apply_contact_forms.py https://endpoint.wasmer.app")

    endpoint = normalize_endpoint(sys.argv[1])
    changed = []
    for filename, source in SOURCES.items():
        path = ROOT / filename
        if update_file(path, source, endpoint):
            changed.append(filename)

    if changed:
        print("Updated: " + ", ".join(changed))
    else:
        print("No form changes were needed.")


if __name__ == "__main__":
    main()
