#!/usr/bin/env python3
"""
Quality Testing Tool for Image Enhancement Pipeline
Tests the advanced image enhancer with sample photos
and provides quality metrics and before/after comparisons.
"""

import os
import cv2
import numpy as np
from PIL import Image
from image_enhancer import AirbnbImageEnhancer
from pathlib import Path
import json
from datetime import datetime


class ImageQualityTester:
    """Test and measure image enhancement quality"""
    
    def __init__(self):
        self.enhancer = AirbnbImageEnhancer()
        self.results = []
    
    def calculate_image_metrics(self, image_path: str) -> dict:
        """Calculate quality metrics for an image"""
        img = cv2.imread(image_path)
        if img is None:
            return {}
        
        # Convert to different color spaces for analysis
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # Calculate metrics
        metrics = {
            'brightness': float(np.mean(lab[:, :, 0])),  # Average L in LAB
            'contrast': float(np.std(gray)),  # Contrast from standard deviation
            'saturation': float(np.mean(hsv[:, :, 1])),  # Average saturation
            'sharpness': self._calculate_sharpness(gray),
            'noise': self._estimate_noise(gray),
            'color_temp': self._estimate_color_temperature(img),
        }
        
        return metrics
    
    def _calculate_sharpness(self, gray_image: np.ndarray) -> float:
        """Calculate image sharpness using Laplacian variance"""
        laplacian = cv2.Laplacian(gray_image, cv2.CV_64F)
        sharpness = np.var(laplacian)
        return float(sharpness)
    
    def _estimate_noise(self, gray_image: np.ndarray) -> float:
        """Estimate noise level using Laplacian"""
        kernel = np.array([[-1, -1, -1],
                          [-1,  8, -1],
                          [-1, -1, -1]])
        noise_map = cv2.filter2D(gray_image, -1, kernel)
        noise_level = np.mean(np.abs(noise_map))
        return float(noise_level)
    
    def _estimate_color_temperature(self, image: np.ndarray) -> float:
        """Estimate color temperature (0=cool/blue, 1=warm/yellow)"""
        b, g, r = cv2.split(image)
        avg_r = np.mean(r)
        avg_b = np.mean(b)
        
        # Warm = high R/B ratio, Cool = low R/B ratio
        color_temp = avg_r / (avg_b + 1)  # +1 to avoid division by zero
        return float(color_temp)
    
    def create_test_image(self, output_path: str = "test_image.jpg"):
        """Create a synthetic test image with common problems"""
        # Create a test image simulating a dark, poorly-lit room
        img = np.zeros((600, 800, 3), dtype=np.uint8)
        
        # Background (wall)
        img[:, :] = (60, 70, 80)  # Dark, blue-tinted wall
        
        # Furniture (brown)
        cv2.rectangle(img, (50, 300), (300, 550), (80, 100, 120), -1)
        
        # Window (white)
        cv2.rectangle(img, (600, 50), (750, 200), (200, 200, 200), -1)
        
        # Add some noise
        noise = np.random.normal(0, 15, img.shape).astype(np.uint8)
        img = cv2.add(img, noise)
        
        # Tilt the image slightly
        h, w = img.shape[:2]
        center = (w // 2, h // 2)
        angle = 2  # 2 degree tilt
        rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        img = cv2.warpAffine(img, rotation_matrix, (w, h))
        
        # Save
        cv2.imwrite(output_path, img)
        print(f"✓ Created test image: {output_path}")
        return output_path
    
    def compare_images(self, original_path: str, enhanced_path: str) -> dict:
        """Compare metrics between original and enhanced image"""
        original_metrics = self.calculate_image_metrics(original_path)
        enhanced_metrics = self.calculate_image_metrics(enhanced_path)
        
        comparison = {
            'timestamp': datetime.now().isoformat(),
            'original_file': os.path.basename(original_path),
            'enhanced_file': os.path.basename(enhanced_path),
            'metrics': {
                'brightness': {
                    'before': original_metrics.get('brightness', 0),
                    'after': enhanced_metrics.get('brightness', 0),
                    'improvement': enhanced_metrics.get('brightness', 0) - original_metrics.get('brightness', 0),
                    'target': 'Higher is better (85-90 optimal)'
                },
                'contrast': {
                    'before': original_metrics.get('contrast', 0),
                    'after': enhanced_metrics.get('contrast', 0),
                    'improvement': enhanced_metrics.get('contrast', 0) - original_metrics.get('contrast', 0),
                    'target': 'Higher is better (25-35 optimal)'
                },
                'saturation': {
                    'before': original_metrics.get('saturation', 0),
                    'after': enhanced_metrics.get('saturation', 0),
                    'improvement': enhanced_metrics.get('saturation', 0) - original_metrics.get('saturation', 0),
                    'target': 'Higher is better (120-140 optimal)'
                },
                'sharpness': {
                    'before': original_metrics.get('sharpness', 0),
                    'after': enhanced_metrics.get('sharpness', 0),
                    'improvement': enhanced_metrics.get('sharpness', 0) - original_metrics.get('sharpness', 0),
                    'target': 'Higher is better (100+ optimal)'
                },
                'noise': {
                    'before': original_metrics.get('noise', 0),
                    'after': enhanced_metrics.get('noise', 0),
                    'improvement': -(enhanced_metrics.get('noise', 0) - original_metrics.get('noise', 0)),
                    'target': 'Lower is better (50-80 optimal)'
                },
                'color_temperature': {
                    'before': original_metrics.get('color_temp', 0),
                    'after': enhanced_metrics.get('color_temp', 0),
                    'improvement': enhanced_metrics.get('color_temp', 0) - original_metrics.get('color_temp', 0),
                    'target': 'Closer to 1.0 is better (neutral)'
                }
            }
        }
        
        return comparison
    
    def quality_grade(self, comparison: dict) -> dict:
        """Grade the enhancement quality"""
        metrics = comparison['metrics']
        grades = {}
        
        # Brightness grade
        brightness_after = metrics['brightness']['after']
        if brightness_after >= 85:
            grades['brightness'] = 'A'
        elif brightness_after >= 75:
            grades['brightness'] = 'B'
        else:
            grades['brightness'] = 'C'
        
        # Contrast grade
        contrast_after = metrics['contrast']['after']
        if contrast_after >= 25:
            grades['contrast'] = 'A'
        elif contrast_after >= 15:
            grades['contrast'] = 'B'
        else:
            grades['contrast'] = 'C'
        
        # Sharpness grade
        sharpness_after = metrics['sharpness']['after']
        if sharpness_after >= 100:
            grades['sharpness'] = 'A'
        elif sharpness_after >= 50:
            grades['sharpness'] = 'B'
        else:
            grades['sharpness'] = 'C'
        
        # Noise grade
        noise_after = metrics['noise']['after']
        if noise_after <= 80:
            grades['noise'] = 'A'
        elif noise_after <= 100:
            grades['noise'] = 'B'
        else:
            grades['noise'] = 'C'
        
        # Calculate overall grade
        grade_values = {'A': 4, 'B': 3, 'C': 2}
        avg_grade = sum(grade_values[g] for g in grades.values()) / len(grades)
        
        if avg_grade >= 3.7:
            overall = 'A'
        elif avg_grade >= 3:
            overall = 'B'
        else:
            overall = 'C'
        
        grades['overall'] = overall
        
        return grades
    
    def run_test(self, test_image_path: str = None) -> dict:
        """Run a complete quality test"""
        print("\n" + "="*60)
        print("🎨 IMAGE ENHANCEMENT QUALITY TEST")
        print("="*60)
        
        # Create or use provided test image
        if test_image_path is None or not os.path.exists(test_image_path):
            print("\n📸 Creating synthetic test image...")
            test_image_path = self.create_test_image("test_image_before.jpg")
        else:
            print(f"\n📸 Using provided test image: {test_image_path}")
        
        # Enhance the image
        print("\n🔄 Enhancing image...")
        enhanced_path = "test_image_after.jpg"
        self.enhancer.enhance_full_pipeline(test_image_path, enhanced_path)
        
        # Compare
        print("\n📊 Calculating metrics...")
        comparison = self.compare_images(test_image_path, enhanced_path)
        grades = self.quality_grade(comparison)
        
        # Display results
        print("\n" + "="*60)
        print("📈 QUALITY IMPROVEMENT REPORT")
        print("="*60)
        
        metrics = comparison['metrics']
        
        print(f"\n🔆 Brightness")
        print(f"   Before: {metrics['brightness']['before']:.1f}")
        print(f"   After:  {metrics['brightness']['after']:.1f}")
        print(f"   Change: +{metrics['brightness']['improvement']:.1f}")
        print(f"   Grade:  {grades['brightness']}")
        
        print(f"\n📊 Contrast")
        print(f"   Before: {metrics['contrast']['before']:.1f}")
        print(f"   After:  {metrics['contrast']['after']:.1f}")
        print(f"   Change: +{metrics['contrast']['improvement']:.1f}")
        print(f"   Grade:  {grades['contrast']}")
        
        print(f"\n✨ Sharpness")
        print(f"   Before: {metrics['sharpness']['before']:.1f}")
        print(f"   After:  {metrics['sharpness']['after']:.1f}")
        print(f"   Change: +{metrics['sharpness']['improvement']:.1f}")
        print(f"   Grade:  {grades['sharpness']}")
        
        print(f"\n🧹 Noise Reduction")
        print(f"   Before: {metrics['noise']['before']:.1f}")
        print(f"   After:  {metrics['noise']['after']:.1f}")
        print(f"   Change: {metrics['noise']['improvement']:.1f}")
        print(f"   Grade:  {grades['noise']}")
        
        print(f"\n🎨 Color Balance")
        print(f"   Before: {metrics['color_temperature']['before']:.2f} (warm)")
        print(f"   After:  {metrics['color_temperature']['after']:.2f} (neutral)")
        print(f"   Change: {metrics['color_temperature']['improvement']:.2f}")
        
        print("\n" + "="*60)
        print(f"📋 OVERALL GRADE: {grades['overall']}")
        print("="*60)
        
        if grades['overall'] == 'A':
            print("✅ Excellent enhancement quality - Ready for production!")
        elif grades['overall'] == 'B':
            print("✅ Good enhancement quality - Suitable for most listings")
        else:
            print("⚠️  Acceptable quality - May need fine-tuning")
        
        print(f"\n📂 Test images saved:")
        print(f"   Before: {test_image_path}")
        print(f"   After:  {enhanced_path}")
        print(f"\n💡 Tip: Compare the images to see the improvements!")
        
        return {
            'comparison': comparison,
            'grades': grades,
            'original_path': test_image_path,
            'enhanced_path': enhanced_path
        }


if __name__ == "__main__":
    print("🎨 Image Enhancement Quality Testing Tool")
    
    tester = ImageQualityTester()
    
    # Run test
    results = tester.run_test()
    
    # Save results
    with open('quality_test_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print("\n✅ Test complete! Results saved to: quality_test_results.json")
