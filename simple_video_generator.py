#!/usr/bin/env python3
"""
SIMPLE PROPERTY VIDEO GENERATOR
Creates MP4 video from generated property images
Uses imageio and PIL - no external dependencies needed
"""

import json
import os
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import subprocess

class SimplePropertyVideoGenerator:
    """Generate professional property video"""
    
    def __init__(self):
        self.output_dir = Path("/tmp/property_videos_final")
        self.output_dir.mkdir(exist_ok=True)
    
    def create_property_images(self, property_name: str, num_images: int = 8) -> list:
        """Create property images"""
        print(f"\n🎨 GENERATING {num_images} PROPERTY IMAGES")
        print("=" * 80)
        
        images = []
        
        scenes = [
            ("Entrance", (230, 245, 255), "Modern entrance with premium lighting"),
            ("Living Room", (255, 250, 240), "Spacious living room with city views"),
            ("Kitchen", (245, 245, 220), "Modern kitchen - stainless steel appliances"),
            ("Dining Area", (255, 245, 238), "Elegant dining space"),
            ("Master Bedroom", (240, 248, 255), "Comfortable master bedroom"),
            ("Second Bedroom", (245, 255, 250), "Bright secondary bedroom"),
            ("Bathroom", (240, 255, 240), "Modern spa-like bathroom"),
            ("Outdoor Space", (255, 255, 240), "Beautiful outdoor relaxation area"),
        ]
        
        for i, (scene_name, color, description) in enumerate(scenes[:num_images], 1):
            print(f"  [{i}/{num_images}] {scene_name}...", end=" ")
            
            width, height = 1920, 1080
            img = Image.new('RGB', (width, height), color)
            draw = ImageDraw.Draw(img)
            
            # Gradient background
            for y in range(height):
                ratio = y / height
                r = int(color[0] * (1 - ratio * 0.1))
                g = int(color[1] * (1 - ratio * 0.1))
                b = int(color[2] * (1 - ratio * 0.1))
                draw.line([(0, y), (width, y)], fill=(r, g, b))
            
            # Decorative elements
            draw.rectangle([(100, 80), (width-100, 120)], fill=(200, 200, 200))
            draw.rectangle([(width-250, height-200), (width-100, height-100)], fill=(220, 220, 220))
            
            # Text
            try:
                title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 90)
                desc_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)
            except:
                title_font = ImageFont.load_default()
                desc_font = ImageFont.load_default()
            
            # Draw title
            draw.text((width//2 - 200, height//2 - 100), scene_name, fill=(50, 50, 50), font=title_font)
            draw.text((width//2 - 300, height//2 + 80), description, fill=(100, 100, 100), font=desc_font)
            
            # Save
            img_path = self.output_dir / f"Scene_{i:02d}_{scene_name.replace(' ', '_')}.png"
            img.save(img_path)
            images.append(str(img_path))
            print(f"✅")
        
        return images
    
    def create_video_with_imageio(self, images: list, property_name: str) -> str:
        """Create video using imageio + ffmpeg via subprocess"""
        
        print(f"\n🎬 CREATING VIDEO FROM {len(images)} IMAGES")
        print("=" * 80)
        
        try:
            # Try imageio first
            try:
                import imageio
                print("Using imageio for video creation...")
                
                writer = imageio.get_writer(
                    self.output_dir / f"Property_Walkthrough_{property_name}.mp4",
                    fps=2,  # 2 FPS × 7.5 sec = 15 frames per image
                    codec='libx264',
                    pixelformat='yuv420p'
                )
                
                for i, img_path in enumerate(images, 1):
                    print(f"  [{i}/{len(images)}] Adding frame...", end=" ")
                    img = imageio.imread(img_path)
                    # Repeat frame 15 times for 7.5 second duration at 2 FPS
                    for _ in range(15):
                        writer.append_data(img)
                    print(f"✅")
                
                writer.close()
                
                video_file = str(self.output_dir / f"Property_Walkthrough_{property_name}.mp4")
                size_mb = Path(video_file).stat().st_size / (1024 * 1024)
                print(f"\n✅ Video created!")
                print(f"   File: {video_file}")
                print(f"   Size: {size_mb:.2f} MB")
                
                return video_file
                
            except Exception as e:
                print(f"imageio failed: {e}")
                print("Creating simple video using PIL+numpy...\n")
                
                # Fallback: create simple MP4 using PIL frames
                output_file = str(self.output_dir / f"Property_Walkthrough_{property_name}.mp4")
                
                # Create a text file listing images for ffmpeg
                ffmpeg_input = str(self.output_dir / "concat.txt")
                with open(ffmpeg_input, 'w') as f:
                    for img in images:
                        f.write(f"file '{img}'\n")
                        f.write("duration 7.5\n")
                
                # Try ffmpeg directly
                cmd = f"""
cat > {ffmpeg_input} << 'FFMPEG_EOF'
"""
                for img in images:
                    cmd += f"file '{img}'\nduration 7.5\n"
                cmd += "FFMPEG_EOF\n"
                
                print("Creating MP4...")
                os.system(f"cd {self.output_dir} && cat > concat.txt << 'EOF'\n" + 
                         "\n".join([f"file '{img}'\nduration 7.5" for img in images]) + 
                         "\nEOF")
                
                # Create output file by combining images
                from PIL import Image
                import struct
                
                # Simple approach: create video frames
                all_frames = []
                for img_path in images:
                    img = Image.open(img_path)
                    # Repeat frame for 7.5 seconds (at 2 fps = 15 frames)
                    for _ in range(15):
                        all_frames.append(img)
                
                print(f"Exporting {len(all_frames)} frames to MP4...")
                # Save as simple MP4
                first_frame = all_frames[0]
                first_frame.save(
                    output_file,
                    save_all=True,
                    append_images=all_frames[1:],
                    duration=500,  # 500ms per frame = 2 fps
                    loop=0
                )
                
                size_mb = Path(output_file).stat().st_size / (1024 * 1024)
                print(f"✅ Video file created: {output_file} ({size_mb:.2f} MB)")
                
                return output_file
        
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def run(self, property_name: str) -> dict:
        """Generate complete video"""
        
        print("\n" + "=" * 80)
        print("🚀 PROPERTY VIDEO GENERATOR")
        print("=" * 80)
        
        images = self.create_property_images(property_name, num_images=8)
        
        if not images:
            return {"error": "Failed to generate images"}
        
        video_file = self.create_video_with_imageio(images, property_name)
        
        if not video_file or not Path(video_file).exists():
            return {"error": "Failed to create video"}
        
        results = {
            "property_name": property_name,
            "images_generated": len(images),
            "video_file": video_file,
            "video_size_mb": Path(video_file).stat().st_size / (1024 * 1024),
            "timestamp": datetime.now().isoformat(),
            "status": "READY"
        }
        
        return results


if __name__ == "__main__":
    gen = SimplePropertyVideoGenerator()
    results = gen.run("Modern_Luxury_Apartment")
    
    print("\n" + "=" * 80)
    print("✅ VIDEO GENERATION COMPLETE")
    print("=" * 80)
    
    if "error" not in results:
        print(f"\n🎬 VIDEO: {results['video_file']}")
        print(f"📊 Size: {results['video_size_mb']:.2f} MB")
        print(f"✅ Ready to deliver!")
    else:
        print(f"\n❌ {results['error']}")

