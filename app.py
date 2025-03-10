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

# Set page title
st.set_page_config(page_title="Video Scene Splitter", layout="wide")

# App title and description
st.title("Video Scene Splitter")
st.write("Upload a video to automatically split it into scenes.")

# File uploader
uploaded_file = st.file_uploader("Upload a video", type=["mp4", "mov", "avi", "mkv"])

# Advanced options
with st.expander("Advanced Options"):
    threshold = st.slider("Scene detection sensitivity", 15, 30, 27, 1, 
                         help="Lower values create more scenes (more sensitive)")
    include_audio = st.checkbox("Include audio in output", value=True)
    output_format = st.selectbox("Output format", ["mp4", "gif"], index=0)

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
        # Detect scenes using PySceneDetect's detect function (like in your desktop app)
        status_text.text("Detecting scenes...")
        progress_bar.progress(10)
        
        # Directly use the detect function from PySceneDetect
        scenes = detect(temp_file_path, ContentDetector(threshold=threshold))
        
        if not scenes:
            st.warning("No scene changes detected. Try lowering the threshold value.")
        else:
            progress_bar.progress(40)
            
            # Use ffmpeg to split video
            status_text.text("Splitting video into scenes...")
            scene_files = []
            base_name = os.path.splitext(os.path.basename(temp_file_path))[0]
            
            # Process each scene
            for idx, (start, end) in enumerate(scenes, start=1):
                progress_value = 40 + int((idx / len(scenes)) * 50)
                progress_bar.progress(progress_value)
                
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
                
                try:
                    subprocess.run(command, check=True, capture_output=True)
                    
                    # Verify the output file exists and has content
                    if os.path.exists(output_file) and os.path.getsize(output_file) > 10000:
                        scene_files.append(output_file)
                        status_text.text(f"Processed scene {idx} of {len(scenes)}")
                    else:
                        st.warning(f"Scene {idx} may not have processed correctly.")
                except subprocess.CalledProcessError as e:
                    st.error(f"Error processing scene {idx}: {str(e)}")
            
            # Complete progress
            progress_bar.progress(100)
            status_text.text("Processing complete!")
            
            # Display number of detected scenes
            st.success(f"Successfully processed {len(scene_files)} out of {len(scenes)} scenes")
            
            # Display and allow downloading of scenes
            if scene_files:
                st.subheader("Scene Previews:")
                
                for i, scene_path in enumerate(scene_files):
                    with st.expander(f"Scene {i+1}"):
                        if output_format == "mp4":
                            st.video(scene_path)
                        else:
                            st.image(scene_path)
                            
                        with open(scene_path, "rb") as file:
                            scene_data = file.read()
                            file_size = len(scene_data) / (1024*1024)  # Size in MB
                            st.download_button(
                                label=f"Download Scene {i+1} ({file_size:.1f} MB)",
                                data=scene_data,
                                file_name=f"scene_{i+1}.{output_format}",
                                mime=f"video/{output_format}" if output_format == "mp4" else "image/gif",
                                key=f"download_{i}"
                            )
                
                # Create a ZIP with all scenes
                st.subheader("Download all scenes:")
                zip_buffer = BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zip_file:
                    for i, scene_path in enumerate(scene_files):
                        zip_file.write(scene_path, f"scene_{i+1}.{output_format}")
                
                zip_size = len(zip_buffer.getvalue()) / (1024*1024)  # Size in MB
                st.download_button(
                    label=f"Download All Scenes as ZIP ({zip_size:.1f} MB)",
                    data=zip_buffer.getvalue(),
                    file_name="all_scenes.zip",
                    mime="application/zip"
                )
                
                # Also show scene timing information
                st.subheader("Scene Timecodes:")
                scene_data = []
                for i, (start, end) in enumerate(scenes):
                    start_time = start.get_seconds()
                    end_time = end.get_seconds()
                    scene_data.append({
                        "Scene": i+1,
                        "Start Time": f"{int(start_time//60):02d}:{int(start_time%60):02d}",
                        "End Time": f"{int(end_time//60):02d}:{int(end_time%60):02d}",
                        "Duration": f"{int((end_time-start_time)//60):02d}:{int((end_time-start_time)%60):02d}"
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
