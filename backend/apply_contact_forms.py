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
    "index.html": {
        '<a class="btn gold" href="mailto:rvs-va@protonmail.com?subject=VA%20support%20inquiry">Email / Contact Me</a>':
            '<a class="btn gold" href="#contact-form">Contact form</a>',
        '<p class="form-help" style="margin-top:12px">Prefer email? This opens a new message addressed directly to me.</p>':
            '<p class="form-help" style="margin-top:12px">Use the form to send your inquiry securely to my client requests inbox.</p>',
    },
    "about.html": {
        "It will open your email app with the details ready to send.":
            "Your inquiry will be sent securely to my client requests inbox for review.",
    },
    "faq.html": {
        "It will prepare an email in your email app for you to review and send.":
            "Your question will be sent securely to my client requests inbox for review.",
    },
    "service-policies.html": {
        "It prepares an email to me using your email application.":
            "Your inquiry will be sent securely to my client requests inbox for review.",
    },
    "privacy.html": {
        '<a class="btn gold" href="mailto:rvs-va@protonmail.com?subject=Privacy%20question%20or%20request">Email / Contact Me</a>':
            '<a class="btn gold" href="#contact-privacy">Contact form</a>',
        "It prepares an email to me using your email application.":
            "Your privacy question or request will be sent securely to my client requests inbox for review.",
        "Contact details are received when you decide to email me or prepare an inquiry through the website.":
            "Contact details are received only when you decide to email me or submit an inquiry through the website.",
        "The website inquiry form does not save your answers to a website database. It prepares an email in your email application so you can send the inquiry directly to me. Once sent, that message may remain in your email provider and in my email account as normal business correspondence.":
            "The website inquiry form sends the information you enter through a secure server-side endpoint hosted on Wasmer. The endpoint creates a private inquiry record in my Notion Client Requests Inbox so I can review and respond. The Notion integration credential is stored server-side and is not included in the public website code.",
        "Inquiry emails, proposals, contracts, payment records, project records, and client correspondence may be kept for as long as there is a reasonable business, contractual, tax, accounting, dispute-resolution, or legal reason to keep them.":
            "Inquiry records and emails, proposals, contracts, payment records, project records, and client correspondence may be kept for as long as there is a reasonable business, contractual, tax, accounting, dispute-resolution, or legal reason to keep them.",
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
    pattern = re.compile(rf'(<(?:input|textarea)\b[^>]*\bid="{re.escape(field_id)}")([^>]*>)')

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
    already_wired = bool(
        re.search(r'<form\b[^>]*method=["\']post["\']', text, re.IGNORECASE)
        and 'name="source"' in text
        and f'value="{source}"' in text
    )

    if FORM_TAG in text:
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
    elif not already_wired:
        raise RuntimeError(f"Expected contact form was not found in {path.name}")

    # Give the homepage button an exact form target instead of merely jumping to the section.
    if path.name == "index.html":
        wired_form = f'<form class="form" action="{endpoint}/api/inquiry" method="POST">'
        wired_form_with_id = f'<form id="contact-form" class="form" action="{endpoint}/api/inquiry" method="POST">'
        if 'id="contact-form"' not in text and wired_form in text:
            text = text.replace(wired_form, wired_form_with_id, 1)

    # Remove the old mailto submit handler even from forms that were wired earlier.
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
