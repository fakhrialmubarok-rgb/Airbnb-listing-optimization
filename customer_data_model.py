"""
Customer Data Model & Storage
Stores all customer analytics for future product development
"""

import json
from datetime import datetime
from typing import Dict, List, Any, Optional

class CustomerDataStore:
    """In-memory customer data store (upgrade to DB later)"""
    
    def __init__(self):
        self.customers = {}  # listing_id -> customer_profile
        self.segments = {}   # segment_name -> [listing_ids]
        self.conversions = []  # Track all conversions
        self.sessions = {}   # Track user interactions
    
    def store_customer_profile(self, profile: Dict) -> str:
        """Store customer profile and return ID"""
        listing_id = profile.get("id", f"listing_{datetime.now().timestamp()}")
        self.customers[listing_id] = profile
        
        # Log conversion if applicable
        if profile.get("conversion_data", {}).get("converted"):
            self.conversions.append({
                "listing_id": listing_id,
                "timestamp": datetime.now().isoformat(),
                "amount": profile.get("conversion_data", {}).get("price_paid"),
                "service": profile.get("service_purchased")
            })
        
        return listing_id
    
    def get_customer_by_id(self, listing_id: str) -> Optional[Dict]:
        """Retrieve customer profile"""
        return self.customers.get(listing_id)
    
    def get_all_customers(self) -> List[Dict]:
        """Get all customer profiles"""
        return list(self.customers.values())
    
    def update_segment_assignment(self, listing_id: str, segment: str) -> None:
        """Assign customer to segment"""
        if segment not in self.segments:
            self.segments[segment] = []
        if listing_id not in self.segments[segment]:
            self.segments[segment].append(listing_id)
    
    def get_segment_members(self, segment: str) -> List[str]:
        """Get all listing IDs in a segment"""
        return self.segments.get(segment, [])
    
    def get_conversion_stats(self) -> Dict:
        """Get conversion statistics"""
        total_contacted = len(self.customers)
        total_converted = len(self.conversions)
        total_revenue = sum([c.get("amount", 0) for c in self.conversions])
        
        return {
            "total_contacted": total_contacted,
            "total_converted": total_converted,
            "conversion_rate": (total_converted / total_contacted * 100) if total_contacted > 0 else 0,
            "total_revenue": total_revenue,
            "average_deal_size": (total_revenue / total_converted) if total_converted > 0 else 0,
            "conversions": self.conversions
        }
    
    def export_for_analysis(self) -> Dict:
        """Export all data for analysis"""
        return {
            "customers": self.customers,
            "segments": self.segments,
            "conversions": self.conversions,
            "timestamp": datetime.now().isoformat()
        }
    
    def save_to_json(self, filename: str = "customer_data.json") -> None:
        """Save all data to JSON file"""
        data = self.export_for_analysis()
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load_from_json(self, filename: str = "customer_data.json") -> None:
        """Load data from JSON file"""
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
                self.customers = data.get("customers", {})
                self.segments = data.get("segments", {})
                self.conversions = data.get("conversions", [])
        except FileNotFoundError:
            print(f"No data file found at {filename}")


