import logging
import math
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from threading import Thread, Event
from logging.handlers import RotatingFileHandler
import whisper
import warnings
import os
from docx import Document
import json
import time
import shutil
import torch
import requests
import subprocess
from platform import system
import sys
from multiprocessing import Process, Queue, freeze_support
from functools import lru_cache
from contextlib import contextmanager

from advanced_settings import AdvancedSettingsWindow
from transcription_settings import TranscriptionSettings

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

class NoConsolePopen(subprocess.Popen):
    def __init__(self, args, **kwargs):
        if system() == 'Windows' and 'startupinfo' not in kwargs:
            kwargs['startupinfo'] = subprocess.STARTUPINFO()
            kwargs['startupinfo'].dwFlags |= subprocess.STARTF_USESHOWWINDOW
        super().__init__(args, **kwargs)

subprocess.Popen = NoConsolePopen


class ErrorHandlers:
    class TranscriptionCancelledException(Exception):
        pass

    @staticmethod
    def handle_exception(e):
        logging.error(f"Erro: {str(e)}")

    @staticmethod
    def handle_file_not_found(e):
        logging.error(f"Arquivo não encontrado: {str(e)}")
        messagebox.showerror("Erro", f"Arquivo não encontrado: {str(e)}")

    @staticmethod
    def handle_subprocess_error(e):
        logging.error(f"Erro no subprocesso: {str(e)}")
        messagebox.showerror("Erro", f"Ocorreu um erro ao processar o arquivo: {str(e)}")

    @staticmethod
    def handle_generic_error(e):
        logging.error(f"Erro inesperado: {str(e)}")
        messagebox.showerror("Erro", f"Ocorreu um erro inesperado: {str(e)}")

    @staticmethod
    def handle_model_load_error(e):
        logging.error(f"Erro ao carregar o modelo: {str(e)}")
        messagebox.showerror("Erro", f"Erro ao carregar o modelo: {str(e)}")

    @staticmethod
    def handle_download_error(e):
        logging.error(f"Erro no download: {str(e)}")
        messagebox.showerror("Erro", f"Ocorreu um erro durante o download: {str(e)}")


def is_production():
    return hasattr(sys, '_MEIPASS')


