#!/usr/bin/env python3
"""
REAL AIRBNB LISTING ANALYZER - Using Claude + Higgsfield MCP
Generates professional videos and analysis for property improvement
"""

import os
import json
import base64
from pathlib import Path
from datetime import datetime
import subprocess
import requests
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from anthropic import Anthropic

class AirbnbPropertyAnalyzer:
    def __init__(self):
        self.client = Anthropic()
        self.model = "claude-opus-4-1-20250805"
        self.output_dir = Path("/tmp/property_analysis")
        self.output_dir.mkdir(exist_ok=True)
        
    def load_property_images(self, image_paths):
        """Load property images and encode them for Claude"""
        images_data = []
        
        for img_path in image_paths:
            if not Path(img_path).exists():
                print(f"⚠️  Image not found: {img_path}")
                continue
                
            with open(img_path, "rb") as f:
                image_data = base64.standard_b64encode(f.read()).decode("utf-8")
                
            # Determine media type
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
                },
                "path": img_path
            })
        
        return images_data
    
    def analyze_property(self, property_name, property_data, images_data):
        """Use Claude to analyze property and generate recommendations"""
        
        print(f"\n🔍 ANALYZING: {property_name}")
        print("=" * 80)
        
        # Build the analysis prompt
        analysis_prompt = f"""
You are a professional Airbnb listing optimization expert. 

Analyze these property images and the property data below:

PROPERTY DATA:
- Name: {property_data.get('name', 'Unknown')}
- Price: ${property_data.get('price', 'N/A')}/night
- Location: {property_data.get('location', 'Unknown')}
- Bedrooms: {property_data.get('bedrooms', 'N/A')}
- Bathrooms: {property_data.get('bathrooms', 'N/A')}
- Current Rating: {property_data.get('rating', 'N/A')}
- Amenities: {', '.join(property_data.get('amenities', []))}
- Description: {property_data.get('description', 'No description')}

PROPERTY IMAGES: {len(images_data)} images provided

Please provide:
1. CURRENT STRENGTHS (3-5 things working well)
2. TOP 5 GAPS (things missing that competitors have)
3. IMPROVEMENT RECOMMENDATIONS (specific, actionable)
4. ESTIMATED ROI (potential revenue impact)
5. VIDEO WALKTHROUGH CONCEPT (what a professional video should showcase)
6. PRICING OPTIMIZATION (should they raise prices based on improvements)

Format as JSON for easy parsing.
"""
        
        # Prepare messages with images
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
        
        # Get analysis from Claude
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            messages=messages
        )
        
        analysis_text = response.content[0].text
        print("\n✅ Analysis complete")
        
        # Try to parse as JSON
        try:
            # Extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
            else:
                analysis = {"raw_analysis": analysis_text}
        except:
            analysis = {"raw_analysis": analysis_text}
        
        return analysis
    
    def generate_video_prompt(self, property_data, analysis):
        """Generate a prompt for Higgsfield video generation"""
        
        video_concept = analysis.get('VIDEO_WALKTHROUGH_CONCEPT', {})
        if isinstance(video_concept, dict):
            video_concept = video_concept.get('concept', str(video_concept))
        
        prompt = f"""
Create a professional 30-second walkthrough video for an Airbnb property:

PROPERTY: {property_data.get('name')}
LOCATION: {property_data.get('location')}
TYPE: {property_data.get('property_type', 'Apartment')}

VIDEO SCRIPT:
1. Opening shot: Welcoming entrance
2. Living area: Spacious, well-lit common spaces
3. Key amenities: {', '.join(property_data.get('amenities', [])[:3])}
4. Bedroom: Comfortable, clean, well-decorated
5. Closing: "Book now for your perfect stay"

STYLE: Professional, cinematic, inviting
MUSIC: Upbeat but not distracting
PACING: Smooth transitions, 4-5 seconds per room

Use these images as reference for the property layout and style.
"""
        
        return prompt
    
    def generate_pdf_report(self, property_name, property_data, analysis, images_data, output_file):
        """Generate professional PDF report"""
        
        print(f"\n📄 Generating PDF report...")
        
        doc = SimpleDocTemplate(output_file, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        story = []
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor("#1F2937"),
            spaceAfter=12,
            alignment=TA_CENTER
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor("#374151"),
            spaceAfter=8,
            spaceBefore=8
        )
        
        # Title
        story.append(Paragraph(f"Property Analysis Report", title_style))
        story.append(Paragraph(f"{property_name}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        # Property Overview
        story.append(Paragraph("Property Overview", heading_style))
        overview_data = [
            ["Price", f"${property_data.get('price', 'N/A')}/night"],
            ["Location", property_data.get('location', 'N/A')],
            ["Bedrooms", str(property_data.get('bedrooms', 'N/A'))],
            ["Bathrooms", str(property_data.get('bathrooms', 'N/A'))],
            ["Rating", str(property_data.get('rating', 'N/A'))],
        ]
        overview_table = Table(overview_data, colWidths=[2*inch, 3*inch])
        overview_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#F3F4F6")),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]))
        story.append(overview_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Add thumbnail images
        if images_data:
            story.append(Paragraph("Property Images", heading_style))
            img_row = []
            for img_data in images_data[:3]:  # Show first 3 images
                if isinstance(img_data, dict) and 'path' in img_data:
                    img_path = img_data['path']
                    if Path(img_path).exists():
                        try:
                            img = Image(img_path, width=1.5*inch, height=1.2*inch)
                            img_row.append(img)
                        except:
                            pass
            
            if img_row:
                img_table = Table([img_row], colWidths=[1.7*inch]*len(img_row))
                story.append(img_table)
                story.append(Spacer(1, 0.3*inch))
        
        # Analysis Results
        story.append(PageBreak())
        story.append(Paragraph("Gap Analysis", heading_style))
        
        if isinstance(analysis, dict):
            if 'GAPS' in analysis:
                gaps = analysis['GAPS']
                if isinstance(gaps, list):
                    for i, gap in enumerate(gaps[:5], 1):
                        story.append(Paragraph(f"{i}. {gap}", styles['Normal']))
        
        story.append(Spacer(1, 0.2*inch))
        story.append(Paragraph("Recommendations", heading_style))
        
        if isinstance(analysis, dict):
            if 'RECOMMENDATIONS' in analysis:
                recs = analysis['RECOMMENDATIONS']
                if isinstance(recs, list):
                    for rec in recs[:5]:
                        story.append(Paragraph(f"• {rec}", styles['Normal']))
                        story.append(Spacer(1, 0.1*inch))
        
        story.append(Spacer(1, 0.2*inch))
        story.append(Paragraph("Estimated Revenue Impact", heading_style))
        
        if isinstance(analysis, dict):
            if 'ROI' in analysis:
                roi = analysis['ROI']
                story.append(Paragraph(f"Potential monthly increase: {roi}", styles['Normal']))
        
        # Build PDF
        doc.build(story)
        
        print(f"✅ PDF generated: {output_file}")
        return output_file
    
    def run_analysis(self, property_name, property_data, image_paths):
        """Run complete analysis"""
        
        # Load images
        print(f"📸 Loading {len(image_paths)} property images...")
        images_data = self.load_property_images(image_paths)
        print(f"✅ Loaded {len(images_data)} images")
        
        # Analyze property
        analysis = self.analyze_property(property_name, property_data, images_data)
        
        # Generate video prompt
        print("\n🎬 Generating video walkthrough prompt...")
        video_prompt = self.generate_video_prompt(property_data, analysis)
        print("✅ Video prompt ready:")
        print("-" * 60)
        print(video_prompt[:500] + "...")
        print("-" * 60)
        
        # Generate PDF report
        pdf_path = self.output_dir / f"Property_Analysis_{property_name.replace(' ', '_')}.pdf"
        pdf_file = self.generate_pdf_report(property_name, property_data, analysis, images_data, str(pdf_path))
        
        # Save analysis data
        analysis_file = self.output_dir / f"Analysis_{property_name.replace(' ', '_')}.json"
        with open(analysis_file, 'w') as f:
            json.dump({
                "property": property_data,
                "analysis": analysis,
                "video_prompt": video_prompt,
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)
        
        print(f"\n✅ Analysis saved to: {analysis_file}")
        
        return {
            "property_data": property_data,
            "analysis": analysis,
            "video_prompt": video_prompt,
            "pdf_file": pdf_file,
            "analysis_file": str(analysis_file)
        }


if __name__ == "__main__":
    # Example usage with real property
    analyzer = AirbnbPropertyAnalyzer()
    
    # Sample property data (user would provide this)
    property_data = {
        "name": "Modern Luxury Apartment in Central Location",
        "location": "Premium Central District",
        "property_type": "Apartment",
        "price": 150,
        "bedrooms": 3,
        "bathrooms": 2,
        "rating": 4.85,
        "amenities": ["WiFi", "Kitchen", "Air Conditioning", "Washing Machine", "TV"],
        "description": "Spacious modern apartment in the heart of the city"
    }
    
    # Example: Use previously downloaded images
    image_paths = [
        "/tmp/property_image_1.png",
        "/tmp/property_image_2.png"
    ]
    
    # Run analysis
    result = analyzer.run_analysis(
        property_data["name"],
        property_data,
        image_paths
    )
    
    print("\n" + "="*80)
    print("✅ COMPLETE ANALYSIS READY")
    print("="*80)
    print(f"PDF Report: {result['pdf_file']}")
    print(f"Analysis Data: {result['analysis_file']}")
    print(f"\nVIDEO PROMPT FOR HIGGSFIELD:")
    print(result['video_prompt'])

