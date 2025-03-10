import streamlit as st
import cv2
import tempfile
import os
import subprocess
import shutil
from scenedetect import detect, ContentDetector
import zipfile
from io import BytesIO
import time
import uuid

# Set page title and configure layout
st.set_page_config(
    page_title="Video Scene Splitter",
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# Custom CSS to improve the UI appearance
st.markdown("""
<style>
    .main-header {color: #6c38a0; font-size: 36px; font-weight: bold; margin-bottom: 10px;}
    .sub-header {font-size: 20px; color: #888; margin-bottom: 20px;}
    .upload-area {background-color: #f8f9fa; padding: 20px; border-radius: 10px; border: 1px dashed #ddd;}
    .control-panel {background-color: #f0f0f8; padding: 20px; border-radius: 10px; margin: 20px 0;}
    .download-section {background-color: #f0f8f0; padding: 20px; border-radius: 10px; margin-top: 20px;}
    .stButton>button {background-color: #6c38a0; color: white; font-weight: bold; padding: 10px 25px; border-radius: 5px;}
    .file-list {margin: 10px 0; background-color: white; padding: 10px; border-radius: 5px; max-height: 200px; overflow-y: auto;}
</style>
""", unsafe_allow_html=True)

# App header
st.markdown('<div class="main-header">Video Scene Splitter</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Upload videos to automatically split them into scenes</div>', unsafe_allow_html=True)

# Initialize session state for storing uploaded files
if 'uploaded_files' not in st.session_state:
    st.session_state.uploaded_files = []
    st.session_state.file_names = []
    st.session_state.ready_for_download = False
    st.session_state.download_data = None
    st.session_state.processing = False
    st.session_state.temp_dirs = []

# File upload section
st.markdown('<div class="upload-area">', unsafe_allow_html=True)
uploaded_file = st.file_uploader("Drop your video files here", 
                                type=["mp4", "mov", "avi", "mkv"], 
                                accept_multiple_files=True)

if uploaded_file:
    for file in uploaded_file:
        if file.name not in st.session_state.file_names:
            st.session_state.uploaded_files.append(file)
            st.session_state.file_names.append(file.name)

# Display list of uploaded files
if st.session_state.uploaded_files:
    st.markdown('<div class="file-list">', unsafe_allow_html=True)
    for i, file_name in enumerate(st.session_state.file_names):
        col1, col2 = st.columns([6, 1])
        with col1:
            st.write(f"{i+1}. {file_name}")
        with col2:
            if st.button("🗑️", key=f"remove_{i}"):
                st.session_state.uploaded_files.pop(i)
                st.session_state.file_names.pop(i)
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Clear all button
    if st.button("Clear All"):
        st.session_state.uploaded_files = []
        st.session_state.file_names = []
        st.rerun()
st.markdown('</div>', unsafe_allow_html=True)

# Control panel
st.markdown('<div class="control-panel">', unsafe_allow_html=True)
st.subheader("Processing Settings")

col1, col2, col3 = st.columns(3)
with col1:
    threshold = st.slider("Scene detection sensitivity", 15, 30, 27, 1,
                         help="Lower values create more scenes (more sensitive)")
with col2:
    include_audio = st.checkbox("Include audio in output", value=True)
with col3:
    output_format = st.selectbox("Output format", ["mp4", "gif"], index=0)

# Process button
if st.button("PROCESS VIDEOS", disabled=len(st.session_state.uploaded_files) == 0 or st.session_state.processing):
    if st.session_state.uploaded_files:
        st.session_state.processing = True
        st.session_state.ready_for_download = False
        
        # Create progress indicators
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Process all videos
        all_scene_files = []
        main_temp_dir = tempfile.mkdtemp()
        st.session_state.temp_dirs.append(main_temp_dir)
        output_dir = os.path.join(main_temp_dir, "scenes")
        os.makedirs(output_dir, exist_ok=True)
        
        for file_idx, uploaded_file in enumerate(st.session_state.uploaded_files):
            file_progress = file_idx / len(st.session_state.uploaded_files)
            status_text.text(f"Processing video {file_idx+1}/{len(st.session_state.uploaded_files)}: {uploaded_file.name}")
            
            # Save file temporarily
            temp_file_path = os.path.join(main_temp_dir, uploaded_file.name)
            with open(temp_file_path, "wb") as temp_file:
                temp_file.write(uploaded_file.getbuffer())
            
            try:
                # Detect scenes
                progress_bar.progress(file_progress * 100 + 10/len(st.session_state.uploaded_files))
                scenes = detect(temp_file_path, ContentDetector(threshold=threshold))
                
                if scenes:
                    base_name = os.path.splitext(os.path.basename(temp_file_path))[0]
                    
                    # Process each scene
                    for idx, (start, end) in enumerate(scenes, start=1):
                        scene_progress = file_progress * 100 + (10 + (idx/len(scenes) * 80))/len(st.session_state.uploaded_files)
                        progress_bar.progress(min(scene_progress, 100))
                        
                        # Prepare output filename
                        if output_format == "gif":
                            output_file = os.path.join(output_dir, f"{base_name}_scene{idx}.gif")
                        else:
                            output_file = os.path.join(output_dir, f"{base_name}_scene{idx}.mp4")
                        
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
                        
                        subprocess.run(command, check=True, capture_output=True)
                        
                        # Verify the output file
                        if os.path.exists(output_file) and os.path.getsize(output_file) > 10000:
                            all_scene_files.append(output_file)
                
            except Exception as e:
                st.error(f"Error processing {uploaded_file.name}: {str(e)}")
        
        # Create ZIP with all scenes
        if all_scene_files:
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zip_file:
                for scene_path in all_scene_files:
                    zip_file.write(scene_path, os.path.basename(scene_path))
            
            # Store for download
            st.session_state.download_data = zip_buffer.getvalue()
            st.session_state.ready_for_download = True
            
            # Complete progress
            progress_bar.progress(100)
            status_text.text(f"Processing complete! Split {len(all_scene_files)} scenes from {len(st.session_state.uploaded_files)} videos.")
        else:
            status_text.text("No scenes could be detected or processed.")
        
        st.session_state.processing = False
        st.rerun()

st.markdown('</div>', unsafe_allow_html=True)

# Download section
if st.session_state.ready_for_download and st.session_state.download_data:
    st.markdown('<div class="download-section">', unsafe_allow_html=True)
    st.subheader("Download Your Scenes")
    zip_size = len(st.session_state.download_data) / (1024*1024)  # Size in MB
    
    st.download_button(
        label=f"DOWNLOAD ALL SCENES ({zip_size:.1f} MB)",
        data=st.session_state.download_data,
        file_name=f"scenes_{uuid.uuid4().hex[:8]}.zip",
        mime="application/zip",
        key="download_all"
    )
    st.markdown('</div>', unsafe_allow_html=True)

# Footer
st.markdown("---")
st.caption("Video Scene Splitter - Automatically split videos into scenes")

# Clean up temporary directories from previous runs
for temp_dir in st.session_state.temp_dirs[:-1]:
    try:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
    except:
        pass
if len(st.session_state.temp_dirs) > 1:
    st.session_state.temp_dirs = st.session_state.temp_dirs[-1:]
