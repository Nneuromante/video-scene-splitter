import streamlit as st
import cv2
import tempfile
import os
import subprocess
import shutil
from scenedetect import VideoManager, SceneManager, StatsManager
from scenedetect.detectors import ContentDetector
import zipfile
from io import BytesIO
import time

# Set page title
st.set_page_config(page_title="Video Scene Splitter", layout="wide")

# App title and description
st.title("Video Scene Splitter")
st.write("Upload a video to automatically split it into scenes.")

# File uploader
uploaded_file = st.file_uploader("Upload a video", type=["mp4", "mov", "avi"])

# Advanced options
with st.expander("Advanced Options"):
    threshold = st.slider("Scene detection sensitivity (lower = more scenes)", 20, 45, 27, 1)
    min_scene_duration = st.slider("Minimum scene duration (seconds)", 0.5, 10.0, 1.0, 0.5)
    use_keyframes = st.checkbox("Use keyframes for better accuracy", value=True)

if uploaded_file is not None:
    # Create a progress bar
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Save file temporarily
    status_text.text("Saving uploaded file...")
    temp_dir = tempfile.mkdtemp()
    temp_file_path = os.path.join(temp_dir, uploaded_file.name)
    
    with open(temp_file_path, "wb") as temp_file:
        temp_file.write(uploaded_file.read())
    
    # Create an output directory for scenes
    output_dir = os.path.join(temp_dir, "scenes")
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # Get video info using ffprobe
        status_text.text("Analyzing video...")
        progress_bar.progress(5)
        
        try:
            # Get video duration
            cmd = [
                "ffprobe", 
                "-v", "error", 
                "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", 
                temp_file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            total_duration = float(result.stdout.strip())
            
            # Get video codec info
            cmd = [
                "ffprobe", 
                "-v", "error", 
                "-select_streams", "v:0", 
                "-show_entries", "stream=codec_name", 
                "-of", "default=noprint_wrappers=1:nokey=1", 
                temp_file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            codec_name = result.stdout.strip()
            
            st.info(f"Video codec: {codec_name}, Duration: {int(total_duration//60)} min {int(total_duration%60)} sec")
        except Exception as e:
            st.warning(f"Couldn't get detailed video info: {str(e)}")
            total_duration = 0
        
        # Detect scenes
        status_text.text("Detecting scenes...")
        progress_bar.progress(10)
        
        # Initialize video manager and scene manager
        video_manager = VideoManager([temp_file_path])
        stats_manager = StatsManager()
        scene_manager = SceneManager(stats_manager)
        
        # Add ContentDetector (requires threshold)
        scene_manager.add_detector(ContentDetector(threshold=threshold))
        
        # Detect scenes
        base_timecode = video_manager.get_base_timecode()
        video_manager.set_downscale_factor()
        
        video_manager.start()
        scene_manager.detect_scenes(frame_source=video_manager)
        
        # Get scene list
        scene_list = scene_manager.get_scene_list(base_timecode)
        
        # Filter out very short scenes
        filtered_scene_list = []
        for scene in scene_list:
            start_time = scene[0].get_seconds()
            end_time = scene[1].get_seconds()
            duration = end_time - start_time
            if duration >= min_scene_duration:
                filtered_scene_list.append(scene)
        
        scene_list = filtered_scene_list
        
        if not scene_list:
            st.warning("No scene changes detected. Try lowering the threshold.")
        else:
            progress_bar.progress(40)
            
            # Use ffmpeg to split video
            status_text.text("Splitting video into scenes...")
            scene_files = []
            failed_scenes = []
            
            # Process each scene
            for i, scene in enumerate(scene_list):
                progress_value = 40 + int((i / len(scene_list)) * 50)
                progress_bar.progress(progress_value)
                
                start_time = scene[0].get_seconds()
                end_time = scene[1].get_seconds()
                duration = end_time - start_time
                
                output_file = os.path.join(output_dir, f"scene_{i+1}.mp4")
                
                # Use different ffmpeg approach based on codec and options
                if use_keyframes and codec_name in ["h264", "hevc", "mpeg4"]:
                    # Method 1: Fast copy (no re-encoding)
                    cmd = [
                        "ffmpeg",
                        "-i", temp_file_path, 
                        "-ss", str(start_time), 
                        "-to", str(end_time),
                        "-c:v", "copy", 
                        "-c:a", "copy", 
                        "-avoid_negative_ts", "1",
                        "-y",
                        output_file
                    ]
                else:
                    # Method 2: More accurate but slower (with re-encoding)
                    cmd = [
                        "ffmpeg",
                        "-ss", str(start_time),
                        "-i", temp_file_path, 
                        "-t", str(duration),
                        "-c:v", "libx264", 
                        "-c:a", "aac",
                        "-preset", "ultrafast",
                        "-y",
                        output_file
                    ]
                
                try:
                    subprocess.run(cmd, check=True, capture_output=True)
                    
                    # Verify the output file has actual content
                    file_size = os.path.getsize(output_file)
                    if file_size < 50000:  # Less than 50KB is suspicious
                        # Try again with re-encoding approach
                        cmd = [
                            "ffmpeg",
                            "-ss", str(start_time),
                            "-i", temp_file_path, 
                            "-t", str(duration),
                            "-c:v", "libx264", 
                            "-c:a", "aac",
                            "-preset", "ultrafast",
                            "-y",
                            output_file
                        ]
                        subprocess.run(cmd, check=True, capture_output=True)
                        file_size = os.path.getsize(output_file)
                        
                    if file_size > 50000:
                        scene_files.append(output_file)
                        status_text.text(f"Processed scene {i+1} of {len(scene_list)}")
                    else:
                        failed_scenes.append(i+1)
                        status_text.text(f"Warning: Scene {i+1} may be invalid")
                except subprocess.CalledProcessError as e:
                    failed_scenes.append(i+1)
                    st.error(f"Error processing scene {i+1}: {str(e)}")
            
            # Complete progress
            progress_bar.progress(100)
            status_text.text("Processing complete!")
            
            # Display number of detected scenes
            if failed_scenes:
                st.warning(f"Detected {len(scene_list)} scenes, but {len(failed_scenes)} failed to process properly.")
            else:
                st.success(f"Successfully processed {len(scene_files)} scenes")
            
            # Display and allow downloading of scenes
            if scene_files:
                st.subheader("Scene Previews:")
                
                for i, scene_path in enumerate(scene_files):
                    scene_number = scene_files.index(scene_path) + 1
                    with st.expander(f"Scene {scene_number}"):
                        st.video(scene_path)
                        with open(scene_path, "rb") as file:
                            scene_data = file.read()
                            file_size = len(scene_data) / (1024*1024)  # Size in MB
                            st.download_button(
                                label=f"Download Scene {scene_number} ({file_size:.1f} MB)",
                                data=scene_data,
                                file_name=f"scene_{scene_number}.mp4",
                                mime="video/mp4",
                                key=f"download_{i}"
                            )
                
                # Create a ZIP with all scenes
                st.subheader("Download all scenes:")
                zip_buffer = BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zip_file:
                    for i, scene_path in enumerate(scene_files):
                        scene_number = scene_files.index(scene_path) + 1
                        zip_file.write(scene_path, f"scene_{scene_number}.mp4")
                
                zip_size = len(zip_buffer.getvalue()) / (1024*1024)  # Size in MB
                st.download_button(
                    label=f"Download All Scenes as ZIP ({zip_size:.1f} MB)",
                    data=zip_buffer.getvalue(),
                    file_name="all_scenes.zip",
                    mime="application/zip"
                )
            
            # Display scene time information
            if scene_list:
                st.subheader("Scene Timecodes:")
                scene_data = []
                for i, scene in enumerate(scene_list):
                    start_time = scene[0].get_seconds()
                    end_time = scene[1].get_seconds()
                    scene_data.append({
                        "Scene": i+1,
                        "Start Time": f"{int(start_time//60):02d}:{int(start_time%60):02d}",
                        "End Time": f"{int(end_time//60):02d}:{int(end_time%60):02d}",
                        "Duration": f"{int((end_time-start_time)//60):02d}:{int((end_time-start_time)%60):02d}",
                        "Status": "Failed" if (i+1) in failed_scenes else "OK"
                    })
                
                st.table(scene_data)
    
    except Exception as e:
        st.error(f"Error during processing: {str(e)}")
    
    # Clean up temporary files
    shutil.rmtree(temp_dir)
else:
    st.info("Please upload a video file to begin.")

# Footer
st.markdown("---")
st.caption("Video Scene Splitter - Automatically split videos into scenes")
