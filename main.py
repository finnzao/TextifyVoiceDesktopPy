import logging
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
from multiprocessing import Process, Queue

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)


class ErrorHandlers:
    class TranscriptionCancelledException(Exception):
        """Exceção para indicar cancelamento da transcrição."""
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
        messagebox.showerror(
            "Erro", f"Ocorreu um erro ao processar o arquivo: {str(e)}")

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
        messagebox.showerror(
            "Erro", f"Ocorreu um erro durante o download: {str(e)}")


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

    def resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
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

            if filepath.lower().endswith(('.mp3', '.wav', '.aac', '.flac', '.m4a', '.ogg')):
                return filepath

            output_path = os.path.join(temp_dir, "temp_audio.aac")
            output_path = os.path.abspath(output_path)

            command = [self.FFMPEG_PATH, '-i', filepath,
                       '-acodec', 'aac', output_path, '-y']
            result = subprocess.run(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

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
                logging.error(
                    f"Arquivo do modelo não encontrado: {model_path}")
                return False

            file_size = os.path.getsize(model_path)
            if file_size < 1000000:
                logging.error(
                    f"Arquivo do modelo parece estar incompleto: {file_size} bytes")
                return False

            device = "cuda" if torch.cuda.is_available() else "cpu"
            whisper.load_model(model_path, device=device)
            logging.info(f"Modelo verificado com sucesso: {model_path}")
            return True
        except Exception as e:
            ErrorHandlers.handle_exception(e)
            try:
                os.remove(model_path)
                logging.info(
                    f"Arquivo de modelo corrompido removido: {model_path}")
            except Exception as del_e:
                ErrorHandlers.handle_exception(del_e)
            return False

    def transcribe_file(self, filepath, output_callback=None):
        try:
            model_path = self.config.config['model_path']
            if not model_path:
                raise Exception("Caminho do modelo não definido")

            result_queue = Queue()
            self.transcription_process = Process(
                target=self.transcribe_file_process,
                args=(
                    model_path,
                    self.config.config,
                    filepath,
                    self.config.TEMP_DIR,
                    result_queue
                )
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
                    raise ErrorHandlers.TranscriptionCancelledException(
                        "Transcrição cancelada pelo usuário")

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
                raise Exception(
                    "Processo de transcrição não retornou nenhum resultado.")

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
    def transcribe_file_process(model_path, config_dict, filepath, temp_dir, result_queue):
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model = whisper.load_model(model_path, device=device)

            config = Config()
            config.config = config_dict
            audio_processor = AudioProcessor(config)

            audio_path = audio_processor.extract_audio(
                filepath, temp_dir)
            result = model.transcribe(audio_path, language="pt")

            nome_arquivo = os.path.splitext(os.path.basename(filepath))[0]
            local_salvamento = os.path.join(os.path.dirname(
                filepath), nome_arquivo + "_text.docx")

            doc = Document()
            for segment in result["segments"]:
                doc.add_paragraph(segment["text"])
            doc.save(local_salvamento)

            if audio_path != filepath:
                os.remove(audio_path)

            result_queue.put({'output_path': local_salvamento})
        except Exception as e:
            result_queue.put({'error': str(e)})


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
            # GPU ou CPU
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
                    logging.info(
                        f"Modelo já existe e está válido: {caminho_modelo}")
                    return caminho_modelo
                else:
                    os.remove(caminho_modelo)
                    logging.info(
                        f"Modelo corrompido removido: {caminho_modelo}")
            except Exception as e:
                ErrorHandlers.handle_exception(e)
                os.remove(caminho_modelo)

        max_tentativas = 3
        for tentativa in range(max_tentativas):
            try:
                session = requests.Session()
                response = session.get(url, stream=True)
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))
                block_size = 1048576  # 1 MB

                with open(caminho_modelo, 'wb') as f:
                    downloaded = 0
                    start_time = time.time()
                    for data in response.iter_content(block_size):
                        if cancel_event and cancel_event.is_set():
                            raise Exception("Download cancelado pelo usuário")
                        f.write(data)
                        downloaded += len(data)
                        if progress_callback and total_size > 0:
                            progress = (downloaded / total_size) * 100
                            progress_callback(progress)
                        else:
                            # Se o tamanho total não for conhecido
                            elapsed_time = time.time() - start_time
                            speed = downloaded / elapsed_time if elapsed_time > 0 else 0
                            progress_callback(
                                f"Baixado {downloaded} bytes a {speed:.2f} bytes/s")
                    else:
                        progress_callback(100)
                session.close()

                if self.verify_download(caminho_modelo, total_size):
                    logging.info(
                        f"Download do modelo concluído com sucesso: {caminho_modelo}")
                    return caminho_modelo
                else:
                    raise Exception(
                        "Arquivo baixado está corrompido ou incompleto")

            except requests.RequestException as e:
                ErrorHandlers.handle_download_error(e)
                if os.path.exists(caminho_modelo):
                    os.remove(caminho_modelo)
                if tentativa == max_tentativas - 1:
                    raise Exception(
                        f"Falha após {max_tentativas} tentativas de download")
                continue
            except Exception as e:
                ErrorHandlers.handle_download_error(e)
                if os.path.exists(caminho_modelo):
                    os.remove(caminho_modelo)
                if str(e) == "Download cancelado pelo usuário":
                    raise e
                if tentativa == max_tentativas - 1:
                    raise Exception(
                        f"Falha após {max_tentativas} tentativas de download")
                continue


