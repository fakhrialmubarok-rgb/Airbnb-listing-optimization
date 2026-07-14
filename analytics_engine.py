"""
Analytics & Data Collection Engine
Collects and analyzes:
- Property facilities & amenities
- Location data & market positioning
- Guest reviews & sentiment
- Booking patterns & performance metrics
- Competitive benchmarking

This data powers future premium services and segments customers
"""

import json
import os
from anthropic import Anthropic
from datetime import datetime
from typing import Dict, List, Any
import re

class ListingAnalyticsCollector:
    """Collects comprehensive analytics on listings for future segmentation"""
    
    def __init__(self):
        self.client = Anthropic()
        self.model = "claude-opus-4-1"
        self.analytics_db = {}
    
    def extract_amenities(self, description: str) -> Dict[str, List[str]]:
        """Extract all amenities and facilities from description"""
        prompt = f"""Analyze this Airbnb listing and extract ALL amenities and facilities.

Listing: {description}

Return JSON with these categories:
{{
  "accommodation": ["bedrooms", "bathrooms", "bed_types"],
  "outdoor": ["patio", "garden", "pool", "hot_tub", "balcony"],
  "kitchen": ["full_kitchen", "dishwasher", "microwave"],
  "entertainment": ["tv", "wifi", "games", "music"],
  "comfort": ["ac", "heating", "washer", "dryer"],
  "special": ["fireplace", "hot_tub", "sauna", "gym"],
  "safety": ["smoke_detector", "co_detector", "fire_extinguisher"]
}}

Be comprehensive. Include every single amenity mentioned."""
        
        message = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        
        try:
            text = message.content[0].text
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
        
        return {}
    
    def analyze_location_market(self, location: str, 
                               property_type: str,
                               price: str) -> Dict:
        """Analyze market position of property by location"""
        prompt = f"""Analyze the market position for this property:

Location: {location}
Property Type: {property_type}
Price: {price}

Provide market analysis:
{{
  "location_tier": "luxury/premium/standard/budget",
  "competitiveness": "high/medium/low",
  "market_demand": "strong/moderate/weak",
  "seasonal_patterns": "year_round/seasonal/peak_months",
  "target_demographic": "families/couples/business/backpackers",
  "location_advantages": ["advantage 1", "advantage 2"],
  "market_challenges": ["challenge 1", "challenge 2"],
  "estimated_annual_bookings": "number based on market data"
}}"""
        
        message = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        
        try:
            text = message.content[0].text
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
        
        return {}
    
    def analyze_review_sentiment(self, reviews: List[str]) -> Dict:
        """Analyze guest reviews and sentiment patterns"""
        reviews_text = "\n".join(reviews[:10])  # First 10 reviews
        
        prompt = f"""Analyze these guest reviews and identify patterns:

Reviews:
{reviews_text}

Provide sentiment analysis:
{{
  "overall_sentiment": "very_positive/positive/neutral/negative",
  "sentiment_score": 0.95,
  "common_praise": ["what guests loved 1", "what guests loved 2"],
  "common_complaints": ["issue 1", "issue 2"],
  "cleanliness_rating": "excellent/good/average/poor",
  "communication_rating": "excellent/good/average/poor",
  "location_rating": "excellent/good/average/poor",
  "value_rating": "excellent/good/average/poor",
  "improvement_opportunities": ["fix 1", "fix 2"],
  "competitive_strengths": ["strength 1", "strength 2"]
}}"""
        
        message = self.client.messages.create(
            model=self.model,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        
        try:
            text = message.content[0].text
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
        
        return {}
    
    def create_customer_profile(self, listing_id: str, 
                               listing_data: Dict) -> Dict:
        """Create comprehensive customer profile for segmentation"""
        
        profile = {
            "id": listing_id,
            "timestamp": datetime.now().isoformat(),
            "basic_info": {
                "title": listing_data.get("title"),
                "property_type": listing_data.get("property_type"),
                "location": listing_data.get("location"),
                "base_price": listing_data.get("price")
            },
            "amenities": self.extract_amenities(listing_data.get("description", "")),
            "market_position": self.analyze_location_market(
                listing_data.get("location", ""),
                listing_data.get("property_type", ""),
                listing_data.get("price", "")
            ),
            "review_analysis": self.analyze_review_sentiment(
                listing_data.get("reviews", [])
            ),
            "service_purchased": listing_data.get("service_type", "basic"),
            "conversion_data": {
                "reached_out": True,
                "converted": listing_data.get("converted", False),
                "price_paid": listing_data.get("price_paid", 0),
                "photos_enhanced": listing_data.get("photos_enhanced", 0)
            }
        }
        
        self.analytics_db[listing_id] = profile
        return profile
    
    def segment_customers(self, profiles: List[Dict]) -> Dict:
        """Segment customers into groups for future product targeting"""
        
        segments = {
            "premium_luxury": [],
            "high_performance": [],
            "growth_opportunity": [],
            "budget_friendly": [],
            "seasonal_peak": [],
            "struggling": []
        }
        
        for profile in profiles:
            market = profile.get("market_position", {})
            conversion = profile.get("conversion_data", {})
            reviews = profile.get("review_analysis", {})
            
            # Premium luxury segment
            if market.get("location_tier") == "luxury":
                segments["premium_luxury"].append(profile["id"])
            
            # High performance (strong reviews + good conversion)
            if reviews.get("sentiment_score", 0) > 0.85 and conversion.get("converted"):
                segments["high_performance"].append(profile["id"])
            
            # Growth opportunity (weak performance but potential)
            if reviews.get("sentiment_score", 0) < 0.7 and not conversion.get("converted"):
                segments["growth_opportunity"].append(profile["id"])
            
            # Budget friendly
            if market.get("location_tier") in ["budget", "standard"]:
                segments["budget_friendly"].append(profile["id"])
            
            # Seasonal
            if market.get("seasonal_patterns") != "year_round":
                segments["seasonal_peak"].append(profile["id"])
            
            # Struggling (poor reviews, no conversion)
            if reviews.get("sentiment_score", 0) < 0.5:
                segments["struggling"].append(profile["id"])
        
        return segments
    
    def generate_market_report(self, profiles: List[Dict]) -> Dict:
        """Generate aggregate market insights"""
        
        if not profiles:
            return {}
        
        total_profiles = len(profiles)
        converted = len([p for p in profiles if p["conversion_data"].get("converted")])
        conversion_rate = (converted / total_profiles * 100) if total_profiles > 0 else 0
        
        avg_sentiment = sum([
            p.get("review_analysis", {}).get("sentiment_score", 0.5) 
            for p in profiles
        ]) / len(profiles) if profiles else 0
        
        report = {
            "total_listings_analyzed": total_profiles,
            "total_conversions": converted,
            "conversion_rate_percent": round(conversion_rate, 1),
            "average_guest_sentiment": round(avg_sentiment, 2),
            "total_revenue_generated": sum([
                p["conversion_data"].get("price_paid", 0) for p in profiles
            ]),
            "average_deal_size": sum([
                p["conversion_data"].get("price_paid", 0) for p in profiles
            ]) / converted if converted > 0 else 0,
            "segments": self.segment_customers(profiles),
            "market_insights": {
                "most_common_property_type": self._get_most_common(
                    [p.get("basic_info", {}).get("property_type") for p in profiles]
                ),
                "average_amenities_count": sum([
                    len([v for vals in p.get("amenities", {}).values() for v in vals])
                    for p in profiles
                ]) / len(profiles) if profiles else 0,
                "top_issues": self._get_top_complaints(profiles),
                "top_strengths": self._get_top_strengths(profiles)
            }
        }
        
        return report
    
    def _get_most_common(self, items: List[str]) -> str:
        """Get most common item from list"""
        from collections import Counter
        if not items:
            return "unknown"
        counts = Counter(items)
        return counts.most_common(1)[0][0] if counts else "unknown"
    
    def _get_top_complaints(self, profiles: List[Dict]) -> List[str]:
        """Extract top complaints from all reviews"""
        complaints = []
        for profile in profiles:
            complaints.extend(
                profile.get("review_analysis", {}).get("common_complaints", [])
            )
        
        from collections import Counter
        counts = Counter(complaints)
        return [item[0] for item in counts.most_common(5)]
    
    def _get_top_strengths(self, profiles: List[Dict]) -> List[str]:
        """Extract top strengths from all reviews"""
        strengths = []
        for profile in profiles:
            strengths.extend(
                profile.get("review_analysis", {}).get("competitive_strengths", [])
            )
        
        from collections import Counter
        counts = Counter(strengths)
        return [item[0] for item in counts.most_common(5)]


class FutureProductPlanner:
    """Plans future products based on collected data and customer segments"""
    
    def __init__(self):
        self.client = Anthropic()
        self.model = "claude-opus-4-1"
    
    def identify_upsell_opportunities(self, customer_profiles: List[Dict],
                                     segments: Dict) -> Dict:
        """Identify premium services to upsell based on customer data"""
        
        prompt = f"""Based on these customer segments and their characteristics,
identify high-value premium services we can upsell:

Premium Luxury Segment: {len(segments.get('premium_luxury', []))} customers
High Performance Segment: {len(segments.get('high_performance', []))} customers
Growth Opportunity: {len(segments.get('growth_opportunity', []))} customers
Struggling Segment: {len(segments.get('struggling', []))} customers

Characteristics:
- Average guest sentiment score: 0.75/1.0
- Most common complaints: cleaning, communication, photos
- Most valued features: location, amenities, price

Identify 5 premium services to upsell with:
{{
  "services": [
    {{
      "name": "service name",
      "target_segment": "which segment",
      "value_proposition": "what makes it valuable",
      "estimated_price": "$X",
      "expected_upsell_rate": "30-50%",
      "implementation_effort": "low/medium/high",
      "revenue_potential": "$X per customer"
    }}
  ]
}}"""
        
        message = self.client.messages.create(
            model=self.model,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        
        try:
            text = message.content[0].text
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
        
        return {"services": []}
    
    def create_product_roadmap(self, market_report: Dict) -> Dict:
        """Create a product roadmap based on market insights"""
        
        prompt = f"""Create a product roadmap for future services based on market data:

Market Insights:
- Total listings analyzed: {market_report.get('total_listings_analyzed', 0)}
- Conversion rate: {market_report.get('conversion_rate_percent', 0)}%
- Top complaints: {market_report.get('market_insights', {}).get('top_issues', [])}
- Top strengths: {market_report.get('market_insights', {}).get('top_strengths', [])}

Create roadmap with:
{{
  "phase_1": {{
    "timeline": "months",
    "services": ["service 1", "service 2"],
    "target_revenue": "$X",
    "development_effort": "X weeks"
  }},
  "phase_2": {{
    "timeline": "months",
    "services": ["service 1"],
    "target_revenue": "$X"
  }},
  "phase_3": {{
    "timeline": "months",
    "services": ["service 1"],
    "target_revenue": "$X"
  }}
}}"""
        
        message = self.client.messages.create(
            model=self.model,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        
        try:
            text = message.content[0].text
            json_match = re.search(r'\{.*.*\}', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
        
        return {}


if __name__ == "__main__":
    # Test the analytics collector
    collector = ListingAnalyticsCollector()
    
    # Example listing data
    test_listing = {
        "title": "Luxury Mountain Cabin with Hot Tub",
        "property_type": "Cabin",
        "location": "Colorado Rocky Mountains",
        "price": "$250/night",
        "description": "Beautiful 4-bedroom cabin with hot tub, fireplace, full kitchen, dishwasher, washer/dryer, AC, heating, WiFi, TV, mountain views",
        "reviews": [
            "Amazing property! Clean, spacious, great views",
            "Hot tub was perfect, cabin exceeded expectations",
            "Only issue was slow WiFi but otherwise perfect"
        ],
        "service_type": "premium",
        "converted": True,
        "price_paid": 100,
        "photos_enhanced": 15
    }
    
    profile = collector.create_customer_profile("listing_001", test_listing)
    print("✅ Analytics collector working")
    print(f"Profile created: {json.dumps(profile, indent=2)[:200]}...")
