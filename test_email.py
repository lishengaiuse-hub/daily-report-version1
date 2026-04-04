#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Email Configuration Test Script
Run this script to test if email settings work correctly
"""

import os
import sys
from pathlib import Path

# Add src to path so we can import mailer
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mailer import EmailSender

def test_email():
    """Test email configuration"""
    
    print("=" * 60)
    print("📧 Samsung CE Intelligence - Email Test")
    print("=" * 60)
    
    # Check environment variables
    print("\n🔍 Checking environment variables:")
    
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    receiver_email = os.getenv("RECEIVER_EMAIL")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = os.getenv("SMTP_PORT", "465")
    
    print(f"   SENDER_EMAIL: {'✅ ' + sender_email if sender_email else '❌ Missing'}")
    print(f"   SENDER_PASSWORD: {'✅ Set' if sender_password else '❌ Missing'}")
    print(f"   RECEIVER_EMAIL: {'✅ ' + receiver_email if receiver_email else '❌ Missing'}")
    print(f"   SMTP_HOST: {smtp_host}")
    print(f"   SMTP_PORT: {smtp_port}")
    
    if not sender_email:
        print("\n❌ Please set SENDER_EMAIL environment variable")
        print("   Example: export SENDER_EMAIL='your-email@gmail.com'")
        return False
    
    if not sender_password:
        print("\n❌ Please set SENDER_PASSWORD environment variable")
        print("   Example: export SENDER_PASSWORD='your-app-password'")
        return False
    
    if not receiver_email:
        print("\n❌ Please set RECEIVER_EMAIL environment variable")
        print("   Example: export RECEIVER_EMAIL='recipient@example.com'")
        return False
    
    # Create email config
    email_config = {
        'smtp_host': smtp_host,
        'smtp_port': int(smtp_port),
        'use_ssl': True
    }
    
    # Create test HTML content
    from datetime import datetime
    
    test_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Samsung CE Intelligence - Test Email</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 20px;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background: white;
                border-radius: 16px;
                padding: 30px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            }}
            .header {{
                background: linear-gradient(135deg, #1428a0 0%, #0f1a5e 100%);
                color: white;
                padding: 20px;
                border-radius: 12px;
                text-align: center;
                margin-bottom: 20px;
            }}
            .content {{
                line-height: 1.6;
                color: #333;
            }}
            .footer {{
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #eee;
                text-align: center;
                color: #666;
                font-size: 12px;
            }}
            .success {{
                color: #10b981;
                font-weight: bold;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔵 Samsung CE Intelligence</h1>
                <p>Email Configuration Test</p>
            </div>
            <div class="content">
                <p><span class="success">✅ Test email sent successfully!</span></p>
                <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p><strong>Sender:</strong> {sender_email}</p>
                <p><strong>Recipient:</strong> {receiver_email}</p>
                <p>If you received this email, your SMTP configuration is working correctly.</p>
                <hr>
                <p><strong>Next Steps:</strong></p>
                <ol>
                    <li>Run <code>python src/main.py --dry-run</code> to test full system</li>
                    <li>Run <code>python src/main.py</code> to send real reports</li>
                    <li>Check GitHub Actions for automated runs</li>
                </ol>
            </div>
            <div class="footer">
                <p>Samsung CE Intelligence System v2.0</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Send test email
    print("\n📧 Sending test email...")
    mailer = EmailSender(email_config)
    success = mailer.send(test_html, "TEST")
    
    if success:
        print("\n" + "=" * 60)
        print("✅ TEST PASSED! Email sent successfully.")
        print("=" * 60)
        print(f"\n📬 Please check your inbox at: {receiver_email}")
        print("   (Also check spam/junk folder if not in inbox)")
        return True
    else:
        print("\n" + "=" * 60)
        print("❌ TEST FAILED! Could not send email.")
        print("=" * 60)
        print("\n🔧 Troubleshooting tips:")
        print("   1. For Gmail: Enable 2-Step Verification and use App Password")
        print("   2. For Gmail: Check https://myaccount.google.com/apppasswords")
        print("   3. Verify SENDER_EMAIL and SENDER_PASSWORD are correct")
        print("   4. Check if SMTP_HOST and SMTP_PORT are correct")
        return False

def test_with_manual_input():
    """Test with manual input (for first-time setup)"""
    print("=" * 60)
    print("📧 Manual Email Configuration Test")
    print("=" * 60)
    
    # Ask for email configuration
    sender_email = input("Enter sender email (e.g., your-email@gmail.com): ").strip()
    sender_password = input("Enter app password (16 characters): ").strip()
    receiver_email = input("Enter recipient email: ").strip()
    
    # Set environment variables
    os.environ['SENDER_EMAIL'] = sender_email
    os.environ['SENDER_PASSWORD'] = sender_password
    os.environ['RECEIVER_EMAIL'] = receiver_email
    
    # Run test
    return test_email()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test email configuration")
    parser.add_argument("--manual", action="store_true", help="Enter credentials manually")
    args = parser.parse_args()
    
    if args.manual:
        success = test_with_manual_input()
    else:
        success = test_email()
    
    sys.exit(0 if success else 1)
