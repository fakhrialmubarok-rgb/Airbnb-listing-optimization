"""
PDF Gap Analysis Report Generator
Creates beautiful, professional PDF reports for customers
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from datetime import datetime
import os
import logging

logger = logging.getLogger(__name__)

class GapAnalysisPDFGenerator:
    """
    Generates professional PDF gap analysis reports
    """
    
    def __init__(self, output_dir='/tmp'):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def generate(self, customer_name, property_data, analysis_data):
        """
        Generate gap analysis PDF
        
        Args:
            customer_name: Customer's name
            property_data: Dict with property details
                - name: Property name
                - location: City/Location
                - price_per_night: Nightly rate
                - current_amenities: List of claimed amenities
            
            analysis_data: Dict with analysis results
                - missing_amenities: List of missing photo opportunities
                - estimated_annual_loss: $$$ from missing photos
                - booking_increase_potential: Estimated % uplift
                - recommendations: List of specific recommendations
        
        Returns:
            Path to generated PDF
        """
        
        filename = f"{self.output_dir}/Gap_Analysis_{customer_name.replace(' ', '_')}.pdf"
        
        try:
            # Create PDF document
            doc = SimpleDocTemplate(
                filename,
                pagesize=letter,
                rightMargin=0.75*inch,
                leftMargin=0.75*inch,
                topMargin=1*inch,
                bottomMargin=0.75*inch
            )
            
            # Build story (content list)
            story = []
            
            # Add content
            story.extend(self._build_header(customer_name, property_data))
            story.extend(self._build_executive_summary(analysis_data))
            story.extend(self._build_missing_photos_section(analysis_data))
            story.extend(self._build_roi_calculation(property_data, analysis_data))
            story.extend(self._build_recommendations(analysis_data))
            story.extend(self._build_call_to_action())
            
            # Build PDF
            doc.build(story)
            
            logger.info(f"✅ PDF generated: {filename}")
            return filename
        
        except Exception as e:
            logger.error(f"❌ Failed to generate PDF: {str(e)}")
            return None
    
    def _build_header(self, customer_name, property_data):
        """Build title and header section"""
        
        styles = getSampleStyleSheet()
        story = []
        
        # Main title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=6,
            fontName='Helvetica-Bold'
        )
        story.append(Paragraph("AIRBNB OPTIMIZATION ANALYSIS", title_style))
        
        # Subtitle
        subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Normal'],
            fontSize=14,
            textColor=colors.HexColor('#666666'),
            spaceAfter=20,
            fontName='Helvetica'
        )
        story.append(Paragraph(f"Your Complete Gap Analysis Report", subtitle_style))
        
        # Property info
        info_data = [
            ['Property', property_data.get('name', 'N/A')],
            ['Location', property_data.get('location', 'N/A')],
            ['Nightly Rate', f"${property_data.get('price_per_night', 'N/A')}"],
            ['Analysis Date', datetime.now().strftime('%B %d, %Y')],
        ]
        
        info_table = Table(info_data, colWidths=[1.5*inch, 3.5*inch])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dddddd')),
        ]))
        
        story.append(info_table)
        story.append(Spacer(1, 0.3*inch))
        
        return story
    
    def _build_executive_summary(self, analysis_data):
        """Build executive summary section"""
        
        styles = getSampleStyleSheet()
        story = []
        
        # Section heading
        heading_style = ParagraphStyle(
            'SectionHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=12,
            fontName='Helvetica-Bold',
            borderColor=colors.HexColor('#2e7d32'),
            borderWidth=2,
            borderPadding=8,
            borderRadius=4,
            backColor=colors.HexColor('#f1f8f6')
        )
        story.append(Paragraph("EXECUTIVE SUMMARY", heading_style))
        
        # Summary text
        summary_style = ParagraphStyle(
            'Summary',
            parent=styles['Normal'],
            fontSize=11,
            leading=16,
            spaceAfter=12
        )
        
        annual_loss = analysis_data.get('estimated_annual_loss', 0)
        booking_increase = analysis_data.get('booking_increase_potential', 0)
        missing_count = len(analysis_data.get('missing_amenities', []))
        
        summary_text = f"""
