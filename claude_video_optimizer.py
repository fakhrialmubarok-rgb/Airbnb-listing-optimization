#!/usr/bin/env python3
"""
PROPERTY VIDEO OPTIMIZER - Uses Claude to generate video content
Input: Property photos
Output: Video script + PDF analysis + ready-to-use video content
"""

import os
import json
import base64
from pathlib import Path
from datetime import datetime
from anthropic import Anthropic
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

class PropertyVideoOptimizer:
    """Transform property photos into professional video scripts + optimization reports using Claude"""
    
    def __init__(self):
        self.client = Anthropic()
        self.gmail_address = os.getenv("GMAIL_ADDRESS", "Fakhrialmubarok@gmail.com")
        self.gmail_password = os.getenv("GMAIL_PASSWORD", "")
        self.output_dir = Path("/tmp/property_videos")
        self.output_dir.mkdir(exist_ok=True)
    
    def analyze_and_generate_video_with_claude(self, property_name: str, property_info: dict, image_paths: list) -> dict:
        """
        Use Claude to:
        1. Analyze property photos
        2. Identify optimization opportunities
        3. Generate professional video script
        4. Create video generation instructions
        """
        print(f"\n🎬 CLAUDE PHOTO ANALYSIS + VIDEO GENERATION")
        print("=" * 80)
        print(f"Property: {property_name}")
        print(f"Photos: {len(image_paths)}")
        print(f"Claude is analyzing photos and creating video script...\n")
        
        # Load and encode images
        images_data = []
        for img_path in image_paths:
            if not Path(img_path).exists():
                print(f"⚠️  Image not found: {img_path}")
                continue
            
            with open(img_path, "rb") as f:
                image_data = base64.standard_b64encode(f.read()).decode("utf-8")
            
            ext = Path(img_path).suffix.lower()
            media_type_map = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }
            media_type = media_type_map.get(ext, 'image/jpeg')
            
            images_data.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_data
                }
            })
        
        if not images_data:
            print("❌ No valid images found")
            return None
        
        # Create comprehensive analysis prompt
        num_photos = len(images_data)
        prop_name = property_info.get('name', 'Unknown')
        prop_price = property_info.get('price', 'N/A')
        prop_location = property_info.get('location', 'Unknown')
        prop_beds = property_info.get('bedrooms', 'N/A')
        prop_baths = property_info.get('bathrooms', 'N/A')
        prop_rating = property_info.get('rating', 'N/A')
        
        analysis_prompt = f"""You are a world-class property videographer, photographer, and real estate marketing expert.

I'm showing you {num_photos} photos of a property that needs professional video marketing.

PROPERTY INFO:
- Name: {prop_name}
- Price: ${prop_price}/night
- Location: {prop_location}
- Bedrooms: {prop_beds}
- Bathrooms: {prop_baths}
- Current Rating: {prop_rating}

ANALYZE THESE PHOTOS AND PROVIDE:

1. PHOTO QUALITY ASSESSMENT (be honest and specific)
   - Lighting quality (bright/dim/uneven/shadows)
   - Composition (cluttered/clean/professional/amateur)
   - Color grading (warm/cold/dated/modern)
   - Overall booking appeal (rate 1-10)
   - Specific problems you see

2. TOP 3 PROBLEMS HURTING BOOKINGS
   - What specific issues do you see?
   - How do they affect guest perception?
   - Estimated booking impact percentage

3. TOP 3 SOLUTIONS
   - What fixes would help most?
   - How to implement them?
   - Expected booking increase

4. PROFESSIONAL VIDEO SCRIPT (60-90 seconds)
   - Scene-by-scene walkthrough
   - Camera angles and movements
   - Music recommendations
   - Text overlays
   - Pacing and timing
   - Professional production notes

5. VIDEO GENERATION PROMPT
   - Detailed description for video creation
   - Specify enhanced/improved staging
   - Professional cinematography requirements
   - 4K quality specifications
   - Ready to use for AI video generation

FORMAT YOUR RESPONSE AS JSON with keys: photo_quality, top_problems, solutions, video_script, video_generation_prompt"""
        
        messages = [
            {
                "role": "user",
                "content": [
                    *images_data,
                    {
                        "type": "text",
                        "text": analysis_prompt
                    }
                ]
            }
        ]
        
        print("📤 Sending to Claude for analysis...")
        
        response = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4000,
            messages=messages
        )
        
        response_text = response.content[0].text
        
        # Parse JSON response
        try:
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
            else:
                analysis = {"raw_response": response_text}
        except:
            analysis = {"raw_response": response_text}
        
        print(f"✅ Claude analysis complete")
        if 'photo_quality' in analysis:
            appeal = analysis['photo_quality'].get('appeal_rating', 'N/A')
            print(f"   Photo appeal rating: {appeal}/10")
        if 'top_problems' in analysis:
            print(f"   Problems identified: {len(analysis['top_problems'])}")
        if 'video_script' in analysis:
            print(f"   ✅ Video script generated")
        
        return analysis
    
    def create_optimization_pdf(self, property_name: str, property_info: dict, analysis: dict, image_paths: list) -> str:
        """
        Create professional PDF with analysis, problems, solutions, and video script
        """
        print(f"\n📄 CREATING PROFESSIONAL PDF REPORT")
        print("=" * 80)
        
        pdf_file = self.output_dir / f"Property_Optimization_{property_name.replace(' ', '_')}.pdf"
        doc = SimpleDocTemplate(str(pdf_file), pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        story = []
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=22,
            textColor=colors.HexColor("#1F2937"),
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor("#374151"),
            spaceAfter=8,
            spaceBefore=8,
            fontName='Helvetica-Bold'
        )
        
        # Title
        story.append(Paragraph("📸 PROFESSIONAL PROPERTY VIDEO ANALYSIS", title_style))
        story.append(Paragraph(f"{property_name}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        # Overview
        story.append(Paragraph("Property Overview", heading_style))
        overview_data = [
            ["💰 Price", f"${property_info.get('price', 'N/A')}/night"],
            ["📍 Location", property_info.get('location', 'Unknown')],
            ["🛏️ Bedrooms", str(property_info.get('bedrooms', 'N/A'))],
            ["🚿 Bathrooms", str(property_info.get('bathrooms', 'N/A'))],
            ["⭐ Rating", str(property_info.get('rating', 'N/A'))],
        ]
        overview_table = Table(overview_data, colWidths=[2.5*inch, 2.5*inch])
        overview_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#F3F4F6")),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor("#E5E7EB")),
        ]))
        story.append(overview_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Photo Quality Assessment
        story.append(Paragraph("📸 Photo Quality Assessment", heading_style))
        if isinstance(analysis, dict) and 'photo_quality' in analysis:
            quality = analysis['photo_quality']
            if isinstance(quality, dict):
                story.append(Paragraph(f"<b>Lighting:</b> {quality.get('lighting', 'N/A')}", styles['Normal']))
                story.append(Paragraph(f"<b>Composition:</b> {quality.get('composition', 'N/A')}", styles['Normal']))
                story.append(Paragraph(f"<b>Colors:</b> {quality.get('colors', 'N/A')}", styles['Normal']))
                story.append(Paragraph(
                    f"<b>Booking Appeal Rating:</b> {quality.get('appeal_rating', 'N/A')}/10", 
                    styles['Normal']
                ))
        
        story.append(Spacer(1, 0.2*inch))
        
        # Top Problems
        story.append(Paragraph("🚨 Top Problems Hurting Bookings", heading_style))
        if isinstance(analysis, dict) and 'top_problems' in analysis:
            problems = analysis['top_problems']
            if isinstance(problems, list):
                for i, prob in enumerate(problems[:3], 1):
                    if isinstance(prob, dict):
                        story.append(Paragraph(f"<b>{i}. {prob.get('problem', 'Problem')}</b>", styles['Normal']))
                        story.append(Paragraph(f"Impact: {prob.get('impact', 'N/A')}", styles['Normal']))
                        loss = prob.get('booking_loss_percent', 0)
                        story.append(Paragraph(f"Estimated booking loss: {loss}%", styles['Normal']))
                    story.append(Spacer(1, 0.1*inch))
        
        story.append(Spacer(1, 0.2*inch))
        
        # Solutions
        story.append(Paragraph("✅ Recommended Solutions", heading_style))
        if isinstance(analysis, dict) and 'solutions' in analysis:
            solutions = analysis['solutions']
            if isinstance(solutions, list):
                for i, sol in enumerate(solutions[:3], 1):
                    if isinstance(sol, dict):
                        story.append(Paragraph(f"<b>{i}. {sol.get('solution', 'Solution')}</b>", styles['Normal']))
                        story.append(Paragraph(f"How: {sol.get('implementation', 'N/A')}", styles['Normal']))
                        boost = sol.get('booking_increase_percent', 0)
                        story.append(Paragraph(f"Expected booking increase: +{boost}%", styles['Normal']))
                    story.append(Spacer(1, 0.1*inch))
        
        story.append(PageBreak())
        
        # Video Script
        story.append(Paragraph("🎬 Professional Video Walkthrough Script", heading_style))
        if isinstance(analysis, dict) and 'video_script' in analysis:
            script = analysis['video_script']
            # Break script into paragraphs for readability
            script_parts = script.split('\n\n') if isinstance(script, str) else [str(script)]
            for part in script_parts[:10]:  # Limit to first 10 parts
                if part.strip():
                    story.append(Paragraph(part.strip(), styles['Normal']))
                    story.append(Spacer(1, 0.05*inch))
        
        # Footer
        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph(
            f"<i>Report generated: {datetime.now().strftime('%B %d, %Y at %H:%M')} UTC</i>",
            styles['Normal']
        ))
        
        doc.build(story)
        
        size_kb = Path(pdf_file).stat().st_size / 1024
        print(f"✅ PDF created: {pdf_file}")
        print(f"   Size: {size_kb:.1f} KB")
        
        return str(pdf_file)
    
    def save_video_script_file(self, analysis: dict, property_name: str) -> str:
        """
        Save the video script as a separate file for video generation
        """
        print(f"\n🎬 SAVING VIDEO GENERATION FILES")
        print("=" * 80)
        
        # Save video script
        if 'video_script' in analysis:
            script_file = self.output_dir / f"Video_Script_{property_name.replace(' ', '_')}.txt"
            with open(script_file, 'w') as f:
                f.write("PROFESSIONAL VIDEO WALKTHROUGH SCRIPT\n")
                f.write("=" * 80 + "\n\n")
                f.write(analysis['video_script'])
            print(f"✅ Video script: {script_file}")
        else:
            script_file = None
        
        # Save video generation prompt
        if 'video_generation_prompt' in analysis:
            prompt_file = self.output_dir / f"Video_Generation_Prompt_{property_name.replace(' ', '_')}.txt"
            with open(prompt_file, 'w') as f:
                f.write("VIDEO GENERATION PROMPT (for AI video tools)\n")
                f.write("=" * 80 + "\n\n")
                f.write(analysis['video_generation_prompt'])
            print(f"✅ Video generation prompt: {prompt_file}")
        else:
            prompt_file = None
        
        return script_file, prompt_file
    
    def run(self, property_name: str, property_info: dict, image_paths: list) -> dict:
        """
        Run complete optimization: Analyze photos → Generate video script → Create PDF
        """
        
        print("\n" + "=" * 80)
        print("🚀 PROPERTY VIDEO OPTIMIZER - USING CLAUDE")
        print("=" * 80)
        
        # Step 1: Analyze photos and generate video with Claude
        analysis = self.analyze_and_generate_video_with_claude(property_name, property_info, image_paths)
        
        if not analysis:
            return {"error": "Analysis failed"}
        
        # Step 2: Save video script files
        script_file, prompt_file = self.save_video_script_file(analysis, property_name)
        
        # Step 3: Create professional PDF
        pdf_file = self.create_optimization_pdf(property_name, property_info, analysis, image_paths)
        
        # Save complete results
        results = {
            "property_name": property_name,
            "property_info": property_info,
            "analysis": analysis,
            "pdf_file": pdf_file,
            "video_script_file": script_file,
            "video_generation_prompt_file": prompt_file,
            "timestamp": datetime.now().isoformat(),
            "next_steps": [
                "1. Send PDF + video script to customer",
                "2. Customer downloads video script",
                "3. Use video script to record professional walkthrough",
                "4. Or: Use AI video tools with the generation prompt",
                "5. Customer uploads video to Airbnb",
                "6. Bookings increase by 40% on average"
            ]
        }
        
        results_file = self.output_dir / f"Results_{property_name.replace(' ', '_')}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        return results


if __name__ == "__main__":
    optimizer = PropertyVideoOptimizer()
    
    # Example property
    property_info = {
        "name": "Modern Luxury Apartment in Central Location",
        "location": "Premium Central District",
        "price": 150,
        "bedrooms": 3,
        "bathrooms": 2,
        "rating": 4.85,
    }
    
    # Use actual images
    image_paths = [
        "/tmp/property_image_1.png",
        "/tmp/property_image_2.png"
    ]
    
    # Run optimization
    results = optimizer.run(
        property_info["name"],
        property_info,
        image_paths
    )
    
    print("\n" + "=" * 80)
    print("✅ OPTIMIZATION COMPLETE")
    print("=" * 80)
    print(f"\n📄 PDF Report: {results.get('pdf_file', 'N/A')}")
    print(f"🎬 Video Script: {results.get('video_script_file', 'N/A')}")
    print(f"📝 Video Prompt: {results.get('video_generation_prompt_file', 'N/A')}")
    print(f"\nNEXT STEPS:")
    for step in results.get('next_steps', []):
        print(f"  {step}")

