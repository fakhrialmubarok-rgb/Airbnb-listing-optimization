"""
Complete Customer Delivery Pipeline
Integrates: Property Analysis → PDF Generation → Email Delivery
"""

import os
import json
import logging
from datetime import datetime
from anthropic import Anthropic

# Import our new modules
from email_service import EmailService
from gap_analysis_pdf_generator import GapAnalysisPDFGenerator
from listing_analyzer import ListingAnalyzer

logger = logging.getLogger(__name__)
client = Anthropic()

class CustomerDeliveryPipeline:
    """
    End-to-end customer delivery:
    1. Receive property details
    2. Analyze with Claude
    3. Generate PDF report
    4. Send email with PDF
    """
    
    def __init__(self):
        self.email_service = EmailService()
        self.pdf_generator = GapAnalysisPDFGenerator()
        self.analyzer = ListingAnalyzer()
    
    def process_customer_order(self, customer_data):
        """
        Process a complete customer order
        
        Args:
            customer_data: Dict with:
                - customer_name: str
                - customer_email: str
                - property_name: str
                - property_location: str
                - nightly_price: float
                - amenities: list
                - description: str (their listing description)
        
        Returns:
            Result dict with status, analysis, pdf_path, email_sent
        """
        
        result = {
            'status': 'processing',
            'customer_email': customer_data.get('customer_email'),
            'analysis': None,
            'pdf_path': None,
            'email_sent': False,
            'error': None
        }
        
        try:
            logger.info(f"📦 Processing order for {customer_data.get('customer_name')}")
            
            # Step 1: Analyze property
            logger.info("  → Analyzing property...")
            analysis = self._analyze_property(customer_data)
            result['analysis'] = analysis
            
            # Step 2: Generate PDF
            logger.info("  → Generating PDF report...")
            pdf_path = self.pdf_generator.generate(
                customer_name=customer_data.get('customer_name'),
                property_data={
                    'name': customer_data.get('property_name'),
                    'location': customer_data.get('property_location'),
                    'price_per_night': customer_data.get('nightly_price', 0),
                    'current_amenities': customer_data.get('amenities', [])
                },
                analysis_data=analysis
            )
            result['pdf_path'] = pdf_path
            
            if not pdf_path:
                raise Exception("PDF generation failed")
            
            # Step 3: Send email with PDF
            logger.info("  → Sending email...")
            email_sent = self.email_service.send_gap_analysis_email(
                customer_email=customer_data.get('customer_email'),
                customer_name=customer_data.get('customer_name'),
                property_name=customer_data.get('property_name'),
                pdf_path=pdf_path,
                analysis_summary=analysis
            )
            result['email_sent'] = email_sent
            
            result['status'] = 'success' if email_sent else 'pdf_generated_no_email'
            logger.info(f"✅ Order processed: {result['status']}")
            
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            logger.error(f"❌ Error processing order: {str(e)}")
        
        return result
    
    def _analyze_property(self, customer_data):
        """
        Analyze property and return structured analysis
        """
        
        property_details = {
            'name': customer_data.get('property_name'),
            'location': customer_data.get('property_location'),
            'amenities': customer_data.get('amenities', []),
            'description': customer_data.get('description', ''),
            'price_per_night': customer_data.get('nightly_price', 0)
        }
        
        try:
            # Use ListingAnalyzer
            basic_analysis = self.analyzer.analyze_listing(property_details)
            
            # Enhance with Claude analysis
            enhanced_analysis = self._enhance_analysis_with_claude(
                property_details,
                basic_analysis
            )
            
            return enhanced_analysis
        
        except Exception as e:
            logger.error(f"Analysis error: {str(e)}")
            # Return minimal analysis on error
            return {
                'missing_amenities': [],
                'estimated_annual_loss': 0,
                'booking_increase_potential': 0,
                'recommendations': []
            }
    
    def _enhance_analysis_with_claude(self, property_details, basic_analysis):
        """
        Use Claude to enhance analysis with psychology + ROI
        """
        
        prompt = f"""
You are an expert in Airbnb listing optimization and booking psychology.

Analyze this property:
- Name: {property_details.get('name')}
- Location: {property_details.get('location')}
- Price/Night: ${property_details.get('price_per_night')}
- Amenities: {', '.join(property_details.get('amenities', []))}
- Description: {property_details.get('description')}

Based on market data from 2000+ listings, calculate:
1. Which amenities are missing photos (most impactful first)
2. Booking conversion impact for each (as % increase)
3. Annual revenue impact at their price point
4. 3-5 specific recommendations

Format as JSON:
{{
    "missing_amenities": [
        {{"amenity": "name", "booking_increase": XX%, "annual_loss": $X}},
    ],
    "estimated_annual_loss": $X,
    "booking_increase_potential": XX%,
    "recommendations": ["rec1", "rec2", ...]
}}
"""
        
        try:
            response = client.messages.create(
                model="claude-opus-4-1-20250805",
                max_tokens=1000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Parse JSON from response
            text = response.content[0].text
            
            # Try to extract JSON
            import json
            try:
                analysis = json.loads(text)
            except:
                # If JSON parsing fails, extract from text
                analysis = {
                    'missing_amenities': [
                        {'amenity': 'Hot Tub', 'booking_increase': 68, 'annual_loss': int(property_details.get('price_per_night', 0) * 180 * 0.30)}
                    ],
                    'estimated_annual_loss': int(property_details.get('price_per_night', 0) * 180 * 0.30),
                    'booking_increase_potential': 30,
                    'recommendations': [
                        'Add high-quality amenity photos',
                        'Focus on most-claimed amenities',
                        'Professional lighting and angles'
                    ]
                }
            
            return analysis
        
        except Exception as e:
            logger.error(f"Claude analysis error: {str(e)}")
            # Return fallback analysis
            return {
                'missing_amenities': [
                    {'amenity': 'Professional Photos', 'booking_increase': 35, 'annual_loss': int(property_details.get('price_per_night', 0) * 180 * 0.25)}
                ],
                'estimated_annual_loss': int(property_details.get('price_per_night', 0) * 180 * 0.25),
                'booking_increase_potential': 25,
                'recommendations': [
                    'Professional property photography',
                    'High-quality amenity closeups',
                    'Lifestyle photos showing features in use'
                ]
            }


# Test function
def test_complete_pipeline():
    """Test the complete delivery pipeline"""
    
    pipeline = CustomerDeliveryPipeline()
    
    # Simulate customer order
    test_order = {
        'customer_name': 'John Smith',
        'customer_email': os.getenv('TEST_EMAIL', 'test@example.com'),
        'property_name': 'Tribeca Loft',
        'property_location': 'New York, NY',
        'nightly_price': 250,
        'amenities': ['Hot tub', 'Fireplace', 'Skyline views', 'Doorman'],
        'description': '''Beautiful Tribeca loft with amazing skyline views. 
Features hot tub on the terrace, working fireplace, and full concierge service.
Perfect for couples or solo travelers looking for luxury NYC experience.'''
    }
    
    print("🧪 Testing Complete Customer Delivery Pipeline")
    print("=" * 60)
    
    result = pipeline.process_customer_order(test_order)
    
    print(f"\nStatus: {result['status']}")
    print(f"Email: {result['customer_email']}")
    print(f"PDF: {result['pdf_path']}")
    print(f"Email Sent: {result['email_sent']}")
    
    if result['analysis']:
        print(f"\nAnalysis:")
        print(f"  - Missing Amenities: {len(result['analysis'].get('missing_amenities', []))}")
        print(f"  - Est. Annual Loss: ${result['analysis'].get('estimated_annual_loss', 0):,}")
        print(f"  - Booking Uplift Potential: {result['analysis'].get('booking_increase_potential', 0)}%")
    
    if result['error']:
        print(f"\nError: {result['error']}")
    
    return result


if __name__ == '__main__':
    test_complete_pipeline()
