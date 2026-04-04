#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Email Sender for Samsung CE Intelligence
Sends HTML-formatted emails via SMTP
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional, Dict  # ← 添加这行导入
from datetime import datetime

class EmailSender:
    """Send formatted email reports"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.smtp_host = os.getenv("SMTP_HOST", config.get('smtp_host', 'smtp.gmail.com'))
        self.smtp_port = int(os.getenv("SMTP_PORT", config.get('smtp_port', 465)))
        self.sender_email = os.getenv("SENDER_EMAIL")
        self.sender_password = os.getenv("SENDER_PASSWORD")
        self.receiver_emails = self._parse_recipients(os.getenv("RECEIVER_EMAIL", ""))
        self.use_ssl = config.get('use_ssl', True)
    
    def _parse_recipients(self, recipients: str) -> List[str]:
        """Parse comma/semicolon separated email list"""
        if not recipients:
            return []
        
        # Split by comma or semicolon
        emails = []
        for part in recipients.replace(';', ',').split(','):
            email = part.strip()
            if '@' in email:
                emails.append(email)
        
        return emails
    
    def send(self, html_content: str, date_str: Optional[str] = None) -> bool:
        """
        Send email report
        
        Args:
            html_content: HTML email body
            date_str: Date string for subject
            
        Returns:
            True if sent successfully
        """
        if not self.sender_email or not self.sender_password:
            print("❌ Email credentials not configured")
            return False
        
        if not self.receiver_emails:
            print("❌ No recipient emails configured")
            return False
        
        if not date_str:
            date_str = datetime.now().strftime('%Y-%m-%d')
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[Samsung CE Intel] Daily Briefing - {date_str}"
            msg['From'] = self.sender_email
            msg['To'] = ", ".join(self.receiver_emails)
            msg['X-Priority'] = '3'
            
            # Attach HTML content
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
            
            # Send email
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
                server.starttls()
            
            server.login(self.sender_email, self.sender_password)
            server.sendmail(self.sender_email, self.receiver_emails, msg.as_string())
            server.quit()
            
            print(f"✅ Email sent to {len(self.receiver_emails)} recipient(s)")
            return True
            
        except smtplib.SMTPAuthenticationError:
            print("❌ SMTP authentication failed. Check email/password.")
            return False
        except smtplib.SMTPException as e:
            print(f"❌ SMTP error: {e}")
            return False
        except Exception as e:
            print(f"❌ Email failed: {e}")
            return False
    
    def send_test_email(self) -> bool:
        """Send a test email to verify configuration"""
        test_html = f"""
        <html>
        <body>
            <h1>Samsung CE Intelligence - Test Email</h1>
            <p>This is a test email to verify SMTP configuration.</p>
            <p>Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <hr>
            <p>If you received this, email configuration is working correctly.</p>
        </body>
        </html>
        """
        
        return self.send(test_html, "TEST")
