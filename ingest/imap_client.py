"""
PHASE 6 FALLBACK — per the project plan: "if OAuth becomes a time sink, ship
with IMAP + CSV export instead." Simpler than Gmail API — no OAuth consent
screen, just host/user/app-password via imaplib (stdlib).

def fetch_new_emails(host: str, user: str, app_password: str, folder: str = "INBOX") -> list[IncomingEmail]:
    raise NotImplementedError
"""