class Config:
    def __init__(self):
        self.CONFIG_FILE = self.resource_path("config.json")
        self.LOGS_DIR = self.resource_path("logs")
        self.TEMP_DIR = self.resource_path("temp")
        self.ICON_PATH = self.resource_path("bin/icon.ico")
        self.DEFAULT_CONFIG = {
            "model_path": "",
            "language": "pt"
        }
        self.config = self.load_config()
        self.setup_logging()

    @lru_cache(maxsize=32)
    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except AttributeError:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def load_config(self):
        if not os.path.exists(self.CONFIG_FILE):
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(self.DEFAULT_CONFIG, f, indent=4)
        try:
            with open(self.CONFIG_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError as e:
            ErrorHandlers.handle_exception(e)
            return self.DEFAULT_CONFIG.copy()

    def save_config(self):
        with open(self.CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=4)

    def setup_logging(self):
        if not os.path.exists(self.LOGS_DIR):
            os.makedirs(self.LOGS_DIR)
        log_handler = RotatingFileHandler(
            os.path.join(self.LOGS_DIR, 'info.log'),
            maxBytes=5*1024*1024,
            backupCount=5
        )
        log_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'))
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        if logger.hasHandlers():
            logger.handlers.clear()
        logger.addHandler(log_handler)


class AudioProcessor:
    AUDIO_EXTENSIONS = ('.mp3', '.wav', '.aac', '.flac', '.m4a', '.ogg')
    
    def __init__(self, config):
        self.config = config
        self.FFMPEG_EXECUTABLE = 'ffmpeg.exe' if system() == 'Windows' else 'ffmpeg'
        self.FFMPEG_PATH = self.config.resource_path(self.FFMPEG_EXECUTABLE)

    def extract_audio(self, filepath, temp_dir):
        try:
            if not os.path.exists(self.FFMPEG_PATH):
                raise FileNotFoundError(
                    f"Executável do FFmpeg não encontrado em: {self.FFMPEG_PATH}")
            
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
            else:
                self.clean_temp_dir(temp_dir)
            
            if filepath.lower().endswith(self.AUDIO_EXTENSIONS):
                return filepath
            
            output_path = os.path.abspath(os.path.join(temp_dir, "temp_audio.aac"))
            command = [self.FFMPEG_PATH, '-i', filepath, '-acodec', 'aac', output_path, '-y']
            
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            if result.returncode != 0:
                raise subprocess.CalledProcessError(result.returncode, command)
            
            return output_path
        except FileNotFoundError as e:
            ErrorHandlers.handle_file_not_found(e)
            raise
        except subprocess.CalledProcessError as e:
            ErrorHandlers.handle_subprocess_error(e)
            raise
        except Exception as e:
            ErrorHandlers.handle_generic_error(e)
            raise

    def clean_temp_dir(self, temp_dir):
        for filename in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                ErrorHandlers.handle_exception(e)


class TranscriptionManager:
    def __init__(self, config, audio_processor):
        self.config = config
        self.audio_processor = audio_processor
        self.model = None
        self.stop_event = Event()
        self.is_transcribing = False
        self.cancel_transcription = False
        self.transcription_process = None
        self.default_settings = TranscriptionSettings()

    def load_model(self, model_path):
        try:
            if not self.verify_model_file(model_path):
                raise Exception("Arquivo do modelo inválido ou corrompido")
            
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logging.info(f"Carregando modelo em: {device}")
            self.model = whisper.load_model(model_path, device=device)
            logging.info("Modelo carregado com sucesso")
        except Exception as e:
            ErrorHandlers.handle_model_load_error(e)
            raise

    def verify_model_file(self, model_path):
        try:
            if not os.path.exists(model_path):
                logging.error(f"Arquivo do modelo não encontrado: {model_path}")
                return False
            
            file_size = os.path.getsize(model_path)
            if file_size < 1000000:
                logging.error(f"Arquivo do modelo parece estar incompleto: {file_size} bytes")
                return False
            
            device = "cuda" if torch.cuda.is_available() else "cpu"
            whisper.load_model(model_path, device=device)
            logging.info(f"Modelo verificado com sucesso: {model_path}")
            return True
        except Exception as e:
            ErrorHandlers.handle_exception(e)
            try:
                os.remove(model_path)
                logging.info(f"Arquivo de modelo corrompido removido: {model_path}")
            except Exception as del_e:
                ErrorHandlers.handle_exception(del_e)
            return False

    def transcribe_file(self, filepath, output_callback=None, settings=None):
        try:
            model_path = self.config.config['model_path']
            if not model_path:
                raise Exception("Caminho do modelo não definido")
            
            settings_obj = settings or self.default_settings
            if isinstance(settings_obj, TranscriptionSettings):
                settings_dict = settings_obj.to_dict()
            elif isinstance(settings_obj, dict):
                settings_dict = settings_obj
            else:
                raise TypeError("Configurações de transcrição inválidas")
            
            result_queue = Queue()
            self.transcription_process = Process(
                target=self.transcribe_file_process,
                args=(model_path, self.config.config, filepath, self.config.TEMP_DIR, settings_dict, result_queue)
            )
            self.transcription_process.start()
            
            while self.transcription_process is not None and self.transcription_process.is_alive():
                time.sleep(0.5)
                if self.cancel_transcription:
                    if self.transcription_process is not None and self.transcription_process.is_alive():
                        self.transcription_process.terminate()
                        self.transcription_process.join()
                        self.transcription_process = None
                    self.cancel_transcription = False
                    raise ErrorHandlers.TranscriptionCancelledException("Transcrição cancelada pelo usuário")
            
            if not result_queue.empty():
                result = result_queue.get()
                if 'error' in result:
                    raise Exception(result['error'])
                else:
                    output_path = result['output_path']
                    if output_callback:
                        output_callback(output_path)
                    return output_path
            else:
                raise Exception("Processo de transcrição não retornou nenhum resultado.")
        except ErrorHandlers.TranscriptionCancelledException:
            raise
        except Exception as e:
            ErrorHandlers.handle_generic_error(e)
            raise
        finally:
            if self.transcription_process is not None:
                if self.transcription_process.is_alive():
                    self.transcription_process.join()
                self.transcription_process = None
            self.cancel_transcription = False

    @staticmethod
    def transcribe_file_process(model_path, config_dict, filepath, temp_dir, settings_dict, result_queue):
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model = whisper.load_model(model_path, device=device)
            
            config = Config()
            config.config = config_dict
            audio_processor = AudioProcessor(config)
            audio_path = audio_processor.extract_audio(filepath, temp_dir)
            
            from transcription_settings import TranscriptionSettings
            settings = TranscriptionSettings.from_dict(settings_dict)
            
            transcribe_kwargs = {"word_timestamps": settings.timestamp_mode == "word"}
            
            if settings.language_strategy == "manual" and settings.manual_language:
                transcribe_kwargs["language"] = settings.manual_language
            elif settings.language_strategy == "auto":
                transcribe_kwargs["language"] = None
            else:
                transcribe_kwargs["language"] = None

            quality_presets = {
                "fast": {"beam_size": 1, "best_of": 1},
                "balanced": {"beam_size": 3, "best_of": 3},
                "accurate": {"beam_size": 5, "best_of": 5}
            }
            transcribe_kwargs.update(quality_presets.get(settings.quality_preset, quality_presets["balanced"]))

            result = model.transcribe(audio_path, **transcribe_kwargs)
            local_salvamento = TranscriptionManager.format_output(result, settings, filepath)
            
            if audio_path != filepath:
                os.remove(audio_path)
            
            result_queue.put({'output_path': local_salvamento})
        except Exception as e:
            result_queue.put({'error': str(e)})

    @staticmethod
    def format_output(result, settings, original_filepath):
        segments = result.get("segments", [])
        base_dir = os.path.dirname(original_filepath)
        base_name = os.path.splitext(os.path.basename(original_filepath))[0]
        
        extension_map = {
            "docx": ".docx",
            "txt": ".txt",
            "srt": ".srt",
            "vtt": ".vtt",
            "json": ".json"
        }
        extension = extension_map.get(settings.output_format, ".docx")
        output_path = os.path.join(base_dir, f"{base_name}_text{extension}")

        format_handlers = {
            "docx": TranscriptionManager._save_docx,
            "txt": TranscriptionManager._save_txt,
            "srt": TranscriptionManager._save_srt,
            "vtt": TranscriptionManager._save_vtt,
            "json": TranscriptionManager._save_json
        }
        
        handler = format_handlers.get(settings.output_format, TranscriptionManager._save_docx)
        handler(output_path, segments, result, settings)
        
        return output_path

    @staticmethod
    def _save_docx(output_path, segments, result, settings):
        doc = Document()
        for paragraph in TranscriptionManager._build_paragraph_texts(segments, settings):
            doc.add_paragraph(paragraph)
        doc.save(output_path)

    @staticmethod
    def _save_txt(output_path, segments, result, settings):
        paragraphs = TranscriptionManager._build_paragraph_texts(segments, settings)
        with open(output_path, "w", encoding="utf-8") as fp:
            fp.write("\n\n".join(paragraphs))

    @staticmethod
    def _save_srt(output_path, segments, result, settings):
        with open(output_path, "w", encoding="utf-8") as fp:
            for index, segment in enumerate(segments, start=1):
                start = TranscriptionManager._format_timestamp_value(
                    segment.get("start", 0.0), settings.timestamp_format, target="srt")
                end = TranscriptionManager._format_timestamp_value(
                    segment.get("end", 0.0), settings.timestamp_format, target="srt")
                text = TranscriptionManager._clean_text(segment.get("text", ""), settings)
                fp.write(f"{index}\n{start} --> {end}\n{text.strip()}\n\n")

    @staticmethod
    def _save_vtt(output_path, segments, result, settings):
        with open(output_path, "w", encoding="utf-8") as fp:
            fp.write("WEBVTT\n\n")
            for segment in segments:
                start = TranscriptionManager._format_timestamp_value(
                    segment.get("start", 0.0), settings.timestamp_format, target="vtt")
                end = TranscriptionManager._format_timestamp_value(
                    segment.get("end", 0.0), settings.timestamp_format, target="vtt")
                text = TranscriptionManager._clean_text(segment.get("text", ""), settings)
                fp.write(f"{start} --> {end}\n{text.strip()}\n\n")

    @staticmethod
    def _save_json(output_path, segments, result, settings):
        payload = {
            "text": result.get("text", ""),
            "segments": [
                {
                    "start": segment.get("start"),
                    "end": segment.get("end"),
                    "text": TranscriptionManager._clean_text(segment.get("text", ""), settings)
                }
                for segment in segments
            ],
            "settings": settings.to_dict()
        }
        with open(output_path, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=4, ensure_ascii=False)

    @staticmethod
    def _build_paragraph_texts(segments, settings):
        paragraphs = []
        for group in TranscriptionManager._group_segments(segments, settings):
            if not group:
                continue
            
            if settings.include_timestamps:
                if settings.timestamp_mode == "word":
                    text = TranscriptionManager._format_word_level(group, settings)
                else:
                    timestamp = TranscriptionManager._format_timestamp_value(
                        group[0].get("start", 0.0), settings.timestamp_format)
                    combined = " ".join(segment.get("text", "").strip() for segment in group).strip()
                    text = f"[{timestamp}] {combined}" if combined else ""
            else:
                text = " ".join(segment.get("text", "").strip() for segment in group).strip()
            
            if not text:
                continue
            
            text = TranscriptionManager._clean_text(text, settings)
            paragraphs.append(text)
        return paragraphs

    @staticmethod
    def _group_segments(segments, settings):
        if not segments:
            return []
        
        if settings.timestamp_mode == "paragraph" or settings.auto_paragraphs:
            groups = []
            current_group = []
            last_end = None
            pause_threshold = 0.5 + (settings.paragraph_sensitivity / 100.0) * 4.5
            
            for segment in segments:
                start = segment.get("start", 0.0) or 0.0
                if last_end is not None and start - last_end > pause_threshold and current_group:
                    groups.append(current_group)
                    current_group = []
                current_group.append(segment)
                last_end = segment.get("end", start)
            
            if current_group:
                groups.append(current_group)
            return groups
        
        return [[segment] for segment in segments]

    @staticmethod
    def _format_word_level(group, settings):
        word_fragments = []
        for segment in group:
            for word in segment.get("words", []) or []:
                timestamp = TranscriptionManager._format_timestamp_value(
                    word.get("start", segment.get("start", 0.0)),
                    settings.timestamp_format)
                word_text = word.get("word", "").strip()
                if word_text:
                    word_fragments.append(f"[{timestamp}] {word_text}")
        
        if not word_fragments:
            combined = " ".join(segment.get("text", "").strip() for segment in group).strip()
            if not combined:
                return ""
            timestamp = TranscriptionManager._format_timestamp_value(
                group[0].get("start", 0.0), settings.timestamp_format)
            return f"[{timestamp}] {combined}"
        
        return " ".join(word_fragments)

    @staticmethod
    def _clean_text(text, settings):
        cleaned = text.strip()
        if not settings.capitalization:
            cleaned = cleaned.lower()
        if not settings.punctuation:
            cleaned = TranscriptionManager._remove_punctuation(cleaned)
        return cleaned

    @staticmethod
    def _remove_punctuation(text):
        return "".join(ch for ch in text if ch.isalnum() or ch.isspace())

    @staticmethod
    def _format_timestamp_value(seconds, fmt, target=None):
        seconds = max(0.0, float(seconds or 0.0))
        milliseconds = int(round(seconds * 1000))
        hours, remainder = divmod(milliseconds, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, millis = divmod(remainder, 1000)
        
        if target == "srt":
            return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"
        if target == "vtt":
            return f"{hours:02}:{minutes:02}:{secs:02}.{millis:03}"
        if fmt == "seconds":
            return f"{seconds:.1f}s"
        if fmt == "minutes":
            total_minutes = hours * 60 + minutes
            tenths = int((millis / 1000) * 10)
            return f"{total_minutes:02}:{secs:02}.{tenths:01d}"
        if fmt == "timecode":
            fractional = seconds - math.floor(seconds)
            frames = int(round(fractional * 25))
            return f"{hours:02}:{minutes:02}:{secs:02}:{frames:02}"
        
        return f"{hours:02}:{minutes:02}:{secs:02}.{millis:03}"


class ModelDownloader:
    MODELS_URLS = {
        "small": "https://openaipublic.azureedge.net/main/whisper/models/9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794/small.pt",
        "medium": "https://openaipublic.azureedge.net/main/whisper/models/345ae4da62f9b3d59415adc60127b97c714f32e89e936602e85993674d08dcb1/medium.pt",
        "large-v1": "https://openaipublic.azureedge.net/main/whisper/models/e4b87e7e0bf463eb8e6956e646f1e277e901512310def2c24bf0e11bd3c28e9a/large-v1.pt",
        "large-v2": "https://openaipublic.azureedge.net/main/whisper/models/81f7c96c852ee8fc832187b0132e569d6c3065a3252ed18e56effd0b6a73e524/large-v2.pt",
        "large-v3": "https://openaipublic.azureedge.net/main/whisper/models/e5b1a55b89c1367dacf97e3e19bfd829a01529dbfdeefa8caeb59b3f1b81dadb/large-v3.pt",
    }

    def __init__(self, config):
        self.config = config

    def verify_download(self, file_path, expected_size=None):
        try:
            if not os.path.exists(file_path):
                return False
            if expected_size and os.path.getsize(file_path) != expected_size:
                return False
            device = "cuda" if torch.cuda.is_available() else "cpu"
            torch.load(file_path, map_location=device)
            return True
        except Exception:
            return False

    def download_model(self, model_name, progress_callback=None, cancel_event=None):
        url = self.MODELS_URLS[model_name]
        diretorio_modelo = self.config.resource_path(".model")
        
        if not os.path.exists(diretorio_modelo):
            os.makedirs(diretorio_modelo)
        
        caminho_modelo = os.path.join(diretorio_modelo, f"{model_name}.pt")
        
        if os.path.exists(caminho_modelo):
            try:
                if self.verify_download(caminho_modelo):
                    logging.info(f"Modelo já existe e está válido: {caminho_modelo}")
                    return caminho_modelo
                else:
                    os.remove(caminho_modelo)
                    logging.info(f"Modelo corrompido removido: {caminho_modelo}")
            except Exception as e:
                ErrorHandlers.handle_exception(e)
                if os.path.exists(caminho_modelo):
                    os.remove(caminho_modelo)
        
        max_tentativas = 3
        block_size = 65536
        
        for tentativa in range(max_tentativas):
            try:
                response = requests.get(url, stream=True)
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                start_time = time.time()
                
                with open(caminho_modelo, 'wb') as f:
                    for data in response.iter_content(block_size):
                        if cancel_event and cancel_event.is_set():
                            raise Exception("Download cancelado pelo usuário")
                        f.write(data)
                        downloaded += len(data)
                        
                        if progress_callback:
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                progress_callback(progress)
                            else:
                                elapsed = time.time() - start_time
                                speed = downloaded / elapsed if elapsed > 0 else 0
                                progress_callback(f"Baixado {downloaded} bytes a {speed:.2f} bytes/s")
                
                if self.verify_download(caminho_modelo, total_size if total_size > 0 else None):
                    logging.info(f"Download do modelo concluído com sucesso: {caminho_modelo}")
                    return caminho_modelo
                else:
                    if os.path.exists(caminho_modelo):
                        os.remove(caminho_modelo)
                    raise Exception("Arquivo baixado está corrompido ou incompleto")
            except requests.RequestException as e:
                ErrorHandlers.handle_download_error(e)
                if os.path.exists(caminho_modelo):
                    os.remove(caminho_modelo)
                if tentativa == max_tentativas - 1:
                    raise Exception(f"Falha após {max_tentativas} tentativas de download")
                continue
            except Exception as e:
                ErrorHandlers.handle_download_error(e)
                if os.path.exists(caminho_modelo):
                    os.remove(caminho_modelo)
                if str(e) == "Download cancelado pelo usuário":
                    raise e
                if tentativa == max_tentativas - 1:
                    raise Exception(f"Falha após {max_tentativas} tentativas de download")
                continue


class GUI:
    def __init__(self):
        self.config = Config()
        self.audio_processor = AudioProcessor(self.config)
        self.transcription_manager = TranscriptionManager(self.config, self.audio_processor)
        self.model_downloader = ModelDownloader(self.config)
        self.root = tk.Tk()
        self.root.withdraw()
        self.settings = TranscriptionSettings()
        self.settings_badge_var = tk.StringVar()
        self.setup_main_window()
        self.setup_styles()
        self.create_widgets()
        self.transcription_window = None
        self.quality_window = None
        self.model_window = None
        self.settings_window = None

    def setup_main_window(self):
        self.root.title("TextifyVoice [ 1.0 ] by@felipe.sh")
        self.root.geometry("700x550")
        self.root.resizable(True, True)
        self.root.minsize(600, 450)
        
        if os.path.exists(self.config.ICON_PATH):
            self.root.iconbitmap(self.config.ICON_PATH)
        
        self.root.configure(bg="#1e1e1e")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        self.colors = {
            'background': "#1e1e1e",
            'surface': "#252526",
            'foreground': "#e4e4e4",
            'accent': "#0e639c",
            'accent_hover': "#1177bb",
            'success': "#0e7a0d",
            'success_hover': "#16a34a",
            'border': "#3f3f46",
            'text_secondary': "#a0a0a0"
        }
        
        style.configure("TFrame", background=self.colors['background'])
        
        style.configure("TButton",
                        background=self.colors['accent'],
                        foreground=self.colors['foreground'],
                        font=("Segoe UI", 10),
                        borderwidth=0,
                        focuscolor='none',
                        padding=(20, 10))
        style.map("TButton",
                  background=[('active', self.colors['accent_hover']),
                             ('pressed', self.colors['accent'])])
        
        style.configure("Modelo.TButton",
                        background=self.colors['success'],
                        foreground=self.colors['foreground'],
                        font=("Segoe UI", 10),
                        borderwidth=0,
                        focuscolor='none',
                        padding=(20, 10))
        style.map("Modelo.TButton",
                  background=[('active', self.colors['success_hover']),
                             ('pressed', self.colors['success'])])
        
        style.configure("TLabel",
                        background=self.colors['background'],
                        foreground=self.colors['foreground'],
                        font=("Segoe UI", 11))
        
        style.configure("Title.TLabel",
                        background=self.colors['background'],
                        foreground=self.colors['foreground'],
                        font=("Segoe UI", 24, "bold"))
        
        style.configure("Subtitle.TLabel",
                        background=self.colors['background'],
                        foreground=self.colors['text_secondary'],
                        font=("Segoe UI", 10))
        
        style.configure("SettingsBadge.TLabel",
                        background=self.colors['surface'],
                        foreground=self.colors['accent'],
                        font=("Segoe UI", 9),
                        padding=10,
                        relief="flat")

    def create_widgets(self):
        title_frame = ttk.Frame(self.root, style="TFrame")
        title_frame.pack(side=tk.TOP, fill=tk.X, padx=30, pady=(30, 10))
        
        titulo = ttk.Label(title_frame, text="TextifyVoice", style="Title.TLabel", anchor="center")
        titulo.pack(side=tk.TOP)
        
        subtitulo = ttk.Label(title_frame, text="Transcrição de áudio e vídeo com IA",
                             style="Subtitle.TLabel", anchor="center")
        subtitulo.pack(side=tk.TOP, pady=(5, 0))
        
        self.main_frame = ttk.Frame(self.root, style="TFrame")
        self.main_frame.pack(expand=True, fill=tk.BOTH, padx=30, pady=20)
        
        self.instruction_text = tk.StringVar(
            value="Selecione os arquivos de áudio ou vídeo para transcrever.")
        instruction_label = ttk.Label(
            self.main_frame, textvariable=self.instruction_text,
            wraplength=650, style="TLabel", justify="center")
        instruction_label.pack(pady=(0, 20))
        
        badge_frame = ttk.Frame(self.main_frame, style="TFrame")
        badge_frame.pack(pady=(0, 25))
        
        badge = ttk.Label(badge_frame, textvariable=self.settings_badge_var,
                         style="SettingsBadge.TLabel")
        badge.pack()
        
        button_row = ttk.Frame(self.main_frame, style="TFrame")
        button_row.pack()
        
        self.btn_select = ttk.Button(button_row, text="Selecionar Arquivos",
                                     command=self.show_file_selection_window, style="TButton")
        self.btn_select.grid(row=0, column=0, padx=8, pady=8)
        
        self.btn_quality = ttk.Button(button_row, text="Selecionar Qualidade",
                                      command=self.show_quality_selection_window, style="Modelo.TButton")
        self.btn_quality.grid(row=0, column=1, padx=8, pady=8)
        
        self.btn_settings = ttk.Button(button_row, text="Configurações Avançadas",
                                       command=self.show_advanced_settings_window, style="TButton")
        self.btn_settings.grid(row=1, column=0, columnspan=2, padx=8, pady=8, sticky="ew")
        
        self.update_settings_badge()

    def show_file_selection_window(self):
        if self.transcription_window and self.transcription_window.winfo_exists():
            self.transcription_window.lift()
            return
        self.transcription_window = TranscriptionWindow(self)

    def show_quality_selection_window(self):
        if hasattr(self, 'quality_window') and self.quality_window and self.quality_window.winfo_exists():
            self.quality_window.lift()
            return
        self.quality_window = QualitySelectionWindow(self)

    def show_advanced_settings_window(self):
        if self.settings_window and self.settings_window.window.winfo_exists():
            self.settings_window.window.lift()
            return
        self.settings_window = AdvancedSettingsWindow(self, self.settings)

    def update_settings_badge(self):
        summary = self.settings.summary()
        self.settings_badge_var.set(f"{summary}")

    def show_loading_window(self):
        self.loading_window = tk.Toplevel(self.root)
        self.loading_window.title("Carregando")
        self.loading_window.geometry("450x220")
        self.loading_window.configure(bg=self.colors['background'])
        self.loading_window.overrideredirect(True)
        self.loading_window.grab_set()
        
        if os.path.exists(self.config.ICON_PATH):
            self.loading_window.iconbitmap(self.config.ICON_PATH)
        
        self.root.update_idletasks()
        width = 450
        height = 220
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.loading_window.geometry(f"{width}x{height}+{x}+{y}")
        
        style = ttk.Style()
        style.configure("Loading.TFrame", background=self.colors['background'])
        style.configure("Loading.TLabel",
                       background=self.colors['background'],
                       foreground=self.colors['foreground'],
                       font=("Segoe UI", 12))
        
        main_frame = ttk.Frame(self.loading_window, style="Loading.TFrame", padding=30)
        main_frame.pack(expand=True, fill=tk.BOTH)
        
        progress_bar = ttk.Progressbar(main_frame, mode='indeterminate', length=300)
        progress_bar.pack(pady=(0, 25))
        progress_bar.start(10)
        
        label = ttk.Label(main_frame,
                         text="Carregando configurações iniciais,\npor favor aguarde...",
                         style="Loading.TLabel",
                         wraplength=390,
                         justify='center')
        label.pack()
        
        self.loading_window.update_idletasks()

    def on_closing(self):
        self.transcription_manager.stop_event.set()
        self.root.destroy()

    def load_initial_configurations(self):
        try:
            self.check_initial_model()
        except Exception as e:
            logging.exception("Exceção ao carregar configurações iniciais")
            self.root.after(0, lambda: ErrorHandlers.handle_exception(e))
        finally:
            self.root.after(0, self.loading_window.destroy)
            self.root.after(0, self.root.deiconify)

    def run(self):
        self.show_loading_window()
        Thread(target=self.load_initial_configurations).start()
        self.root.mainloop()

    def check_initial_model(self):
        model_path = self.config.config.get('model_path')
        
        if not model_path:
            logging.info("Nenhum modelo configurado")
            self.root.after(0, self.show_quality_selection_window)
            return
        
        try:
            if not os.path.exists(model_path):
                logging.warning("Modelo configurado não encontrado")
                self.root.after(0, self.show_quality_selection_window)
                return
            
            if not self.transcription_manager.verify_model_file(model_path):
                logging.warning("Modelo configurado está corrompido")
                self.root.after(0, self.show_quality_selection_window)
                return
            
            self.transcription_manager.load_model(model_path)
            logging.info("Modelo inicial carregado com sucesso")
        except Exception as e:
            logging.exception("Erro ao carregar o modelo inicial")
            self.root.after(0, self.show_quality_selection_window)


class TranscriptionWindow:
    def __init__(self, main_gui):
        self.main_gui = main_gui
        self.window = tk.Toplevel(main_gui.root)
        
        if os.path.exists(self.main_gui.config.ICON_PATH):
            self.window.iconbitmap(self.main_gui.config.ICON_PATH)
        
        self.setup_window()
        self.create_widgets()
        self.current_item = None

    def setup_window(self):
        self.window.title("Seleção de Arquivos")
        self.window.geometry("800x500")
        self.window.minsize(700, 400)
        self.window.grab_set()
        self.window.configure(bg=self.main_gui.colors['background'])
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        toolbar_frame = ttk.Frame(self.window, style="TFrame")
        toolbar_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        
        self.btn_add = ttk.Button(toolbar_frame, text="Adicionar Arquivo",
                                  command=self.add_files, style="TButton")
        self.btn_add.pack(side=tk.LEFT)
        
        self.create_file_list()
        
        self.buttons_frame = ttk.Frame(self.window, style="TFrame")
        self.buttons_frame.pack(pady=20, padx=20, fill=tk.X)
        
        self.btn_start = ttk.Button(self.buttons_frame, text="Iniciar Transcrição",
                                    command=self.start_transcription, style="Modelo.TButton")
        self.btn_cancel = ttk.Button(self.buttons_frame, text="Cancelar",
                                     command=self.on_closing, style="TButton")
        
        self.btn_start.pack(side=tk.LEFT, padx=(0, 10), fill=tk.X, expand=True)
        self.btn_cancel.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def create_file_list(self):
        list_frame = ttk.Frame(self.window, style="TFrame")
        list_frame.pack(expand=True, fill='both', padx=20, pady=(0, 10))
        
        columns = ('Arquivo', 'Status', 'Transcrito')
        self.file_list = ttk.Treeview(list_frame, columns=columns, show='headings', height=12)
        
        self.file_list.heading('Arquivo', text='Arquivo')
        self.file_list.heading('Status', text='Status')
        self.file_list.heading('Transcrito', text='')
        
        self.file_list.column('Arquivo', width=450)
        self.file_list.column('Status', width=200)
        self.file_list.column('Transcrito', width=0, stretch=False)
        
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.file_list.yview)
        self.file_list.configure(yscrollcommand=scrollbar.set)
        
        self.file_list.pack(side=tk.LEFT, expand=True, fill='both')
        scrollbar.pack(side=tk.RIGHT, fill='y')
        
        self.file_list.bind("<Double-1>", self.open_file_location)

    def add_files(self):
        filepaths = filedialog.askopenfilenames(
            title="Escolha os arquivos de áudio ou vídeo para transcrever",
            filetypes=[
                ("Arquivos suportados", "*.mp4;*.mp3;*.wav;*.mkv;*.aac;*.flac;*.m4a;*.ogg"),
                ("Arquivos MP4", "*.mp4"),
                ("Arquivos MP3", "*.mp3"),
                ("Arquivos WAV", "*.wav"),
                ("Arquivos AAC", "*.aac"),
                ("Arquivos FLAC", "*.flac"),
                ("Arquivos M4A", "*.m4a"),
                ("Arquivos OGG", "*.ogg")
            ]
        )
        
        for filepath in filepaths:
            if not self.file_exists_in_list(filepath):
                self.file_list.insert('', 'end', values=(filepath, 'Preparado', ''))

    def file_exists_in_list(self, filepath):
        for item in self.file_list.get_children():
            if self.file_list.item(item)['values'][0] == filepath:
                return True
        return False

    def start_transcription(self):
        self.btn_start.config(state=tk.DISABLED)
        self.btn_add.config(state=tk.DISABLED)
        self.main_gui.transcription_manager.cancel_transcription = False
        self.main_gui.transcription_manager.is_transcribing = True
        
        thread = Thread(target=self.process_files)
        thread.daemon = True
        thread.start()

    def process_files(self):
        items = self.file_list.get_children()
        
        for item in items:
            if self.main_gui.transcription_manager.cancel_transcription:
                break
            
            values = self.file_list.item(item)['values']
            status = values[1]
            
            if status not in ['Finalizado', 'Cancelado', 'Erro']:
                self.current_item = item
                self.file_list.set(item, 'Status', 'Transcrição em progresso...')
                
                try:
                    filepath = values[0]
                    result_path = self.main_gui.transcription_manager.transcribe_file(
                        filepath,
                        lambda path: self.update_transcription_result(item, path),
                        settings=self.main_gui.settings
                    )
                    self.file_list.set(item, 'Status', 'Finalizado')
                    self.file_list.set(item, 'Transcrito', result_path)
                except ErrorHandlers.TranscriptionCancelledException:
                    self.file_list.set(item, 'Status', 'Cancelado')
                except Exception as e:
                    ErrorHandlers.handle_exception(e)
                    self.file_list.set(item, 'Status', 'Erro')
                finally:
                    self.current_item = None
        
        self.main_gui.transcription_manager.is_transcribing = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_add.config(state=tk.NORMAL)
        
        if not self.main_gui.transcription_manager.cancel_transcription:
            messagebox.showinfo("Concluído", "Todas as transcrições foram finalizadas!")
        else:
            messagebox.showinfo("Cancelado", "A transcrição foi cancelada pelo usuário.")
            self.main_gui.transcription_manager.cancel_transcription = False

    def update_transcription_result(self, item, path):
        self.file_list.set(item, 'Transcrito', path)

    def open_file_location(self, event):
        item = self.file_list.identify_row(event.y)
        if item:
            values = self.file_list.item(item)['values']
            if values[1] == 'Finalizado':
                transcribed_file = values[2]
                if os.path.exists(transcribed_file):
                    os.startfile(os.path.dirname(transcribed_file))
                else:
                    messagebox.showerror("Erro", "Arquivo transcrito não encontrado.")
            else:
                messagebox.showinfo("Info", "Arquivo ainda não foi transcrito.")

    def on_closing(self):
        if self.main_gui.transcription_manager.is_transcribing:
            if messagebox.askyesno("Confirmar", "Deseja realmente cancelar a transcrição em andamento?"):
                self.main_gui.transcription_manager.cancel_transcription = True
                transcription_process = self.main_gui.transcription_manager.transcription_process
                
                if transcription_process is not None and transcription_process.is_alive():
                    transcription_process.terminate()
                    transcription_process.join()
                    self.main_gui.transcription_manager.transcription_process = None
                
                if self.current_item:
                    self.file_list.set(self.current_item, 'Status', 'Cancelado')
                
                self.main_gui.transcription_manager.is_transcribing = False
            else:
                pass
        else:
            self.window.destroy()

    def winfo_exists(self):
        return self.window.winfo_exists()


class QualitySelectionWindow:
    def __init__(self, main_gui):
        self.main_gui = main_gui
        self.window = tk.Toplevel(main_gui.root)
        
        if os.path.exists(self.main_gui.config.ICON_PATH):
            self.window.iconbitmap(self.main_gui.config.ICON_PATH)
        
        self.setup_window()
        self.create_widgets()
        self.cancel_download = Event()

    def setup_window(self):
        self.window.title("Selecionar Qualidade")
        self.window.geometry("550x250")
        self.window.resizable(False, False)
        self.window.grab_set()
        self.window.configure(bg=self.main_gui.colors['background'])
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)

    def winfo_exists(self):
        return self.window.winfo_exists()

    def create_widgets(self):
        main_frame = ttk.Frame(self.window, style="TFrame", padding=30)
        main_frame.pack(expand=True, fill=tk.BOTH)
        
        label = ttk.Label(main_frame,
                         text="Escolha um dos modelos de transcrição:",
                         style="TLabel")
        label.pack(pady=(0, 20))
        
        model_path = self.main_gui.config.config.get('model_path', '')
        default_model_name = "medium"
        
        if model_path:
            default_model_name = os.path.splitext(os.path.basename(model_path))[0]
            if default_model_name not in self.main_gui.model_downloader.MODELS_URLS:
                default_model_name = "medium"
        
        self.quality_var = tk.StringVar(value=default_model_name)
        
        self.quality_dropdown = ttk.OptionMenu(
            main_frame,
            self.quality_var,
            self.quality_var.get(),
            *self.main_gui.model_downloader.MODELS_URLS.keys()
        )
        self.quality_dropdown.pack(pady=(0, 20), fill=tk.X)
        
        self.btn_download = ttk.Button(main_frame,
                                       text="Selecionar Modelo",
                                       command=self.download_model,
                                       style="Modelo.TButton")
        self.btn_download.pack(fill=tk.X)

    def lift(self):
        self.window.lift()

    def download_model(self):
        self.btn_download.config(state=tk.DISABLED)
        model_name = self.quality_var.get()
        
        progress_window = tk.Toplevel(self.window)
        progress_window.title("Baixando Modelo")
        progress_window.geometry("500x250")
        progress_window.resizable(False, False)
        progress_window.grab_set()
        progress_window.configure(bg=self.main_gui.colors['background'])
        
        if os.path.exists(self.main_gui.config.ICON_PATH):
            progress_window.iconbitmap(self.main_gui.config.ICON_PATH)
        
        progress_frame = ttk.Frame(progress_window, style="TFrame", padding=30)
        progress_frame.pack(expand=True, fill=tk.BOTH)
        
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(progress_frame, variable=progress_var, maximum=100, length=400)
        progress_bar.pack(pady=(0, 20), fill=tk.X)
        
        progress_label = ttk.Label(progress_frame,
                                   text="Baixando o modelo, por favor aguarde...",
                                   style="TLabel")
        progress_label.pack(pady=(0, 20))
        
        btn_cancel_download = ttk.Button(progress_frame,
                                        text="Cancelar Download",
                                        command=lambda: self.cancel_download_process(progress_window),
                                        style="TButton")
        btn_cancel_download.pack(fill=tk.X)
        
        progress_window.protocol("WM_DELETE_WINDOW",
                                lambda: self.cancel_download_process(progress_window))
        
        self.cancel_download.clear()

        def update_progress(progress):
            self.window.after(0, lambda: self._update_progress_ui(
                progress, progress_var, progress_label, progress_window))

        def download_thread():
            try:
                model_path = self.main_gui.model_downloader.download_model(
                    model_name, progress_callback=update_progress, cancel_event=self.cancel_download)
                
                if self.main_gui.transcription_manager.verify_model_file(model_path):
                    self.main_gui.config.config['model_path'] = model_path
                    self.main_gui.config.save_config()
                    
                    if progress_window.winfo_exists():
                        progress_window.destroy()
                    
                    messagebox.showinfo("Sucesso", "Modelo baixado e verificado com sucesso!")
                    
                    if self.window.winfo_exists():
                        self.window.destroy()
                else:
                    raise Exception("Falha na verificação final do modelo")
            except Exception as e:
                if progress_window.winfo_exists():
                    progress_window.destroy()
                
                if str(e) == "Download cancelado pelo usuário":
                    self.window.after(0, lambda: messagebox.showinfo(
                        "Cancelado", "O download foi cancelado pelo usuário."))
                else:
                    self.window.after(0, lambda e=e: messagebox.showerror(
                        "Erro", f"Erro ao baixar modelo: {str(e)}"))
                
                ErrorHandlers.handle_exception(e)
            finally:
                self.window.after(0, self.reenable_download_button)

        thread = Thread(target=download_thread)
        thread.start()

    def _update_progress_ui(self, progress, progress_var, progress_label, progress_window):
        if progress_window.winfo_exists():
            if isinstance(progress, (float, int)):
                progress_var.set(progress)
                progress_label.config(text=f"Baixando... {progress:.2f}%")
                if progress >= 100:
                    progress_label.config(text="Verificando integridade do arquivo...")
            else:
                progress_label.config(text=str(progress))

    def cancel_download_process(self, progress_window):
        if messagebox.askyesno("Confirmar", "Deseja mesmo cancelar o download?"):
            self.cancel_download.set()
            if progress_window.winfo_exists():
                progress_window.destroy()
            if self.window.winfo_exists():
                self.btn_download.config(state=tk.NORMAL)

    def reenable_download_button(self):
        if self.window.winfo_exists() and self.btn_download.winfo_exists():
            self.btn_download.config(state=tk.NORMAL)

    def on_closing(self):
        if messagebox.askyesno("Confirmar", "Deseja mesmo cancelar o download?"):
            self.cancel_download.set()
            if self.window.winfo_exists():
                self.window.destroy()


def main():
    app = GUI()
    app.run()


if __name__ == '__main__':
    freeze_support()
    main()