class GUI:
    """Classe principal da interface gráfica"""

    def __init__(self):
        self.config = Config()
        self.audio_processor = AudioProcessor(self.config)
        self.transcription_manager = TranscriptionManager(
            self.config, self.audio_processor)
        self.model_downloader = ModelDownloader(self.config)

        self.root = tk.Tk()
        self.root.withdraw()  # Oculta a janela principal inicialmente
        self.setup_main_window()
        self.setup_styles()
        self.create_widgets()

        self.transcription_window = None
        self.quality_window = None
        self.model_window = None

    def setup_main_window(self):
        self.root.title("TextifyVoice [ 1.0 ] by@felipe.sh")
        self.root.geometry("650x500")
        if os.path.exists(self.config.ICON_PATH):
            self.root.iconbitmap(self.config.ICON_PATH)
        self.root.configure(bg="#343a40")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')

        self.colors = {
            'background': "#343a40",
            'foreground': "#f8f9fa",
            'accent': "#007bff",
            'model': "#28a745"
        }

        style.configure("TFrame", background=self.colors['background'])
        style.configure("TButton",
                        background=self.colors['accent'],
                        foreground=self.colors['foreground'],
                        font=("Arial", 10, "bold"),
                        borderwidth=1,
                        relief="flat")
        style.configure("Modelo.TButton",
                        background=self.colors['model'],
                        foreground=self.colors['foreground'],
                        font=("Arial", 10, "bold"),
                        borderwidth=1,
                        relief="flat")
        style.configure("TLabel",
                        background=self.colors['background'],
                        foreground=self.colors['foreground'],
                        font=("Arial", 12))
        style.configure("Title.TLabel",
                        background=self.colors['background'],
                        foreground=self.colors['foreground'],
                        font=("Arial", 16, "bold"))

    def create_widgets(self):
        title_frame = ttk.Frame(self.root, style="TFrame", height=70)
        title_frame.pack(side=tk.TOP, fill=tk.X)
        title_frame.pack_propagate(False)

        titulo = ttk.Label(title_frame, text="TextifyVoice",
                           style="Title.TLabel", anchor="center")
        titulo.pack(side=tk.TOP, fill=tk.X, pady=20)

        self.main_frame = ttk.Frame(self.root, style="TFrame")
        self.main_frame.pack(expand=True, fill=tk.BOTH, padx=20, pady=20)

        self.instruction_text = tk.StringVar(
            value="Selecione os arquivos de áudio ou vídeo para transcrever.")
        instruction_label = ttk.Label(self.main_frame,
                                      textvariable=self.instruction_text,
                                      wraplength=650,
                                      style="TLabel")
        instruction_label.pack()

        self.btn_select = ttk.Button(self.main_frame,
                                     text="Selecionar Arquivos",
                                     command=self.show_file_selection_window,
                                     style="TButton")
        self.btn_select.pack(pady=(10, 0))

        self.btn_quality = ttk.Button(self.main_frame,
                                      text="Selecionar Qualidade",
                                      command=self.show_quality_selection_window,
                                      style="Modelo.TButton")
        self.btn_quality.pack(pady=(10, 0))

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

    def show_loading_window(self):
        self.loading_window = tk.Toplevel(self.root)
        self.loading_window.title("Carregando")
        self.loading_window.geometry("400x200")
        self.loading_window.configure(bg=self.colors['background'])
        self.loading_window.overrideredirect(True)
        self.loading_window.grab_set()

        if os.path.exists(self.config.ICON_PATH):
            self.loading_window.iconbitmap(self.config.ICON_PATH)

        # Centraliza a janela no meio da tela
        self.root.update_idletasks()
        width = 400
        height = 200
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.loading_window.geometry(f"{width}x{height}+{x}+{y}")

        # Cria um estilo personalizado para a janela de carregamento
        style = ttk.Style()
        style.configure("Loading.TFrame", background=self.colors['background'])
        style.configure("Loading.TLabel",
                        background=self.colors['background'],
                        foreground=self.colors['foreground'],
                        font=("Helvetica", 13))

        main_frame = ttk.Frame(self.loading_window,
                               style="Loading.TFrame", padding=20)
        main_frame.pack(expand=True, fill=tk.BOTH)

        progress_bar = ttk.Progressbar(
            main_frame,
            mode='indeterminate',
            length=200
        )
        progress_bar.pack(pady=(0, 20))

        progress_bar.start(10)

        label = ttk.Label(
            main_frame,
            text="Carregando configurações iniciais, por favor aguarde...",
            style="Loading.TLabel",
            wraplength=360,
            justify='center',
        )

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
            self.root.after(0, self.root.deiconify)  # Sem parênteses

    def run(self):
        self.show_loading_window()
        Thread(target=self.load_initial_configurations).start()
        self.root.mainloop()

    def check_initial_model(self):
        model_path = self.config.config.get('model_path')
        if model_path:
            model_valid = False
            try:
                if not os.path.exists(model_path):
                    logging.warning("Modelo configurado não encontrado")
                elif not self.transcription_manager.verify_model_file(model_path):
                    logging.warning("Modelo configurado está corrompido")
                else:
                    self.transcription_manager.load_model(model_path)
                    logging.info("Modelo inicial carregado com sucesso")
                    model_valid = True
            except Exception as e:
                logging.exception("Erro ao carregar o modelo inicial")
                model_valid = False
            if not model_valid:
                self.root.after(0, self.show_quality_selection_window)
        else:
            logging.info("Nenhum modelo configurado")
            self.root.after(0, self.show_quality_selection_window)


