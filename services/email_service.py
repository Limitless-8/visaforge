from __future__ import annotations

import html
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config.settings import settings


def _build_html_email(subject: str, body: str) -> str:
    safe_subject = html.escape(subject)
    safe_body = html.escape(body).replace("\n", "<br>")

    return f"""
<!doctype html>
<html>
<body style="margin:0;padding:0;background:#f4f7fb;font-family:Arial,Helvetica,sans-serif;color:#111827;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f7fb;padding:32px 0;">
    <tr>
      <td align="center">
        <table width="640" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:18px;overflow:hidden;border:1px solid #e5e7eb;box-shadow:0 8px 28px rgba(15,23,42,0.08);">
          
          <tr>
            <td style="background:linear-gradient(135deg,#2563eb,#7c3aed);padding:28px 32px;color:white;">
              <div style="font-size:26px;font-weight:800;letter-spacing:-0.5px;">✈️ VisaForge</div>
              <div style="font-size:14px;opacity:0.9;margin-top:6px;">AI-assisted immigration & scholarship guidance</div>
            </td>
          </tr>

          <tr>
            <td style="padding:32px;">
              <h2 style="margin:0 0 18px;font-size:24px;line-height:1.3;color:#111827;">
                {safe_subject}
              </h2>

              <div style="font-size:16px;line-height:1.75;color:#374151;">
                {safe_body}
              </div>

              <div style="margin-top:28px;padding:18px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:14px;color:#1e40af;font-size:14px;line-height:1.6;">
                <strong>Tip:</strong> Log in to VisaForge to view your dashboard, route plan, document vault, and AI guidance.
              </div>
            </td>
          </tr>

          <tr>
            <td style="padding:22px 32px;background:#f9fafb;border-top:1px solid #e5e7eb;">
              <p style="margin:0;font-size:12px;line-height:1.6;color:#6b7280;">
                VisaForge provides guidance and information support only. It is not legal or immigration advice.
                Always verify requirements with official government and institutional sources.
              </p>
            </td>
          </tr>

        </table>

        <p style="font-size:12px;color:#9ca3af;margin-top:16px;">
          © VisaForge. Helping students plan smarter.
        </p>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def send_email(to_email: str, subject: str, body: str) -> bool:
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"VisaForge <{settings.EMAIL_FROM}>"
        msg["To"] = to_email

        plain_text = body
        html_body = _build_html_email(subject, body)

        msg.attach(MIMEText(plain_text, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)

        return True

    except Exception as e:
        print("Email error:", e)
        return False