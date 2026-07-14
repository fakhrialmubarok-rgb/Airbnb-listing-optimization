"""
Automation Manager: Self-Optimizing Process Orchestration
Every process: scheduled, monitored, self-healing, and self-optimizing
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable
from enum import Enum
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProcessFrequency(Enum):
    """Automation frequency options"""
    EVERY_5_MIN = 5 * 60
    EVERY_15_MIN = 15 * 60
    EVERY_30_MIN = 30 * 60
    HOURLY = 60 * 60
    EVERY_6_HOURS = 6 * 60 * 60
    DAILY = 24 * 60 * 60
    WEEKLY = 7 * 24 * 60 * 60

class ProcessMetrics:
    """Track metrics for each automation process"""
    
    def __init__(self, process_name: str):
        self.process_name = process_name
        self.total_runs = 0
        self.successful_runs = 0
        self.failed_runs = 0
        self.total_items_processed = 0
        self.success_rate = 0.0
        self.avg_processing_time = 0.0
        self.last_run = None
        self.last_error = None
        self.improvement_trend = []  # Track success rate over time
        self.winning_angles = {}  # Track what works best
        self.errors_fixed = {}  # Track bugs fixed
    
    def record_run(self, success: bool, items_processed: int, 
                   processing_time: float, error: Optional[str] = None):
        """Record metrics for a run"""
        self.total_runs += 1
        if success:
            self.successful_runs += 1
        else:
            self.failed_runs += 1
            self.last_error = error
        
        self.total_items_processed += items_processed
        self.last_run = datetime.now().isoformat()
        
        # Update success rate
        self.success_rate = (self.successful_runs / self.total_runs * 100) if self.total_runs > 0 else 0
        
        # Update avg processing time
        self.avg_processing_time = processing_time
        
        # Track improvement trend (last 10 runs)
        self.improvement_trend.append(self.success_rate)
        if len(self.improvement_trend) > 10:
            self.improvement_trend.pop(0)
    
    def record_winning_angle(self, angle_name: str, performance: float):
        """Record a winning angle/approach"""
        if angle_name not in self.winning_angles:
            self.winning_angles[angle_name] = {"count": 0, "total_performance": 0}
        
        self.winning_angles[angle_name]["count"] += 1
        self.winning_angles[angle_name]["total_performance"] += performance
    
    def record_bug_fixed(self, bug_description: str, solution: str):
        """Record a bug that was fixed"""
        self.errors_fixed[bug_description] = {
            "fixed_at": datetime.now().isoformat(),
            "solution": solution
        }
    
    def get_top_winning_angles(self, limit: int = 3) -> List[Dict]:
        """Get top performing angles"""
        if not self.winning_angles:
            return []
        
        sorted_angles = sorted(
            self.winning_angles.items(),
            key=lambda x: x[1]["total_performance"] / x[1]["count"],
            reverse=True
        )
        
        return [
            {
                "angle": name,
                "avg_performance": data["total_performance"] / data["count"],
                "uses": data["count"]
            }
            for name, data in sorted_angles[:limit]
        ]
    
    def get_improvement_status(self) -> str:
        """Determine if process is improving"""
        if len(self.improvement_trend) < 2:
            return "insufficient_data"
        
        recent_avg = sum(self.improvement_trend[-5:]) / min(5, len(self.improvement_trend))
        previous_avg = sum(self.improvement_trend[:-5]) / max(1, len(self.improvement_trend) - 5)
        
        if recent_avg > previous_avg * 1.1:
            return "improving"
        elif recent_avg < previous_avg * 0.9:
            return "declining"
        else:
            return "stable"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for reporting"""
        return {
            "process_name": self.process_name,
            "total_runs": self.total_runs,
            "successful_runs": self.successful_runs,
            "failed_runs": self.failed_runs,
            "success_rate": round(self.success_rate, 1),
            "total_items_processed": self.total_items_processed,
            "avg_processing_time": round(self.avg_processing_time, 2),
            "last_run": self.last_run,
            "last_error": self.last_error,
            "top_winning_angles": self.get_top_winning_angles(),
            "improvement_status": self.get_improvement_status(),
            "bugs_fixed": len(self.errors_fixed)
        }


