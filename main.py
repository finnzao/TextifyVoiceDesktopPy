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


def set_app_id():
    """Define o AppUserModelID para exibir o ícone correto na barra de tarefas do Windows"""
    if system() == 'Windows':
        try:
            from ctypes import windll
            myappid = 'com.felipesh.textifyvoice.1.0'
            windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception as e:
            logging.warning(f"Não foi possível definir AppUserModelID: {e}")


class NoConsolePopen(subprocess.Popen):
    """Evita que janelas de console apareçam ao executar subprocessos no Windows"""
    def __init__(self, args, **kwargs):
        if system() == 'Windows' and 'startupinfo' not in kwargs:
            kwargs['startupinfo'] = subprocess.STARTUPINFO()
            kwargs['startupinfo'].dwFlags |= subprocess.STARTF_USESHOWWINDOW
        super().__init__(args, **kwargs)

subprocess.Popen = NoConsolePopen


class ErrorHandlers:
    """Centralizador de tratamento de erros com mensagens amigáveis"""
    
    class TranscriptionCancelledException(Exception):
        """Exceção lançada quando o usuário cancela a transcrição"""
        pass

    @staticmethod
    def handle_exception(e):
        """Tratamento genérico de exceções com log"""
        error_msg = str(e)
        logging.error(f"Erro: {error_msg}", exc_info=True)
        return error_msg

    @staticmethod
    def handle_file_not_found(e):
        """Tratamento de erros de arquivo não encontrado"""
        error_msg = f"Arquivo não encontrado: {str(e)}"
        logging.error(error_msg)
        messagebox.showerror(
            "Arquivo Não Encontrado", 
            f"{error_msg}\n\nVerifique se o arquivo existe e se você tem permissão para acessá-lo."
        )
        return error_msg

    @staticmethod
    def handle_subprocess_error(e):
        """Tratamento de erros em subprocessos (FFmpeg)"""
        error_msg = f"Erro ao processar arquivo: {str(e)}"
        logging.error(error_msg, exc_info=True)
        messagebox.showerror(
            "Erro de Processamento", 
            f"Ocorreu um erro ao processar o arquivo de áudio/vídeo.\n\n"
            f"Detalhes técnicos:\n{str(e)}\n\n"
            f"Possíveis soluções:\n"
            f"• Verifique se o arquivo não está corrompido\n"
            f"• Tente converter o arquivo para um formato diferente\n"
            f"• Verifique se o FFmpeg está instalado corretamente"
        )
        return error_msg

    @staticmethod
    def handle_generic_error(e):
        """Tratamento de erros genéricos"""
        error_msg = f"Erro inesperado: {str(e)}"
        logging.error(error_msg, exc_info=True)
        messagebox.showerror(
            "Erro Inesperado", 
            f"Ocorreu um erro inesperado durante a operação.\n\n"
            f"Detalhes: {str(e)}\n\n"
            f"Por favor, verifique o arquivo de log para mais informações."
        )
        return error_msg

    @staticmethod
    def handle_model_load_error(e):
        """Tratamento de erros ao carregar o modelo"""
        error_msg = f"Erro ao carregar o modelo: {str(e)}"
        logging.error(error_msg, exc_info=True)
        messagebox.showerror(
            "Erro ao Carregar Modelo", 
            f"Não foi possível carregar o modelo de transcrição.\n\n"
            f"Detalhes: {str(e)}\n\n"
            f"Possíveis soluções:\n"
            f"• Faça o download do modelo novamente\n"
            f"• Verifique se há espaço em disco suficiente\n"
            f"• Verifique se o arquivo do modelo não está corrompido"
        )
        return error_msg

    @staticmethod
    def handle_download_error(e):
        """Tratamento de erros durante download"""
        error_msg = f"Erro no download: {str(e)}"
        logging.error(error_msg, exc_info=True)
        messagebox.showerror(
            "Erro no Download", 
            f"Ocorreu um erro durante o download do modelo.\n\n"
            f"Detalhes: {str(e)}\n\n"
            f"Possíveis soluções:\n"
            f"• Verifique sua conexão com a internet\n"
            f"• Tente novamente em alguns minutos\n"
            f"• Verifique se há espaço em disco suficiente"
        )
        return error_msg

    @staticmethod
    def handle_ffmpeg_not_found():
        """Tratamento específico para FFmpeg não encontrado"""
        error_msg = "FFmpeg não encontrado no sistema"
        logging.error(error_msg)
        messagebox.showerror(
            "FFmpeg Não Encontrado",
            "O FFmpeg é necessário para processar arquivos de vídeo.\n\n"
            "O programa procurou nos seguintes locais:\n"
            "• Pasta raiz da aplicação\n"
            "• Pasta ./ffmpeg\n"
            "• Pasta ./bin\n"
            "• PATH do sistema\n\n"
            "Soluções:\n"
            "1. Baixe o FFmpeg em: https://ffmpeg.org/download.html\n"
            "2. Extraia o arquivo ffmpeg.exe (Windows) ou ffmpeg (Linux/Mac)\n"
            "3. Coloque em uma das pastas acima\n\n"
            "OU\n\n"
            "Instale o FFmpeg no sistema e adicione ao PATH."
        )
        return error_msg

    @staticmethod
    def handle_permission_error(e):
        """Tratamento de erros de permissão"""
        error_msg = f"Erro de permissão: {str(e)}"
        logging.error(error_msg)
        messagebox.showerror(
            "Erro de Permissão",
            f"Não foi possível acessar o arquivo ou pasta.\n\n"
            f"Detalhes: {str(e)}\n\n"
            f"Possíveis soluções:\n"
            f"• Execute o programa como administrador\n"
            f"• Verifique se o arquivo não está aberto em outro programa\n"
            f"• Verifique as permissões da pasta"
        )
        return error_msg

    @staticmethod
    def handle_disk_space_error():
        """Tratamento de erro de espaço em disco"""
        error_msg = "Espaço em disco insuficiente"
        logging.error(error_msg)
        messagebox.showerror(
            "Espaço em Disco Insuficiente",
            "Não há espaço suficiente no disco para completar a operação.\n\n"
            "Possíveis soluções:\n"
            "• Libere espaço em disco\n"
            "• Escolha um local diferente para salvar o arquivo\n"
            "• Remova arquivos temporários desnecessários"
        )
        return error_msg


def is_production():
    """Verifica se está rodando em ambiente de produção (empacotado)"""
    return hasattr(sys, '_MEIPASS')


