"""
Airbnb Listing Analyzer & Auditor
Analyzes listings to:
1. Extract claimed amenities and features
2. Detect what photos are missing
3. Recommend which photos to improve
4. Identify gaps between claims and proof
"""

from anthropic import Anthropic
import json
from typing import List, Dict, Optional


class ListingAnalyzer:
    """Analyze Airbnb listings to find gaps and optimization opportunities"""
    
    def __init__(self):
        self.client = Anthropic()
        self.model = "claude-opus-4-1"
    
    def extract_amenities(self, listing_description: str) -> Dict:
        """Extract all claimed amenities from listing description"""
        
        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": f"""Analyze this Airbnb listing and extract ALL amenities, features, and highlights mentioned.

LISTING:
{listing_description}

Return a JSON object with:
{{
  "amenities": ["list of specific amenities"],
  "features": ["list of special features"],
  "highlights": ["list of key selling points"],
  "outdoor": ["outdoor amenities if any"],
  "categories": ["bedroom", "bathroom", "kitchen", "living", "outdoor", etc.]
}}

Be specific and comprehensive. Include everything mentioned."""
                }
            ]
        )
        
        response_text = message.content[0].text
        
        # Parse JSON from response
        try:
            # Find JSON in the response
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            json_str = response_text[start:end]
            return json.loads(json_str)
        except:
            return {
                "amenities": [],
                "features": [],
                "highlights": [],
                "outdoor": [],
                "categories": []
            }
    
    def analyze_photos(self, photo_descriptions: List[str]) -> Dict:
        """Analyze what's shown in the provided photos"""
        
        photo_list = "\n".join([f"{i+1}. {desc}" for i, desc in enumerate(photo_descriptions)])
        
        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": f"""Analyze what's shown in these Airbnb photos:

PHOTOS:
{photo_list}

Return a JSON object with:
{{
  "rooms_shown": ["bedroom", "kitchen", "bathroom", etc.],
  "amenities_visible": ["hot tub", "balcony", "fireplace", etc.],
  "features_visible": ["list of visible features"],
  "photo_count": number,
  "coverage": "percentage of rooms/amenities shown"
}}"""
                }
            ]
        )
        
        response_text = message.content[0].text
        
        try:
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            json_str = response_text[start:end]
            return json.loads(json_str)
        except:
            return {
                "rooms_shown": [],
                "amenities_visible": [],
                "features_visible": [],
                "photo_count": len(photo_descriptions),
                "coverage": "Unknown"
            }
    
    def find_photo_gaps(self, claimed_amenities: Dict, photo_analysis: Dict) -> Dict:
        """Find gaps between claimed amenities and photos"""
        
        claimed = set()
        for key in ["amenities", "features", "highlights", "outdoor"]:
            claimed.update(claimed_amenities.get(key, []))
        
        visible = set(photo_analysis.get("amenities_visible", []))
        visible.update(photo_analysis.get("features_visible", []))
        
        missing = claimed - visible
        
        return {
            "claimed_total": len(claimed),
            "documented_total": len(visible),
            "missing_photos": list(missing),
            "missing_count": len(missing),
            "coverage_percentage": (len(visible) / len(claimed) * 100) if claimed else 100,
            "recommendations": self._generate_recommendations(missing, claimed)
        }
    
    def _generate_recommendations(self, missing: set, claimed: set) -> List[str]:
        """Generate specific photo recommendations"""
        
        recommendations = []
        
        # Priority mapping
        priority_items = {
            "hot tub": "🔥 HOT TUB - HIGHLY IMPORTANT",
            "pool": "🏊 POOL - HIGHLY IMPORTANT",
            "balcony": "🌅 BALCONY/PATIO - VERY IMPORTANT",
            "patio": "🌳 PATIO - VERY IMPORTANT",
            "view": "👀 VIEW - VERY IMPORTANT",
            "kitchen": "🍳 KITCHEN - IMPORTANT",
            "bathroom": "🚿 BATHROOM - IMPORTANT",
            "bedroom": "🛏️ BEDROOM - IMPORTANT",
            "fireplace": "🔥 FIREPLACE - IMPORTANT",
            "outdoor": "🌲 OUTDOOR SPACE - IMPORTANT",
            "wifi": "📡 WIFI/TECH - NICE TO HAVE",
            "parking": "🅿️ PARKING - NICE TO HAVE",
        }
        
        for item in missing:
            item_lower = item.lower()
            
            # Check if it's a priority item
            for key, priority in priority_items.items():
                if key in item_lower:
                    recommendations.append(f"{priority}: '{item}'")
                    break
            else:
                # Generic recommendation
                recommendations.append(f"📷 REQUEST PHOTO: '{item}'")
        
        return recommendations
    
    def generate_host_message(self, gaps: Dict) -> str:
        """Generate a friendly message to send to the host"""
        
        if not gaps["missing_photos"]:
            return """✅ Great news! Your listing photos cover all your claimed amenities.

Our team can still enhance your existing photos to make them look even more professional and attractive. We'll improve:
• Lighting and brightness
• Color balance
• Clarity and sharpness
• Overall professional quality

