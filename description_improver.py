import os
from anthropic import Anthropic

client = Anthropic()

def improve_listing_description(original_description: str) -> str:
    """
    Use Claude to improve Airbnb listing descriptions.
    Makes them more compelling, highlights amenities, increases coverage appeal.
    """
    prompt = f"""You are an expert Airbnb listing copywriter. Your job is to take an Airbnb listing description and make it MORE compelling while keeping all factual information intact.

IMPORTANT: Make the description MORE engaging, highlight unique selling points, and increase the perceived value. Use persuasive language that makes guests WANT to book. Mention comfort, convenience, location perks, and special features.

Also mention that photos have been professionally enhanced to showcase the property accurately.

Original Description:
{original_description}

Please provide an improved version that:
1. Opens with a compelling hook
2. Highlights the best features first
3. Uses sensory language (cozy, bright, spacious, etc.)
4. Mentions the professional photography
5. Ends with a call-to-action
6. Is 20-30% longer but still scannable

Return ONLY the improved description, no explanations."""

    message = client.messages.create(
        model="claude-opus-4-1",
        max_tokens=500,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    return message.content[0].text

def generate_title_suggestions(property_type: str, key_features: str, location: str) -> list:
    """
    Generate compelling Airbnb titles using Claude.
    """
    prompt = f"""You are an expert in writing compelling Airbnb listing titles. Generate 5 different title options for this property.

Property Type: {property_type}
Key Features: {key_features}
Location: {location}

Requirements for titles:
- Maximum 50 characters
- Include the most attractive feature
- Make guests want to click
- Be specific and unique
- Follow Airbnb best practices

Return ONLY the 5 titles, one per line, no numbering or explanations."""

    message = client.messages.create(
        model="claude-opus-4-1",
        max_tokens=300,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    titles = message.content[0].text.strip().split('\n')
    return [t.strip() for t in titles if t.strip()]

if __name__ == "__main__":
    # Test the description improvement
    test_desc = "Nice apartment in the city. Has 2 bedrooms and 1 bathroom. Close to subway."
    improved = improve_listing_description(test_desc)
    print("Original:", test_desc)
    print("\nImproved:", improved)
