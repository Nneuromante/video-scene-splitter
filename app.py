import streamlit as st
import cv2
import tempfile
import os
import shutil
from scenedetect import VideoManager, SceneManager, StatsManager
from scenedetect.detectors import ContentDetector
import zipfile
from io import BytesIO
from moviepy.editor import VideoFileClip

# Set page title
st.set_page_config(page_title="Video Scene Splitter", layout="wide")

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
    status_text.text("Analyzing video for scene changes...")
    progress_bar.progress(10)
    
    try:
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
        
        if not scene_list:
            st.warning("No scene changes detected. Try lowering the threshold.")
        else:
            progress_bar.progress(40)
            
            # Split video using MoviePy
            status_text.text("Splitting video into scenes...")
            
            scene_files = []
            # Load the video file
            video = VideoFileClip(temp_file_path)
            
            # Process each scene
            for i, scene in enumerate(scene_list):
                progress_value = 40 + int((i / len(scene_list)) * 50)
                progress_bar.progress(progress_value)
                
                start_time = scene[0].get_seconds()
                end_time = scene[1].get_seconds()
                
                # Extract the scene
                scene_clip = video.subclip(start_time, end_time)
                output_file = os.path.join(output_dir, f"scene_{i+1}.mp4")
                
                # Write the scene to a file
                scene_clip.write_videofile(output_file, codec='libx264', audio_codec='aac', 
                                         verbose=False, logger=None)
                scene_files.append(output_file)
                status_text.text(f"Processed scene {i+1} of {len(scene_list)}")
            
            # Close the video file
            video.close()
            
            # Complete progress
            progress_bar.progress(100)
            status_text.text("Processing complete!")
            
            # Display number of detected scenes
            st.success(f"Detected and split {len(scene_files)} scenes")
            
            # Display and allow downloading of scenes
            if scene_files:
                st.subheader("Scene Previews:")
                
                for i, scene_path in enumerate(scene_files):
                    with st.expander(f"Scene {i+1}"):
                        st.video(scene_path)
                        with open(scene_path, "rb") as file:
                            scene_data = file.read()
                            st.download_button(
                                label=f"Download Scene {i+1} ({os.path.getsize(scene_path) / (1024*1024):.1f} MB)",
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
            
    except Exception as e:
        st.error(f"Error during processing: {str(e)}")
        st.error("Full error: " + str(e))
    
    # Clean up temporary files
    shutil.rmtree(temp_dir)
else:
    st.info("Please upload a video file to begin.")

# Footer
st.markdown("---")
st.caption("Video Scene Splitter - Automatically split videos into scenes")
