"""
Test script for Model Info functionality.
Tests the complete flow: scan -> get model info -> render HTML
"""

import sys
import os
import json

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import our modules
from cb_api import CivitAIClient, scan_installed_civitai_models, make_installed_cards_html

def test_api():
    """Test CivitAI API directly."""
    print("\n" + "="*70)
    print("TEST 1: CivitAI API - Get Model Info")
    print("="*70 + "\n")
    
    api = CivitAIClient()
    
    # Test with model ID 2326387
    test_model_id = 2326387
    
    print(f"Fetching model {test_model_id}...")
    model_data = api.get_model(test_model_id)
    
    if not model_data:
        print("❌ ERROR: Could not fetch model data")
        return None
    
    print(f"✓ Model Name: {model_data.get('name', 'Unknown')}")
    print(f"✓ Creator: {model_data.get('creator', {}).get('username', 'Unknown')}")
    print(f"✓ Type: {model_data.get('type', 'Unknown')}")
    
    versions = model_data.get('modelVersions', [])
    print(f"✓ Total Versions: {len(versions)}")
    
    if versions:
        v = versions[0]
        version_id = v.get('id', '')
        version_name = v.get('name', '')
        images = v.get('images', [])
        
        print(f"\n  Version: {version_name} (ID: {version_id})")
        print(f"  Images from models API: {len(images)}")
        
        # Check for meta in search results
        meta_count = sum(1 for img in images if img.get('meta'))
        print(f"  Images with meta: {meta_count}/{len(images)}")
        
        # Now fetch version details
        print(f"\n  Fetching version details from /model-versions/{version_id}...")
        version_data = api.get_model_version(version_id)
        
        if version_data:
            version_images = version_data.get('images', [])
            print(f"  ✓ Images from version API: {len(version_images)}")
            
            # Check for meta in version images
            v_meta_count = sum(1 for img in version_images if img.get('meta'))
            print(f"  ✓ Images with meta: {v_meta_count}/{len(version_images)}")
            
            # Print details for first 3 images
            for i, img in enumerate(version_images[:3]):
                img_id = img.get('id', 'N/A')
                img_meta = img.get('meta')
                
                print(f"\n    Image {i+1} (ID: {img_id}):")
                if img_meta:
                    if isinstance(img_meta, dict):
                        print(f"      Type: dict")
                        print(f"      Keys: {list(img_meta.keys())[:8]}")
                        prompt = img_meta.get('prompt', '')
                        if prompt:
                            print(f"      ✓ Has prompt ({len(prompt)} chars)")
                            print(f"      First 80 chars: {prompt[:80]}...")
                        else:
                            print(f"      ✗ No prompt in meta")
                    elif isinstance(img_meta, str):
                        print(f"      Type: string ({len(img_meta)} chars)")
                        if img_meta.strip().startswith('{'):
                            print(f"      Looks like JSON")
                            try:
                                parsed = json.loads(img_meta)
                                prompt = parsed.get('prompt', '')
                                if prompt:
                                    print(f"      ✓ Parsed - Has prompt ({len(prompt)} chars)")
                                else:
                                    print(f"      ✗ Parsed - No prompt")
                            except:
                                print(f"      ✗ Failed to parse JSON")
                        else:
                            print(f"      Does not look like JSON")
                else:
                    print(f"      ✗ No meta data")
            
            return version_images
        else:
            print("  ❌ ERROR: Could not fetch version data")
            return None
    
    return None


def test_installed_scan():
    """Test scanning installed models."""
    print("\n" + "="*70)
    print("TEST 2: Scan Installed Models")
    print("="*70 + "\n")
    
    installed_models, folders = scan_installed_civitai_models()
    
    print(f"Found {len(installed_models)} installed models")
    print(f"Found {len(folders)} folders\n")
    
    # Check for duplicates
    paths = [m['path'] for m in installed_models]
    unique_paths = set(paths)
    
    if len(paths) != len(unique_paths):
        print(f"⚠ WARNING: Found {len(paths) - len(unique_paths)} duplicate(s)!")
    else:
        print("✓ No duplicates found")
    
    # Show models with CivitAI ID
    models_with_id = [m for m in installed_models if m.get('civitai_model_id')]
    print(f"\nModels with CivitAI ID: {len(models_with_id)}/{len(installed_models)}")
    
    if models_with_id:
        print("\nFirst 5 models with CivitAI ID:")
        for i, m in enumerate(models_with_id[:5]):
            print(f"  {i+1}. {m['filename']}")
            print(f"     ID: {m['civitai_model_id']}")
            print(f"     Name: {m['civitai_model_name']}")
            print(f"     Folder: {m['folder']}")
    
    return installed_models


def test_model_info_html(model_id):
    """Test get_model_info_html function."""
    print("\n" + "="*70)
    print(f"TEST 3: Generate Model Info HTML (Model ID: {model_id})")
    print("="*70 + "\n")
    
    # Import the function
    from cb_main import get_model_info_html
    
    html = get_model_info_html(str(model_id))
    
    # Check HTML content
    if 'civ-error' in html:
        print(f"❌ ERROR in HTML: {html}")
        return False
    
    # Count images
    img_count = html.count('civ-sample-item-list')
    print(f"✓ Generated HTML with {img_count} images")
    
    # Check for prompts
    prompt_count = html.count('civ-prompt-text')
    print(f"✓ Found {prompt_count} prompt blocks")
    
    # Check for "No prompt data" messages
    no_prompt_count = html.count('No prompt data')
    print(f"  - With 'No prompt data': {no_prompt_count}")
    print(f"  - With actual prompt: {prompt_count - no_prompt_count}")
    
    # Show a sample
    if prompt_count > 0 and no_prompt_count < prompt_count:
        print("\n✓ SUCCESS: Some images have prompt data!")
        # Find and print first prompt
        start = html.find('<div class="civ-prompt-text">')
        if start != -1:
            end = html.find('</div>', start)
            prompt_text = html[start+28:end]
            if prompt_text and 'No prompt data' not in prompt_text:
                print(f"\n  Sample prompt (first 100 chars):")
                print(f"  {prompt_text[:100]}...")
    else:
        print("\n❌ WARNING: All images show 'No prompt data'")
    
    return True


def test_installed_model_html(installed_models):
    """Test make_installed_cards_html function."""
    print("\n" + "="*70)
    print("TEST 4: Generate Installed Models HTML")
    print("="*70 + "\n")
    
    html = make_installed_cards_html(installed_models)
    
    # Count cards
    card_count = html.count('civ-installed-card')
    print(f"✓ Generated HTML with {card_count} model cards")
    
    # Check for CivitAI badges
    badge_count = html.count('civ-card-civitai-badge')
    no_badge_count = html.count('civ-card-no-civitai')
    print(f"  - With CivitAI badge: {badge_count}")
    print(f"  - Without CivitAI badge: {no_badge_count}")
    
    return html


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("CIVITAI BROWSER - MODEL INFO TEST SUITE")
    print("="*70)
    
    # Test 1: API
    version_images = test_api()
    
    # Test 2: Scan installed
    installed_models = test_installed_scan()
    
    # Test 3: Model info HTML
    if version_images:
        test_model_info_html(2326387)
    
    # Test 4: Installed model HTML
    if installed_models:
        test_installed_model_html(installed_models)
    
    print("\n" + "="*70)
    print("TEST SUITE COMPLETE")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
