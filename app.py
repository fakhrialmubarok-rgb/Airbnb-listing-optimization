import os
import json
import logging
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
from description_improver import improve_listing_description, generate_title_suggestions
from image_enhancer import enhance_image, batch_enhance_images
from listing_analyzer import ListingAnalyzer, ListingEnhancementPlan
from premium_qc import PremiumQCReport, FreemiumPreviewEngine, ValuePerceptionEngine
from analytics_engine import ListingAnalyticsCollector, FutureProductPlanner
from customer_data_model import CustomerDataStore, ConversionFunnelAnalysis, DataInsights
from research_reports import (
    MonthlyResearchReportGenerator,
    SubscriptionManager,
    ResearchReportAPI,
    ResearchReportScheduler
)
from automation_orchestrator import create_automation_system
from description_improver import improve_listing_description, generate_title_suggestions
from customer_delivery_pipeline import CustomerDeliveryPipeline

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

# Initialize automation orchestrator
automation_system = create_automation_system()
logger.info("✅ Automation system initialized with 9 processes")

# Initialize customer delivery pipeline
delivery_pipeline = CustomerDeliveryPipeline()
logger.info("✅ Customer delivery pipeline initialized")

# Initialize analytics components
data_store = CustomerDataStore()
analytics_collector = ListingAnalyticsCollector()
funnel_analysis = ConversionFunnelAnalysis(data_store)
product_planner = FutureProductPlanner()
report_generator = MonthlyResearchReportGenerator()
report_scheduler = ResearchReportScheduler()

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/improve-description', methods=['POST'])
def api_improve_description():
    """Improve listing description using Claude."""
    try:
        data = request.json
        original_desc = data.get('description', '')
        
        if not original_desc or len(original_desc) < 10:
            return jsonify({'error': 'Description too short'}), 400
        
        improved = improve_listing_description(original_desc)
        
        return jsonify({
            'success': True,
            'original': original_desc,
            'improved': improved
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-titles', methods=['POST'])
def api_generate_titles():
    """Generate title suggestions using Claude."""
    try:
        data = request.json
        property_type = data.get('property_type', 'Apartment')
        key_features = data.get('key_features', '')
        location = data.get('location', '')
        
        titles = generate_title_suggestions(property_type, key_features, location)
        
        return jsonify({
            'success': True,
            'titles': titles
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/enhance-images', methods=['POST'])
def api_enhance_images():
    """Enhance uploaded images."""
    try:
        if 'images' not in request.files:
            return jsonify({'error': 'No images provided'}), 400
        
        files = request.files.getlist('images')
        results = {}
        
        for file in files:
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                # Enhance the image
                img_base64 = enhance_image(filepath)
                results[filename] = {
                    'status': 'success',
                    'base64': img_base64
                }
        
        if not results:
            return jsonify({'error': 'No valid images provided'}), 400
        
        return jsonify({
            'success': True,
            'images': results,
            'count': len(results)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/preview', methods=['POST'])
def api_preview():
    """Generate a full preview (description + titles + images)."""
    try:
        data = request.json
        
        description = data.get('description', '')
        property_type = data.get('property_type', 'Apartment')
        key_features = data.get('key_features', '')
        location = data.get('location', '')
        
        # Improve description
        improved_desc = improve_listing_description(description)
        
        # Generate titles
        titles = generate_title_suggestions(property_type, key_features, location)
        
        return jsonify({
            'success': True,
            'improved_description': improved_desc,
            'title_suggestions': titles
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/audit-listing', methods=['POST'])
def api_audit_listing():
    """Audit a listing to find gaps and missing photos."""
    try:
        data = request.json
        description = data.get('description', '')
        photos = data.get('photos', [])
        
        if not description or len(description) < 20:
            return jsonify({'error': 'Description too short'}), 400
        
        analyzer = ListingAnalyzer()
        audit = analyzer.generate_full_audit(description, photos)
        
        return jsonify({
            'success': True,
            'audit': audit
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/enhancement-plan', methods=['POST'])
def api_enhancement_plan():
    """Generate a complete enhancement plan for a listing."""
    try:
        data = request.json
        description = data.get('description', '')
        photos = data.get('photos', [])
        
        if not description or len(description) < 20:
            return jsonify({'error': 'Description too short'}), 400
        
        planner = ListingEnhancementPlan()
        plan = planner.create_action_plan(description, photos)
        
        return jsonify({
            'success': True,
            'plan': plan
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/premium-qc-report', methods=['POST'])
def api_premium_qc():
    """Generate comprehensive QC report before delivery."""
    try:
        data = request.json
        description = data.get('description', '')
        property_type = data.get('property_type', 'Apartment')
        base_price = data.get('base_price', '$100/night')
        images = data.get('images', [])
        
        if not description or len(description) < 20:
            return jsonify({'error': 'Description too short'}), 400
        
        qc_engine = PremiumQCReport()
        report = qc_engine.generate_full_qc_report(
            description,
            property_type,
            base_price,
            images or ["Image 1", "Image 2", "Image 3"]
        )
        
        return jsonify({
            'success': True,
            'qc_report': report
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/freemium-preview', methods=['POST'])
def api_freemium_preview():
    """Generate watermarked preview to show value without giving away full work."""
    try:
        data = request.json
        images = data.get('images', [])
        best_image_index = data.get('best_image_index', 0)
        
        if not images:
            return jsonify({'error': 'No images provided'}), 400
        
        preview = FreemiumPreviewEngine.create_preview_package(
            images,
            best_image_index
        )
        
        return jsonify({
            'success': True,
            'preview': preview
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/value-perception', methods=['POST'])
def api_value_perception():
    """Show host why $20 investment feels like $5000+ value."""
    try:
        data = request.json
        property_type = data.get('property_type', 'Apartment')
        base_price = data.get('base_price', '$100/night')
        enhancements = data.get('enhancements', [
            'Professional lighting enhancement',
            'Color correction',
            'Clarity optimization',
            'Composition refinement'
        ])
        
        engine = ValuePerceptionEngine()
        
        roi = engine.calculate_roi_impact(property_type, base_price, enhancements)
        value_prop = engine.generate_value_proposition(property_type, enhancements)
        
        return jsonify({
            'success': True,
            'roi_impact': roi,
            'value_proposition': value_prop
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/collect-listing-analytics', methods=['POST'])
def api_collect_analytics():
    """Collect comprehensive analytics on a listing"""
    try:
        data = request.json
        listing_id = data.get('listing_id', f"listing_{data.get('title', 'unknown')}")
        
        # Create comprehensive profile
        profile = analytics_collector.create_customer_profile(listing_id, data)
        
        # Store in data store
        data_store.store_customer_profile(profile)
        
        return jsonify({
            'status': 'success',
            'listing_id': listing_id,
            'profile': profile,
            'segments': data_store.segments
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/funnel-analytics', methods=['GET'])
def api_funnel_analytics():
    """Get conversion funnel metrics"""
    try:
        metrics = funnel_analysis.get_funnel_metrics()
        return jsonify({
            'status': 'success',
            'funnel_metrics': metrics,
            'high_value_customers': len(funnel_analysis.get_high_value_customers()),
            'churned_customers': len(funnel_analysis.get_churned_customers())
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/segment-performance', methods=['GET'])
def api_segment_performance():
    """Get performance metrics by customer segment"""
    try:
        performance = funnel_analysis.get_segment_performance()
        return jsonify({
            'status': 'success',
            'segment_performance': performance
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/market-insights', methods=['GET'])
def api_market_insights():
    """Get market insights from all customers"""
    try:
        customers = data_store.get_all_customers()
        insights = DataInsights.identify_patterns(data_store)
        
        return jsonify({
            'status': 'success',
            'total_customers': len(customers),
            'patterns': insights,
            'conversion_stats': data_store.get_conversion_stats()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/future-upsells', methods=['GET'])
def api_future_upsells():
    """Get identified upsell opportunities"""
    try:
        customers = data_store.get_all_customers()
        segments = data_store.segments
        
        upsells = product_planner.identify_upsell_opportunities(customers, segments)
        
        return jsonify({
            'status': 'success',
            'upsell_opportunities': upsells,
            'total_customers': len(customers)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export-analytics', methods=['GET'])
def api_export_analytics():
    """Export all collected analytics"""
    try:
        export_data = data_store.export_for_analysis()
        data_store.save_to_json('customer_data_export.json')
        
        return jsonify({
            'status': 'success',
            'data': export_data,
            'export_file': 'customer_data_export.json'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/subscribe-research-reports', methods=['POST'])
def api_subscribe_research_reports():
    """Subscribe customer to $50/month research reports"""
    try:
        data = request.json
        customer_id = data.get('customer_id', f"customer_{data.get('name', 'unknown')}")
        initial_service_charge = data.get('initial_service_charge', 0.0)
        
        # Create subscription
        result = research_api.subscribe_to_research_reports(
            customer_id=customer_id,
            initial_service_charge=initial_service_charge
        )
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/monthly-report-preview', methods=['GET'])
def api_monthly_report_preview():
    """Preview what subscribers receive monthly"""
    try:
        customers = data_store.get_all_customers()
        preview = research_api.get_monthly_reports_preview(customers)
        
        return jsonify(preview)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-subscriber-reports', methods=['POST'])
def api_generate_subscriber_reports():
    """Generate monthly reports for all active subscribers"""
    try:
        # Get all active subscriptions
        active_subs = research_api.subscription_manager.get_active_subscriptions()
        subscriber_ids = [sub['customer_id'] for sub in active_subs]
        
        # Get all customer data
        customers = data_store.get_all_customers()
        
        # Generate reports
        reports = report_scheduler.generate_reports_for_subscribers(
            customers, 
            subscriber_ids
        )
        
        # Mark reports as sent
        for sub_id in subscriber_ids:
            research_api.subscription_manager.mark_report_sent(sub_id)
        
        return jsonify({
            'status': 'success',
            'reports_generated': len(reports),
            'active_subscribers': len(subscriber_ids),
            'sample_report_excerpt': list(reports.values())[0]['report_content'][:500] if reports else ""
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/subscription-status/<customer_id>', methods=['GET'])
def api_subscription_status(customer_id):
    """Get subscription status for a customer"""
    try:
        sub = research_api.subscription_manager.get_subscription(customer_id)
        
        if not sub:
            return jsonify({'status': 'no_subscription', 'customer_id': customer_id})
        
        return jsonify({
            'status': 'success',
            'subscription': sub,
            'monthly_mrr': sub['effective_price'],
            'reports_received': sub['reports_received']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/subscription-roi', methods=['GET'])
def api_subscription_roi():
    """Show ROI of combined services"""
    try:
        roi = research_api.calculate_subscription_roi()
        
        return jsonify({
            'status': 'success',
            'roi': roi
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/monthly-mrr', methods=['GET'])
def api_monthly_mrr():
    """Get current monthly recurring revenue"""
    try:
        mrr = research_api.subscription_manager.calculate_monthly_revenue()
        active_subs = research_api.subscription_manager.get_active_subscriptions()
        
        return jsonify({
            'status': 'success',
            'monthly_recurring_revenue': mrr,
            'active_subscribers': len(active_subs),
            'average_subscription_price': round(mrr / len(active_subs), 2) if active_subs else 0
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/customer/process-order', methods=['POST'])
def api_customer_process_order():
    """
    Complete customer order processing:
    1. Analyze property
    2. Generate PDF gap analysis
    3. Send email with PDF
    
    Request:
    {
        "customer_name": "John Smith",
        "customer_email": "john@example.com",
        "property_name": "Tribeca Loft",
        "property_location": "New York, NY",
        "nightly_price": 250,
        "amenities": ["Hot tub", "Fireplace"],
        "description": "Beautiful loft..."
    }
    """
    
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ['customer_name', 'customer_email', 'property_name', 'property_location', 'nightly_price', 'amenities']
        for field in required_fields:
            if field not in data:
                return jsonify({'status': 'error', 'message': f'Missing field: {field}'}), 400
        
        # Process order through delivery pipeline
        result = delivery_pipeline.process_customer_order(data)
        
        return jsonify(result), 200 if result['status'] == 'success' else 400
    
    except Exception as e:
        logger.error(f"❌ Customer order error: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/customer/analyze-property', methods=['POST'])
def api_customer_analyze_property():
    """
    Quick property analysis without PDF/email
    Returns: Analysis data only
    """
    
    try:
        data = request.json
        
        # Analyze
        analysis = delivery_pipeline._analyze_property(data)
        
        return jsonify({
            'status': 'success',
            'property': data.get('property_name'),
            'analysis': analysis
        }), 200
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/automation/status', methods=['GET'])
def api_automation_status():
    """Get status of all automation processes"""
    metrics = automation_system.get_all_metrics()
    return jsonify({
        "status": "running",
        "processes": metrics,
        "total_processes": len(automation_system.processes)
    })


@app.route('/api/automation/execute-all', methods=['POST'])
async def api_automation_execute_all():
    """Execute all automation processes that are due"""
    results = await automation_system.execute_all_due()
    return jsonify({
        "status": "success",
        "processes_executed": len(results),
        "results": results
    })


@app.route('/api/automation/execute/<process_name>', methods=['POST'])
async def api_automation_execute_single(process_name):
    """Execute a specific automation process"""
    result = await automation_system.execute_process(process_name)
    return jsonify(result)


@app.route('/api/automation/report', methods=['GET'])
def api_automation_report():
    """Get comprehensive optimization report"""
    report = automation_system.generate_optimization_report()
    return jsonify(report)


@app.route('/api/automation/winning-strategies', methods=['GET'])
def api_automation_winning_strategies():
    """Get winning strategies across all processes"""
    strategies = automation_system.get_winning_strategies()
    return jsonify({
        "status": "success",
        "winning_strategies": strategies
    })


@app.route('/api/automation/process/<process_name>/metrics', methods=['GET'])
def api_process_metrics(process_name):
    """Get detailed metrics for a specific process"""
    if process_name not in automation_system.processes:
        return jsonify({"error": f"Process {process_name} not found"}), 404
    
    process = automation_system.processes[process_name]
    return jsonify({
        "process": process_name,
        "metrics": process.metrics.to_dict(),
        "description": process.description,
        "frequency": process.frequency.name
    })


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    logger.info('Starting ListingBoost server on http://localhost:5001')
    app.run(host='127.0.0.1', port=5001, debug=False)
