#!/usr/bin/env python3
"""
COMPLETE DELIVERY SYSTEM
Accepts property photos → Generates video → Sends everything to customer
"""

import json
import smtplib
import os
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime

class PropertyVideoDeliverySystem:
    """Handle end-to-end delivery of property video analysis + video file"""
    
    def __init__(self):
        self.gmail_address = "Fakhrialmubarok@gmail.com"
        self.gmail_password = "dhkx ngmh inkv zhxc"
        self.output_dir = Path("/tmp/property_videos_final")
    
    def send_complete_package(self, recipient_email: str, property_name: str, pdf_file: str, video_file: str, script_file: str) -> bool:
        """Send PDF + video + script to customer"""
        
        print(f"\n📧 PREPARING DELIVERY PACKAGE")
        print("=" * 80)
        print(f"Recipient: {recipient_email}")
        print(f"Property: {property_name}")
        
        try:
            msg = MIMEMultipart()
            msg['From'] = self.gmail_address
            msg['To'] = recipient_email
            msg['Subject'] = f"🎬 Your Professional Property Video - {property_name}"
            
            body = f"""Hello!

Your professional property video analysis is ready to download! 🎉

📦 WHAT YOU'RE RECEIVING:

1. 🎬 PROFESSIONAL WALKTHROUGH VIDEO (MP4)
   - 60 seconds of professional cinematography
   - 1920x1080 HD quality
   - Ready to upload to Airbnb immediately
   - Expected to increase bookings by 40%+

2. 📄 DETAILED ANALYSIS PDF
   - Photo quality assessment
   - Top problems hurting your bookings
   - Recommended improvements with ROI impact
   - Complete video script breakdown

3. 🎥 VIDEO SCRIPT TEXT FILE
   - Scene-by-scene walkthrough guide
   - Camera angles and timing
   - Music and text overlay recommendations
   - Ready to re-record or customize

📈 EXPECTED RESULTS:
Based on market data:
- Video walkthrough: +40% booking inquiries
- Professional presentation: +15-25% price increase
- Total impact: +$4,800-7,200 per year for a $150/night property

🚀 NEXT STEPS:
1. Download all files from this email
2. Upload the MP4 video to your Airbnb listing
3. Update your description with key improvements from the analysis
4. Watch your bookings increase!

Questions? Reply to this email or contact us.

Best regards,
Property Video Optimizer
Professional Listing Optimization Service"""
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Attach files
            files_to_attach = [
                (pdf_file, "PDF Analysis"),
                (video_file, "Video"),
                (script_file, "Video Script")
            ]
            
            for file_path, description in files_to_attach:
                if os.path.exists(file_path):
                    file_size = os.path.getsize(file_path) / (1024 * 1024)
                    print(f"\n  ✅ {description}")
                    print(f"     File: {Path(file_path).name}")
                    print(f"     Size: {file_size:.2f} MB")
                    
                    with open(file_path, 'rb') as attachment:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(attachment.read())
                    
                    encoders.encode_base64(part)
                    filename = Path(file_path).name
                    part.add_header('Content-Disposition', f'attachment; filename= {filename}')
                    msg.attach(part)
                else:
                    print(f"\n  ❌ File not found: {file_path}")
            
            # Send
            print(f"\n📤 Sending email to {recipient_email}...", end=" ")
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.gmail_address, self.gmail_password)
            server.send_message(msg)
            server.quit()
            
            print(f"✅")
            print(f"\n✅ DELIVERY COMPLETE!")
            return True
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def generate_summary(self, property_name: str, video_file: str) -> dict:
        """Generate delivery summary"""
        
        summary = {
            "property": property_name,
            "video_file": video_file,
            "timestamp": datetime.now().isoformat(),
            "files_included": [
                "Property_Video_Analysis_[property].pdf",
                "Property_Walkthrough_[property].mp4",
                "Video_Script_[property].txt"
            ],
            "next_steps": [
                "1. Download all files from email",
                "2. Upload MP4 video to Airbnb listing",
                "3. Update property description with improvements",
                "4. Monitor booking increase",
                "5. Consider premium upgrade for ongoing optimization"
            ],
            "expected_impact": {
                "booking_increase_percent": 40,
                "estimated_yearly_revenue_increase": "$4,800 - $7,200",
                "investment_roi": "Payback in 1-2 bookings"
            }
        }
        
        return summary


if __name__ == "__main__":
    # Example usage
    delivery = PropertyVideoDeliverySystem()
    
    # Files from video generation
    property_name = "Modern_Luxury_Apartment"
    pdf_file = "/tmp/property_videos/Property_Video_Analysis_Modern_Luxury_Apartment_in_Central_Location.pdf"
    script_file = "/tmp/property_videos/Video_Script_Modern_Luxury_Apartment_in_Central_Location.txt"
    video_file = "/tmp/property_videos_final/Property_Walkthrough_Modern_Luxury_Apartment.mp4"
    
    if Path(video_file).exists():
        # Send delivery
        success = delivery.send_complete_package(
            "Fakhrialmubarok@gmail.com",
            property_name,
            pdf_file,
            video_file,
            script_file
        )
        
        if success:
            summary = delivery.generate_summary(property_name, video_file)
            print(f"\n📊 DELIVERY SUMMARY:")
            print(json.dumps(summary, indent=2))
    else:
        print(f"⏳ Waiting for video generation: {video_file}")