class AutomationProcess:
    """Base class for an automation process"""
    
    def __init__(self, name: str, frequency: ProcessFrequency, 
                 executor: Callable, frequency_adjustment: bool = True):
        self.name = name
        self.frequency = frequency
        self.executor = executor
        self.frequency_adjustment = frequency_adjustment  # Auto-adjust frequency
        self.metrics = ProcessMetrics(name)
        self.is_active = True
        self.last_executed = None
        self.self_healing_rules = {}
        self.optimization_rules = {}
    
    async def execute(self) -> Dict[str, Any]:
        """Execute the process and record metrics"""
        if not self.is_active:
            return {"status": "skipped", "reason": "process_inactive"}
        
        try:
            start_time = datetime.now()
            
            # Execute the actual process
            result = await self.executor()
            
            end_time = datetime.now()
            processing_time = (end_time - start_time).total_seconds()
            
            # Record metrics
            items_processed = result.get("items_processed", 1)
            self.metrics.record_run(
                success=result.get("success", True),
                items_processed=items_processed,
                processing_time=processing_time
            )
            
            # Record winning angles
            if "winning_angle" in result:
                self.metrics.record_winning_angle(
                    result["winning_angle"],
                    result.get("performance_score", 1.0)
                )
            
            self.last_executed = datetime.now().isoformat()
            
            logger.info(f"✅ {self.name} executed successfully in {processing_time:.2f}s")
            
            return {
                "status": "success",
                "process": self.name,
                "items_processed": items_processed,
                "processing_time": processing_time,
                "result": result
            }
        
        except Exception as e:
            self.metrics.record_run(
                success=False,
                items_processed=0,
                processing_time=0,
                error=str(e)
            )
            
            logger.error(f"❌ {self.name} failed: {str(e)}")
            
            # Try self-healing
            healing_result = await self._self_heal(str(e))
            
            return {
                "status": "error",
                "process": self.name,
                "error": str(e),
                "healing_attempted": healing_result
            }
    
    async def _self_heal(self, error: str) -> Dict:
        """Attempt to self-heal from errors"""
        logger.info(f"🔧 Attempting to self-heal {self.name}...")
        
        # Check if we have a healing rule for this error
        for error_pattern, healing_action in self.self_healing_rules.items():
            if error_pattern.lower() in error.lower():
                try:
                    result = await healing_action()
                    self.metrics.record_bug_fixed(error, str(result))
                    logger.info(f"✅ Self-healing succeeded for {self.name}")
                    return {"healed": True, "action": healing_action.__name__}
                except Exception as e:
                    logger.error(f"❌ Self-healing failed: {str(e)}")
                    return {"healed": False, "error": str(e)}
        
        return {"healed": False, "reason": "no_healing_rule_found"}
    
    def adjust_frequency(self):
        """Auto-adjust frequency based on performance"""
        if not self.frequency_adjustment:
            return
        
        status = self.metrics.get_improvement_status()
        current_frequency_sec = self.frequency.value
        
        if status == "improving" and self.metrics.success_rate > 95:
            # Can run more frequently if working well
            new_frequency_sec = int(current_frequency_sec * 0.8)
            logger.info(f"📈 {self.name}: Increasing frequency (working well)")
        elif status == "declining" or self.metrics.success_rate < 70:
            # Run less frequently if having issues
            new_frequency_sec = int(current_frequency_sec * 1.5)
            logger.warning(f"📉 {self.name}: Decreasing frequency (needs fixes)")
        else:
            return
        
        # Find closest frequency enum
        for freq in ProcessFrequency:
            if abs(freq.value - new_frequency_sec) < current_frequency_sec * 0.2:
                self.frequency = freq
                logger.info(f"⏱️ {self.name}: Adjusted to {freq.name}")
                break
    
    def add_self_healing_rule(self, error_pattern: str, healing_action: Callable):
        """Add a self-healing rule for specific error"""
        self.self_healing_rules[error_pattern] = healing_action
    
    def add_optimization_rule(self, condition: str, optimization: Callable):
        """Add an optimization rule"""
        self.optimization_rules[condition] = optimization


class AutomationScheduler:
    """Main scheduler for all automation processes"""
    
    def __init__(self):
        self.processes: Dict[str, AutomationProcess] = {}
        self.execution_log = []
        self.performance_report = {}
    
    def register_process(self, process: AutomationProcess):
        """Register an automation process"""
        self.processes[process.name] = process
        logger.info(f"📋 Registered process: {process.name} ({process.frequency.name})")
    
    def get_process_status(self) -> Dict[str, Any]:
        """Get status of all processes"""
        return {
            process_name: process.metrics.to_dict()
            for process_name, process in self.processes.items()
        }
    
    def get_winning_strategies(self) -> Dict[str, List]:
        """Get winning strategies across all processes"""
        strategies = {}
        for process_name, process in self.processes.items():
            winning = process.metrics.get_top_winning_angles()
            if winning:
                strategies[process_name] = winning
        return strategies
    
    def generate_optimization_report(self) -> Dict[str, Any]:
        """Generate comprehensive optimization report"""
        report = {
            "generated_at": datetime.now().isoformat(),
            "processes": {},
            "recommendations": [],
            "overall_health": "good"
        }
        
        total_success_rate = 0
        process_count = 0
        
        for process_name, process in self.processes.items():
            metrics = process.metrics.to_dict()
            report["processes"][process_name] = metrics
            total_success_rate += metrics["success_rate"]
            process_count += 1
            
            # Generate recommendations
            if metrics["success_rate"] < 80:
                report["recommendations"].append({
                    "process": process_name,
                    "issue": "Low success rate",
                    "suggestion": f"Review and fix bugs. Current rate: {metrics['success_rate']}%"
                })
            
            if metrics["improvement_status"] == "declining":
                report["recommendations"].append({
                    "process": process_name,
                    "issue": "Performance declining",
                    "suggestion": "Investigate recent changes or environmental factors"
                })
            
            if metrics["top_winning_angles"]:
                report["recommendations"].append({
                    "process": process_name,
                    "issue": "Winning strategy identified",
                    "suggestion": f"Replicate {metrics['top_winning_angles'][0]['angle']} approach"
                })
        
        # Overall health
        if process_count > 0:
            avg_success = total_success_rate / process_count
            if avg_success > 95:
                report["overall_health"] = "excellent"
            elif avg_success > 85:
                report["overall_health"] = "good"
            elif avg_success > 70:
                report["overall_health"] = "fair"
            else:
                report["overall_health"] = "needs_attention"
        
        return report


