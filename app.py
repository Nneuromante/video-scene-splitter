import streamlit as st
import cv2
import tempfile
import os
import subprocess
import shutil
from scenedetect import VideoManager, SceneManager, StatsManager
from scenedetect.detectors import ContentDetector
from scenedetect.scene_manager import save_images
import zipfile
from io import BytesIO

st.title("Video Scene Splitter")
uploaded_file = st.file_uploader("Upload a video", type=["mp4", "mov", "avi"])

threshold = st.slider("Scene detection sensitivity", 25, 45, 30, 1)

if uploaded_file is not None:
    # Save file temporarily
    temp_dir = tempfile.mkdtemp()
    temp_file_path = os.path.join(temp_dir, uploaded_file.name)
    
    with open(temp_file_path, "wb") as temp_file:
        temp_file.write(uploaded_file.read())
    
    # Create an output directory for scenes
    output_dir = os.path.join(temp_dir, "scenes")
    os.makedirs(output_dir, exist_ok=True)
    
    # Detect scenes
    with st.spinner("Detecting scenes..."):
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
        
        # Use ffmpeg to split video
        scene_files = []
        for i, scene in enumerate(scene_list):
            start_time = scene[0].get_seconds()
            end_time = scene[1].get_seconds()
            duration = end_time - start_time
            
            output_file = os.path.join(output_dir, f"scene_{i+1}.mp4")
            
            # Use ffmpeg to extract the scene
            cmd = [
                "ffmpeg", "-i", temp_file_path, 
                "-ss", str(start_time), "-t", str(duration),
                "-c:v", "copy", "-c:a", "copy", output_file
            ]
            
            try:
                subprocess.run(cmd, check=True)
                scene_files.append(output_file)
            except subprocess.CalledProcessError as e:
                st.error(f"Error processing scene {i+1}: {e}")
    
    # Display number of detected scenes
    st.success(f"Detected {len(scene_files)} scenes")
    
    # Display and allow downloading of scenes
    for i, scene_path in enumerate(scene_files):
        st.subheader(f"Scene {i+1}")
        st.video(scene_path)
        
        with open(scene_path, "rb") as file:
            scene_data = file.read()
            st.download_button(
                label=f"Download Scene {i+1}",
                data=scene_data,
                file_name=f"scene_{i+1}.mp4",
                mime="video/mp4"
            )
    
    # Create a ZIP with all scenes
    if scene_files:
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            for i, scene_path in enumerate(scene_files):
                zip_file.write(scene_path, f"scene_{i+1}.mp4")
        
        st.download_button(
            label="Download All Scenes (ZIP)",
            data=zip_buffer.getvalue(),
            file_name="all_scenes.zip",
            mime="application/zip"
        )
    
    # Clean up temporary files
    shutil.rmtree(temp_dir)
