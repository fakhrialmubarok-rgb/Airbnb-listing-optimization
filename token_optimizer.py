"""
Token & Credit Optimization Engine
Minimizes API costs while maintaining quality
Includes fallbacks, caching, batching, and intelligent routing
"""

import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class ModelTier(Enum):
    """Model tiers by cost efficiency"""
    CHEAP = "claude-3-5-haiku-20241022"      # $0.80/M input, $4/M output
    STANDARD = "claude-3-5-sonnet-20241022"  # $3/M input, $15/M output
    PREMIUM = "claude-opus-4-1"               # $15/M input, $75/M output

class CostOptimizer:
    """Tracks and optimizes token usage across all operations"""
    
    def __init__(self):
        self.call_history = []
        self.cost_budget = 100.0  # Start with $100/month budget
        self.current_spend = 0.0
        self.cache = {}
        self.batch_queue = []
        self.fallback_responses = {}
        
        # Model pricing (per million tokens)
        self.pricing = {
            ModelTier.CHEAP: {"input": 0.80, "output": 4.00},
            ModelTier.STANDARD: {"input": 3.00, "output": 15.00},
            ModelTier.PREMIUM: {"input": 15.00, "output": 75.00},
        }
        
    def estimate_cost(self, tokens: int, model: ModelTier, is_output: bool = False) -> float:
        """Estimate cost for given tokens"""
        rate_type = "output" if is_output else "input"
        return (tokens * self.pricing[model][rate_type]) / 1_000_000
    
    def get_optimal_model(self, task: str, budget_remaining: float) -> ModelTier:
        """Select most cost-effective model for task"""
        # Route by cost efficiency
        if budget_remaining > 50:
            # Use premium model for highest quality early in budget
            return ModelTier.PREMIUM
        elif budget_remaining > 20:
            # Use standard model in middle
            return ModelTier.STANDARD
        else:
            # Use cheap model when budget low
            return ModelTier.CHEAP
    
    def record_call(self, task: str, tokens_in: int, tokens_out: int, 
                   model: ModelTier, success: bool = True):
        """Record API call for cost tracking"""
        cost_in = self.estimate_cost(tokens_in, model, False)
        cost_out = self.estimate_cost(tokens_out, model, True)
        total_cost = cost_in + cost_out
        
        self.current_spend += total_cost
        
        record = {
            "timestamp": datetime.now(),
            "task": task,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "model": model.value,
            "cost": total_cost,
            "success": success,
        }
        
        self.call_history.append(record)
        logger.info(f"📊 API Call: {task} ({tokens_in}→{tokens_out} tokens, ${total_cost:.4f})")
        
        return total_cost
    
    def get_budget_status(self) -> Dict[str, Any]:
        """Get current budget status"""
        remaining = self.cost_budget - self.current_spend
        burn_rate = self.current_spend / max(1, len(self.call_history))
        
        return {
            "budget": self.cost_budget,
            "spent": round(self.current_spend, 2),
            "remaining": round(remaining, 2),
            "calls": len(self.call_history),
            "avg_cost_per_call": round(burn_rate, 4),
            "health": "healthy" if remaining > 20 else "warning" if remaining > 5 else "critical"
        }


class PromptCompressor:
    """Compresses prompts to minimize token usage"""
    
    @staticmethod
    def compress_description(description: str) -> str:
        """Remove redundancy from descriptions"""
        lines = description.split('\n')
        unique_lines = []
        seen = set()
        
        for line in lines:
            normalized = line.strip().lower()
            if normalized and normalized not in seen:
                unique_lines.append(line)
                seen.add(normalized)
        
        return '\n'.join(unique_lines)
    
    @staticmethod
    def compress_listing_data(listing: Dict) -> Dict:
        """Remove unnecessary fields before sending to API"""
        essential_fields = {
            "id", "title", "description", "amenities", 
            "price", "location", "rating", "reviews"
        }
        
        return {k: v for k, v in listing.items() if k in essential_fields}
    
    @staticmethod
    def create_summary_prompt(long_text: str, max_tokens: int = 500) -> str:
        """Create efficient summary prompt"""
        # Extract key sentences instead of full text
        sentences = long_text.split('.')
        important = []
        
        keywords = ['amenity', 'feature', 'include', 'provide', 'modern', 'luxury']
        
        for sent in sentences[:10]:  # Limit to first 10 sentences
            if any(kw in sent.lower() for kw in keywords):
                important.append(sent.strip())
        
        if not important:
            important = sentences[:3]
        
        return '. '.join(important)[:500]


