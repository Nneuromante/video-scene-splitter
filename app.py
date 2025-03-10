import streamlit as st
import cv2
import tempfile
import os
import subprocess
import shutil
from scenedetect import detect, ContentDetector
import zipfile
from io import BytesIO
import uuid

# Set page title
st.set_page_config(page_title="Video Scene Splitter", layout="wide")

# App title and description
st.title("Video Scene Splitter")
st.write("Upload videos to automatically split them into scenes.")

# Initialize session state for storing videos
if 'uploaded_videos' not in st.session_state:
    st.session_state.uploaded_videos = []
    st.session_state.video_names = []
    st.session_state.processing = False

# File uploader with immediate display of uploaded files
uploaded_files = st.file_uploader("Upload videos", 
                              type=["mp4", "mov", "avi", "mkv"], 
                              accept_multiple_files=True)

# Add newly uploaded files to session state
if uploaded_files:
    for file in uploaded_files:
        # Check if file is not already in the list
        if file.name not in st.session_state.video_names:
            st.session_state.uploaded_videos.append(file)
            st.session_state.video_names.append(file.name)

# Display list of uploaded files with X to remove
if st.session_state.uploaded_videos:
    st.write("Uploaded Videos:")
    
    for i, video_file in enumerate(st.session_state.uploaded_videos):
        col1, col2 = st.columns([20, 1])
        with col1:
            file_size_mb = len(video_file.getvalue()) / (1024 * 1024)
            st.text(f"{video_file.name}  {file_size_mb:.1f}MB")
        with col2:
            if st.button("❌", key=f"x_{i}", help="Remove this video"):
                st.session_state.uploaded_videos.pop(i)
                st.session_state.video_names.pop(i)
                st.rerun()

# Advanced options
with st.expander("Advanced Options"):
    threshold = st.slider("Scene detection sensitivity", 15, 30, 27, 1, 
                         help="Lower values create more scenes (more sensitive)")
    include_audio = st.checkbox("Include audio in output", value=False)  # Default is now False
    output_format = st.selectbox("Output format", ["mp4", "gif"], index=0)

# Process button (only enabled if videos are uploaded and not currently processing)
process_button = st.button("Process Videos", 
                          disabled=len(st.session_state.uploaded_videos) == 0 or st.session_state.processing,
                          type="primary")