# ============================================================================
# SPECIFIC AUTOMATION PROCESSES FOR LISTINGBOOST
# ============================================================================

class LeadGenerationProcess(AutomationProcess):
    """Daily lead generation: 20-50 properties per day"""
    
    async def execute(self) -> Dict[str, Any]:
        # This would connect to Airbnb scraping or property database
        # For now, simulated
        
        result = {
            "success": True,
            "items_processed": 35,  # Generated 35 leads today
            "leads_generated": 35,
            "winning_angle": "high_price_range_filter"  # What worked best
        }
        
        return await super().execute()


class OutreachProcess(AutomationProcess):
    """Check responses every 5 minutes"""
    
    async def execute(self) -> Dict[str, Any]:
        # Check for responses, auto-reply to inquiries
        
        result = {
            "success": True,
            "items_processed": 5,  # Checked 5 recent outreach emails
            "responses_found": 2,
            "auto_replies_sent": 2,
            "winning_angle": "psychology_focused_subject_line"
        }
        
        return await super().execute()


class ReportGenerationProcess(AutomationProcess):
    """Generate monthly reports for active subscribers"""
    
    async def execute(self) -> Dict[str, Any]:
        # Generate PDF reports for all subscribers
        
        result = {
            "success": True,
            "items_processed": 15,  # Generated 15 reports
            "reports_generated": 15,
            "emails_sent": 15,
            "winning_angle": "detailed_benchmarking_insights"
        }
        
        return await super().execute()


class ConversionOptimizationProcess(AutomationProcess):
    """Analyze conversions and optimize messaging"""
    
    async def execute(self) -> Dict[str, Any]:
        # Analyze which messages convert best
        
        result = {
            "success": True,
            "items_processed": 100,  # Analyzed 100 conversations
            "conversions_analyzed": 25,
            "conversion_rate": 0.25,
            "winning_angle": "value_anchoring_approach"
        }
        
        return await super().execute()


class PaymentProcessingProcess(AutomationProcess):
    """Process payments and subscriptions"""
    
    async def execute(self) -> Dict[str, Any]:
        # Process new subscriptions and renewals
        
        result = {
            "success": True,
            "items_processed": 5,
            "new_subscriptions": 3,
            "renewals": 2,
            "revenue_processed": 250.0,
            "winning_angle": "first_month_credit_conversion"
        }
        
        return await super().execute()


class DataAnalysisProcess(AutomationProcess):
    """Analyze customer data and identify trends"""
    
    async def execute(self) -> Dict[str, Any]:
        # Weekly deep dive into data
        
        result = {
            "success": True,
            "items_processed": 50,  # Analyzed 50 customers
            "insights_found": 5,
            "amenities_ranked": ["hot_tub", "cold_plunge", "sauna"],
            "winning_angle": "sentiment_correlation_analysis"
        }
        
        return await super().execute()


class BugFixProcess(AutomationProcess):
    """Auto-detect and fix bugs"""
    
    async def execute(self) -> Dict[str, Any]:
        # Monitor for errors and auto-fix
        
        result = {
            "success": True,
            "items_processed": 10,  # Scanned 10 error logs
            "bugs_found": 1,
            "bugs_fixed": 1,
            "winning_angle": "pattern_matching_detection"
        }
        
        return await super().execute()


if __name__ == "__main__":
    print("✅ Automation Framework Loaded")
    print("   - ProcessFrequency: 5min, 15min, 30min, hourly, 6hr, daily, weekly")
    print("   - ProcessMetrics: Tracks success rate, winning angles, bugs fixed")
    print("   - AutomationProcess: Base class with self-healing")
    print("   - AutomationScheduler: Orchestrates all processes")
    print("   - 6 specific processes: Lead gen, Outreach, Reports, Conversion, Payments, Analysis")