class CacheManager:
    """Smart caching to avoid redundant API calls"""
    
    def __init__(self):
        self.cache = {}
        self.ttl = {}  # Time to live for cache entries
    
    def get_cache_key(self, task: str, input_data: str) -> str:
        """Generate cache key"""
        data_hash = hashlib.sha256(input_data.encode()).hexdigest()[:16]
        return f"{task}:{data_hash}"
    
    def get(self, task: str, input_data: str) -> Optional[str]:
        """Get cached result if available and fresh"""
        key = self.get_cache_key(task, input_data)
        
        if key in self.cache:
            if key in self.ttl:
                if datetime.now() < self.ttl[key]:
                    logger.info(f"✅ Cache HIT: {task}")
                    return self.cache[key]
            else:
                return self.cache[key]
        
        return None
    
    def set(self, task: str, input_data: str, output: str, ttl_hours: int = 24):
        """Cache result"""
        key = self.get_cache_key(task, input_data)
        self.cache[key] = output
        self.ttl[key] = datetime.now() + timedelta(hours=ttl_hours)
        logger.info(f"💾 Cached: {task}")
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        fresh = sum(1 for k in self.ttl if datetime.now() < self.ttl[k])
        return {
            "total_entries": len(self.cache),
            "fresh_entries": fresh,
            "stale_entries": len(self.cache) - fresh
        }


class BatchProcessor:
    """Batches multiple requests to save tokens"""
    
    def __init__(self, batch_size: int = 5):
        self.batch_size = batch_size
        self.queue = []
    
    def add(self, task: str, input_data: str):
        """Add task to batch"""
        self.queue.append({"task": task, "input": input_data})
        
        if len(self.queue) >= self.batch_size:
            return self.flush()
        return None
    
    def flush(self) -> Optional[List]:
        """Process entire batch at once"""
        if not self.queue:
            return None
        
        logger.info(f"📦 Processing batch of {len(self.queue)} items")
        # Would send all at once to save on API calls
        result = self.queue
        self.queue = []
        return result


class FallbackStrategies:
    """Fallback responses when API fails or budget depleted"""
    
    def __init__(self):
        self.templates = {
            "describe_amenity": {
                "hot_tub": "Luxurious hot tub perfect for relaxation and entertaining guests.",
                "pool": "Beautiful swimming pool ideal for families and groups.",
                "wifi": "High-speed WiFi throughout property for work and entertainment.",
                "kitchen": "Fully equipped kitchen with modern appliances.",
                "fireplace": "Cozy fireplace perfect for winter evenings.",
                "garden": "Private garden ideal for outdoor entertaining.",
            },
            
            "gap_detection": {
                "claimed_but_not_shown": [
                    "Hot tub listed but no hot tub photos",
                    "Pool listed but no pool photos",
                    "Garden listed but no garden photos",
                ],
                "recommendation": "Missing visual proof of listed amenities could reduce bookings by 15-20%"
            },
            
            "psychology_analysis": {
                "low_cost": "Add more lifestyle photos showing entertainment value",
                "mid_cost": "Add unique amenity photos (hot tub, fireplace, view)",
                "high_cost": "Add luxury spa/wellness imagery to justify premium pricing",
            },
            
            "title_suggestions": [
                "Modern {location} Home with {main_amenity}",
                "Luxury {location} Retreat - {main_amenity} & WiFi",
                "Beautiful {location} Property Perfect for Families",
                "Spacious {location} Home with Pool & Garden",
                "Cozy {location} Getaway with Hot Tub & Fireplace",
            ]
        }
    
    def get_response(self, task: str, context: Dict) -> str:
        """Get fallback response based on task"""
        if task == "describe_amenity":
            amenity = context.get("amenity", "").lower()
            return self.templates["describe_amenity"].get(
                amenity, 
                f"Beautiful {amenity} that guests will love."
            )
        
        elif task == "gap_detection":
            return json.dumps(self.templates["gap_detection"])
        
        elif task == "psychology_analysis":
            price = context.get("price", 100)
            if price < 150:
                return self.templates["psychology_analysis"]["low_cost"]
            elif price < 250:
                return self.templates["psychology_analysis"]["mid_cost"]
            else:
                return self.templates["psychology_analysis"]["high_cost"]
        
        elif task == "title_suggestions":
            location = context.get("location", "Property")
            amenity = context.get("amenity", "Amenity")
            titles = [t.replace("{location}", location).replace("{main_amenity}", amenity) 
                     for t in self.templates["title_suggestions"]]
            return json.dumps(titles)
        
        return "Error: Fallback not available for this task"