if process_button:
    st.session_state.processing = True
    
    # Create progress indicators
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Create temp directory for processing
    temp_dir = tempfile.mkdtemp()
    output_dir = os.path.join(temp_dir, "scenes")
    os.makedirs(output_dir, exist_ok=True)
    
    all_scene_files = []
    total_videos = len(st.session_state.uploaded_videos)
    
    # Process each video
    for video_idx, video_file in enumerate(st.session_state.uploaded_videos):
        # Calculate base progress percentage for this video (0-1 scale)
        video_progress_base = video_idx / total_videos
        status_text.text(f"Processing video {video_idx+1}/{total_videos}: {video_file.name}")
        
        # Save file temporarily
        temp_file_path = os.path.join(temp_dir, video_file.name)
        with open(temp_file_path, "wb") as temp_file:
            temp_file.write(video_file.getbuffer())
        
        try:
            # Detect scenes
            status_text.text(f"Detecting scenes in {video_file.name}...")
            progress_bar.progress(video_progress_base + 0.05/total_videos)  # Small increment
            
            scenes = detect(temp_file_path, ContentDetector(threshold=threshold))
            
            if not scenes:
                st.warning(f"No scene changes detected in {video_file.name}. Try lowering the threshold value.")
                progress_bar.progress(video_progress_base + 0.9/total_videos)  # Move almost to the next video
            else:
                progress_bar.progress(video_progress_base + 0.1/total_videos)  # 10% progress for this video
                
                # Use ffmpeg to split video
                status_text.text(f"Splitting {video_file.name} into scenes...")
                video_scene_files = []
                base_name = os.path.splitext(os.path.basename(temp_file_path))[0]
                
                # Process each scene
                for idx, (start, end) in enumerate(scenes, start=1):
                    # Calculate the progress within this video's portion
                    scene_portion = 0.8 / total_videos  # 80% of this video's portion for scene processing
                    scene_progress = (idx / len(scenes)) * scene_portion
                    current_progress = min(video_progress_base + 0.1/total_videos + scene_progress, 1.0)
                    progress_bar.progress(current_progress)
                    
                    # Prepare output filename - sanitize base_name to remove problematic characters
                    safe_base_name = "".join(c if c.isalnum() or c in ['-', '_'] else '_' for c in base_name)
                    if output_format == "gif":
                        output_file = os.path.join(output_dir, f"{safe_base_name}_scene{idx}.gif")
                    else:
                        output_file = os.path.join(output_dir, f"{safe_base_name}_scene{idx}.mp4")
                    
                    # Prepare ffmpeg command
                    command = [
                        "ffmpeg",
                        "-i", temp_file_path,
                        "-ss", str(start.get_seconds()),
                        "-t", str(end.get_seconds() - start.get_seconds()),
                    ]
                    
                    if output_format == "mp4":
                        command += [
                            "-preset", "fast",
                            "-c:v", "libx264",
                            "-crf", "23",
                        ]
                        if include_audio:
                            command += ["-c:a", "aac"]
                        else:
                            command += ["-an"]
                    else:  # GIF
                        command += [
                            "-vf", "fps=10,scale=480:-1:flags=lanczos",
                            "-loop", "0",
                            "-c:v", "gif"
                        ]
                    
                    command += ["-y", output_file]
                    
                    try:
                        subprocess.run(command, check=True, capture_output=True)
                        
                        # Verify the output file exists and has content
                        if os.path.exists(output_file) and os.path.getsize(output_file) > 10000:
                            video_scene_files.append(output_file)
                            all_scene_files.append(output_file)
                            status_text.text(f"Processed scene {idx} of {len(scenes)} for {video_file.name}")
                        else:
                            st.warning(f"Scene {idx} of {video_file.name} may not have processed correctly.")
                    except subprocess.CalledProcessError as e:
                        st.error(f"Error processing scene {idx} of {video_file.name}: {str(e)}")
                
                # Update progress to the end of this video's portion
                progress_bar.progress(min((video_idx + 1) / total_videos, 1.0))
                
                # Display summary for this video
                st.info(f"Successfully processed {len(video_scene_files)} out of {len(scenes)} scenes from {video_file.name}")
        
        except Exception as e:
            st.error(f"Error processing {video_file.name}: {str(e)}")
    
    # Complete progress
    progress_bar.progress(1.0)
    status_text.text("Processing complete!")
    
    # Create a ZIP with all scenes from all videos
    if all_scene_files:
        st.success(f"Successfully processed {len(all_scene_files)} scenes from {total_videos} videos")
        
        # Create ZIP file
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            for scene_path in all_scene_files:
                zip_file.write(scene_path, os.path.basename(scene_path))
        
        # Provide download button for ZIP
        zip_size = len(zip_buffer.getvalue()) / (1024*1024)  # Size in MB
        st.download_button(
            label=f"Download All Scenes as ZIP ({zip_size:.1f} MB)",
            data=zip_buffer.getvalue(),
            file_name=f"all_scenes_{uuid.uuid4().hex[:8]}.zip",
            mime="application/zip",
            key="download_all"
        )
    
    # Clean up temporary files
    shutil.rmtree(temp_dir)
    
    # Reset processing state
    st.session_state.processing = False

# Show a message if no videos are uploaded
if not st.session_state.uploaded_videos:
    st.info("Please upload one or more video files to begin.")

# Footer
st.markdown("---")
st.caption("Video Scene Splitter - Automatically split videos into scenes")