class TranscriptionWindow:
    """Janela de seleção e transcrição de arquivos"""

    def __init__(self, main_gui):
        self.main_gui = main_gui
        self.window = tk.Toplevel(main_gui.root)

        # Definir o ícone da janela
        if os.path.exists(self.main_gui.config.ICON_PATH):
            self.window.iconbitmap(self.main_gui.config.ICON_PATH)

        self.setup_window()
        self.create_widgets()
        self.current_item = None

    def setup_window(self):
        self.window.title("Seleção de Arquivos")
        self.window.geometry("700x400")
        self.window.grab_set()
        self.window.configure(bg=self.main_gui.colors['background'])
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        self.btn_add = ttk.Button(self.window,
                                  text="Adicionar Arquivo",
                                  command=self.add_files,
                                  style="Selecao.TButton")
        self.btn_add.pack(pady=10)

        self.create_file_list()

        self.buttons_frame = ttk.Frame(self.window, style="Selecao.TFrame")
        self.buttons_frame.pack(pady=10)

        self.btn_start = ttk.Button(self.buttons_frame,
                                    text="Iniciar Transcrição",
                                    command=self.start_transcription,
                                    style="Selecao.TButton")
        self.btn_cancel = ttk.Button(self.buttons_frame,
                                     text="Cancelar",
                                     command=self.on_closing,
                                     style="Selecao.TButton")
        self.btn_start.pack(side=tk.LEFT, padx=5)
        self.btn_cancel.pack(side=tk.LEFT, padx=5)

    def create_file_list(self):
        columns = ('Arquivo', 'Status', 'Transcrito')
        self.file_list = ttk.Treeview(
            self.window, columns=columns, show='headings')

        self.file_list.heading('Arquivo', text='Arquivo')
        self.file_list.heading('Status', text='Status')
        self.file_list.heading('Transcrito', text='')

        self.file_list.column('Arquivo', width=400)
        self.file_list.column('Status', width=150)
        self.file_list.column('Transcrito', width=0, stretch=False)

        self.file_list.pack(expand=True, fill='both')
        self.file_list.bind("<Double-1>", self.open_file_location)

    def add_files(self):
        filepaths = filedialog.askopenfilenames(
            title="Escolha os arquivos de áudio ou vídeo para transcrever",
            filetypes=[
                ("Arquivos suportados",
                 "*.mp4;*.mp3;*.wav;*.mkv;*.aac;*.flac;*.m4a;*.ogg"),
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
                self.file_list.insert(
                    '', 'end', values=(filepath, 'Preparado', ''))

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
                self.file_list.set(
                    item, 'Status', 'Transcrição em progresso...')
                try:
                    filepath = values[0]
                    result_path = self.main_gui.transcription_manager.transcribe_file(
                        filepath,
                        lambda path: self.update_transcription_result(
                            item, path)
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
            messagebox.showinfo(
                "Concluído", "Todas as transcrições foram finalizadas!")
        else:
            messagebox.showinfo(
                "Cancelado", "A transcrição foi cancelada pelo usuário.")
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
                    messagebox.showerror(
                        "Erro", "Arquivo transcrito não encontrado.")
            else:
                messagebox.showinfo(
                    "Info", "Arquivo ainda não foi transcrito.")

    def on_closing(self):
        if self.main_gui.transcription_manager.is_transcribing:
            if messagebox.askyesno("Confirmar",
                                   "Deseja realmente cancelar a transcrição em andamento?"):
                self.main_gui.transcription_manager.cancel_transcription = True
                transcription_process = self.main_gui.transcription_manager.transcription_process
                if transcription_process is not None and transcription_process.is_alive():
                    transcription_process.terminate()
                    transcription_process.join()
                    self.main_gui.transcription_manager.transcription_process = None
                if self.current_item:
                    self.file_list.set(self.current_item,
                                       'Status', 'Cancelado')
                self.main_gui.transcription_manager.is_transcribing = False
            else:
                pass
        else:
            self.window.destroy()

    def winfo_exists(self):
        return self.window.winfo_exists()


class QualitySelectionWindow:
    """Janela de seleção de qualidade do modelo"""

    def __init__(self, main_gui):
        self.main_gui = main_gui
        self.window = tk.Toplevel(main_gui.root)

        # Definir o ícone da janela
        if os.path.exists(self.main_gui.config.ICON_PATH):
            self.window.iconbitmap(self.main_gui.config.ICON_PATH)

        self.setup_window()
        self.create_widgets()
        self.cancel_download = Event()

    def setup_window(self):
        self.window.title("Selecionar Qualidade")
        self.window.geometry("500x200")
        self.window.grab_set()
        self.window.configure(bg=self.main_gui.colors['background'])
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)

    def winfo_exists(self):
        return self.window.winfo_exists()

    def create_widgets(self):
        label = ttk.Label(self.window,
                          text="Escolha um dos modelos de transcrição:",
                          style="TLabel")
        label.pack(pady=20)

        model_path = self.main_gui.config.config.get('model_path', '')
        default_model_name = "medium"  # Padrão caso não encontre

        if model_path:
            default_model_name = os.path.splitext(
                os.path.basename(model_path))[0]
            # Verificar se o nome está nas opções disponíveis
            if default_model_name not in self.main_gui.model_downloader.MODELS_URLS:
                default_model_name = "medium"

        self.quality_var = tk.StringVar(value=default_model_name)
        self.quality_dropdown = ttk.OptionMenu(
            self.window,
            self.quality_var,
            self.quality_var.get(),
            *self.main_gui.model_downloader.MODELS_URLS.keys()
        )
        self.quality_dropdown.pack(pady=10)

        self.btn_download = ttk.Button(
            self.window,
            text="Selecionar Modelo",
            command=self.download_model,
            style="TButton"
        )
        self.btn_download.pack(pady=10)

    def lift(self):
        self.window.lift()

    def download_model(self):
        self.btn_download.config(state=tk.DISABLED)
        model_name = self.quality_var.get()

        progress_window = tk.Toplevel(self.window)
        progress_window.title("Baixando Modelo")
        progress_window.geometry("400x200")
        progress_window.resizable(False, False)
        progress_window.grab_set()

        # Definir o ícone da janela de progresso
        if os.path.exists(self.main_gui.config.ICON_PATH):
            progress_window.iconbitmap(self.main_gui.config.ICON_PATH)

        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(
            progress_window,
            variable=progress_var,
            maximum=100
        )
        progress_bar.pack(pady=20, padx=20, fill=tk.X)

        progress_label = ttk.Label(
            progress_window,
            text="Baixando o modelo, por favor aguarde..."
        )
        progress_label.pack(pady=5)

        btn_cancel_download = ttk.Button(
            progress_window,
            text="Cancelar Download",
            command=lambda: self.cancel_download_process(progress_window)
        )
        btn_cancel_download.pack(pady=10)

        progress_window.protocol(
            "WM_DELETE_WINDOW", lambda: self.cancel_download_process(progress_window))

        self.cancel_download.clear()

        def update_progress(progress):
            self.window.after(0, lambda: self._update_progress_ui(
                progress, progress_var, progress_label, progress_window))

        def download_thread():
            try:
                model_path = self.main_gui.model_downloader.download_model(
                    model_name,
                    progress_callback=update_progress,
                    cancel_event=self.cancel_download
                )

                if self.main_gui.transcription_manager.verify_model_file(model_path):
                    self.main_gui.config.config['model_path'] = model_path
                    self.main_gui.config.save_config()
                    if progress_window.winfo_exists():
                        progress_window.destroy()
                    messagebox.showinfo(
                        "Sucesso", "Modelo baixado e verificado com sucesso!")
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
            progress_var.set(progress)
            progress_label.config(text=f"Baixando... {progress:.2f}%")
            if progress >= 100:
                progress_label.config(
                    text="Verificando integridade do arquivo...")

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


if __name__ == "__main__":
    main()
