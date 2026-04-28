"""
Microsoft Graph email connector.

Authenticates against Azure AD using the client-credentials flow (MSAL),
pulls a user's sent-mail folder via the Graph API, and feeds the emails
to the CPA enrollment endpoint.

This module provides two ways to use it:

  1. As a library:  call `fetch_sent_emails()` to get raw emails, then
     pass them to `enroll_user_from_graph()` which POSTs to /enroll.

  2. As a CLI:  `python graph_connector.py enroll user@example.com`
     does both steps end-to-end.

Environment:
    AZURE_TENANT_ID       Azure AD tenant ID
    AZURE_CLIENT_ID       App registration client ID
    AZURE_CLIENT_SECRET   App registration client secret
    CPA_BASE_URL          CPA service URL (default: http://localhost:8000)
    CPA_API_KEY           API key for CPA service (if auth enabled)
    CPA_TENANT_ID         Logical tenant ID for CPA (default: "default")

Graph permissions required (Application):
    Mail.Read             Read sent-mail history for enrollment
    User.Read.All         Resolve user principal names
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from msal import ConfidentialClientApplication

log = logging.getLogger(__name__)

# ---- Config ----

AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID", "")
AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET", "")

CPA_BASE_URL = os.environ.get("CPA_BASE_URL", "http://localhost:8000").rstrip("/")
CPA_API_KEY = os.environ.get("CPA_API_KEY", "")
CPA_TENANT_ID = os.environ.get("CPA_TENANT_ID", "default")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPES = ["https://graph.microsoft.com/.default"]

MAX_EMAILS = int(os.environ.get("CPA_MAX_ENROLL_EMAILS", "2000"))
PAGE_SIZE = 100  # Graph API max for messages


# ---- MSAL auth ----

_msal_app: Optional[ConfidentialClientApplication] = None


def _get_msal_app() -> ConfidentialClientApplication:
    global _msal_app
    if _msal_app is None:
        if not all([AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET]):
            raise RuntimeError(
                "Missing Azure AD credentials. Set AZURE_TENANT_ID, "
                "AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET."
            )
        _msal_app = ConfidentialClientApplication(
            client_id=AZURE_CLIENT_ID,
            client_credential=AZURE_CLIENT_SECRET,
            authority=f"https://login.microsoftonline.com/{AZURE_TENANT_ID}",
        )
    return _msal_app


def get_graph_token() -> str:
    """Acquire a Graph API access token via client-credentials flow."""
    app = _get_msal_app()
    result = app.acquire_token_for_client(scopes=GRAPH_SCOPES)
    if "access_token" not in result:
        error = result.get("error_description", result.get("error", "Unknown error"))
        raise RuntimeError(f"Failed to acquire Graph token: {error}")
    return result["access_token"]


# ---- Graph API helpers ----

def _graph_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {get_graph_token()}",
        "Content-Type": "application/json",
    }


def resolve_user(user_email: str) -> dict:
    """
    Look up a user by email/UPN. Returns Graph user object with id, mail,
    displayName, etc.
    """
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{GRAPH_BASE}/users/{user_email}",
            headers=_graph_headers(),
            params={"$select": "id,mail,displayName,userPrincipalName,department,jobTitle"},
        )
        resp.raise_for_status()
        return resp.json()


def fetch_sent_emails(
    user_email: str,
    max_emails: int = MAX_EMAILS,
) -> list[dict]:
    """
    Pull sent emails from a user's mailbox via Graph API.

    Returns a list of dicts with keys:
        recipient_email, body, sent_at

    The Graph sentItems folder path is:
        /users/{id}/mailFolders/sentitems/messages

    We request only the fields we need (toRecipients, body, sentDateTime)
    to minimize bandwidth.
    """
    emails: list[dict] = []
    url = f"{GRAPH_BASE}/users/{user_email}/mailFolders/sentitems/messages"
    params = {
        "$select": "toRecipients,body,sentDateTime,subject",
        "$top": str(PAGE_SIZE),
        "$orderby": "sentDateTime desc",
    }

    log.info("Fetching sent emails for %s (max %d)", user_email, max_emails)
    started = time.time()

    with httpx.Client(timeout=60) as client:
        while url and len(emails) < max_emails:
            resp = client.get(url, headers=_graph_headers(), params=params)
            resp.raise_for_status()
            data = resp.json()

            for msg in data.get("value", []):
                # Skip emails with no recipients or no body
                recipients = msg.get("toRecipients", [])
                body_obj = msg.get("body", {})
                body_content = body_obj.get("content", "")

                if not recipients or not body_content:
                    continue

                # Use the first To: recipient as the primary recipient.
                # Multi-recipient emails are still included — enrollment
                # handles them fine — but we key on the first for bucketing.
                primary_recipient = recipients[0].get("emailAddress", {}).get("address", "")
                if not primary_recipient:
                    continue

                # Strip HTML if body is HTML format
                if body_obj.get("contentType", "").lower() == "html":
                    body_content = _strip_html(body_content)

                emails.append({
                    "recipient_email": primary_recipient,
                    "body": body_content,
                    "sent_at": msg.get("sentDateTime"),
                })

                if len(emails) >= max_emails:
                    break

            # Follow @odata.nextLink for pagination
            url = data.get("@odata.nextLink")
            params = {}  # nextLink includes params already

    elapsed = time.time() - started
    log.info(
        "Fetched %d sent emails for %s in %.1fs",
        len(emails), user_email, elapsed,
    )
    return emails


def _strip_html(html: str) -> str:
    """
    Quick HTML-to-text extraction. We don't need perfect fidelity —
    the CPA preprocessor handles further cleaning. This just gets us
    from Outlook HTML to readable text.
    """
    import re
    # Remove style/script blocks
    text = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Replace <br>, <p>, <div> with newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|tr|li)>", "\n", text, flags=re.IGNORECASE)
    # Strip all remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode common HTML entities
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'")
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


# ---- Enrollment via CPA API ----

def enroll_user_from_graph(
    user_email: str,
    tenant_id: str = CPA_TENANT_ID,
    max_emails: int = MAX_EMAILS,
) -> dict:
    """
    End-to-end: fetch emails from Graph → POST to CPA /enroll.

    Returns the parsed JSON response from /enroll.
    """
    # Resolve user to get display name and department
    try:
        user_info = resolve_user(user_email)
        log.info(
            "Resolved user: %s (%s, %s)",
            user_info.get("displayName"),
            user_info.get("department"),
            user_info.get("jobTitle"),
        )
    except Exception as e:
        log.warning("Could not resolve user %s: %s (continuing anyway)", user_email, e)
        user_info = {}

    # Fetch sent emails
    raw_emails = fetch_sent_emails(user_email, max_emails=max_emails)
    if not raw_emails:
        raise ValueError(f"No sent emails found for {user_email}")

    log.info("Enrolling %s with %d emails via CPA API", user_email, len(raw_emails))

    # Build the enrollment payload
    user_id = hashlib.sha256(user_email.lower().encode()).hexdigest()[:16]
    payload = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "user_email": user_email,
        "emails": raw_emails,
    }

    # POST to CPA
    headers = {"Content-Type": "application/json"}
    if CPA_API_KEY:
        headers["X-API-Key"] = CPA_API_KEY

    with httpx.Client(timeout=300) as client:  # enrollment can be slow
        resp = client.post(
            f"{CPA_BASE_URL}/enroll",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()

    result = resp.json()
    log.info(
        "Enrollment complete: version=%s hash=%s trained=%d emails",
        result.get("cpp_version"),
        result.get("content_hash", "")[:12],
        result.get("training_email_count", 0),
    )
    return result


def score_email_via_api(
    user_email: str,
    recipient_email: str,
    email_body: str,
    tenant_id: str = CPA_TENANT_ID,
) -> dict:
    """Score a single email via the CPA /score endpoint."""
    headers = {"Content-Type": "application/json"}
    if CPA_API_KEY:
        headers["X-API-Key"] = CPA_API_KEY

    payload = {
        "tenant_id": tenant_id,
        "user_email": user_email,
        "recipient_email": recipient_email,
        "email_body": email_body,
    }

    with httpx.Client(timeout=30) as client:
        resp = client.post(
            f"{CPA_BASE_URL}/score",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
    return resp.json()


def get_cpp_status(
    user_email: str,
    tenant_id: str = CPA_TENANT_ID,
) -> dict:
    """Check enrollment status for a user."""
    headers = {}
    if CPA_API_KEY:
        headers["X-API-Key"] = CPA_API_KEY

    with httpx.Client(timeout=15) as client:
        resp = client.get(
            f"{CPA_BASE_URL}/cpp-status",
            params={"tenant_id": tenant_id, "user_email": user_email},
            headers=headers,
        )
        resp.raise_for_status()
    return resp.json()


# ---- Bulk enrollment ----

def enroll_mailboxes(
    emails: list[str],
    tenant_id: str = CPA_TENANT_ID,
    max_emails_per_user: int = MAX_EMAILS,
) -> dict[str, dict]:
    """
    Enroll a list of mailboxes. Returns {email: result_or_error} dict.
    """
    results = {}
    for i, email in enumerate(emails, 1):
        log.info("--- Enrolling %d/%d: %s ---", i, len(emails), email)
        try:
            result = enroll_user_from_graph(
                email,
                tenant_id=tenant_id,
                max_emails=max_emails_per_user,
            )
            results[email] = {"status": "success", **result}
        except Exception as e:
            log.error("Failed to enroll %s: %s", email, e)
            results[email] = {"status": "error", "error": str(e)}
    return results


# ---- CLI ----

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if len(sys.argv) < 3:
        print("Usage:")
        print("  python graph_connector.py enroll user@example.com [user2@example.com ...]")
        print("  python graph_connector.py status user@example.com")
        print("  python graph_connector.py score user@example.com recipient@example.com \"email body text\"")
        print()
        print("Environment variables:")
        print("  AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET")
        print("  CPA_BASE_URL (default: http://localhost:8000)")
        print("  CPA_API_KEY (optional)")
        print("  CPA_TENANT_ID (default: 'default')")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "enroll":
        user_emails = sys.argv[2:]
        if len(user_emails) == 1:
            result = enroll_user_from_graph(user_emails[0])
            print(json.dumps(result, indent=2))
        else:
            results = enroll_mailboxes(user_emails)
            print(json.dumps(results, indent=2))

    elif command == "status":
        result = get_cpp_status(sys.argv[2])
        print(json.dumps(result, indent=2))

    elif command == "score":
        if len(sys.argv) < 5:
            print("Usage: python graph_connector.py score user@example.com recipient@example.com \"body\"")
            sys.exit(1)
        result = score_email_via_api(sys.argv[2], sys.argv[3], sys.argv[4])
        print(json.dumps(result, indent=2))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