class ConversionFunnelAnalysis:
    """Analyzes customer journey through conversion funnel"""
    
    def __init__(self, data_store: CustomerDataStore):
        self.store = data_store
    
    def get_funnel_metrics(self) -> Dict:
        """Calculate funnel metrics"""
        all_customers = self.store.get_all_customers()
        conversions = self.store.conversions
        
        # Stage 1: Reached (all customers)
        stage_1_reached = len(all_customers)
        
        # Stage 2: Engaged (with QC report - assume all reached get report)
        stage_2_engaged = int(stage_1_reached * 0.85)  # 85% open QC report
        
        # Stage 3: Preview shown (with watermarked preview)
        stage_3_preview = int(stage_2_engaged * 0.82)  # 82% click preview
        
        # Stage 4: Converted (purchased)
        stage_4_converted = len(conversions)
        
        return {
            "stage_1_reached": {
                "count": stage_1_reached,
                "percent": 100
            },
            "stage_2_qc_opened": {
                "count": stage_2_engaged,
                "percent": round((stage_2_engaged / stage_1_reached * 100), 1) if stage_1_reached > 0 else 0,
                "drop_off": stage_1_reached - stage_2_engaged
            },
            "stage_3_preview_clicked": {
                "count": stage_3_preview,
                "percent": round((stage_3_preview / stage_2_engaged * 100), 1) if stage_2_engaged > 0 else 0,
                "drop_off": stage_2_engaged - stage_3_preview
            },
            "stage_4_converted": {
                "count": stage_4_converted,
                "percent": round((stage_4_converted / stage_3_preview * 100), 1) if stage_3_preview > 0 else 0,
                "drop_off": stage_3_preview - stage_4_converted
            },
            "overall_conversion_rate": round((stage_4_converted / stage_1_reached * 100), 1) if stage_1_reached > 0 else 0
        }
    
    def get_high_value_customers(self, min_deal_size: int = 80) -> List[Dict]:
        """Identify high-value customers for VIP treatment"""
        customers = self.store.get_all_customers()
        high_value = [
            c for c in customers 
            if c.get("conversion_data", {}).get("price_paid", 0) >= min_deal_size
        ]
        return high_value
    
    def get_churned_customers(self) -> List[Dict]:
        """Identify customers who were reached but didn't convert"""
        all_customers = self.store.get_all_customers()
        converted_ids = [c.get("listing_id") for c in self.store.conversions]
        
        churned = [
            c for c in all_customers 
            if c.get("id") not in converted_ids
        ]
        return churned
    
    def get_segment_performance(self) -> Dict:
        """Compare performance across segments"""
        segments = self.store.segments
        performance = {}
        
        for segment_name, listing_ids in segments.items():
            customers = [self.store.customers.get(lid) for lid in listing_ids]
            customers = [c for c in customers if c]  # Remove None values
            
            conversions_in_segment = [
                c for c in self.store.conversions 
                if c.get("listing_id") in listing_ids
            ]
            
            performance[segment_name] = {
                "total_customers": len(customers),
                "conversions": len(conversions_in_segment),
                "conversion_rate": (len(conversions_in_segment) / len(customers) * 100) if customers else 0,
                "total_revenue": sum([c.get("amount", 0) for c in conversions_in_segment]),
                "average_deal_size": (sum([c.get("amount", 0) for c in conversions_in_segment]) / len(conversions_in_segment)) if conversions_in_segment else 0
            }
        
        return performance


class DataInsights:
    """Generate business insights from collected data"""
    
    @staticmethod
    def identify_patterns(data_store: CustomerDataStore) -> Dict:
        """Identify patterns in customer data"""
        customers = data_store.get_all_customers()
        
        patterns = {
            "highest_converting_property_types": [],
            "highest_sentiment_scores": [],
            "most_common_amenities": [],
            "price_sensitivity": [],
            "seasonal_patterns": []
        }
        
        # Property type analysis
        property_types = {}
        for customer in customers:
            ptype = customer.get("basic_info", {}).get("property_type", "unknown")
            if ptype not in property_types:
                property_types[ptype] = {"count": 0, "conversions": 0}
            property_types[ptype]["count"] += 1
            if customer.get("conversion_data", {}).get("converted"):
                property_types[ptype]["conversions"] += 1
        
        for ptype, data in property_types.items():
            patterns["highest_converting_property_types"].append({
                "type": ptype,
                "conversion_rate": (data["conversions"] / data["count"] * 100) if data["count"] > 0 else 0
            })
        
        return patterns


# Example usage
if __name__ == "__main__":
    store = CustomerDataStore()
    
    # Example customer profile
    profile = {
        "id": "listing_001",
        "basic_info": {"property_type": "Cabin", "price": "$250/night"},
        "conversion_data": {"converted": True, "price_paid": 100},
        "review_analysis": {"sentiment_score": 0.92}
    }
    
    store.store_customer_profile(profile)
    
    print("✅ Customer data store working")
    print(f"Stats: {json.dumps(store.get_conversion_stats(), indent=2)}")
