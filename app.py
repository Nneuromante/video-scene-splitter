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

# Set page title
st.set_page_config(page_title="Video Scene Splitter", layout="wide")

# Check if ffmpeg is available
try:
    subprocess.run(['ffmpeg', '-version'], check=True, capture_output=True)
    ffmpeg_available = True
except (subprocess.SubprocessError, FileNotFoundError):
    ffmpeg_available = False
    st.warning("⚠️ FFmpeg is not available. Video processing may not work correctly.")

# App title and description
st.title("Video Scene Splitter")
st.write("Upload a video to automatically split it into scenes.")

# File uploader
uploaded_file = st.file_uploader("Upload a video", type=["mp4", "mov", "avi"])

# Sensitivity slider
threshold = st.slider("Scene detection sensitivity (lower = more scenes)", 25, 45, 30, 1)

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
    progress_bar.progress(40)
    
    # Use ffmpeg to split video
    status_text.text("Splitting video into scenes...")
    scene_files = []
    
    # Get video info
    cap = cv2.VideoCapture(temp_file_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 25  # Default fallback if fps can't be determined
    cap.release()
    
    # Process each scene
    for i, scene in enumerate(scene_list):
        progress_value = 40 + int((i / len(scene_list)) * 50)
        progress_bar.progress(progress_value)
        
        start_time = scene[0].get_seconds()
        end_time = scene[1].get_seconds()
        duration = end_time - start_time
        
        output_file = os.path.join(output_dir, f"scene_{i+1}.mp4")
        
        # Use ffmpeg to extract the scene
        cmd = [
            "ffmpeg",
            "-i", temp_file_path, 
            "-ss", str(start_time), 
            "-t", str(duration),
            "-c:v", "copy", 
            "-c:a", "copy", 
            output_file
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            scene_files.append(output_file)
            status_text.text(f"Processed scene {i+1} of {len(scene_list)}")
        except subprocess.CalledProcessError as e:
            st.error(f"Error processing scene {i+1}: {str(e)}")
            status_text.text(f"Error processing scene {i+1}")
    
    # Complete progress
    progress_bar.progress(100)
    status_text.text("Processing complete!")
    
    # Display number of detected scenes
    st.success(f"Detected {len(scene_files)} scenes")
    
    # Display and allow downloading of scenes
    if scene_files:
        st.subheader("Download individual scenes:")
        
        # Create columns for better layout
        cols = st.columns(3)
        for i, scene_path in enumerate(scene_files):
            col_idx = i % 3
            with cols[col_idx]:
                with open(scene_path, "rb") as file:
                    scene_data = file.read()
                    st.download_button(
                        label=f"Scene {i+1} ({os.path.getsize(scene_path) / (1024*1024):.1f} MB)",
                        data=scene_data,
                        file_name=f"scene_{i+1}.mp4",
                        mime="video/mp4",
                        key=f"download_{i}"
                    )
        
        # Create a ZIP with all scenes
        st.subheader("Download all scenes:")
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            for i, scene_path in enumerate(scene_files):
                zip_file.write(scene_path, f"scene_{i+1}.mp4")
        
        zip_size = len(zip_buffer.getvalue()) / (1024*1024)  # Size in MB
        st.download_button(
            label=f"Download All Scenes as ZIP ({zip_size:.1f} MB)",
            data=zip_buffer.getvalue(),
            file_name="all_scenes.zip",
            mime="application/zip"
        )
    
    # Preview scenes
    if scene_files:
        st.subheader("Scene Previews:")
        
        for i, scene_path in enumerate(scene_files):
            with st.expander(f"Scene {i+1}"):
                st.video(scene_path)
    
    # Clean up temporary files
    shutil.rmtree(temp_dir)
else:
    st.info("Please upload a video file to begin.")

# Footer
st.markdown("---")
st.caption("Video Scene Splitter - Automatically split videos into scenes")