class TokenOptimizationAPI:
    """Complete token optimization system"""
    
    def __init__(self):
        self.cost_optimizer = CostOptimizer()
        self.compressor = PromptCompressor()
        self.cache = CacheManager()
        self.batcher = BatchProcessor()
        self.fallbacks = FallbackStrategies()
        
    def optimize_call(self, task: str, input_data: Dict, 
                     fallback_context: Dict = None) -> Tuple[str, Dict]:
        """
        Execute optimized API call with fallbacks
        
        Returns: (response, metadata)
        """
        
        # Check budget first
        budget_status = self.cost_optimizer.get_budget_status()
        if budget_status["health"] == "critical":
            logger.warning("⚠️ CRITICAL: Budget depleted, using fallback")
            response = self.fallbacks.get_response(task, fallback_context or {})
            return response, {
                "source": "fallback",
                "reason": "budget_depleted",
                "cost": 0.0
            }
        
        # Generate cache key
        input_str = json.dumps(input_data, sort_keys=True)
        
        # Check cache first
        cached = self.cache.get(task, input_str)
        if cached:
            return cached, {
                "source": "cache",
                "cost": 0.0
            }
        
        # Compress input to reduce tokens
        compressed_input = self.compressor.compress_summary_prompt(input_str)
        
        # Select optimal model based on budget
        optimal_model = self.cost_optimizer.get_optimal_model(
            task, 
            budget_status["remaining"]
        )
        
        logger.info(f"🚀 Optimized call: task={task}, model={optimal_model.value}")
        
        # Would make actual API call here
        # For now, return structured metadata
        
        return None, {
            "source": "api",
            "model": optimal_model.value,
            "compressed_input": len(compressed_input),
            "estimated_cost": "pending"
        }
    
    def get_efficiency_report(self) -> Dict[str, Any]:
        """Get token efficiency report"""
        budget = self.cost_optimizer.get_budget_status()
        cache_stats = self.cache.get_stats()
        
        return {
            "budget": budget,
            "cache": cache_stats,
            "recommendations": self._generate_recommendations(budget, cache_stats)
        }
    
    def _generate_recommendations(self, budget: Dict, cache: Dict) -> List[str]:
        """Generate optimization recommendations"""
        recommendations = []
        
        if budget["health"] == "critical":
            recommendations.append("🚨 Budget critical - switch to Haiku model only")
        elif budget["health"] == "warning":
            recommendations.append("⚠️ Budget low - increase caching, use Haiku for routine tasks")
        
        if budget["avg_cost_per_call"] > 0.1:
            recommendations.append("💰 High cost per call - compress inputs more aggressively")
        
        if cache["fresh_entries"] < 5:
            recommendations.append("📝 Cache underutilized - more opportunities for reuse")
        
        if budget["health"] == "healthy":
            recommendations.append("✅ Operating efficiently - maintain current approach")
        
        return recommendations


# Usage example
if __name__ == "__main__":
    optimizer = TokenOptimizationAPI()
    
    # Simulate task execution
    print("="*70)
    print("TOKEN & CREDIT OPTIMIZATION SYSTEM")
    print("="*70)
    
    # Check budget
    status = optimizer.cost_optimizer.get_budget_status()
    print(f"\n💰 Budget Status:")
    print(f"   Total Budget: ${status['budget']}")
    print(f"   Spent: ${status['spent']}")
    print(f"   Remaining: ${status['remaining']}")
    print(f"   Health: {status['health']}")
    
    # Cache efficiency
    print(f"\n💾 Cache Status:")
    cache_stats = optimizer.cache.get_stats()
    print(f"   Total Entries: {cache_stats['total_entries']}")
    print(f"   Fresh: {cache_stats['fresh_entries']}")
    
    # Get recommendations
    print(f"\n📊 Efficiency Report:")
    report = optimizer.get_efficiency_report()
    for rec in report["recommendations"]:
        print(f"   {rec}")
    
    print("\n" + "="*70)
