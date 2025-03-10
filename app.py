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
import time

# Colori EVA-01
EVA_BG = "#3A2A59"  # Viola scuro
EVA_FG = "#A4FF00"  # Verde acido

# Set page config
st.set_page_config(
    page_title="Super Awesome Mega Video Splitter (EVA-01)",
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# EVA-01 Style CSS
st.markdown(f"""
<style>
    /* Colori base */
    .stApp {{
        background-color: {EVA_BG};
        color: {EVA_FG};
    }}
    .main-header {{
        color: {EVA_FG}; 
        font-size: 36px; 
        font-weight: bold; 
        text-align: center;
        margin-bottom: 30px;
    }}
    /* Widgets e controlli */
    div.stButton > button {{
        background-color: {EVA_BG};
        color: {EVA_FG};
        border: 2px solid {EVA_FG};
        border-radius: 4px;
        padding: 10px 24px;
        font-weight: bold;
    }}
    div.stButton > button:hover {{
        background-color: rgba(164, 255, 0, 0.2);
    }}
    .css-1n76uvr, .css-1kyxreq {{
        color: {EVA_FG} !important;
    }}
    .stSlider > div {{
        color: {EVA_FG};
    }}
    .stCheckbox {{
        color: {EVA_FG};
    }}
    .stSelectbox > div > div {{
        background-color: black !important;
        color: white !important;
    }}
    /* Sezioni */
    .section {{
        padding: 10px;
        margin-bottom: 20px;
        border-radius: 5px;
    }}
    .section-header {{
        font-size: 20px;
        font-weight: bold;
        margin-bottom: 10px;
    }}
    /* File list */
    .file-list {{
        background-color: black;
        border-radius: 5px;
        padding: 10px;
        height: 200px;
        overflow-y: auto;
        margin-top: 10px;
    }}
    .file-item {{
        padding: 5px;
        border-bottom: 1px solid #555;
    }}
    /* Barra di avanzamento */
    .stProgress > div > div {{
        background-color: {EVA_FG};
    }}
    /* Nascondi elementi inutili */
    #MainMenu, footer {{display: none;}}
    /* Download button */
    .download-button {{
        display: block;
        background-color: {EVA_FG};
        color: {EVA_BG} !important;
        text-align: center;
        padding: 12px;
        font-weight: bold;
        border-radius: 5px;
        margin-top: 20px;
        font-size: 18px;
    }}
    /* Big button */
    .big-button {{
        font-size: 24px !important;
        padding: 15px !important;
    }}
</style>
""", unsafe_allow_html=True)

# Intestazione
st.markdown(f'<div class="main-header">Super Awesome Mega Video Splitter (EVA-01)</div>', unsafe_allow_html=True)

# Inizializzazione dello stato
if 'uploaded_files' not in st.session_state:
    st.session_state.uploaded_files = []
    st.session_state.file_names = []
    st.session_state.ready_for_download = False
    st.session_state.download_data = None
    st.session_state.processing = False

# Sezione video
st.markdown('<div class="section-header">Video da dividere:</div>', unsafe_allow_html=True)
col1, col2 = st.columns([1, 1])

with col1:
    uploaded_files = st.file_uploader("Aggiungi Video", 
                                 accept_multiple_files=True, 
                                 type=["mp4", "mov", "avi", "mkv"],
                                 key="uploader")
    if uploaded_files:
        for file in uploaded_files:
            if file.name not in st.session_state.file_names:
                st.session_state.uploaded_files.append(file)
                st.session_state.file_names.append(file.name)

with col2:
    if st.button("Rimuovi Tutti"):
        st.session_state.uploaded_files = []
        st.session_state.file_names = []
        st.rerun()

# Lista file
st.markdown('<div class="file-list">', unsafe_allow_html=True)
if st.session_state.file_names:
    for i, filename in enumerate(st.session_state.file_names):
        st.markdown(f'<div class="file-item">{filename}</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="file-item">Nessun file selezionato</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# Opzioni
st.markdown('<div class="section-header">Opzioni:</div>', unsafe_allow_html=True)
options_col1, options_col2 = st.columns(2)

with options_col1:
    split_method = st.selectbox("Metodo di divisione:", ["scene", "time"])
    include_audio = st.checkbox("Includi Audio")

with options_col2:
    threshold = st.slider("Sensibilità rilevamento (15-30):", 15, 30, 27)
    if split_method == "time":
        chunk_length = st.number_input("Lunghezza segmenti (secondi):", 1, 60, 4)
    output_format = st.selectbox("Formato di output:", ["mp4", "gif"])

# Pulsante AVVIA
if st.button("AVVIA", key="avvia_button", disabled=len(st.session_state.uploaded_files) == 0 or st.session_state.processing, 
            help="Clicca per iniziare l'elaborazione"):
    st.session_state.processing = True
    
    # Crea una barra di progresso e un testo di stato
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Crea directory temporanea per l'elaborazione
    temp_dir = tempfile.mkdtemp()
    output_dir = os.path.join(temp_dir, "scenes")
    os.makedirs(output_dir, exist_ok=True)
    
    # Processa tutti i video
    all_scene_files = []
    total_videos = len(st.session_state.uploaded_files)
    
    for file_idx, uploaded_file in enumerate(st.session_state.uploaded_files):
        file_progress = file_idx / total_videos
        status_text.text(f"Elaborazione video {file_idx+1}/{total_videos}: {uploaded_file.name}")
        
        # Salva file temporaneamente
        temp_file_path = os.path.join(temp_dir, uploaded_file.name)
        
        with open(temp_file_path, "wb") as temp_file:
            temp_file.write(uploaded_file.getbuffer())
        
        try:
            if split_method == "scene":
                # Rilevamento scene
                progress_bar.progress(file_progress * 100 + 5/total_videos)
                scenes = detect(temp_file_path, ContentDetector(threshold=threshold))
                
                if scenes:
                    base_name = os.path.splitext(os.path.basename(temp_file_path))[0]
                    
                    # Elabora ogni scena
                    for idx, (start, end) in enumerate(scenes, start=1):
                        scene_progress = file_progress * 100 + (5 + (idx/len(scenes) * 85))/total_videos
                        progress_bar.progress(min(scene_progress, 100))
                        
                        # Prepara nome file di output
                        if output_format == "gif":
                            output_file = os.path.join(output_dir, f"{base_name}_scena{idx}.gif")
                        else:
                            output_file = os.path.join(output_dir, f"{base_name}_scena{idx}.mp4")
                        
                        # Comando ffmpeg
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
                            all_scene_files.append(output_file)
                            status_text.text(f"Creata scena {idx} di {len(scenes)} per il video {file_idx+1}/{total_videos}")
                        except subprocess.CalledProcessError as e:
                            st.error(f"Errore durante la creazione della scena {idx}: {str(e)}")
            else:
                # Divisione a tempo fisso
                # Get video duration
                try:
                    cmd = [
                        "ffprobe", 
                        "-v", "error", 
                        "-show_entries", "format=duration", 
                        "-of", "default=noprint_wrappers=1:nokey=1", 
                        temp_file_path
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                    total_duration = float(result.stdout.strip())
                    
                    base_name = os.path.splitext(os.path.basename(temp_file_path))[0]
                    start_time = 0.0
                    segment_index = 1
                    num_segments = int(total_duration / float(chunk_length)) + 1
                    
                    while start_time < total_duration:
                        segment_duration = min(float(chunk_length), total_duration - start_time)
                        segment_progress = file_progress * 100 + (segment_index / num_segments * 90) / total_videos
                        progress_bar.progress(min(segment_progress, 100))
                        
                        # Prepara nome file di output
                        if output_format == "gif":
                            output_file = os.path.join(output_dir, f"{base_name}_part{segment_index}.gif")
                        else:
                            output_file = os.path.join(output_dir, f"{base_name}_part{segment_index}.mp4")
                        
                        # Comando ffmpeg
                        command = [
                            "ffmpeg",
                            "-i", temp_file_path,
                            "-ss", str(start_time),
                            "-t", str(segment_duration),
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
                            all_scene_files.append(output_file)
                            status_text.text(f"Creato segmento {segment_index} di {num_segments} per il video {file_idx+1}/{total_videos}")
                        except subprocess.CalledProcessError as e:
                            st.error(f"Errore durante la creazione del segmento {segment_index}: {str(e)}")
                        
                        start_time += segment_duration
                        segment_index += 1
                        
                except Exception as e:
                    st.error(f"Errore durante l'analisi video: {str(e)}")
        
        except Exception as e:
            st.error(f"Errore nell'elaborazione di {uploaded_file.name}: {str(e)}")
    
    # Crea ZIP con tutte le scene
    if all_scene_files:
        status_text.text("Preparazione file di download...")
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            for scene_path in all_scene_files:
                zip_file.write(scene_path, os.path.basename(scene_path))
        
        # Salva per il download
        st.session_state.download_data = zip_buffer.getvalue()
        st.session_state.ready_for_download = True
    
    # Completa la barra di progresso
    progress_bar.progress(100)
    status_text.text(f"Elaborazione completata! {len(all_scene_files)} scene create.")
    
    # Pulizia
    try:
        shutil.rmtree(temp_dir)
    except:
        pass
    
    st.session_state.processing = False
    st.rerun()

# Sezione download
if st.session_state.ready_for_download and st.session_state.download_data:
    st.markdown("---")
    st.markdown('<div class="section-header">Download:</div>', unsafe_allow_html=True)
    
    zip_size = len(st.session_state.download_data) / (1024*1024)  # Size in MB
    
    download_button = st.download_button(
        label=f"DOWNLOAD SCENE ({zip_size:.1f} MB)",
        data=st.session_state.download_data,
        file_name=f"scene_splittate_{uuid.uuid4().hex[:6]}.zip",
        mime="application/zip",
        key="download_button",
        help="Scarica tutte le scene in un unico file ZIP"
    )