class Config:
    """Gerenciador de configurações e recursos da aplicação"""
    
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
        """Obtém o caminho absoluto para recursos, funciona tanto em dev quanto em produção"""
        try:
            base_path = sys._MEIPASS
        except AttributeError:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def load_config(self):
        """Carrega configurações do arquivo JSON"""
        if not os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'w') as f:
                    json.dump(self.DEFAULT_CONFIG, f, indent=4)
            except Exception as e:
                logging.warning(f"Não foi possível criar arquivo de configuração: {e}")
                return self.DEFAULT_CONFIG.copy()
        
        try:
            with open(self.CONFIG_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError as e:
            ErrorHandlers.handle_file_not_found(e)
            return self.DEFAULT_CONFIG.copy()
        except json.JSONDecodeError as e:
            logging.error(f"Erro ao ler configurações: {e}")
            return self.DEFAULT_CONFIG.copy()

    def save_config(self):
        """Salva configurações no arquivo JSON"""
        try:
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            ErrorHandlers.handle_exception(e)

    def setup_logging(self):
        """Configura o sistema de logging com rotação de arquivos"""
        try:
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
        except Exception as e:
            print(f"Erro ao configurar logging: {e}")


class AudioProcessor:
    """Processador de áudio/vídeo usando FFmpeg"""
    
    AUDIO_EXTENSIONS = ('.mp3', '.wav', '.aac', '.flac', '.m4a', '.ogg')
    
    def __init__(self, config):
        self.config = config
        self.FFMPEG_EXECUTABLE = 'ffmpeg.exe' if system() == 'Windows' else 'ffmpeg'
        self.FFMPEG_PATH = self._find_ffmpeg()

    def _find_ffmpeg(self):
        """Procura o FFmpeg em diferentes locais possíveis"""
        possible_locations = [
            # 1. Pasta raiz
            os.path.join(os.path.dirname(__file__), self.FFMPEG_EXECUTABLE),
            # 2. Pasta ./ffmpeg
            os.path.join(os.path.dirname(__file__), 'ffmpeg', self.FFMPEG_EXECUTABLE),
            # 3. Pasta ./bin
            os.path.join(os.path.dirname(__file__), 'bin', self.FFMPEG_EXECUTABLE),
            # 4. Pasta do executável empacotado
            self.config.resource_path(self.FFMPEG_EXECUTABLE),
            # 5. Pasta ffmpeg dentro do executável empacotado
            self.config.resource_path(os.path.join('ffmpeg', self.FFMPEG_EXECUTABLE)),
            # 6. Pasta bin dentro do executável empacotado
            self.config.resource_path(os.path.join('bin', self.FFMPEG_EXECUTABLE)),
        ]
        
        # Verifica em cada local possível
        for path in possible_locations:
            if os.path.exists(path):
                logging.info(f"FFmpeg encontrado em: {path}")
                return path
        
        # Tenta encontrar no PATH do sistema
        try:
            result = subprocess.run(
                ['where' if system() == 'Windows' else 'which', 'ffmpeg'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                system_path = result.stdout.strip().split('\n')[0]
                if os.path.exists(system_path):
                    logging.info(f"FFmpeg encontrado no PATH: {system_path}")
                    return system_path
        except Exception as e:
            logging.warning(f"Erro ao procurar FFmpeg no PATH: {e}")
        
        # Se não encontrou em lugar nenhum, retorna o caminho esperado na raiz
        logging.warning("FFmpeg não encontrado em nenhum local")
        return os.path.join(os.path.dirname(__file__), self.FFMPEG_EXECUTABLE)

    def check_ffmpeg_available(self):
        """Verifica se o FFmpeg está disponível e funcional"""
        try:
            result = subprocess.run(
                [self.FFMPEG_PATH, '-version'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False
        except Exception as e:
            logging.warning(f"Erro ao verificar FFmpeg: {e}")
            return False

    def extract_audio(self, filepath, temp_dir):
        """Extrai áudio de arquivo de vídeo ou copia arquivo de áudio"""
        try:
            # Verifica se FFmpeg está disponível
            if not self.check_ffmpeg_available():
                ErrorHandlers.handle_ffmpeg_not_found()
                raise FileNotFoundError("FFmpeg não encontrado")
            
            # Cria diretório temporário se não existir
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
            else:
                self.clean_temp_dir(temp_dir)
            
            # Se já é um arquivo de áudio, retorna diretamente
            if filepath.lower().endswith(self.AUDIO_EXTENSIONS):
                logging.info(f"Arquivo já é de áudio, não precisa extrair: {filepath}")
                return filepath
            
            # Extrai áudio do vídeo
            output_path = os.path.abspath(os.path.join(temp_dir, "temp_audio.aac"))
            command = [
                self.FFMPEG_PATH,
                '-i', filepath,
                '-acodec', 'aac',
                '-vn',  # Remove vídeo
                '-y',  # Sobrescreve arquivo existente
                output_path
            ]
            
            logging.info(f"Executando FFmpeg: {' '.join(command)}")
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=300  # Timeout de 5 minutos
            )
            
            if result.returncode != 0:
                error_output = result.stderr.decode('utf-8', errors='ignore')
                logging.error(f"Erro do FFmpeg: {error_output}")
                raise subprocess.CalledProcessError(
                    result.returncode,
                    command,
                    stderr=error_output
                )
            
            if not os.path.exists(output_path):
                raise FileNotFoundError(f"Arquivo de áudio não foi criado: {output_path}")
            
            logging.info(f"Áudio extraído com sucesso: {output_path}")
            return output_path
            
        except FileNotFoundError as e:
            ErrorHandlers.handle_file_not_found(e)
            raise
        except subprocess.CalledProcessError as e:
            ErrorHandlers.handle_subprocess_error(e)
            raise
        except PermissionError as e:
            ErrorHandlers.handle_permission_error(e)
            raise
        except subprocess.TimeoutExpired:
            error_msg = "Timeout ao processar arquivo (operação demorou mais de 5 minutos)"
            logging.error(error_msg)
            messagebox.showerror("Timeout", error_msg)
            raise Exception(error_msg)
        except Exception as e:
            ErrorHandlers.handle_generic_error(e)
            raise

    def clean_temp_dir(self, temp_dir):
        """Limpa diretório temporário"""
        try:
            for filename in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    logging.warning(f"Erro ao limpar arquivo temporário {file_path}: {e}")
        except Exception as e:
            logging.warning(f"Erro ao limpar diretório temporário: {e}")


class TranscriptionManager:
    """Gerenciador de transcrições usando Whisper"""
    
    def __init__(self, config, audio_processor):
        self.config = config
        self.audio_processor = audio_processor
        self.model = None
        self.stop_event = Event()
        self.is_transcribing = False
        self.cancel_transcription = False
        self.transcription_process = None
        self.default_settings = TranscriptionSettings()
        self.progress_callback = None  # Callback para atualizar progresso na UI

    def load_model(self, model_path):
        """Carrega o modelo Whisper"""
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
        """Verifica se o arquivo do modelo é válido"""
        try:
            if not os.path.exists(model_path):
                logging.error(f"Arquivo do modelo não encontrado: {model_path}")
                return False
            
            file_size = os.path.getsize(model_path)
            if file_size < 1000000:  # Menor que 1MB
                logging.error(f"Arquivo do modelo parece estar incompleto: {file_size} bytes")
                return False
            
            # Tenta carregar o modelo para verificar integridade
            device = "cuda" if torch.cuda.is_available() else "cpu"
            whisper.load_model(model_path, device=device)
            logging.info(f"Modelo verificado com sucesso: {model_path}")
            return True
            
        except Exception as e:
            logging.error(f"Erro ao verificar modelo: {e}")
            try:
                os.remove(model_path)
                logging.info(f"Arquivo de modelo corrompido removido: {model_path}")
            except Exception as del_e:
                logging.error(f"Erro ao remover modelo corrompido: {del_e}")
            return False

    def transcribe_file(self, filepath, output_callback=None, settings=None, progress_callback=None):
        """Transcreve um arquivo de áudio/vídeo"""
        try:
            self.progress_callback = progress_callback
            model_path = self.config.config['model_path']
            if not model_path:
                raise Exception("Caminho do modelo não definido. Por favor, selecione um modelo primeiro.")
            
            if not os.path.exists(filepath):
                raise FileNotFoundError(f"Arquivo não encontrado: {filepath}")
            
            # Prepara configurações
            settings_obj = settings or self.default_settings
            if isinstance(settings_obj, TranscriptionSettings):
                settings_dict = settings_obj.to_dict()
            elif isinstance(settings_obj, dict):
                settings_dict = settings_obj
            else:
                raise TypeError("Configurações de transcrição inválidas")
            
            # Inicia processo de transcrição
            result_queue = Queue()
            progress_queue = Queue()
            
            self.transcription_process = Process(
                target=self.transcribe_file_process,
                args=(model_path, self.config.config, filepath, self.config.TEMP_DIR, 
                      settings_dict, result_queue, progress_queue)
            )
            self.transcription_process.start()
            
            # Aguarda conclusão enquanto atualiza progresso
            while self.transcription_process is not None and self.transcription_process.is_alive():
                # Verifica progresso
                try:
                    while not progress_queue.empty():
                        progress_data = progress_queue.get_nowait()
                        if progress_callback:
                            progress_callback(progress_data)
                except:
                    pass
                
                time.sleep(0.1)
                
                if self.cancel_transcription:
                    if self.transcription_process is not None and self.transcription_process.is_alive():
                        self.transcription_process.terminate()
                        self.transcription_process.join()
                        self.transcription_process = None
                    self.cancel_transcription = False
                    raise ErrorHandlers.TranscriptionCancelledException("Transcrição cancelada pelo usuário")
            
            # Processa resultado
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
        except FileNotFoundError as e:
            ErrorHandlers.handle_file_not_found(e)
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
    def transcribe_file_process(model_path, config_dict, filepath, temp_dir, settings_dict, result_queue, progress_queue):
        """Processo separado para transcrição (evita problemas com multiprocessing)"""
        try:
            # Atualiza progresso: carregando modelo (removido verbose para não poluir console)
            try:
                progress_queue.put({"status": "loading_model", "percent": 10})
            except:
                pass
            
            # Carrega modelo
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model = whisper.load_model(model_path, device=device)
            
            try:
                progress_queue.put({"status": "extracting_audio", "percent": 20})
            except:
                pass
            
            # Prepara processador de áudio
            config = Config()
            config.config = config_dict
            audio_processor = AudioProcessor(config)
            audio_path = audio_processor.extract_audio(filepath, temp_dir)
            
            # Prepara configurações
            from transcription_settings import TranscriptionSettings
            settings = TranscriptionSettings.from_dict(settings_dict)
            
            # Log das configurações aplicadas
            logging.info(f"Configurações de transcrição: {settings.to_dict()}")
            
            try:
                progress_queue.put({"status": "transcribing", "percent": 30})
            except:
                pass
            
            # Configurações de transcrição
            transcribe_kwargs = {
                "word_timestamps": settings.timestamp_mode == "word",
                "verbose": False  # Desabilita verbose para não poluir console
            }
            
            # Configuração de idioma
            if settings.language_strategy == "manual" and settings.manual_language:
                transcribe_kwargs["language"] = settings.manual_language
                logging.info(f"Usando idioma manual: {settings.manual_language}")
            elif settings.language_strategy == "auto":
                transcribe_kwargs["language"] = None
                logging.info("Detecção automática de idioma")
            else:
                transcribe_kwargs["language"] = None
    
            # Aplica preset de qualidade
            quality_presets = {
                "fast": {
                    "beam_size": 1, 
                    "best_of": 1,
                    "temperature": 0.0
                },
                "balanced": {
                    "beam_size": 3, 
                    "best_of": 3,
                    "temperature": 0.0
                },
                "accurate": {
                    "beam_size": 5, 
                    "best_of": 5,
                    "temperature": 0.0,
                    "patience": 1.0
                }
            }
            preset = quality_presets.get(settings.quality_preset, quality_presets["balanced"])
            transcribe_kwargs.update(preset)
            
            logging.info(f"Preset de qualidade: {settings.quality_preset}")
            
            try:
                progress_queue.put({"status": "transcribing", "percent": 50})
            except:
                pass
    
            # Realiza transcrição
            result = model.transcribe(audio_path, **transcribe_kwargs)
            
            try:
                progress_queue.put({"status": "saving", "percent": 90})
            except:
                pass
            
            logging.info(f"Transcrição concluída. Segmentos: {len(result.get('segments', []))}")
            
            # Formata saída
            local_salvamento = TranscriptionManager.format_output(result, settings, filepath)
            
            try:
                progress_queue.put({"status": "completed", "percent": 100})
            except:
                pass
            
            logging.info(f"Arquivo salvo em: {local_salvamento}")
            
            # Limpa arquivo temporário
            if audio_path != filepath and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except:
                    pass
            
            result_queue.put({'output_path': local_salvamento})
            
        except Exception as e:
            logging.error(f"Erro no processo de transcrição: {e}", exc_info=True)
            result_queue.put({'error': str(e)})

    @staticmethod
    def format_output(result, settings, original_filepath):
        """Formata a saída da transcrição de acordo com as configurações"""
        segments = result.get("segments", [])
        base_dir = os.path.dirname(original_filepath)
        base_name = os.path.splitext(os.path.basename(original_filepath))[0]
        
        # Mapa de extensões
        extension_map = {
            "docx": ".docx",
            "txt": ".txt",
            "srt": ".srt",
            "vtt": ".vtt",
            "json": ".json"
        }
        extension = extension_map.get(settings.output_format, ".docx")
        output_path = os.path.join(base_dir, f"{base_name}_text{extension}")

        # Handlers de formatação por tipo
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
        """Salva transcrição em formato Word"""
        doc = Document()
        
        # Processa os parágrafos
        paragraphs = TranscriptionManager._build_paragraphs(segments, settings)
        
        for para_text in paragraphs:
            if para_text.strip():
                doc.add_paragraph(para_text)
        
        doc.save(output_path)

    @staticmethod
    def _save_txt(output_path, segments, result, settings):
        """Salva transcrição em formato texto simples"""
        with open(output_path, "w", encoding="utf-8") as fp:
            paragraphs = TranscriptionManager._build_paragraphs(segments, settings)
            fp.write("\n\n".join(paragraphs))

    @staticmethod
    def _build_paragraphs(segments, settings):
        """Constrói parágrafos baseados nas configurações - SIMPLIFICADO"""
        paragraphs = []
        
        # Se parágrafos automáticos estão habilitados
        if settings.auto_paragraphs:
            # Agrupa segmentos por pausas
            pause_threshold = 2.0 + (settings.paragraph_sensitivity / 100.0) * 3.0
            groups = []
            current_group = []
            
            for i, segment in enumerate(segments):
                current_group.append(segment)
                
                # Verifica se deve criar novo parágrafo
                if i < len(segments) - 1:
                    current_end = segment.get("end", 0)
                    next_start = segments[i + 1].get("start", 0)
                    pause = next_start - current_end
                    
                    if pause > pause_threshold:
                        # Cria parágrafo com o grupo atual
                        groups.append(current_group)
                        current_group = []
            
            # Adiciona último grupo
            if current_group:
                groups.append(current_group)
            
        else:
            # Cada segmento vira um "grupo" individual
            groups = [[seg] for seg in segments]
        
        # Processa cada grupo
        for group in groups:
            if not group:
                continue
            
            # Monta o texto do parágrafo
            if settings.include_timestamps:
                if settings.timestamp_mode == "paragraph" and len(group) > 0:
                    # Timestamp no início do parágrafo
                    timestamp = TranscriptionManager._format_timestamp_value(
                        group[0].get("start", 0.0), settings.timestamp_format)
                    texts = [seg.get("text", "").strip() for seg in group]
                    combined = " ".join(texts)
                    combined = TranscriptionManager._clean_text(combined, settings)
                    if combined:
                        paragraphs.append(f"[{timestamp}] {combined}")
                        
                elif settings.timestamp_mode == "segment":
                    # Timestamp para cada segmento
                    para_parts = []
                    for seg in group:
                        timestamp = TranscriptionManager._format_timestamp_value(
                            seg.get("start", 0.0), settings.timestamp_format)
                        text = TranscriptionManager._clean_text(seg.get("text", "").strip(), settings)
                        if text:
                            para_parts.append(f"[{timestamp}] {text}")
                    if para_parts:
                        paragraphs.append(" ".join(para_parts))
                        
                else:  # none ou word (word não implementado aqui por simplicidade)
                    texts = [seg.get("text", "").strip() for seg in group]
                    combined = " ".join(texts)
                    combined = TranscriptionManager._clean_text(combined, settings)
                    if combined:
                        paragraphs.append(combined)
            else:
                # Sem timestamps
                texts = [seg.get("text", "").strip() for seg in group]
                combined = " ".join(texts)
                combined = TranscriptionManager._clean_text(combined, settings)
                if combined:
                    paragraphs.append(combined)
        
        # Se não gerou nenhum parágrafo, retorna o texto completo
        if not paragraphs:
            full_text = " ".join(seg.get("text", "").strip() for seg in segments)
            full_text = TranscriptionManager._clean_text(full_text, settings)
            if full_text:
                paragraphs.append(full_text)
        
        return paragraphs

    @staticmethod
    def _save_srt(output_path, segments, result, settings):
        """Salva transcrição em formato SRT (legendas)"""
        with open(output_path, "w", encoding="utf-8") as fp:
            for index, segment in enumerate(segments, start=1):
                start = TranscriptionManager._format_timestamp_value(
                    segment.get("start", 0.0), settings.timestamp_format, target="srt")
                end = TranscriptionManager._format_timestamp_value(
                    segment.get("end", 0.0), settings.timestamp_format, target="srt")
                text = TranscriptionManager._clean_text(segment.get("text", ""), settings)

                if text.strip():
                    fp.write(f"{index}\n{start} --> {end}\n{text.strip()}\n\n")

    @staticmethod
    def _save_vtt(output_path, segments, result, settings):
        """Salva transcrição em formato WebVTT"""
        with open(output_path, "w", encoding="utf-8") as fp:
            fp.write("WEBVTT\n\n")

            for segment in segments:
                start = TranscriptionManager._format_timestamp_value(
                    segment.get("start", 0.0), settings.timestamp_format, target="vtt")
                end = TranscriptionManager._format_timestamp_value(
                    segment.get("end", 0.0), settings.timestamp_format, target="vtt")
                text = TranscriptionManager._clean_text(segment.get("text", ""), settings)

                if text.strip():
                    fp.write(f"{start} --> {end}\n{text.strip()}\n\n")

    @staticmethod
    def _save_json(output_path, segments, result, settings):
        """Salva transcrição em formato JSON"""
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
    def _clean_text(text, settings):
        """Limpa e formata texto de acordo com as configurações"""
        cleaned = text.strip()

        # Aplica capitalização
        if settings.capitalization:
            # Mantém a capitalização original ou capitaliza primeira letra
            if cleaned and not cleaned[0].isupper():
                cleaned = cleaned[0].upper() + cleaned[1:]
        else:
            # Remove capitalização
            cleaned = cleaned.lower()

        # Remove pontuação se configurado
        if not settings.punctuation:
            import string
            # Remove toda pontuação
            cleaned = ''.join(ch for ch in cleaned if ch not in string.punctuation or ch.isspace())

        return cleaned

    @staticmethod
    def _format_timestamp_value(seconds, fmt, target=None):
        """Formata valor de timestamp em diferentes formatos"""
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
        
        # Formato padrão: HH:MM:SS
        return f"{hours:02}:{minutes:02}:{secs:02}"


class ModelDownloader:
    """Gerenciador de download de modelos Whisper"""
    
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
        """Verifica se o download foi bem sucedido"""
        try:
            if not os.path.exists(file_path):
                return False
            
            if expected_size and os.path.getsize(file_path) != expected_size:
                logging.warning(f"Tamanho do arquivo difere do esperado: {os.path.getsize(file_path)} vs {expected_size}")
                return False
            
            # Tenta carregar o modelo para verificar integridade
            device = "cuda" if torch.cuda.is_available() else "cpu"
            torch.load(file_path, map_location=device)
            return True
            
        except Exception as e:
            logging.error(f"Erro ao verificar download: {e}")
            return False

    def download_model(self, model_name, progress_callback=None, cancel_event=None):
        """Baixa um modelo Whisper"""
        url = self.MODELS_URLS[model_name]
        diretorio_modelo = self.config.resource_path(".model")
        
        try:
            if not os.path.exists(diretorio_modelo):
                os.makedirs(diretorio_modelo)
        except Exception as e:
            ErrorHandlers.handle_permission_error(e)
            raise
        
        caminho_modelo = os.path.join(diretorio_modelo, f"{model_name}.pt")
        
        # Verifica se já existe e está válido
        if os.path.exists(caminho_modelo):
            try:
                if self.verify_download(caminho_modelo):
                    logging.info(f"Modelo já existe e está válido: {caminho_modelo}")
                    return caminho_modelo
                else:
                    os.remove(caminho_modelo)
                    logging.info(f"Modelo corrompido removido: {caminho_modelo}")
            except Exception as e:
                logging.error(f"Erro ao verificar modelo existente: {e}")
                if os.path.exists(caminho_modelo):
                    os.remove(caminho_modelo)
        
        max_tentativas = 3
        block_size = 65536
        
        for tentativa in range(max_tentativas):
            try:
                logging.info(f"Tentativa {tentativa + 1} de {max_tentativas} para baixar {model_name}")
                
                response = requests.get(url, stream=True, timeout=30)
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))
                
                # Verifica espaço em disco
                if total_size > 0:
                    stat = shutil.disk_usage(diretorio_modelo)
                    if stat.free < total_size * 1.1:  # 10% de margem
                        ErrorHandlers.handle_disk_space_error()
                        raise Exception("Espaço em disco insuficiente")
                
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
                
                # Verifica integridade do download
                if self.verify_download(caminho_modelo, total_size if total_size > 0 else None):
                    logging.info(f"Download do modelo concluído com sucesso: {caminho_modelo}")
                    return caminho_modelo
                else:
                    if os.path.exists(caminho_modelo):
                        os.remove(caminho_modelo)
                    raise Exception("Arquivo baixado está corrompido ou incompleto")
                    
            except requests.RequestException as e:
                logging.error(f"Erro de requisição na tentativa {tentativa + 1}: {e}")
                if os.path.exists(caminho_modelo):
                    os.remove(caminho_modelo)
                if tentativa == max_tentativas - 1:
                    ErrorHandlers.handle_download_error(e)
                    raise Exception(f"Falha após {max_tentativas} tentativas de download")
                time.sleep(2)  # Aguarda antes de tentar novamente
                continue
                
            except Exception as e:
                logging.error(f"Erro na tentativa {tentativa + 1}: {e}")
                if os.path.exists(caminho_modelo):
                    os.remove(caminho_modelo)
                if str(e) == "Download cancelado pelo usuário":
                    raise e
                if tentativa == max_tentativas - 1:
                    ErrorHandlers.handle_download_error(e)
                    raise Exception(f"Falha após {max_tentativas} tentativas de download")
                continue


# Classes GUI continuam...
class GUI:
    """Interface gráfica principal do aplicativo"""
    
    def __init__(self):
        set_app_id()  # Define ID do app para ícone correto na barra de tarefas
        
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
        """Configura a janela principal"""
        self.root.title("TextifyVoice [ 1.0 ] by@felipe.sh")
        self.root.geometry("700x550")
        self.root.resizable(True, True)
        self.root.minsize(600, 450)
        
        if os.path.exists(self.config.ICON_PATH):
            try:
                self.root.iconbitmap(self.config.ICON_PATH)
            except Exception as e:
                logging.warning(f"Não foi possível definir ícone da janela: {e}")
        
        self.root.configure(bg="#1e1e1e")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_styles(self):
        """Configura estilos visuais do ttk"""
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        
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
        """Cria widgets da interface principal"""
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
        """Abre janela de seleção de arquivos"""
        if self.transcription_window and self.transcription_window.winfo_exists():
            self.transcription_window.lift()
            return
        self.transcription_window = TranscriptionWindow(self)

    def show_quality_selection_window(self):
        """Abre janela de seleção de qualidade"""
        if hasattr(self, 'quality_window') and self.quality_window and self.quality_window.winfo_exists():
            self.quality_window.lift()
            return
        self.quality_window = QualitySelectionWindow(self)

    def show_advanced_settings_window(self):
        """Abre janela de configurações avançadas"""
        if self.settings_window and self.settings_window.window.winfo_exists():
            self.settings_window.window.lift()
            return
        self.settings_window = AdvancedSettingsWindow(self, self.settings)

    def update_settings_badge(self):
        """Atualiza badge de resumo das configurações"""
        summary = self.settings.summary()
        self.settings_badge_var.set(f"{summary}")

    def show_loading_window(self):
        """Exibe janela de carregamento inicial"""
        self.loading_window = tk.Toplevel(self.root)
        self.loading_window.title("Carregando")
        self.loading_window.geometry("450x220")
        self.loading_window.configure(bg=self.colors['background'])
        self.loading_window.overrideredirect(True)
        self.loading_window.grab_set()
        
        if os.path.exists(self.config.ICON_PATH):
            try:
                self.loading_window.iconbitmap(self.config.ICON_PATH)
            except Exception as e:
                logging.warning(f"Não foi possível definir ícone: {e}")
        
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
        """Chamado ao fechar a janela principal"""
        self.transcription_manager.stop_event.set()
        self.root.destroy()

    def load_initial_configurations(self):
        """Carrega configurações iniciais em thread separada"""
        try:
            self.check_initial_model()
        except Exception as e:
            logging.exception("Exceção ao carregar configurações iniciais")
            self.root.after(0, lambda: ErrorHandlers.handle_exception(e))
        finally:
            self.root.after(0, self.loading_window.destroy)
            self.root.after(0, self.root.deiconify)

    def run(self):
        """Inicia a aplicação"""
        self.show_loading_window()
        Thread(target=self.load_initial_configurations, daemon=True).start()
        self.root.mainloop()

    def check_initial_model(self):
        """Verifica se há modelo configurado e válido"""
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
    """Janela de seleção e transcrição de arquivos"""
    
    def __init__(self, main_gui):
        self.main_gui = main_gui
        self.window = tk.Toplevel(main_gui.root)
        
        if os.path.exists(self.main_gui.config.ICON_PATH):
            try:
                self.window.iconbitmap(self.main_gui.config.ICON_PATH)
            except Exception as e:
                logging.warning(f"Não foi possível definir ícone: {e}")
        
        self.setup_window()
        self.create_widgets()
        self.current_item = None

    def setup_window(self):
        """Configura a janela de transcrição"""
        self.window.title("Seleção de Arquivos")
        self.window.geometry("800x600")
        self.window.minsize(700, 500)
        self.window.grab_set()
        self.window.configure(bg=self.main_gui.colors['background'])
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        """Cria widgets da janela de transcrição"""
        toolbar_frame = ttk.Frame(self.window, style="TFrame")
        toolbar_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        
        self.btn_add = ttk.Button(toolbar_frame, text="Adicionar Arquivo",
                                  command=self.add_files, style="TButton")
        self.btn_add.pack(side=tk.LEFT)
        
        self.create_file_list()
        
        # Frame para progresso de transcrição individual
        self.transcription_progress_frame = ttk.Frame(self.window, style="TFrame")
        self.transcription_progress_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        self.transcription_progress_label = ttk.Label(
            self.transcription_progress_frame,
            text="",
            style="TLabel"
        )
        self.transcription_progress_label.pack(anchor=tk.W, pady=(0, 5))
        
        self.transcription_progress_bar = ttk.Progressbar(
            self.transcription_progress_frame,
            mode='determinate',
            maximum=100,
            length=760
        )
        self.transcription_progress_bar.pack(fill=tk.X)
        
        # Inicialmente esconde o frame de progresso
        self.transcription_progress_frame.pack_forget()
        
        # Barra de progresso geral
        self.progress_frame = ttk.Frame(self.window, style="TFrame")
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            variable=self.progress_var,
            maximum=100,
            mode='determinate',
            length=760
        )
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))
        
        self.progress_label = ttk.Label(
            self.progress_frame,
            text="",
            style="TLabel"
        )
        self.progress_label.pack(anchor=tk.W)
        
        # Botões de ação
        self.buttons_frame = ttk.Frame(self.window, style="TFrame")
        self.buttons_frame.pack(pady=20, padx=20, fill=tk.X)
        
        self.btn_start = ttk.Button(self.buttons_frame, text="Iniciar Transcrição",
                                    command=self.start_transcription, style="Modelo.TButton")
        self.btn_cancel = ttk.Button(self.buttons_frame, text="Cancelar",
                                     command=self.on_closing, style="TButton")
        
        self.btn_start.pack(side=tk.LEFT, padx=(0, 10), fill=tk.X, expand=True)
        self.btn_cancel.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def create_file_list(self):
        """Cria lista de arquivos"""
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
        """Adiciona arquivos à lista"""
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
        """Verifica se arquivo já está na lista"""
        for item in self.file_list.get_children():
            if self.file_list.item(item)['values'][0] == filepath:
                return True
        return False

    def update_transcription_progress(self, progress_data):
        """Atualiza a barra de progresso da transcrição individual"""
        try:
            # Verifica se os widgets existem antes de atualizar
            if not progress_data:
                return
                
            if not hasattr(self, 'transcription_progress_label') or not self.transcription_progress_label:
                return
                
            if not hasattr(self, 'transcription_progress_bar') or not self.transcription_progress_bar:
                return
            
            status = progress_data.get("status", "")
            percent = progress_data.get("percent", 0)
            
            # Mapa de status para mensagens em português
            status_messages = {
                "loading_model": "Carregando modelo...",
                "extracting_audio": "Extraindo áudio...",
                "transcribing": "Transcrevendo...",
                "saving": "Salvando arquivo...",
                "completed": "Concluído!"
            }
            
            message = status_messages.get(status, status)
            
            # Atualiza interface de forma segura
            if self.transcription_progress_label.winfo_exists():
                self.transcription_progress_label.config(text=f"{message} ({percent}%)")
            
            if self.transcription_progress_bar.winfo_exists():
                self.transcription_progress_bar['value'] = percent
                
            self.window.update_idletasks()
            
        except Exception as e:
            logging.warning(f"Erro ao atualizar progresso: {e}")

    def start_transcription(self):
        """Inicia processo de transcrição"""
        self.btn_start.config(state=tk.DISABLED)
        self.btn_add.config(state=tk.DISABLED)
        self.main_gui.transcription_manager.cancel_transcription = False
        self.main_gui.transcription_manager.is_transcribing = True
        
        thread = Thread(target=self.process_files, daemon=True)
        thread.start()

    def process_files(self):
        """Processa todos os arquivos da lista"""
        items = self.file_list.get_children()
        total_items = len([i for i in items if self.file_list.item(i)['values'][1] not in ['Finalizado', 'Cancelado', 'Erro']])
        
        if total_items == 0:
            self.main_gui.transcription_manager.is_transcribing = False
            self.window.after(0, lambda: self.btn_start.config(state=tk.NORMAL))
            self.window.after(0, lambda: self.btn_add.config(state=tk.NORMAL))
            return
        
        # Mostra barras de progresso
        self.window.after(0, lambda: self.progress_frame.pack(fill=tk.X, padx=20, pady=(0, 10)))
        self.window.after(0, lambda: self.transcription_progress_frame.pack(fill=tk.X, padx=20, pady=(0, 10)))
        
        processed = 0
        
        for item in items:
            if self.main_gui.transcription_manager.cancel_transcription:
                break
            
            values = self.file_list.item(item)['values']
            status = values[1]
            
            if status not in ['Finalizado', 'Cancelado', 'Erro']:
                self.current_item = item
                
                # Atualiza progresso geral
                filename = os.path.basename(values[0])
                self.window.after(0, lambda f=filename: self.progress_label.config(text=f"Arquivo: {f}"))
                self.file_list.set(item, 'Status', 'Transcrição em progresso...')
                
                # Reseta e atualiza barra de progresso individual
                self.window.after(0, lambda: self.transcription_progress_bar.configure(value=0))
                self.window.after(0, lambda: self.transcription_progress_label.config(text="Iniciando transcrição..."))
                
                # Mostra progresso em etapas simples
                def simple_progress_callback(data):
                    """Callback simplificado de progresso"""
                    if data and self.window.winfo_exists():
                        try:
                            self.window.after(0, lambda: self.update_transcription_progress(data))
                        except:
                            pass
                
                try:
                    filepath = values[0]
                    
                    # Atualiza para mostrar que está processando
                    self.window.after(0, lambda: self.transcription_progress_label.config(text="Processando..."))
                    self.window.after(0, lambda: self.transcription_progress_bar.configure(value=50))
                    
                    result_path = self.main_gui.transcription_manager.transcribe_file(
                        filepath,
                        lambda path: self.update_transcription_result(item, path),
                        settings=self.main_gui.settings,
                        progress_callback=simple_progress_callback
                    )
                    
                    # Marca como finalizado
                    self.file_list.set(item, 'Status', 'Finalizado')
                    self.file_list.set(item, 'Transcrito', result_path)
                    
                    # Atualiza barra para 100%
                    self.window.after(0, lambda: self.transcription_progress_bar.configure(value=100))
                    self.window.after(0, lambda: self.transcription_progress_label.config(text="Concluído!"))
                    
                except ErrorHandlers.TranscriptionCancelledException:
                    self.file_list.set(item, 'Status', 'Cancelado')
                    
                except Exception as e:
                    ErrorHandlers.handle_exception(e)
                    self.file_list.set(item, 'Status', 'Erro')
                    
                finally:
                    self.current_item = None
                    processed += 1
                    
                    # Atualiza barra de progresso geral
                    progress_percentage = (processed / total_items) * 100
                    self.window.after(0, lambda p=progress_percentage: self.progress_var.set(p))
                    self.window.after(0, lambda pr=processed, tot=total_items: 
                                    self.progress_label.config(text=f"Progresso geral: {pr}/{tot} arquivos concluídos"))
        
        # Esconde as barras de progresso ao finalizar
        self.window.after(0, lambda: self.progress_frame.pack_forget())
        self.window.after(0, lambda: self.transcription_progress_frame.pack_forget())
        self.window.after(0, lambda: self.progress_var.set(0))
        
        self.main_gui.transcription_manager.is_transcribing = False
        self.window.after(0, lambda: self.btn_start.config(state=tk.NORMAL))
        self.window.after(0, lambda: self.btn_add.config(state=tk.NORMAL))
        
        if not self.main_gui.transcription_manager.cancel_transcription:
            self.window.after(0, lambda: messagebox.showinfo(
                "Concluído", 
                f"Todas as transcrições foram finalizadas!\n\n"
                f"Total de arquivos processados: {processed}"
            ))
        else:
            self.window.after(0, lambda: messagebox.showinfo(
                "Cancelado", 
                "A transcrição foi cancelada pelo usuário."
            ))
            self.main_gui.transcription_manager.cancel_transcription = False

    def update_transcription_result(self, item, path):
        """Atualiza resultado da transcrição na lista"""
        self.file_list.set(item, 'Transcrito', path)

    def open_file_location(self, event):
        """Abre localização do arquivo transcrito"""
        item = self.file_list.identify_row(event.y)
        if item:
            values = self.file_list.item(item)['values']
            if values[1] == 'Finalizado':
                transcribed_file = values[2]
                if os.path.exists(transcribed_file):
                    try:
                        if system() == 'Windows':
                            os.startfile(os.path.dirname(transcribed_file))
                        elif system() == 'Darwin':  # macOS
                            subprocess.run(['open', os.path.dirname(transcribed_file)])
                        else:  # Linux
                            subprocess.run(['xdg-open', os.path.dirname(transcribed_file)])
                    except Exception as e:
                        ErrorHandlers.handle_exception(e)
                        messagebox.showerror(
                            "Erro", 
                            f"Não foi possível abrir a pasta.\n\nCaminho: {os.path.dirname(transcribed_file)}"
                        )
                else:
                    messagebox.showerror(
                        "Erro", 
                        "Arquivo transcrito não encontrado.\n\n"
                        "O arquivo pode ter sido movido ou excluído."
                    )
            else:
                messagebox.showinfo(
                    "Info", 
                    "Este arquivo ainda não foi transcrito.\n\n"
                    "Aguarde a conclusão da transcrição."
                )

    def on_closing(self):
        """Chamado ao fechar a janela"""
        if self.main_gui.transcription_manager.is_transcribing:
            if messagebox.askyesno(
                "Confirmar", 
                "Há uma transcrição em andamento.\n\n"
                "Deseja realmente cancelar?\n\n"
                "O progresso atual será perdido."
            ):
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
            self.window.destroy()

    def winfo_exists(self):
        """Verifica se a janela existe"""
        try:
            return self.window.winfo_exists()
        except:
            return False

    def lift(self):
        """Traz janela para frente"""
        self.window.lift()
        