This helps increase views and bookings!"""
        
        missing_list = "\n".join([f"• {item}" for item in gaps["recommendations"][:5]])
        
        message = f"""Hi! We reviewed your listing and noticed some great features you mention that aren't shown in photos yet:

{missing_list}

{'...' if len(gaps['recommendations']) > 5 else ''}

Here's what we recommend:

1️⃣  Send us photos of these amenities (even just from your phone!)
2️⃣  We'll enhance them to professional quality
3️⃣  Add them to your listing
4️⃣  Watch your bookings increase

Current photo coverage: {gaps['coverage_percentage']:.0f}% of your claimed amenities
Missing photos: {gaps['missing_count']}

For just ${gaps['missing_count'] * 20 + (10 if gaps['missing_count'] > 0 else 0)}, we'll:
✨ Enhance all new photos
✨ Fix lighting and colors
✨ Make everything camera-ready

Every missing amenity that's not shown = lost bookings. Let's fix that!"""
        
        return message
    
    def generate_full_audit(self, 
                           listing_description: str,
                           photo_descriptions: Optional[List[str]] = None) -> Dict:
        """Generate a complete listing audit report"""
        
        print("🔍 Analyzing listing...")
        claimed = self.extract_amenities(listing_description)
        
        print("📸 Analyzing photos...")
        if not photo_descriptions:
            photo_descriptions = ["No photos provided yet"]
        
        photos = self.analyze_photos(photo_descriptions)
        
        print("🔎 Finding gaps...")
        gaps = self.find_photo_gaps(claimed, photos)
        
        print("📝 Generating recommendations...")
        host_message = self.generate_host_message(gaps)
        
        return {
            "claimed_amenities": claimed,
            "photos_analysis": photos,
            "photo_gaps": gaps,
            "host_outreach_message": host_message,
            "audit_summary": {
                "status": "⚠️ NEEDS PHOTOS" if gaps["missing_count"] > 0 else "✅ COMPLETE",
                "completeness": f"{gaps['coverage_percentage']:.0f}%",
                "priority_actions": gaps["recommendations"][:3],
                "estimated_value": f"${(len(claimed) - len(set(photos.get('amenities_visible', [])))) * 50}" if gaps["missing_count"] > 0 else "Listing optimized"
            }
        }


class ListingEnhancementPlan:
    """Create an enhancement plan for a listing"""
    
    def __init__(self):
        self.analyzer = ListingAnalyzer()
    
    def create_action_plan(self, listing_description: str, 
                          current_photos: Optional[List[str]] = None) -> Dict:
        """Create a complete enhancement and photography action plan"""
        
        audit = self.analyzer.generate_full_audit(listing_description, current_photos)
        
        plan = {
            "phase_1_photography": {
                "title": "📸 Phase 1: Capture Missing Photos",
                "urgency": "HIGHEST" if audit["photo_gaps"]["missing_count"] > 3 else "HIGH",
                "items": audit["photo_gaps"]["recommendations"],
                "timeline": "1-2 days",
                "cost": "$0 (you provide photos)",
                "expected_boost": "Increases coverage from {:.0f}% to 100%".format(
                    audit["photo_gaps"]["coverage_percentage"]
                )
            },
            "phase_2_enhancement": {
                "title": "✨ Phase 2: Professional Photo Enhancement",
                "urgency": "HIGH",
                "items": [
                    "Improve lighting and brightness",
                    "Fix color balance and white balance",
                    "Enhance clarity and sharpness",
                    "Make spaces look inviting and spacious",
                    "Ensure consistent style across all photos"
                ],
                "timeline": "Same day",
                "cost": f"${audit['photo_gaps']['missing_count'] * 20} for new photos + ${len(audit['photos_analysis']['photo_count']) * 10} for existing",
                "expected_boost": "Professional photography quality at 5% of the cost"
            },
            "phase_3_listing_optimization": {
                "title": "📝 Phase 3: Listing Copy Optimization",
                "urgency": "MEDIUM",
                "items": [
                    "Rewrite title to highlight top amenities",
                    "Enhance description to emphasize missing features",
                    "Add calls-to-action focused on key amenities",
                    "Improve SEO for local searches"
                ],
                "timeline": "2 hours",
                "cost": "$20",
                "expected_boost": "Increases click-through rate by 20-30%"
            },
            "total_investment": f"${audit['photo_gaps']['missing_count'] * 20 + 40}",
            "expected_roi": "3-5x in increased bookings",
            "timeline_to_completion": "3-5 days total"
        }
        
        return {
            "audit": audit,
            "enhancement_plan": plan
        }


if __name__ == "__main__":
    print("🎨 Listing Analysis Tool Ready")
    print("\nCapabilities:")
    print("  ✅ Extract claimed amenities from descriptions")
    print("  ✅ Analyze what's shown in photos")
    print("  ✅ Find gaps between claims and photos")
    print("  ✅ Generate host outreach messages")
    print("  ✅ Create enhancement action plans")
    print("\nUsage:")
    print("  analyzer = ListingAnalyzer()")
    print("  audit = analyzer.generate_full_audit(description, photos)")
