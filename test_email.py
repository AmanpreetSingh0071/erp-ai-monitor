import smtplib
from email.mime.text import MIMEText

msg = MIMEText("Test ERP Alert")
msg["Subject"] = "ERP Monitoring Test"
msg["From"] = "amanpreet.m.ahluwalia@gmail.com"
msg["To"] = "work.amanpreet.singh@gmail.com"

server = smtplib.SMTP("smtp.gmail.com", 587)
server.starttls()
server.login("amanpreet.m.ahluwalia@gmail.com", "tforqlzqtfivgxth")
server.send_message(msg)
server.quit()

print("Email sent")