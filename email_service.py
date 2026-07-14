"""
Email Service: Handles all customer email delivery
Sends gap analyses, confirmations, follow-ups with PDF attachments
"""

import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.utils import formatdate
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class EmailService:
    """
    Email delivery service for ListingBoost
    Supports: Gap analysis PDFs, confirmations, follow-ups
    """
    
    def __init__(self, gmail_address=None, gmail_password=None, use_sendgrid=False):
        """
        Initialize email service with credentials
        
        Gmail approach:
          - gmail_address: your Gmail
          - gmail_password: App password (NOT your Gmail password)
          - Get from: Google Account > Security > App passwords
        
        SendGrid approach (alternative):
          - Set use_sendgrid=True
          - Set SENDGRID_API_KEY environment variable
        """
        self.gmail_address = gmail_address or os.getenv('GMAIL_ADDRESS')
        self.gmail_password = gmail_password or os.getenv('GMAIL_PASSWORD')
        self.use_sendgrid = use_sendgrid
        
        if use_sendgrid:
            from sendgrid import SendGridAPIClient
            self.sg = SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
        
        if not use_sendgrid and (not self.gmail_address or not self.gmail_password):
            logger.warning("⚠️ Email service: No credentials provided. Email sending will fail.")
            logger.warning("Set GMAIL_ADDRESS and GMAIL_PASSWORD env vars or pass to init()")
    
    def send_gap_analysis_email(self, 
                                 customer_email, 
                                 customer_name, 
                                 property_name,
                                 pdf_path=None,
                                 analysis_summary=None):
        """
        Send gap analysis email to customer
        
        Args:
            customer_email: Recipient email
            customer_name: Customer's name for personalization
            property_name: Their property name
            pdf_path: Path to PDF attachment (optional)
            analysis_summary: Dict with analysis details
        
        Returns:
            True if sent successfully, False otherwise
        """
        
        subject = f"{customer_name}: Your Personalized Airbnb Gap Analysis"
        
        # Build email body
        body = f"""Hi {customer_name},

Thank you for your interest in optimizing your Airbnb listing!

I've analyzed your property "{property_name}" and created a personalized gap analysis report.

KEY FINDINGS:
"""
        
        if analysis_summary:
            if 'missing_amenities' in analysis_summary:
                body += "\nMissing photo opportunities:\n"
                for item in analysis_summary['missing_amenities'][:3]:
                    booking_impact = item.get('booking_increase', 'Unknown')
                    body += f"  • {item.get('amenity', 'Amenity')}: +{booking_impact}% bookings\n"
            
            if 'estimated_annual_loss' in analysis_summary:
                body += f"\nEstimated annual revenue loss: ${analysis_summary['estimated_annual_loss']:,}\n"
        
        body += """
NEXT STEPS:
1. Review the attached PDF gap analysis
2. Decide which photos to add
3. Reply to this email or click below to proceed

Want professional enhancement?
I can add these photos in 24 hours for $50-100.
Let me know and we'll get started.

---
Best regards,
ListingBoost Team

P.S. Your gap analysis is attached as a PDF. Keep it for your records!
"""
        
        try:
            if self.use_sendgrid:
                return self._send_via_sendgrid(customer_email, subject, body, pdf_path)
            else:
                return self._send_via_gmail(customer_email, subject, body, pdf_path)
        except Exception as e:
            logger.error(f"❌ Failed to send email to {customer_email}: {str(e)}")
            return False
    
    def send_payment_confirmation_email(self, 
                                         customer_email, 
                                         customer_name,
                                         property_name,
                                         pdf_path=None):
        """
        Send order confirmation after payment
        """
        
        subject = f"✅ Payment Received - Analysis Coming Tomorrow"
        
        body = f"""Hi {customer_name},

Thank you for your purchase! Payment received.

Your property "{property_name}" gap analysis will be completed by tomorrow.

WHAT HAPPENS NEXT:
1. We'll enhance your photos over the next 24 hours
2. You'll receive before/after comparison
3. We'll show booking impact estimates

TIMELINE:
- Today: Gap analysis sent (see attachment)
- Tomorrow: Enhanced photos ready
- Within 48 hours: Your property with optimized photos live

Questions? Reply to this email anytime.

---
Best regards,
ListingBoost Team

P.S. Start with the attached gap analysis to identify opportunities!
"""
        
        try:
            if self.use_sendgrid:
                return self._send_via_sendgrid(customer_email, subject, body, pdf_path)
            else:
                return self._send_via_gmail(customer_email, subject, body, pdf_path)
        except Exception as e:
            logger.error(f"❌ Failed to send confirmation email to {customer_email}: {str(e)}")
            return False
    
    def send_monthly_report_email(self,
                                   customer_email,
                                   customer_name,
                                   property_name,
                                   monthly_pdf_path,
                                   booking_metrics=None):
        """
        Send monthly research report to subscriber
        """
        
        subject = f"📊 Your Monthly Airbnb Report - {property_name}"
        
        body = f"""Hi {customer_name},

Your monthly Airbnb optimization report is ready!

HIGHLIGHTS THIS MONTH:
"""
        
        if booking_metrics:
            body += f"""
  • Estimated booking improvement: {booking_metrics.get('booking_improvement', '---')}%
  • Estimated revenue impact: ${booking_metrics.get('revenue_impact', 0):,}
  • Amenity performance: {booking_metrics.get('top_amenity', 'TBD')}
"""
        
        body += """
WHAT'S INSIDE YOUR REPORT:
  • Market comparison for your location
  • Top-performing amenities in your market
  • Recommendations for next month
  • Booking psychology insights

Keep optimizing! Reply with questions anytime.

---
Best regards,
ListingBoost Research Team

P.S. Next month's report will be even better with more data!
"""
        
        try:
            if self.use_sendgrid:
                return self._send_via_sendgrid(customer_email, subject, body, monthly_pdf_path)
            else:
                return self._send_via_gmail(customer_email, subject, body, monthly_pdf_path)
        except Exception as e:
            logger.error(f"❌ Failed to send monthly report to {customer_email}: {str(e)}")
            return False
    
    def _send_via_gmail(self, to_email, subject, body, pdf_path=None):
        """
        Internal: Send email via Gmail SMTP
        """
        
        # Create message
        message = MIMEMultipart('alternative')
        message['From'] = self.gmail_address
        message['To'] = to_email
        message['Subject'] = subject
        message['Date'] = formatdate(localtime=True)
        
        # Attach body
        message.attach(MIMEText(body, 'plain'))
        
        # Attach PDF if provided
        if pdf_path and os.path.exists(pdf_path):
            try:
                with open(pdf_path, 'rb') as attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment.read())
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename= {Path(pdf_path).name}'
                    )
                    message.attach(part)
                logger.info(f"✅ PDF attached: {pdf_path}")
            except Exception as e:
                logger.error(f"⚠️ Could not attach PDF: {str(e)}")
        
        # Send via Gmail
        try:
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(self.gmail_address, self.gmail_password)
                server.send_message(message)
            
            logger.info(f"✅ Email sent to {to_email}")
            return True
        
        except smtplib.SMTPAuthenticationError:
            logger.error("❌ Gmail authentication failed. Check credentials.")
            logger.error("   Use App Password, not your Gmail password:")
            logger.error("   https://myaccount.google.com/apppasswords")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"❌ SMTP error: {str(e)}")
            return False
    
    def _send_via_sendgrid(self, to_email, subject, body, pdf_path=None):
        """
        Internal: Send email via SendGrid
        """
        from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType
        import base64
        
        try:
            message = Mail(
                from_email=self.gmail_address,
                to_emails=to_email,
                subject=subject,
                plain_text_content=body
            )
            
            # Attach PDF if provided
            if pdf_path and os.path.exists(pdf_path):
                with open(pdf_path, 'rb') as attachment:
                    encoded = base64.b64encode(attachment.read()).decode()
                    message.attachment = Attachment(
                        FileContent(encoded),
                        FileName(Path(pdf_path).name),
                        FileType('application/pdf')
                    )
            
            # Send
            self.sg.send(message)
            logger.info(f"✅ Email sent via SendGrid to {to_email}")
            return True
        
        except Exception as e:
            logger.error(f"❌ SendGrid error: {str(e)}")
            return False


# Quick test function
def test_email_service():
    """
    Test email service with sample email
    """
    
    # Initialize
    email_service = EmailService()
    
    # Test (send to your own email)
    test_email = os.getenv('TEST_EMAIL', 'your-email@gmail.com')
    
    success = email_service.send_gap_analysis_email(
        customer_email=test_email,
        customer_name='Test Customer',
        property_name='Test Property',
        analysis_summary={
            'missing_amenities': [
                {'amenity': 'Hot Tub', 'booking_increase': 68},
                {'amenity': 'Pool', 'booking_increase': 55},
            ],
            'estimated_annual_loss': 7800
        }
    )
    
    if success:
        print(f"✅ Test email sent to {test_email}")
    else:
        print("❌ Test email failed. Check credentials.")
    
    return success


if __name__ == '__main__':
    test_email_service()
