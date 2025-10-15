"""Tkinter window for configuring advanced transcription settings."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk, messagebox, simpledialog

from transcription_settings import (
    TRANSCRIPTION_OPTIONS,
    TranscriptionSettings,
    ensure_default_presets,
)


class AdvancedSettingsWindow:
    """Modal window that allows fine-grained configuration of transcription options."""

    def __init__(self, main_gui, settings: TranscriptionSettings | None = None):
        self.main_gui = main_gui
        self.settings = TranscriptionSettings.from_dict(
            settings.to_dict() if settings else {}
        )
        ensure_default_presets(self.settings)
        
        self.preview_widget = None
        self.settings_changed = False
        
        self.window = tk.Toplevel(main_gui.root)
        self.window.title("Configurações Avançadas de Transcrição")
        self.window.geometry("900x700")
        self.window.minsize(800, 600)
        self.window.grab_set()
        
        if hasattr(main_gui.config, "ICON_PATH") and main_gui.config.ICON_PATH:
            try:
                if main_gui.config.ICON_PATH and main_gui.config.ICON_PATH.endswith(".ico"):
                    self.window.iconbitmap(main_gui.config.ICON_PATH)
            except Exception:
                pass
        
        self.window.configure(bg=main_gui.colors.get("background", "#1e1e1e"))
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        
        self.create_styles()
        self.create_widgets()
        self.update_preview()

    def create_styles(self) -> None:
        style = ttk.Style(self.window)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        
        bg = self.main_gui.colors.get("background", "#1e1e1e")
        surface = self.main_gui.colors.get("surface", "#252526")
        fg = self.main_gui.colors.get("foreground", "#e4e4e4")
        accent = self.main_gui.colors.get("accent", "#0e639c")
        success = self.main_gui.colors.get("success", "#0e7a0d")
        text_secondary = self.main_gui.colors.get("text_secondary", "#a0a0a0")
        
        style.configure("Settings.TFrame", background=bg)
        style.configure("Settings.TLabel", background=bg, foreground=fg, font=("Segoe UI", 9))
        style.configure("SettingsDesc.TLabel", background=bg, foreground=text_secondary, font=("Segoe UI", 8))
        style.configure("SettingsTitle.TLabel", background=bg, foreground=fg, font=("Segoe UI", 10, "bold"))
        style.configure("SettingsSection.TLabelframe", background=bg, foreground=fg)
        style.configure("SettingsSection.TLabelframe.Label", foreground=fg, font=("Segoe UI", 9, "bold"))
        
        style.configure("Settings.TButton", background=accent, foreground=fg, font=("Segoe UI", 9), padding=(10, 5))
        style.configure("SettingsSmall.TButton", background=accent, foreground=fg, font=("Segoe UI", 8), padding=(8, 4))
        style.configure("SettingsConfirm.TButton", background=success, foreground=fg, font=("Segoe UI", 10, "bold"), padding=(15, 8))
        
        style.configure("Settings.TCheckbutton", background=bg, foreground=fg, font=("Segoe UI", 9))
        style.configure("Settings.TRadiobutton", background=bg, foreground=fg, font=("Segoe UI", 9))

    def create_widgets(self) -> None:
        main_container = ttk.Frame(self.window, style="Settings.TFrame")
        main_container.pack(expand=True, fill=tk.BOTH)
        
        canvas = tk.Canvas(main_container, bg=self.main_gui.colors.get("background", "#1e1e1e"), 
                          highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style="Settings.TFrame")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        container = ttk.Frame(scrollable_frame, style="Settings.TFrame", padding=15)
        container.pack(expand=True, fill=tk.BOTH)

        presets_frame = ttk.LabelFrame(container, text="Presets Pré-configurados", 
                                       style="SettingsSection.TLabelframe", padding=12)
        presets_frame.pack(fill=tk.X, pady=(0, 12))
        
        desc_label = ttk.Label(presets_frame, 
                               text="Carregue configurações prontas para diferentes tipos de conteúdo",
                               style="SettingsDesc.TLabel")
        desc_label.pack(anchor=tk.W, pady=(0, 6))
        
        preset_controls = ttk.Frame(presets_frame, style="Settings.TFrame")
        preset_controls.pack(fill=tk.X)
        
        ttk.Label(preset_controls, text="Preset:", style="Settings.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        
        preset_names = sorted(self.settings.available_presets().keys())
        self.preset_var = tk.StringVar(value=preset_names[0] if preset_names else "")
        
        self.preset_combo = ttk.Combobox(
            preset_controls,
            textvariable=self.preset_var,
            values=preset_names,
            state="readonly",
            width=25,
        )
        self.preset_combo.pack(side=tk.LEFT, padx=(0, 6))
        self.preset_combo.bind("<<ComboboxSelected>>", self.on_preset_selected)
        
        ttk.Button(
            preset_controls,
            text="Aplicar",
            command=self.load_selected_preset,
            style="SettingsSmall.TButton",
        ).pack(side=tk.LEFT)

        self.notebook = ttk.Notebook(container)
        self.notebook.pack(expand=True, fill=tk.BOTH, pady=(0, 12))

        self.create_format_tab()
        self.create_timestamp_tab()
        self.create_formatting_tab()
        self.create_language_tab()
        self.create_quality_tab()

        preview_frame = ttk.LabelFrame(container, text="Prévia da Transcrição", 
                                       style="SettingsSection.TLabelframe", padding=12)
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 12))
        
        preview_desc = ttk.Label(preview_frame,
                                text="Veja como suas configurações afetarão o resultado final",
                                style="SettingsDesc.TLabel")
        preview_desc.pack(anchor=tk.W, pady=(0, 6))
        
        preview_scroll_frame = ttk.Frame(preview_frame, style="Settings.TFrame")
        preview_scroll_frame.pack(fill=tk.BOTH, expand=True)
        
        preview_scrollbar = ttk.Scrollbar(preview_scroll_frame)
        preview_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.preview_widget = tk.Text(
            preview_scroll_frame,
            height=6,
            wrap="word",
            bg="#0d1117",
            fg="#c9d1d9",
            relief="flat",
            font=("Consolas", 9),
            padx=12,
            pady=10,
            yscrollcommand=preview_scrollbar.set
        )
        self.preview_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        preview_scrollbar.config(command=self.preview_widget.yview)
        
        self.preview_widget.tag_configure("timestamp", foreground="#58a6ff", font=("Consolas", 8, "bold"))
        self.preview_widget.tag_configure("speaker", foreground="#f78166", font=("Consolas", 9, "bold"))
        self.preview_widget.tag_configure("text", foreground="#c9d1d9")
        self.preview_widget.tag_configure("paragraph_break", spacing1=8)
        
        self.preview_widget.insert("1.0", "")
        self.preview_widget.configure(state=tk.DISABLED)

        button_frame = ttk.Frame(container, style="Settings.TFrame")
        button_frame.pack(fill=tk.X)

        left_buttons = ttk.Frame(button_frame, style="Settings.TFrame")
        left_buttons.pack(side=tk.LEFT)

        ttk.Button(
            left_buttons,
            text="Importar",
            command=self.import_settings,
            style="SettingsSmall.TButton",
        ).pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(
            left_buttons,
            text="Exportar",
            command=self.export_settings,
            style="SettingsSmall.TButton",
        ).pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(
            left_buttons,
            text="Salvar Preset",
            command=self.save_preset,
            style="SettingsSmall.TButton",
        ).pack(side=tk.LEFT)

        right_buttons = ttk.Frame(button_frame, style="Settings.TFrame")
        right_buttons.pack(side=tk.RIGHT)

        ttk.Button(
            right_buttons,
            text="Cancelar",
            command=self.close,
            style="Settings.TButton",
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            right_buttons,
            text="Confirmar Alterações",
            command=self.apply_settings,
            style="SettingsConfirm.TButton",
        ).pack(side=tk.LEFT)

    def create_format_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=15, style="Settings.TFrame")
        self.notebook.add(frame, text="📄 Formato")

        ttk.Label(
            frame,
            text="Formato de Saída",
            style="SettingsTitle.TLabel"
        ).pack(anchor=tk.W, pady=(0, 4))
        
        ttk.Label(
            frame,
            text="Escolha o tipo de arquivo que será gerado após a transcrição",
            style="SettingsDesc.TLabel"
        ).pack(anchor=tk.W, pady=(0, 10))

        self.output_format_var = tk.StringVar(value=self.settings.output_format)
        
        format_descriptions = {
            "docx": "Ideal para edição e formatação avançada no Microsoft Word",
            "txt": "Arquivo simples, compatível com qualquer editor de texto",
            "srt": "Formato de legenda padrão para vídeos (compatível com YouTube, VLC, etc.)",
            "vtt": "Formato de legenda web (HTML5), usado em players modernos",
            "json": "Formato estruturado para integração com sistemas e análise de dados"
        }
        
        for key, label in TRANSCRIPTION_OPTIONS["output_format"].items():
            radio_frame = ttk.Frame(frame, style="Settings.TFrame")
            radio_frame.pack(anchor=tk.W, pady=3, fill=tk.X)
            
            ttk.Radiobutton(
                radio_frame,
                text=label,
                value=key,
                variable=self.output_format_var,
                style="Settings.TRadiobutton",
                command=self.on_setting_change,
            ).pack(anchor=tk.W)
            
            ttk.Label(
                radio_frame,
                text=f"   • {format_descriptions.get(key, '')}",
                style="SettingsDesc.TLabel"
            ).pack(anchor=tk.W, padx=(20, 0))

    def create_timestamp_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=15, style="Settings.TFrame")
        self.notebook.add(frame, text="⏱️ Timestamps")

        ttk.Label(
            frame,
            text="Marcas de Tempo",
            style="SettingsTitle.TLabel"
        ).pack(anchor=tk.W, pady=(0, 4))
        
        self.include_timestamps_var = tk.BooleanVar(value=self.settings.include_timestamps)
        check_frame = ttk.Frame(frame, style="Settings.TFrame")
        check_frame.pack(anchor=tk.W, pady=(0, 12), fill=tk.X)
        
        ttk.Checkbutton(
            check_frame,
            text="Incluir marcas de tempo na transcrição",
            variable=self.include_timestamps_var,
            style="Settings.TCheckbutton",
            command=self.on_setting_change,
        ).pack(anchor=tk.W)
        
        ttk.Label(
            check_frame,
            text="Adiciona indicadores de tempo para facilitar navegação e referência",
            style="SettingsDesc.TLabel"
        ).pack(anchor=tk.W, padx=(22, 0))

        ttk.Label(
            frame,
            text="Modo de Exibição",
            style="SettingsTitle.TLabel"
        ).pack(anchor=tk.W, pady=(12, 4))
        
        ttk.Label(
            frame,
            text="Define a granularidade das marcas de tempo",
            style="SettingsDesc.TLabel"
        ).pack(anchor=tk.W, pady=(0, 6))
        
        self.timestamp_mode_var = tk.StringVar(value=self.settings.timestamp_mode)
        
        mode_descriptions = {
            "none": "Sem marcas de tempo no texto",
            "segment": "Uma marca por segmento de fala (recomendado)",
            "word": "Uma marca para cada palavra (muito detalhado)",
            "paragraph": "Uma marca por parágrafo inteiro"
        }
        
        for key, label in TRANSCRIPTION_OPTIONS["timestamp_mode"].items():
            radio_frame = ttk.Frame(frame, style="Settings.TFrame")
            radio_frame.pack(anchor=tk.W, pady=2, fill=tk.X)
            
            ttk.Radiobutton(
                radio_frame,
                text=label,
                value=key,
                variable=self.timestamp_mode_var,
                style="Settings.TRadiobutton",
                command=self.on_setting_change,
            ).pack(anchor=tk.W)
            
            ttk.Label(
                radio_frame,
                text=f"   • {mode_descriptions.get(key, '')}",
                style="SettingsDesc.TLabel"
            ).pack(anchor=tk.W, padx=(20, 0))

        ttk.Label(
            frame,
            text="Formato de Exibição",
            style="SettingsTitle.TLabel"
        ).pack(anchor=tk.W, pady=(12, 4))
        
        ttk.Label(
            frame,
            text="Como os timestamps serão mostrados no texto",
            style="SettingsDesc.TLabel"
        ).pack(anchor=tk.W, pady=(0, 6))
        
        self.timestamp_format_var = tk.StringVar(value=self.settings.timestamp_format)
        
        format_examples = {
            "seconds": "Ex: 125.5s - Simples e compacto",
            "minutes": "Ex: 02:05.5 - Fácil de ler",
            "full": "Ex: 00:02:05.500 - Formato completo",
            "timecode": "Ex: 00:02:05:15 - Padrão profissional de vídeo"
        }
        
        for key, label in TRANSCRIPTION_OPTIONS["timestamp_format"].items():
            radio_frame = ttk.Frame(frame, style="Settings.TFrame")
            radio_frame.pack(anchor=tk.W, pady=2, fill=tk.X)
            
            ttk.Radiobutton(
                radio_frame,
                text=label,
                value=key,
                variable=self.timestamp_format_var,
                style="Settings.TRadiobutton",
                command=self.on_setting_change,
            ).pack(anchor=tk.W)
            
            ttk.Label(
                radio_frame,
                text=f"   • {format_examples.get(key, '')}",
                style="SettingsDesc.TLabel"
            ).pack(anchor=tk.W, padx=(20, 0))

    def create_formatting_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=15, style="Settings.TFrame")
        self.notebook.add(frame, text="✨ Formatação")

        ttk.Label(
            frame,
            text="Opções de Formatação Automática",
            style="SettingsTitle.TLabel"
        ).pack(anchor=tk.W, pady=(0, 10))

        self.paragraphs_var = tk.BooleanVar(value=self.settings.auto_paragraphs)
        para_frame = ttk.Frame(frame, style="Settings.TFrame")
        para_frame.pack(anchor=tk.W, pady=4, fill=tk.X)
        
        ttk.Checkbutton(
            para_frame,
            text="Separar em parágrafos automaticamente",
            variable=self.paragraphs_var,
            style="Settings.TCheckbutton",
            command=self.on_setting_change,
        ).pack(anchor=tk.W)
        
        ttk.Label(
            para_frame,
            text="Detecta pausas longas na fala e cria parágrafos para melhor legibilidade",
            style="SettingsDesc.TLabel"
        ).pack(anchor=tk.W, padx=(22, 0))

        self.speakers_var = tk.BooleanVar(value=self.settings.detect_speakers)
        speaker_frame = ttk.Frame(frame, style="Settings.TFrame")
        speaker_frame.pack(anchor=tk.W, pady=4, fill=tk.X)
        
        ttk.Checkbutton(
            speaker_frame,
            text="Identificar diferentes falantes (diarização)",
            variable=self.speakers_var,
            style="Settings.TCheckbutton",
            command=self.on_setting_change,
        ).pack(anchor=tk.W)
        
        ttk.Label(
            speaker_frame,
            text="Distingue entre diferentes vozes em entrevistas, reuniões e podcasts",
            style="SettingsDesc.TLabel"
        ).pack(anchor=tk.W, padx=(22, 0))

        self.punctuation_var = tk.BooleanVar(value=self.settings.punctuation)
        punct_frame = ttk.Frame(frame, style="Settings.TFrame")
        punct_frame.pack(anchor=tk.W, pady=4, fill=tk.X)
        
        ttk.Checkbutton(
            punct_frame,
            text="Adicionar pontuação automática",
            variable=self.punctuation_var,
            style="Settings.TCheckbutton",
            command=self.on_setting_change,
        ).pack(anchor=tk.W)
        
        ttk.Label(
            punct_frame,
            text="Insere vírgulas, pontos e pontos de interrogação baseado na entonação",
            style="SettingsDesc.TLabel"
        ).pack(anchor=tk.W, padx=(22, 0))

        self.capitalization_var = tk.BooleanVar(value=self.settings.capitalization)
        cap_frame = ttk.Frame(frame, style="Settings.TFrame")
        cap_frame.pack(anchor=tk.W, pady=4, fill=tk.X)
        
        ttk.Checkbutton(
            cap_frame,
            text="Capitalização automática",
            variable=self.capitalization_var,
            style="Settings.TCheckbutton",
            command=self.on_setting_change,
        ).pack(anchor=tk.W)
        
        ttk.Label(
            cap_frame,
            text="Deixa maiúsculas no início de frases e em nomes próprios",
            style="SettingsDesc.TLabel"
        ).pack(anchor=tk.W, padx=(22, 0))

        ttk.Label(
            frame,
            text="Sensibilidade de Parágrafo",
            style="SettingsTitle.TLabel"
        ).pack(anchor=tk.W, pady=(16, 4))
        
        ttk.Label(
            frame,
            text="Ajusta quanto tempo de pausa é necessário para criar um novo parágrafo",
            style="SettingsDesc.TLabel"
        ).pack(anchor=tk.W, pady=(0, 6))
        
        sensitivity_frame = ttk.Frame(frame, style="Settings.TFrame")
        sensitivity_frame.pack(fill=tk.X, pady=(0, 4))
        
        ttk.Label(sensitivity_frame, text="Menos pausas", style="SettingsDesc.TLabel").pack(side=tk.LEFT)
        ttk.Label(sensitivity_frame, text="Mais pausas", style="SettingsDesc.TLabel").pack(side=tk.RIGHT)
        
        self.paragraph_sensitivity = tk.IntVar(value=self.settings.paragraph_sensitivity)
        self.sensitivity_scale = ttk.Scale(
            frame,
            from_=0,
            to=100,
            variable=self.paragraph_sensitivity,
            orient=tk.HORIZONTAL,
            command=lambda *_: self.update_sensitivity_label(),
        )
        self.sensitivity_scale.pack(fill=tk.X)
        
        self.sensitivity_label = ttk.Label(frame, text="", style="SettingsDesc.TLabel")
        self.sensitivity_label.pack(anchor=tk.W, pady=(2, 0))
        self.update_sensitivity_label()

    def create_language_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=15, style="Settings.TFrame")
        self.notebook.add(frame, text="🌍 Idioma")

        ttk.Label(
            frame,
            text="Detecção de Idioma",
            style="SettingsTitle.TLabel"
        ).pack(anchor=tk.W, pady=(0, 4))
        
        ttk.Label(
            frame,
            text="Configure como o idioma do áudio será identificado",
            style="SettingsDesc.TLabel"
        ).pack(anchor=tk.W, pady=(0, 10))
        
        self.language_strategy_var = tk.StringVar(value=self.settings.language_strategy)
        
        strategy_descriptions = {
            "auto": "O modelo detecta automaticamente o idioma falado (recomendado)",
            "manual": "Você especifica o idioma manualmente (mais rápido se souber o idioma)",
            "multi": "Suporta múltiplos idiomas no mesmo áudio (experimental)"
        }
        
        for key, label in TRANSCRIPTION_OPTIONS["language_detection"].items():
            radio_frame = ttk.Frame(frame, style="Settings.TFrame")
            radio_frame.pack(anchor=tk.W, pady=3, fill=tk.X)
            
            ttk.Radiobutton(
                radio_frame,
                text=label,
                value=key,
                variable=self.language_strategy_var,
                style="Settings.TRadiobutton",
                command=lambda *_: self.toggle_language_entry(),
            ).pack(anchor=tk.W)
            
            ttk.Label(
                radio_frame,
                text=f"   • {strategy_descriptions.get(key, '')}",
                style="SettingsDesc.TLabel"
            ).pack(anchor=tk.W, padx=(20, 0))

        ttk.Label(
            frame,
            text="Código do Idioma Manual",
            style="SettingsTitle.TLabel"
        ).pack(anchor=tk.W, pady=(16, 4))
        
        ttk.Label(
            frame,
            text="Use códigos ISO 639-1: pt (Português), en (Inglês), es (Espanhol), fr (Francês)",
            style="SettingsDesc.TLabel"
        ).pack(anchor=tk.W, pady=(0, 6))
        
        self.manual_language_var = tk.StringVar(value=self.settings.manual_language)
        self.manual_entry = ttk.Entry(frame, textvariable=self.manual_language_var, width=15)
        self.manual_entry.pack(anchor=tk.W)

        ttk.Label(
            frame,
            text="Pós-processamento de Áudio",
            style="SettingsTitle.TLabel"
        ).pack(anchor=tk.W, pady=(20, 10))

        self.remove_noise_var = tk.BooleanVar(value=self.settings.remove_noise)
        noise_frame = ttk.Frame(frame, style="Settings.TFrame")
        noise_frame.pack(anchor=tk.W, pady=4, fill=tk.X)
        
        ttk.Checkbutton(
            noise_frame,
            text="Remover ruídos de fundo",
            variable=self.remove_noise_var,
            style="Settings.TCheckbutton",
        ).pack(anchor=tk.W)
        
        ttk.Label(
            noise_frame,
            text="Filtra sons ambientes e ruídos para melhorar a qualidade da transcrição",
            style="SettingsDesc.TLabel"
        ).pack(anchor=tk.W, padx=(22, 0))

        self.normalize_audio_var = tk.BooleanVar(value=self.settings.normalize_audio)
        norm_frame = ttk.Frame(frame, style="Settings.TFrame")
        norm_frame.pack(anchor=tk.W, pady=4, fill=tk.X)
        
        ttk.Checkbutton(
            norm_frame,
            text="Normalizar volume do áudio",
            variable=self.normalize_audio_var,
            style="Settings.TCheckbutton",
        ).pack(anchor=tk.W)
        
        ttk.Label(
            norm_frame,
            text="Equilibra o volume em áudios com variações de intensidade",
            style="SettingsDesc.TLabel"
        ).pack(anchor=tk.W, padx=(22, 0))

        self.toggle_language_entry()

    def create_quality_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=15, style="Settings.TFrame")
        self.notebook.add(frame, text="⚡ Qualidade")

        ttk.Label(
            frame,
            text="Balanceamento Velocidade vs Precisão",
            style="SettingsTitle.TLabel"
        ).pack(anchor=tk.W, pady=(0, 4))
        
        ttk.Label(
            frame,
            text="Escolha o equilíbrio ideal entre velocidade de processamento e qualidade do resultado",
            style="SettingsDesc.TLabel",
            wraplength=700
        ).pack(anchor=tk.W, pady=(0, 12))

        self.quality_var = tk.StringVar(value=self.settings.quality_preset)
        
        quality_info = {
            "fast": {
                "title": "Rápido",
                "desc": "Processamento veloz, ideal para rascunhos e revisões rápidas",
                "details": "• Até 3x mais rápido\n• Boa precisão para áudios claros\n• Recomendado para testes"
            },
            "balanced": {
                "title": "Equilibrado",
                "desc": "Melhor relação entre velocidade e qualidade para uso geral",
                "details": "• Velocidade moderada\n• Excelente precisão na maioria dos casos\n• Recomendado para uso diário"
            },
            "accurate": {
                "title": "Preciso",
                "desc": "Máxima qualidade, ideal para transcrições profissionais",
                "details": "• Processamento mais lento\n• Máxima precisão e detalhamento\n• Recomendado para áudios difíceis ou trabalhos finais"
            }
        }
        
        for key in ["fast", "balanced", "accurate"]:
            info = quality_info[key]
            
            quality_frame = ttk.LabelFrame(frame, text=info["title"], 
                                          style="SettingsSection.TLabelframe", padding=12)
            quality_frame.pack(fill=tk.X, pady=6)
            
            ttk.Radiobutton(
                quality_frame,
                text=info["desc"],
                value=key,
                variable=self.quality_var,
                style="Settings.TRadiobutton",
            ).pack(anchor=tk.W)
            
            ttk.Label(
                quality_frame,
                text=info["details"],
                style="SettingsDesc.TLabel"
            ).pack(anchor=tk.W, padx=(22, 0), pady=(4, 0))

    def on_setting_change(self) -> None:
        self.settings_changed = True
        self.update_preview()

    def toggle_language_entry(self) -> None:
        state = tk.NORMAL if self.language_strategy_var.get() == "manual" else tk.DISABLED
        self.manual_entry.configure(state=state)
        self.on_setting_change()

    def update_sensitivity_label(self) -> None:
        value = self.paragraph_sensitivity.get()
        pause_time = 0.5 + (value / 100.0) * 4.5
        
        if value < 25:
            desc = "Muito sensível - Cria parágrafos com pausas curtas"
        elif value < 50:
            desc = "Moderado - Equilíbrio entre parágrafos curtos e longos"
        elif value < 75:
            desc = "Menos sensível - Parágrafos mais longos"
        else:
            desc = "Pouco sensível - Apenas pausas muito longas criam parágrafos"
        
        self.sensitivity_label.config(text=f"Pausa necessária: {pause_time:.1f}s - {desc}")
        self.on_setting_change()

    def update_preview(self) -> None:
        if not self.preview_widget:
            return
        
        include_ts = self.include_timestamps_var.get()
        ts_mode = self.timestamp_mode_var.get()
        ts_format = self.timestamp_format_var.get()
        show_speakers = self.speakers_var.get()
        auto_para = self.paragraphs_var.get()
        has_punct = self.punctuation_var.get()
        has_caps = self.capitalization_var.get()
        output_fmt = self.output_format_var.get()
        
        example_text = [
            (0, "Olá e bem-vindo ao TextifyVoice", "Speaker 1"),
            (3.5, "este é um exemplo de como suas configurações afetarão o resultado final da transcrição", "Speaker 1"),
            (9.2, "note como os timestamps e a formatação mudam conforme você ajusta as opções", "Speaker 1"),
            (15.8, "você concorda com isso", "Speaker 2"),
            (17.5, "sim concordo perfeitamente", "Speaker 1"),
            (20.1, "as configurações de parágrafo detectam pausas longas na fala", "Speaker 1"),
            (26.3, "e criam quebras automáticas para melhorar a legibilidade do texto transcrito", "Speaker 1"),
        ]
        
        self.preview_widget.configure(state=tk.NORMAL)
        self.preview_widget.delete("1.0", tk.END)
        
        if output_fmt == "srt":
            for i, (time, text, speaker) in enumerate(example_text, 1):
                self.preview_widget.insert(tk.END, f"{i}\n")
                ts = self._format_preview_timestamp(time, "srt")
                end_ts = self._format_preview_timestamp(time + 3, "srt")
                self.preview_widget.insert(tk.END, f"{ts} --> {end_ts}\n", "timestamp")
                
                final_text = self._apply_text_formatting(text, has_punct, has_caps)
                self.preview_widget.insert(tk.END, f"{final_text}\n\n")
        
        elif output_fmt == "vtt":
            self.preview_widget.insert(tk.END, "WEBVTT\n\n", "timestamp")
            for time, text, speaker in example_text:
                ts = self._format_preview_timestamp(time, "vtt")
                end_ts = self._format_preview_timestamp(time + 3, "vtt")
                self.preview_widget.insert(tk.END, f"{ts} --> {end_ts}\n", "timestamp")
                
                final_text = self._apply_text_formatting(text, has_punct, has_caps)
                self.preview_widget.insert(tk.END, f"{final_text}\n\n")
        
        elif output_fmt == "json":
            json_preview = '{\n  "text": "Transcrição completa...",\n  "segments": [\n'
            json_preview += '    {\n      "start": 0.0,\n      "end": 3.5,\n'
            json_preview += '      "text": "Olá e bem-vindo..."\n    },\n'
            json_preview += '    ...\n  ]\n}'
            self.preview_widget.insert(tk.END, json_preview, "text")
        
        else:
            last_speaker = None
            paragraph_start_index = 0
            
            for i, (time, text, speaker) in enumerate(example_text):
                should_break = False
                
                if auto_para and i > 0:
                    time_diff = time - example_text[i-1][0]
                    sensitivity = self.paragraph_sensitivity.get()
                    pause_threshold = 0.5 + (sensitivity / 100.0) * 4.5
                    should_break = time_diff > pause_threshold
                
                if should_break or (show_speakers and speaker != last_speaker):
                    if i > 0:
                        self.preview_widget.insert(tk.END, "\n\n")
                    paragraph_start_index = i
                
                if show_speakers and (speaker != last_speaker or should_break):
                    self.preview_widget.insert(tk.END, f"{speaker}: ", "speaker")
                    last_speaker = speaker
                
                if include_ts:
                    if ts_mode == "word":
                        words = text.split()
                        for j, word in enumerate(words):
                            word_time = time + (j * 0.3)
                            ts = self._format_preview_timestamp(word_time, ts_format)
                            self.preview_widget.insert(tk.END, f"[{ts}] ", "timestamp")
                            final_word = self._apply_text_formatting(word, has_punct, has_caps)
                            self.preview_widget.insert(tk.END, f"{final_word} ", "text")
                    else:
                        if ts_mode == "segment" or (ts_mode == "paragraph" and i == paragraph_start_index):
                            ts = self._format_preview_timestamp(time, ts_format)
                            self.preview_widget.insert(tk.END, f"[{ts}] ", "timestamp")
                        
                        final_text = self._apply_text_formatting(text, has_punct, has_caps)
                        self.preview_widget.insert(tk.END, final_text, "text")
                else:
                    final_text = self._apply_text_formatting(text, has_punct, has_caps)
                    self.preview_widget.insert(tk.END, final_text, "text")
                
                if i < len(example_text) - 1:
                    self.preview_widget.insert(tk.END, " ", "text")
        
        self.preview_widget.configure(state=tk.DISABLED)

    def _apply_text_formatting(self, text: str, punct: bool, caps: bool) -> str:
        result = text
        
        if not caps:
            result = result.lower()
        elif caps and result and not result[0].isupper():
            result = result[0].upper() + result[1:]
        
        if punct and not any(result.endswith(p) for p in ['.', '!', '?', ',']):
            if "?" in text or "você" in text.lower():
                result += "?"
            else:
                result += "."
        elif not punct:
            result = result.rstrip('.,!?;:')
        
        return result

    def _format_preview_timestamp(self, seconds: float, mode: str) -> str:
        if mode == "srt":
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            millis = int((seconds % 1) * 1000)
            return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"
        
        if mode == "vtt":
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            millis = int((seconds % 1) * 1000)
            return f"{hours:02}:{minutes:02}:{secs:02}.{millis:03}"
        
        if mode == "seconds":
            return f"{seconds:.1f}s"
        
        if mode == "minutes":
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes:02}:{secs:04.1f}"
        
        if mode == "timecode":
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            frames = int((seconds % 1) * 25)
            return f"{hours:02}:{minutes:02}:{secs:02}:{frames:02}"
        
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02}:{minutes:02}:{secs:05.2f}"

    def apply_settings(self) -> None:
        self.apply_settings_to_instance()
        self.main_gui.settings = TranscriptionSettings.from_dict(self.settings.to_dict())
        if hasattr(self.main_gui, "update_settings_badge"):
            self.main_gui.update_settings_badge()
        messagebox.showinfo("Sucesso", "Configurações aplicadas com sucesso!")
        self.settings_changed = False
        self.close()

    def save_preset(self) -> None:
        name = simpledialog.askstring("Salvar preset", "Nome do preset:", parent=self.window)
        if not name:
            return
        try:
            self.apply_settings_to_instance()
            self.settings.save_preset(name)
            self.preset_combo.configure(values=sorted(self.settings.available_presets().keys()))
            messagebox.showinfo("Preset salvo", f"Preset '{name}' salvo com sucesso!")
        except Exception as exc:
            messagebox.showerror("Erro", str(exc))

    def apply_settings_to_instance(self) -> None:
        self.settings.output_format = self.output_format_var.get()
        self.settings.include_timestamps = self.include_timestamps_var.get()
        self.settings.timestamp_mode = self.timestamp_mode_var.get()
        self.settings.timestamp_format = self.timestamp_format_var.get()
        self.settings.auto_paragraphs = self.paragraphs_var.get()
        self.settings.detect_speakers = self.speakers_var.get()
        self.settings.punctuation = self.punctuation_var.get()
        self.settings.capitalization = self.capitalization_var.get()
        self.settings.paragraph_sensitivity = int(self.paragraph_sensitivity.get())
        self.settings.language_strategy = self.language_strategy_var.get()
        self.settings.manual_language = self.manual_language_var.get()
        self.settings.remove_noise = self.remove_noise_var.get()
        self.settings.normalize_audio = self.normalize_audio_var.get()
        self.settings.quality_preset = self.quality_var.get()

    def import_settings(self) -> None:
        filepath = filedialog.askopenfilename(
            parent=self.window,
            title="Importar configurações",
            filetypes=[("Arquivos JSON", "*.json")],
        )
        if not filepath:
            return
        try:
            self.settings.import_config(filepath)
            self._load_values_from_settings()
            messagebox.showinfo("Configurações importadas", "Configurações aplicadas com sucesso!")
        except Exception as exc:
            messagebox.showerror("Erro", f"Não foi possível importar: {exc}")

    def export_settings(self) -> None:
        filepath = filedialog.asksaveasfilename(
            parent=self.window,
            title="Exportar configurações",
            defaultextension=".json",
            filetypes=[("Arquivos JSON", "*.json")],
        )
        if not filepath:
            return
        try:
            self.apply_settings_to_instance()
            self.settings.export_config(filepath)
            messagebox.showinfo("Configurações exportadas", "Arquivo salvo com sucesso!")
        except Exception as exc:
            messagebox.showerror("Erro", f"Não foi possível exportar: {exc}")

    def _load_values_from_settings(self) -> None:
        self.output_format_var.set(self.settings.output_format)
        self.include_timestamps_var.set(self.settings.include_timestamps)
        self.timestamp_mode_var.set(self.settings.timestamp_mode)
        self.timestamp_format_var.set(self.settings.timestamp_format)
        self.paragraphs_var.set(self.settings.auto_paragraphs)
        self.speakers_var.set(self.settings.detect_speakers)
        self.punctuation_var.set(self.settings.punctuation)
        self.capitalization_var.set(self.settings.capitalization)
        self.paragraph_sensitivity.set(self.settings.paragraph_sensitivity)
        self.language_strategy_var.set(self.settings.language_strategy)
        self.manual_language_var.set(self.settings.manual_language)
        self.remove_noise_var.set(self.settings.remove_noise)
        self.normalize_audio_var.set(self.settings.normalize_audio)
        self.quality_var.set(self.settings.quality_preset)
        self.toggle_language_entry()
        self.update_preview()
        if hasattr(self, "preset_combo"):
            self.preset_combo.set("")

    def on_preset_selected(self, _event=None) -> None:
        self.load_selected_preset()

    def load_selected_preset(self) -> None:
        preset_name = self.preset_var.get().strip()
        if not preset_name:
            return
        try:
            self.settings.load_preset(preset_name)
            self._load_values_from_settings()
            messagebox.showinfo("Preset aplicado", f"Preset '{preset_name}' carregado com sucesso!")
        except Exception as exc:
            messagebox.showerror("Erro", f"Não foi possível carregar o preset: {exc}")

    def close(self) -> None:
        if self.settings_changed:
            response = messagebox.askyesnocancel(
                "Alterações não salvas",
                "Você tem alterações não confirmadas. Deseja aplicá-las antes de fechar?"
            )
            if response is None:
                return
            elif response:
                self.apply_settings()
                return
        
        if hasattr(self.main_gui, "settings_window") and self.main_gui.settings_window is self:
            self.main_gui.settings_window = None
        if self.window.winfo_exists():
            self.window.destroy()