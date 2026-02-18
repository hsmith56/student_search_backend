import logging
import smtplib
import ssl
from email.message import EmailMessage

from core.config import settings

logger = logging.getLogger(__name__)


def send_signup_invitation_email(
    *,
    recipient_email: str,
    first_name: str,
    last_name: str,
    signup_code: str,
) -> bool:
    smtp_user = settings.smtp_user.strip()
    smtp_pass = settings.smtp_pass

    if smtp_user == "" or smtp_pass == "":
        logger.warning(
            "Skipping signup invitation email for %s because SMTP credentials are missing",
            recipient_email,
        )
        return False

    msg = EmailMessage()
    msg["From"] = smtp_user
    msg["To"] = recipient_email
    msg["Subject"] = "Alternative Beacon Search Account Creation"
    msg.set_content(
        f"""Hello {first_name.strip().title()}, Please use the following sign up code during account creation.

CODE: {signup_code}

To get started, begin creating your account here:
{settings.signup_invite_url}
"""
    )

    context = ssl.create_default_context()

    try:
        with smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            context=context,
            timeout=settings.smtp_timeout_seconds,
        ) as smtp_client:
            smtp_client.login(smtp_user, smtp_pass)
            smtp_client.send_message(msg)
        return True
    except Exception:
        logger.exception(
            "Failed to send signup invitation email to %s", recipient_email
        )
        return False