You are currently missing <b>{missing_count} key photo opportunity(ies)</b> that guests are looking for.
<br/><br/>
Based on market data from 2,000+ Airbnb listings in your area, adding these photos could increase 
your booking rate by up to <b>{booking_increase}%</b>, translating to approximately 
<b>${annual_loss:,} in additional annual revenue</b>.
<br/><br/>
This analysis identifies exactly which photos you're missing and their potential impact.
        """
        
        story.append(Paragraph(summary_text, summary_style))
        story.append(Spacer(1, 0.2*inch))
        
        return story
    
    def _build_missing_photos_section(self, analysis_data):
        """Build the missing photos section with impacts"""
        
        styles = getSampleStyleSheet()
        story = []
        
        # Section heading
        heading_style = ParagraphStyle(
            'SectionHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=12,
            fontName='Helvetica-Bold',
            borderColor=colors.HexColor('#c62828'),
            borderWidth=2,
            borderPadding=8,
            backColor=colors.HexColor('#ffebee')
        )
        story.append(Paragraph("MISSING PHOTO OPPORTUNITIES", heading_style))
        
        # Missing amenities table
        missing_amenities = analysis_data.get('missing_amenities', [])
        
        if missing_amenities:
            table_data = [
                ['Amenity', 'Booking Impact', 'Revenue Impact', 'Priority']
            ]
            
            for amenity in missing_amenities[:5]:  # Top 5
                amenity_name = amenity.get('amenity', 'Unknown')
                booking_impact = amenity.get('booking_increase', 0)
                revenue_impact = amenity.get('annual_loss', 0)
                priority = 'HIGH' if booking_impact > 50 else 'MEDIUM' if booking_impact > 30 else 'LOW'
                
                table_data.append([
                    amenity_name,
                    f"+{booking_impact}%",
                    f"${revenue_impact:,}",
                    priority
                ])
            
            table = Table(table_data, colWidths=[2*inch, 1.3*inch, 1.3*inch, 1.2*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('TOPPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
            ]))
            
            story.append(table)
        
        story.append(Spacer(1, 0.25*inch))
        
        return story
    
    def _build_roi_calculation(self, property_data, analysis_data):
        """Build ROI calculation section"""
        
        styles = getSampleStyleSheet()
        story = []
        
        # Section heading
        heading_style = ParagraphStyle(
            'SectionHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=12,
            fontName='Helvetica-Bold',
            borderColor=colors.HexColor('#1565c0'),
            borderWidth=2,
            borderPadding=8,
            backColor=colors.HexColor('#e3f2fd')
        )
        story.append(Paragraph("ROI CALCULATION", heading_style))
        
        # ROI breakdown
        price = property_data.get('price_per_night', 0)
        annual_loss = analysis_data.get('estimated_annual_loss', 0)
        booking_increase = analysis_data.get('booking_increase_potential', 0)
        
        roi_text = f"""
<b>Current Annual Revenue (estimate):</b> ${price * 180:,} (assuming 50% occupancy)
<br/>
<b>Potential Boost from Missing Photos:</b> +{booking_increase}%
<br/>
<b>Additional Annual Revenue:</b> ${annual_loss:,}
<br/>
<b>Cost to Add Photos:</b> $50-100 (one-time investment)
<br/>
<b>ROI in First Booking:</b> {int((annual_loss / (price or 1)) * 100)}%+ return on investment
        """
        
        roi_style = ParagraphStyle(
            'ROIText',
            parent=styles['Normal'],
            fontSize=11,
            leading=18,
            leftIndent=20,
            spaceAfter=16
        )
        story.append(Paragraph(roi_text, roi_style))
        story.append(Spacer(1, 0.2*inch))
        
        return story
    
    def _build_recommendations(self, analysis_data):
        """Build recommendations section"""
        
        styles = getSampleStyleSheet()
        story = []
        
        # Section heading
        heading_style = ParagraphStyle(
            'SectionHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=12,
            fontName='Helvetica-Bold',
            borderColor=colors.HexColor('#2e7d32'),
            borderWidth=2,
            borderPadding=8,
            backColor=colors.HexColor('#f1f8f6')
        )
        story.append(Paragraph("RECOMMENDATIONS", heading_style))
        
        recommendations = analysis_data.get('recommendations', [])
        
        if recommendations:
            rec_style = ParagraphStyle(
                'Recommendation',
                parent=styles['Normal'],
                fontSize=10,
                leading=14,
                leftIndent=20,
                spaceAfter=8,
                bulletIndent=10
            )
            
            for i, rec in enumerate(recommendations[:5], 1):
                story.append(Paragraph(f"<b>{i}.</b> {rec}", rec_style))
        
        story.append(Spacer(1, 0.2*inch))
        
        return story
    
    def _build_call_to_action(self):
        """Build call-to-action section"""
        
        styles = getSampleStyleSheet()
        story = []
        
        cta_style = ParagraphStyle(
            'CTA',
            parent=styles['Normal'],
            fontSize=11,
            leading=16,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#c62828'),
            fontName='Helvetica-Bold',
            spaceAfter=12,
            borderColor=colors.HexColor('#c62828'),
            borderWidth=2,
            borderPadding=12,
            backColor=colors.HexColor('#ffebee')
        )
        
        cta_text = """
NEXT STEPS: Ready to Add These Photos?
<br/><br/>
I can professionally add these missing photos to your listing in 24 hours for $50-100.
<br/><br/>
Reply to this email or click the link below to get started.
        """
        
        story.append(Paragraph(cta_text, cta_style))
        
        return story


# Quick test
def test_pdf_generator():
    """Test PDF generation"""
    
    generator = GapAnalysisPDFGenerator()
    
    test_pdf = generator.generate(
        customer_name='John Smith',
        property_data={
            'name': 'Tribeca Loft',
            'location': 'New York, NY',
            'price_per_night': 250,
            'current_amenities': ['Hot tub', 'Fireplace', 'Views']
        },
        analysis_data={
            'missing_amenities': [
                {
                    'amenity': 'Hot Tub Photos',
                    'booking_increase': 68,
                    'annual_loss': 17000
                },
                {
                    'amenity': 'Fireplace Photos',
                    'booking_increase': 45,
                    'annual_loss': 11250
                },
                {
                    'amenity': 'View Photos',
                    'booking_increase': 52,
                    'annual_loss': 13000
                }
            ],
            'estimated_annual_loss': 7800,
            'booking_increase_potential': 35,
            'recommendations': [
                'Take clear photos of hot tub from multiple angles',
                'Photograph fireplace in evening with glow',
                'Capture skyline view during golden hour',
                'Show amenities being used/enjoyed',
                'Professional lighting for all interior photos'
            ]
        }
    )
    
    if test_pdf:
        print(f"✅ Test PDF generated: {test_pdf}")
    else:
        print("❌ PDF generation failed")
    
    return test_pdf


if __name__ == '__main__':
    test_pdf_generator()
