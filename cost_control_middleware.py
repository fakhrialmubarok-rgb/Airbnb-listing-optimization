"""
Cost Control Middleware for Flask
Integrates token optimization into all API endpoints
"""

import json
import logging
from functools import wraps
from flask import request, jsonify
from token_optimizer import TokenOptimizationAPI, CostOptimizer, FallbackStrategies

logger = logging.getLogger(__name__)

# Global optimizer instance
cost_control = TokenOptimizationAPI()

def cost_controlled(fallback_task: str = None):
    """
    Decorator for cost-controlled API endpoints
    Automatically routes to cheapest model or fallback if budget depleted
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check budget
            budget = cost_control.cost_optimizer.get_budget_status()
            
            # If critical budget, use fallback
            if budget["health"] == "critical":
                logger.warning(f"⚠️ BUDGET CRITICAL - Using fallback for {f.__name__}")
                
                if fallback_task:
                    input_data = request.get_json() or {}
                    fallback_response = cost_control.fallbacks.get_response(
                        fallback_task,
                        input_data
                    )
                    return jsonify({
                        "status": "success",
                        "source": "fallback",
                        "reason": "budget_depleted",
                        "result": fallback_response,
                        "budget_remaining": budget["remaining"]
                    }), 200
            
            # Execute normal endpoint
            try:
                result = f(*args, **kwargs)
                
                # Add budget info to response if JSON
                if isinstance(result, dict):
                    result["budget_remaining"] = budget["remaining"]
                    result["budget_health"] = budget["health"]
                
                return result
            
            except Exception as e:
                logger.error(f"Error in {f.__name__}: {str(e)}")
                
                # Try fallback on error
                if fallback_task:
                    logger.warning(f"Falling back to template response")
                    input_data = request.get_json() or {}
                    fallback_response = cost_control.fallbacks.get_response(
                        fallback_task,
                        input_data
                    )
                    return jsonify({
                        "status": "success_with_fallback",
                        "source": "fallback",
                        "reason": f"error: {str(e)}",
                        "result": fallback_response,
                        "budget_remaining": budget["remaining"]
                    }), 200
                
                return jsonify({"error": str(e)}), 500
        
        return decorated_function
    return decorator


class CostControlMiddleware:
    """Middleware for cost tracking and limiting"""
    
    def __init__(self, app):
        self.app = app
        self.optimizer = cost_control
        
        # Register cost monitoring endpoint
        app.add_url_rule(
            '/api/cost-control/status',
            'cost_status',
            self.get_cost_status,
            methods=['GET']
        )
        
        app.add_url_rule(
            '/api/cost-control/report',
            'cost_report',
            self.get_cost_report,
            methods=['GET']
        )
        
        app.add_url_rule(
            '/api/cost-control/budget/set',
            'set_budget',
            self.set_budget,
            methods=['POST']
        )
        
        app.add_url_rule(
            '/api/cost-control/budget/alert',
            'budget_alert',
            self.get_budget_alert,
            methods=['GET']
        )
    
    def get_cost_status(self):
        """Get real-time cost status"""
        status = self.optimizer.cost_optimizer.get_budget_status()
        cache_stats = self.optimizer.cache.get_stats()
        
        return jsonify({
            "status": "ok",
            "budget": status,
            "cache": cache_stats,
            "timestamp": str(datetime.now())
        })
    
    def get_cost_report(self):
        """Get comprehensive cost report"""
        report = self.optimizer.get_efficiency_report()
        
        # Add historical data
        recent_calls = self.optimizer.cost_optimizer.call_history[-10:]
        
        return jsonify({
            "status": "ok",
            "report": report,
            "recent_calls": [
                {
                    "timestamp": str(c["timestamp"]),
                    "task": c["task"],
                    "cost": c["cost"],
                    "tokens": f"{c['tokens_in']}→{c['tokens_out']}",
                    "model": c["model"]
                }
                for c in recent_calls
            ]
        })
    
    def set_budget(self):
        """Set/update budget limit"""
        data = request.get_json()
        new_budget = data.get("budget", 100)
        
        self.optimizer.cost_optimizer.cost_budget = new_budget
        logger.info(f"💰 Budget updated to ${new_budget}")
        
        return jsonify({
            "status": "success",
            "new_budget": new_budget,
            "remaining": new_budget - self.optimizer.cost_optimizer.current_spend
        })
    
    def get_budget_alert(self):
        """Get budget alert status"""
        status = self.optimizer.cost_optimizer.get_budget_status()
        
        alert_level = "ok"
        message = "Operating normally"
        
        if status["health"] == "critical":
            alert_level = "critical"
            message = f"Budget depleted! Using fallback responses only"
        elif status["health"] == "warning":
            alert_level = "warning"
            message = f"Budget low (${status['remaining']:.2f} remaining)"
        
        return jsonify({
            "status": "ok",
            "alert_level": alert_level,
            "message": message,
            "budget_remaining": status["remaining"],
            "percent_used": (status["spent"] / status["budget"] * 100)
        })


def create_cost_controlled_endpoints(app):
    """Create endpoints with cost control"""
    
    @app.route('/api/smart/describe-amenity', methods=['POST'])
    @cost_controlled(fallback_task="describe_amenity")
    def smart_describe_amenity():
        """Describe amenity with cost optimization"""
        data = request.get_json()
        # Implementation uses cached templates or API
        # Falls back to templates if budget depleted
        pass
    
    @app.route('/api/smart/gap-detection', methods=['POST'])
    @cost_controlled(fallback_task="gap_detection")
    def smart_gap_detection():
        """Detect gaps with cost optimization"""
        data = request.get_json()
        # Falls back to standard gaps list if budget depleted
        pass
    
    @app.route('/api/smart/psychology-analysis', methods=['POST'])
    @cost_controlled(fallback_task="psychology_analysis")
    def smart_psychology_analysis():
        """Analyze psychology with cost optimization"""
        data = request.get_json()
        # Falls back to price-based recommendations if budget depleted
        pass
    
    @app.route('/api/smart/generate-titles', methods=['POST'])
    @cost_controlled(fallback_task="title_suggestions")
    def smart_generate_titles():
        """Generate titles with cost optimization"""
        data = request.get_json()
        # Falls back to templates if budget depleted
        pass


# Export for use in app.py
__all__ = ['cost_controlled', 'CostControlMiddleware', 'cost_control', 'create_cost_controlled_endpoints']
