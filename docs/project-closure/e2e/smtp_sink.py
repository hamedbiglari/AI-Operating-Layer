"""A real SMTP server (aiosmtpd) on 127.0.0.1:1025 that writes each received message to /tmp/smtp_inbox/."""
import os, time
from aiosmtpd.controller import Controller
os.makedirs("/tmp/smtp_inbox", exist_ok=True)
class H:
    async def handle_DATA(self, server, session, envelope):
        open(f"/tmp/smtp_inbox/{time.time_ns()}.eml", "wb").write(envelope.content)
        return "250 OK"
c = Controller(H(), hostname="127.0.0.1", port=1025); c.start()
while True: time.sleep(3600)
