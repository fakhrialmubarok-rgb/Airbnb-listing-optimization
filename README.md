# 🚀 ListingBoost - Airbnb Listing Improvement Platform

Transform Airbnb listings with AI-powered descriptions, professional titles, and enhanced photos. Help hosts boost their bookings without expensive photographers.

## ✨ Features

### 1. **Description Improvement** 📝
- AI-powered content rewrite using Claude 3.5 Sonnet
- Makes descriptions more compelling and conversion-focused
- Highlights unique features and amenities
- Mentions professional photography enhancements
- 20-30% longer but maintains scannability

### 2. **Title Suggestions** 🎨
- Generates 5 different title options
- Each under 50 characters (Airbnb optimized)
- Includes most attractive feature first
- SEO-friendly for better discoverability
- Tested for high click-through rates

### 3. **Photo Enhancement** ✨
- Automatically enhances listing images
- Increases brightness and contrast (+15-25%)
- Boosts color saturation (+35%)
- Sharpens details for professional look
- Processes multiple images at once
- Returns high-quality JPEG output

## 💰 Business Model

Perfect for serving Airbnb hosts who want professional results without photographer costs:

- **$20 Package**: Description + Title suggestions (text-only)
- **$50 Package**: Description + Titles + Image enhancement (complete)
- **Competitive advantage**: Traditional photographers charge $500+

## 🛠️ Tech Stack

- **Backend**: Flask (Python)
- **AI/ML**: Anthropic Claude API (descriptions & titles)
- **Image Processing**: OpenCV + Pillow (enhancement)
- **Frontend**: Modern HTML/CSS/JavaScript (no frameworks needed)
- **Styling**: Responsive design with purple gradient theme

## 📦 Installation

### Prerequisites
- Python 3.9+
- macOS (easily portable to Linux/Windows)

### Quick Start

```bash
# Clone or navigate to project
cd airbnb-lister

# Run startup script (handles venv setup)
bash start.sh

# Or manually:
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

The app will start on `http://localhost:5000`

## 🔌 API Endpoints

All endpoints return JSON responses.

### 1. **Improve Description**
```bash
POST /api/improve-description
Content-Type: application/json

{
  "description": "Nice apartment in the city. Has 2 bedrooms..."
}

Response:
{
  "success": true,
  "original": "...",
  "improved": "Welcome to this stunning urban apartment...[enhanced version]"
}
```

### 2. **Generate Titles**
```bash
POST /api/generate-titles
Content-Type: application/json

{
  "property_type": "Apartment",
  "key_features": "Ocean view, Modern kitchen, Rooftop",
  "location": "San Francisco, Marina District"
}

Response:
{
  "success": true,
  "titles": [
    "Stunning Ocean-View Marina Apartment",
    "Modern Rooftop Apartment with Golden Gate Views",
    "Luxury Marina Home - Ocean Views Included",
    "Bright Modern Apartment Steps from Beach",
    "Premium Marina Living with Sunset Views"
  ]
}
```

### 3. **Enhance Images**
```bash
POST /api/enhance-images
Content-Type: multipart/form-data

Files: [image1.jpg, image2.png, ...]

Response:
{
  "success": true,
  "count": 3,
  "images": {
    "image1.jpg": {
      "status": "success",
      "base64": "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
    }
  }
}
```

### 4. **Health Check**
```bash
GET /health

Response:
{
  "status": "ok"
}
```

## 📝 Usage Examples

### Via Web Interface
1. Visit `http://localhost:5000`
2. Choose a tab (Description, Titles, or Images)
3. Fill in the required information
4. Click the enhancement button
5. Copy results to clipboard or implement in Airbnb

### Via API (cURL)
```bash
# Improve a description
curl -X POST http://localhost:5000/api/improve-description \
  -H "Content-Type: application/json" \
  -d '{
    "description": "2 bed apartment near subway"
  }'

# Generate titles
curl -X POST http://localhost:5000/api/generate-titles \
  -H "Content-Type: application/json" \
  -d '{
    "property_type": "Apartment",
    "key_features": "Modern, Bright, Near Transit",
    "location": "Downtown Brooklyn"
  }'

# Enhance images
curl -X POST http://localhost:5000/api/enhance-images \
  -F "images=@photo1.jpg" \
  -F "images=@photo2.jpg"
```