class QualitySelectionWindow:
    """Janela de seleção e download de modelos"""
    
    def __init__(self, main_gui):
        self.main_gui = main_gui
        self.window = tk.Toplevel(main_gui.root)
        
        if os.path.exists(self.main_gui.config.ICON_PATH):
            try:
                self.window.iconbitmap(self.main_gui.config.ICON_PATH)
            except Exception as e:
                logging.warning(f"Não foi possível definir ícone: {e}")
        
        self.setup_window()
        self.create_widgets()
        self.cancel_download = Event()

    def setup_window(self):
        """Configura a janela de seleção de qualidade"""
        self.window.title("Selecionar Qualidade")
        self.window.geometry("550x300")
        self.window.resizable(False, False)
        self.window.grab_set()
        self.window.configure(bg=self.main_gui.colors['background'])
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)

    def winfo_exists(self):
        """Verifica se a janela existe"""
        try:
            return self.window.winfo_exists()
        except:
            return False

    def create_widgets(self):
        """Cria widgets da janela"""
        main_frame = ttk.Frame(self.window, style="TFrame", padding=30)
        main_frame.pack(expand=True, fill=tk.BOTH)
        
        # Título
        title_label = ttk.Label(
            main_frame,
            text="Escolha a qualidade do modelo de transcrição:",
            style="TLabel",
            font=("Segoe UI", 11, "bold")
        )
        title_label.pack(pady=(0, 10))
        
        # Descrição
        desc_label = ttk.Label(
            main_frame,
            text="Modelos maiores são mais precisos, mas mais lentos.\n"
                 "Recomendamos 'medium' para uso geral.",
            style="TLabel",
            foreground=self.main_gui.colors['text_secondary'],
            justify="center"
        )
        desc_label.pack(pady=(0, 20))
        
        # Obtém modelo atual
        model_path = self.main_gui.config.config.get('model_path', '')
        default_model_name = "medium"
        
        if model_path:
            default_model_name = os.path.splitext(os.path.basename(model_path))[0]
            if default_model_name not in self.main_gui.model_downloader.MODELS_URLS:
                default_model_name = "medium"
        
        self.quality_var = tk.StringVar(value=default_model_name)
        
        # Dropdown de modelos
        self.quality_dropdown = ttk.OptionMenu(
            main_frame,
            self.quality_var,
            self.quality_var.get(),
            *self.main_gui.model_downloader.MODELS_URLS.keys()
        )
        self.quality_dropdown.pack(pady=(0, 10), fill=tk.X)
        
        info_label = ttk.Label(
            main_frame,
            style="TLabel",
            foreground=self.main_gui.colors['text_secondary'],
            font=("Segoe UI", 9),
            justify="left"
        )
        info_label.pack(pady=(0, 20))
        
        # Botão de download
        self.btn_download = ttk.Button(
            main_frame,
            text="Selecionar e Baixar Modelo",
            command=self.download_model,
            style="Modelo.TButton"
        )
        self.btn_download.pack(fill=tk.X)

    def lift(self):
        """Traz janela para frente"""
        self.window.lift()

    def download_model(self):
        """Inicia download do modelo selecionado"""
        self.btn_download.config(state=tk.DISABLED)
        model_name = self.quality_var.get()
        
        # Cria janela de progresso
        progress_window = tk.Toplevel(self.window)
        progress_window.title("Baixando Modelo")
        progress_window.geometry("550x280")
        progress_window.resizable(False, False)
        progress_window.grab_set()
        progress_window.configure(bg=self.main_gui.colors['background'])
        
        if os.path.exists(self.main_gui.config.ICON_PATH):
            try:
                progress_window.iconbitmap(self.main_gui.config.ICON_PATH)
            except Exception as e:
                logging.warning(f"Não foi possível definir ícone: {e}")
        
        progress_frame = ttk.Frame(progress_window, style="TFrame", padding=30)
        progress_frame.pack(expand=True, fill=tk.BOTH)
        
        # Título
        title = ttk.Label(
            progress_frame,
            text=f"Baixando modelo: {model_name}",
            style="TLabel",
            font=("Segoe UI", 11, "bold")
        )
        title.pack(pady=(0, 20))
        
        # Barra de progresso
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(
            progress_frame,
            variable=progress_var,
            maximum=100,
            length=480
        )
        progress_bar.pack(pady=(0, 15), fill=tk.X)
        
        # Label de status
        progress_label = ttk.Label(
            progress_frame,
            text="Iniciando download...",
            style="TLabel"
        )
        progress_label.pack(pady=(0, 10))
        
        # Label de informações adicionais
        info_label = ttk.Label(
            progress_frame,
            text="Isso pode levar alguns minutos dependendo da sua conexão.",
            style="TLabel",
            foreground=self.main_gui.colors['text_secondary'],
            font=("Segoe UI", 9)
        )
        info_label.pack(pady=(0, 20))
        
        # Botão de cancelar
        btn_cancel_download = ttk.Button(
            progress_frame,
            text="Cancelar Download",
            command=lambda: self.cancel_download_process(progress_window),
            style="TButton"
        )
        btn_cancel_download.pack(fill=tk.X)
        
        progress_window.protocol("WM_DELETE_WINDOW",
                                lambda: self.cancel_download_process(progress_window))
        
        self.cancel_download.clear()

        def update_progress(progress):
            """Atualiza UI com progresso do download"""
            self.window.after(0, lambda: self._update_progress_ui(
                progress, progress_var, progress_label, progress_window))

        def download_thread():
            """Thread de download"""
            try:
                model_path = self.main_gui.model_downloader.download_model(
                    model_name, 
                    progress_callback=update_progress, 
                    cancel_event=self.cancel_download
                )
                
                # Verifica integridade do modelo baixado
                if self.main_gui.transcription_manager.verify_model_file(model_path):
                    self.main_gui.config.config['model_path'] = model_path
                    self.main_gui.config.save_config()
                    
                    if progress_window.winfo_exists():
                        progress_window.destroy()
                    
                    self.window.after(0, lambda: messagebox.showinfo(
                        "Sucesso", 
                        f"Modelo '{model_name}' baixado e verificado com sucesso!\n\n"
                        f"O modelo está pronto para uso."
                    ))
                    
                    if self.window.winfo_exists():
                        self.window.destroy()
                else:
                    raise Exception("Falha na verificação final do modelo")
                    
            except Exception as e:
                if progress_window.winfo_exists():
                    progress_window.destroy()
                
                if str(e) == "Download cancelado pelo usuário":
                    self.window.after(0, lambda: messagebox.showinfo(
                        "Cancelado", 
                        "O download foi cancelado.\n\n"
                        "Você pode tentar novamente quando quiser."
                    ))
                else:
                    self.window.after(0, lambda e=e: messagebox.showerror(
                        "Erro no Download", 
                        f"Não foi possível baixar o modelo.\n\n"
                        f"Detalhes: {str(e)}\n\n"
                        f"Possíveis soluções:\n"
                        f"• Verifique sua conexão com a internet\n"
                        f"• Verifique se há espaço em disco suficiente\n"
                        f"• Tente novamente em alguns minutos"
                    ))
                
                ErrorHandlers.handle_exception(e)
            finally:
                self.window.after(0, self.reenable_download_button)

        thread = Thread(target=download_thread, daemon=True)
        thread.start()

    def _update_progress_ui(self, progress, progress_var, progress_label, progress_window):
        """Atualiza interface com progresso do download"""
        if progress_window.winfo_exists():
            if isinstance(progress, (float, int)):
                progress_var.set(progress)
                if progress < 100:
                    progress_label.config(text=f"Baixando... {progress:.1f}%")
                else:
                    progress_label.config(text="Download concluído. Verificando integridade...")
            else:
                progress_label.config(text=str(progress))

    def cancel_download_process(self, progress_window):
        """Cancela processo de download"""
        if messagebox.askyesno(
            "Confirmar", 
            "Deseja realmente cancelar o download?\n\n"
            "O progresso será perdido."
        ):
            self.cancel_download.set()
            if progress_window.winfo_exists():
                progress_window.destroy()
            if self.window.winfo_exists():
                self.btn_download.config(state=tk.NORMAL)

    def reenable_download_button(self):
        """Reabilita botão de download"""
        if self.window.winfo_exists() and self.btn_download.winfo_exists():
            self.btn_download.config(state=tk.NORMAL)

    def on_closing(self):
        """Chamado ao fechar a janela"""
        if self.window.winfo_exists():
            self.window.destroy()


def main():
    """Função principal da aplicação"""
    try:
        app = GUI()
        app.run()
    except Exception as e:
        logging.critical(f"Erro fatal na aplicação: {e}", exc_info=True)
        messagebox.showerror(
            "Erro Fatal",
            f"Ocorreu um erro fatal na aplicação:\n\n{str(e)}\n\n"
            f"Por favor, verifique o arquivo de log para mais detalhes."
        )
        sys.exit(1)


if __name__ == '__main__':
    freeze_support()
    main()