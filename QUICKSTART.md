# 🎯 ListingBoost - Quick Start & Deployment Checklist

## ✅ Pre-Launch Checklist

- [ ] **Test all components locally**
  ```bash
  python test_components.py
  ```

- [ ] **Verify API key is set**
  ```bash
  echo $ANTHROPIC_API_KEY  # Should show your key
  ```

- [ ] **Test each endpoint manually**
  ```bash
  # Test description improvement
  curl -X POST http://localhost:5000/api/improve-description \
    -H "Content-Type: application/json" \
    -d '{"description":"Basic 2 bed apartment"}'
  
  # Test title generation
  curl -X POST http://localhost:5000/api/generate-titles \
    -H "Content-Type: application/json" \
    -d '{
      "property_type":"Apartment",
      "key_features":"Spacious, Modern",
      "location":"San Francisco"
    }'
  ```

- [ ] **Test web interface**
  - Visit http://localhost:5000
  - Try each tab (Description, Titles, Images)
  - Upload and enhance a sample photo

## 🚀 Quick Start Commands

```bash
# Start development server
cd airbnb-lister
bash start.sh

# Or manually
source venv/bin/activate
python app.py
```

Visit: **http://localhost:5000**

## 📊 Testing Sample Data

### Test Description
```
Nice apartment in downtown area. Close to subway. 2 bedrooms, 1 bathroom. Recently renovated. Good for families and couples.
```

### Test Location/Features
- Property: Apartment
- Features: Spacious, Modern kitchen, Downtown location
- City: San Francisco / New York / Los Angeles

### Test Images
- Use any .jpg or .png photo
- Ideally 2000x1500px or larger
- Multiple images (bedroom, kitchen, living room, bathroom)

## 💻 API Quick Reference

### POST /api/improve-description
```json
{
  "description": "Your current Airbnb listing text..."
}
```

### POST /api/generate-titles
```json
{
  "property_type": "Apartment|House|Studio|Villa|Condo|Townhouse",
  "key_features": "Feature1, Feature2, Feature3",
  "location": "City, Neighborhood or Area"
}
```

### POST /api/enhance-images
```
multipart/form-data
- images: [file1.jpg, file2.png, ...]
```

## 🔧 Configuration

### Change Port
Edit `app.py` line at bottom:
```python
app.run(host='127.0.0.1', port=8000)  # Change 5000 to 8000
```

### Change Upload Folder
Edit `app.py`:
```python
UPLOAD_FOLDER = '/path/to/uploads'
```

### Customize Styling
Edit `templates/index.html` CSS section (lines ~15-400)

### Adjust Image Enhancement
Edit `image_enhancer.py` enhancement values:
```python
enhancer.enhance(1.15)  # Brightness (1.0 = no change)
enhancer.enhance(1.25)  # Contrast
enhancer.enhance(1.35)  # Saturation
enhancer.enhance(1.3)   # Sharpness
```

## 📱 Usage Workflow

### For Hosts (Web Interface)
1. Paste current description → Improve → Copy new text
2. Enter property details → Generate titles → Pick best one
3. Upload photos → Enhance → Download
4. Pay $20-50 → Implement changes → Increase bookings!

### For Developers (API)
1. Call `/api/improve-description` with listing text
2. Call `/api/generate-titles` with property details
3. Call `/api/enhance-images` with photos
4. Store results in database
5. Integrate with automation/outreach tools

## 🎨 Customization Ideas

### Add Features
- [ ] Database to store results
- [ ] Payment integration (Stripe)
- [ ] Email delivery of results
- [ ] Bulk upload via CSV
- [ ] A/B testing different prompts
- [ ] Analytics dashboard

### Improve Results
- [ ] Fine-tune Claude prompts for your market
- [ ] Add Airbnb-specific rules (character limits, keywords)
- [ ] Test different image enhancement settings
- [ ] Add title keyword optimization

### Scale It
- [ ] Deploy to Heroku/AWS/Digital Ocean
- [ ] Add database (PostgreSQL, MongoDB)
- [ ] Create admin dashboard
- [ ] Build host marketplace
- [ ] Add payment processing

## 🚨 Common Issues & Fixes

```bash
# Issue: Module not found
# Fix:
source venv/bin/activate
pip install -r requirements.txt

# Issue: Port 5000 in use
# Fix: Kill process or use different port
lsof -i :5000
kill -9 <PID>

# Issue: API key error
# Fix: Set environment variable
export ANTHROPIC_API_KEY="sk-ant-..."

# Issue: Image enhancement fails
# Fix: Check image format and file size
file image.jpg  # Should be JPEG/PNG
ls -lh image.jpg  # Should be < 10MB
```

## 📈 Pricing Strategy

**Option 1: Per-Listing Pricing**
- $20 - Text only (description + titles)
- $50 - Full package (text + images)
- $100 - Premium (includes Airbnb submission help)

**Option 2: Tiered Packages**
- Starter: 1 listing per month
- Pro: 10 listings per month
- Business: Unlimited + support

**Option 3: Property Manager Pricing**
- $500/month for up to 50 properties
- $1,000/month for 50-200 properties
- Custom pricing for 200+

## 📞 Next Steps After MVP

1. **User Testing** - Get feedback from 5-10 Airbnb hosts
2. **Payment Setup** - Add Stripe integration
3. **Marketing** - Create landing page, outreach emails
4. **Scale** - Deploy to production, add analytics
5. **Automate** - Implement bulk processing, auto-submit

## 🎓 Learning Resources

- Flask Docs: https://flask.palletsprojects.com/
- Anthropic API: https://docs.anthropic.com/
- OpenCV: https://docs.opencv.org/
- Airbnb Listing Tips: https://www.airbnb.com/help/article/14/what-makes-a-great-listing

---

**Ready to launch? Start with `bash start.sh` and begin processing listings!**