### Via Python
```python
import requests

# Improve description
response = requests.post(
    'http://localhost:5000/api/improve-description',
    json={'description': 'Your listing description here...'}
)
improved = response.json()['improved']
print(improved)

# Generate titles
response = requests.post(
    'http://localhost:5000/api/generate-titles',
    json={
        'property_type': 'Apartment',
        'key_features': 'Spacious, Modern, Ocean view',
        'location': 'Malibu'
    }
)
titles = response.json()['titles']
for title in titles:
    print(f"- {title}")
```

## 📊 Project Structure

```
airbnb-lister/
├── app.py                      # Flask application
├── description_improver.py     # Claude API integration for text
├── image_enhancer.py          # OpenCV/Pillow image processing
├── requirements.txt           # Python dependencies
├── templates/
│   └── index.html            # Web interface (single page)
├── uploads/                  # Temporary image storage
├── start.sh                  # Startup script
├── test_components.py        # Component verification
└── README.md                 # This file
```

## 🔐 Security & Best Practices

### Production Deployment

For production use, consider:

1. **API Key Management**
   ```python
   # Use environment variables for Anthropic API key
   import os
   api_key = os.getenv('ANTHROPIC_API_KEY')
   ```

2. **Rate Limiting**
   ```python
   from flask_limiter import Limiter
   limiter = Limiter(app, key_func=lambda: request.remote_addr)
   @limiter.limit("10/minute")
   def api_improve_description():
       ...
   ```

3. **File Upload Security**
   - Limit file size (currently 10MB)
   - Validate file types
   - Store in secure location
   - Clean up old files regularly

4. **CORS in Production**
   ```python
   CORS(app, origins=["yourdomain.com"])  # Restrict to your domain
   ```

### Environment Variables
```bash
export ANTHROPIC_API_KEY="your-key-here"
export FLASK_ENV=production
export FLASK_DEBUG=0
```

## 🚀 Deployment Options

### Option 1: Heroku
```bash
echo "web: gunicorn app:app" > Procfile
git push heroku main
```

### Option 2: AWS Lambda + API Gateway
Use AWS Lambda with Flask adapter for serverless deployment.

### Option 3: Docker
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "app.py"]
```

## 💡 Usage Scenarios

### 1. **Self-Service for Hosts**
- Hosts visit your landing page
- Paste their listing details
- Download improved content
- Copy to Airbnb manually

### 2. **Bulk Processing**
- API integration for property managers
- Process 100+ listings at scale
- Store results in database

### 3. **Integration with PM Software**
- Embed in property management platforms
- One-click enhancement
- Auto-sync improvements to Airbnb

## 📈 Optimization Tips

### For Best Description Results
- Provide complete current listing (more context = better results)
- Include specific amenities and features
- Mention unique selling points

### For Best Titles
- Provide accurate property type
- Include 3-5 key features
- Specify exact location/area

### For Best Images
- Use high-quality source photos (2000x1500px+)
- Good lighting in original
- Recent photos (furniture/decor)
- Multiple angles/rooms

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| Flask 403 error | Check templates folder exists and has index.html |
| Claude API error | Verify `ANTHROPIC_API_KEY` environment variable is set |
| Image enhancement fails | Check file format (.jpg, .png, .webp) |
| Port 5000 already in use | `lsof -i :5000` to find process, or use different port |

## 📞 Next Steps

1. **Test locally** - Verify all components work with sample listings
2. **Customize branding** - Update colors, text, pricing in HTML
3. **Add payment** - Integrate Stripe/PayPal for automation
4. **Build outreach** - Email templates to reach Airbnb hosts
5. **Scale** - Deploy to cloud, add database for tracking

## 📄 License

This project is provided as-is for personal/commercial use.

---

**Built with ❤️ for Airbnb hosts who want professional listings.**

Questions? Start with `test_components.py` to verify everything works.
