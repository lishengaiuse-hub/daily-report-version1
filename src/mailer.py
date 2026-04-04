#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Email Sender for Samsung CE Intelligence
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional, Dict
from datetime import datetime


class EmailSender:
    """Send formatted email reports"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "465"))
        self.sender_email = os.getenv("SENDER_EMAIL")
        self.sender_password = os.getenv("SENDER_PASSWORD")
        self.receiver_emails = self._parse_recipients(os.getenv("RECEIVER_EMAIL", ""))
        self.use_ssl = True
    
    def _parse_recipients(self, recipients: str) -> List[str]:
        """Parse comma/semicolon separated email list"""
        if not recipients:
            return []
        emails = []
        for part in recipients.replace(';', ',').split(','):
            email = part.strip()
            if '@' in email:
                emails.append(email)
        return emails
    
    def send(self, html_content: str, date_str: str = None) -> bool:
        """Send email report"""
        if not self.sender_email or not self.sender_password:
            print("❌ Email credentials not configured")
            return False
        
        if not self.receiver_emails:
            print("❌ No recipient emails configured")
            return False
        
        if not date_str:
            date_str = datetime.now().strftime('%Y-%m-%d')
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[Samsung CE Intel] Daily Briefing - {date_str}"
            msg['From'] = self.sender_email
            msg['To'] = ", ".join(self.receiver_emails)
            
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
            
            server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=30)
            server.login(self.sender_email, self.sender_password)
            server.sendmail(self.sender_email, self.receiver_emails, msg.as_string())
            server.quit()
            
            print(f"✅ Email sent to {len(self.receiver_emails)} recipient(s)")
            return True
        except Exception as e:
            print(f"❌ Email failed: {e}")
            return False
