#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional, Dict
from datetime import datetime

class EmailSender:
    def __init__(self, config: Dict):
        self.config = config
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "465"))
        self.sender_email = os.getenv("SENDER_EMAIL")
        self.sender_password = os.getenv("SENDER_PASSWORD")
        self.receiver_emails = self._parse_recipients(os.getenv("RECEIVER_EMAIL", ""))
        self.use_ssl = True
        
        # 调试信息
        print(f"📧 Email Configuration:")
        print(f"   SMTP Host: {self.smtp_host}")
        print(f"   SMTP Port: {self.smtp_port}")
        print(f"   Sender Email: {self.sender_email}")
        print(f"   Sender Password: {'✅ Set' if self.sender_password else '❌ Missing'}")
        print(f"   Recipients: {self.receiver_emails}")
    
    def _parse_recipients(self, recipients: str) -> List[str]:
        if not recipients:
            return []
        emails = []
        for part in recipients.replace(';', ',').split(','):
            email = part.strip()
            if '@' in email:
                emails.append(email)
        return emails
    
    def send(self, html_content: str, date_str: str = None) -> bool:
        if not self.sender_email:
            print("❌ SENDER_EMAIL not configured")
            return False
        
        if not self.sender_password:
            print("❌ SENDER_PASSWORD not configured")
            return False
        
        if not self.receiver_emails:
            print("❌ RECEIVER_EMAIL not configured")
            print("   Current value: " + os.getenv("RECEIVER_EMAIL", "NOT SET"))
            return False
        
        if not date_str:
            date_str = datetime.now().strftime('%Y-%m-%d')
        
        try:
            print(f"📧 Attempting to send email to {len(self.receiver_emails)} recipients...")
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[Samsung CE Intel] Daily Briefing - {date_str}"
            msg['From'] = self.sender_email
            msg['To'] = ", ".join(self.receiver_emails)
            
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
            
            print(f"📧 Connecting to {self.smtp_host}:{self.smtp_port}...")
            server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=30)
            
            print(f"📧 Logging in as {self.sender_email}...")
            server.login(self.sender_email, self.sender_password)
            
            print(f"📧 Sending message...")
            server.sendmail(self.sender_email, self.receiver_emails, msg.as_string())
            server.quit()
            
            print(f"✅ Email sent successfully to {len(self.receiver_emails)} recipient(s)")
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            print(f"❌ SMTP Authentication Failed: {e}")
            print("   Please check:")
            print("   1. SENDER_EMAIL is correct")
            print("   2. SENDER_PASSWORD is the correct App Password (16 characters)")
            print("   3. 2-Step Verification is enabled in Google Account")
            return False
        except smtplib.SMTPException as e:
            print(f"❌ SMTP Error: {e}")
            return False
        except Exception as e:
            print(f"❌ Email failed: {e}")
            import traceback
            traceback.print_exc()
            return False
