import smtplib
from email.mime.text import MIMEText

EMAIL_FROM = "amanpreet.m.ahluwalia@gmail.com"
EMAIL_TO = "work.amanpreet.singh@gmail.com"
EMAIL_PASSWORD = "tforqlzqtfivgxth"


def send_alert(event, violations=None, anomaly=False):

    subject = "ERP Monitoring Alert"

    body = f"""
ERP Monitoring Alert

Transaction: {event["transaction_id"]}
System: {event["system"]}
Partner: {event["partner"]}

Rule Violations: {violations}
AI Anomaly: {anomaly}

Retry Count: {event["retry_count"]}
Delay Minutes: {event["delay_minutes"]}
"""

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        server.quit()

        print("Email alert sent")

    except Exception as e:
        print("Email alert failed:", e)