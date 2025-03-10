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
    .stTextInput > div > div > input {{
        background-color: black;
        color: white;
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
    /* Button accent */
    .accent-button {{
        background-color: {EVA_FG} !important;
        color: {EVA_BG} !important;
        font-weight: bold !important;
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
    st.session_state.temp_dirs = []

# Sezione video
st.markdown('<div class="section-header">Video da dividere:</div>', unsafe_allow_html=True)
col1, col2 = st.columns([1, 1])

with col1:
    if st.button("Aggiungi Video"):
        uploaded_files = st.file_uploader("Seleziona uno o più video", 
                                     accept_multiple_files=True, 
                                     type=["mp4", "mov", "avi", "mkv"],
                                     key="uploader_" + str(len(st.session_state.uploaded_files)))
        if uploaded_files:
            for file in uploaded_files:
                if file.name not in st.session_state.file_names:
                    st.session_state.uploaded_files.append(file)
                    st.session_state.file_names.append(file.name)

with col2:
    if st.button("Rimuovi Selezionati"):
        # In una vera app con interfaccia grafica avremmo la selezione
        # Qui rimuoviamo semplicemente l'ultimo file caricato
        if st.session_state.uploaded_files:
            st.session_state.uploaded_files.pop()
            st.session_state.file_names.pop()
            st.rerun()

# Lista file
st.markdown('<div class="file-list">', unsafe_allow_html=True)
if st.session_state.file_names:
    for i, filename in enumerate(st.session_state.file_names):
        st.markdown(f'<div class="file-item">{filename}</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="file-item">Nessun file selezionato</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# Cartella di destinazione
st.markdown('<div class="section-header">Cartella di base (dove creare la cartella \'Video_Splitted\'):</div>', unsafe_allow_html=True)
output_path = st.text_input("", value=os.path.expanduser("~/Downloads"), 
                           label_visibility="collapsed")

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

# Pulsanti di controllo
control_col1, control_col2 = st.columns(2)

with control_col1:
    start_button = st.button("AVVIA", key="avvia_button", disabled=len(st.session_state.uploaded_files) == 0)

with control_col2:
    stop_button = st.button("INTERROMPI", key="interrompi_button", 
                           disabled=not st.session_state.processing)

# Barra di progresso
progress_placeholder = st.empty()
status_text = st.empty()

# Logica di elaborazione
if start_button and st.session_state.uploaded_files and not st.session_state.processing:
    st.session_state.processing = True
    
    progress_bar = progress_placeholder.progress(0)
    status_text.text("Inizializzazione...")
    
    # Crea cartella di output unica
    base_dir = output_path
    output_dir_name = "Video_Splitted"
    counter = 0
    output_dir = os.path.join(base_dir, output_dir_name)
    
    while os.path.exists(output_dir):
        counter += 1
        output_dir = os.path.join(base_dir, f"{output_dir_name}_{counter}")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Processa tutti i video
    all_scene_files = []
    
    for file_idx, uploaded_file in enumerate(st.session_state.uploaded_files):
        file_progress = file_idx / len(st.session_state.uploaded_files)
        status_text.text(f"Elaborazione video {file_idx+1}/{len(st.session_state.uploaded_files)}: {uploaded_file.name}")
        
        # Salva file temporaneamente
        temp_dir = tempfile.mkdtemp()
        st.session_state.temp_dirs.append(temp_dir)
        temp_file_path = os.path.join(temp_dir, uploaded_file.name)
        
        with open(temp_file_path, "wb") as temp_file:
            temp_file.write(uploaded_file.getbuffer())
        
        try:
            if split_method == "scene":
                # Rilevamento scene
                progress_bar.progress(file_progress * 100 + 10/len(st.session_state.uploaded_files))
                scenes = detect(temp_file_path, ContentDetector(threshold=threshold))
                
                if scenes:
                    base_name = os.path.splitext(os.path.basename(temp_file_path))[0]
                    
                    # Elabora ogni scena
                    for idx, (start, end) in enumerate(scenes, start=1):
                        scene_progress = file_progress * 100 + (10 + (idx/len(scenes) * 80))/len(st.session_state.uploaded_files)
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
                        except subprocess.CalledProcessError as e:
                            st.error(f"Errore durante l'elaborazione: {str(e)}")
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
                    
                    while start_time < total_duration:
                        segment_duration = min(float(chunk_length), total_duration - start_time)
                        segment_progress = file_progress * 100 + (start_time / total_duration * 90) / len(st.session_state.uploaded_files)
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
                        except subprocess.CalledProcessError as e:
                            st.error(f"Errore durante l'elaborazione: {str(e)}")
                        
                        start_time += segment_duration
                        segment_index += 1
                        
                except Exception as e:
                    st.error(f"Errore durante l'analisi video: {str(e)}")
        
        except Exception as e:
            st.error(f"Errore nell'elaborazione di {uploaded_file.name}: {str(e)}")
    
    # Completa la barra di progresso
    progress_bar.progress(100)
    status_text.text(f"Elaborazione completata! {len(all_scene_files)} scene create in: {output_dir}")
    
    st.session_state.processing = False
    st.success(f"Tutti i video sono stati elaborati! Le scene sono disponibili in: {output_dir}")

# Pulizia directory temporanee
for temp_dir in st.session_state.temp_dirs:
    try:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
    except:
        pass
