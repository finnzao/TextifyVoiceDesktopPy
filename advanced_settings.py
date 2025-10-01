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
        self.window = tk.Toplevel(main_gui.root)
        self.window.title("Configurações Avançadas")
        self.window.geometry("620x520")
        self.window.grab_set()
        if hasattr(main_gui.config, "ICON_PATH") and main_gui.config.ICON_PATH:
            try:
                if main_gui.config.ICON_PATH and main_gui.config.ICON_PATH.endswith(".ico"):
                    self.window.iconbitmap(main_gui.config.ICON_PATH)
            except Exception:
                pass
        self.window.configure(bg=main_gui.colors.get("background", "#2b2d31"))
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.create_styles()
        self.create_widgets()
        self.update_preview()

    # ------------------------------------------------------------------
    def create_styles(self) -> None:
        style = ttk.Style(self.window)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        bg = self.main_gui.colors.get("background", "#2b2d31")
        fg = self.main_gui.colors.get("foreground", "#f5f5f5")
        accent = self.main_gui.colors.get("accent", "#4f46e5")
        style.configure("Settings.TFrame", background=bg)
        style.configure("Settings.TLabel", background=bg, foreground=fg)
        style.configure(
            "SettingsSection.TLabelframe",
            background=bg,
            foreground=fg,
        )
        style.configure(
            "SettingsSection.TLabelframe.Label",
            foreground=fg,
        )
        style.configure(
            "Settings.TButton",
            background=accent,
            foreground=fg,
            font=("Segoe UI", 10, "bold"),
        )
        style.configure("Settings.TCheckbutton", background=bg, foreground=fg)
        style.configure("Settings.TMenubutton", background=bg, foreground=fg)

    def create_widgets(self) -> None:
        container = ttk.Frame(self.window, style="Settings.TFrame", padding=16)
        container.pack(expand=True, fill=tk.BOTH)

        presets_frame = ttk.Frame(container, style="Settings.TFrame")
        presets_frame.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(
            presets_frame,
            text="Presets",
            style="Settings.TLabel",
        ).pack(side=tk.LEFT)
        preset_names = sorted(self.settings.available_presets().keys())
        self.preset_var = tk.StringVar(value=preset_names[0] if preset_names else "")
        self.preset_combo = ttk.Combobox(
            presets_frame,
            textvariable=self.preset_var,
            values=preset_names,
            state="readonly",
            width=25,
        )
        self.preset_combo.pack(side=tk.LEFT, padx=(8, 0))
        self.preset_combo.bind("<<ComboboxSelected>>", self.on_preset_selected)
        ttk.Button(
            presets_frame,
            text="Aplicar preset",
            command=self.load_selected_preset,
            style="Settings.TButton",
        ).pack(side=tk.LEFT, padx=(8, 0))

        self.notebook = ttk.Notebook(container)
        self.notebook.pack(expand=True, fill=tk.BOTH)

        self.create_format_tab()
        self.create_timestamp_tab()
        self.create_formatting_tab()
        self.create_language_tab()
        self.create_quality_tab()

        footer = ttk.Frame(container, style="Settings.TFrame")
        footer.pack(fill=tk.X, pady=(12, 0))

        preview_box = tk.Text(
            footer,
            height=5,
            wrap="word",
            bg="#1e1f24",
            fg="#f0f0f0",
            relief="flat",
            font=("Consolas", 10),
        )
        preview_box.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        preview_box.insert("1.0", "")
        preview_box.configure(state=tk.DISABLED)
        self.preview_widget = preview_box

        button_frame = ttk.Frame(footer, style="Settings.TFrame")
        button_frame.pack(fill=tk.X)

        ttk.Button(
            button_frame,
            text="Importar",
            command=self.import_settings,
            style="Settings.TButton",
        ).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(
            button_frame,
            text="Exportar",
            command=self.export_settings,
            style="Settings.TButton",
        ).pack(side=tk.LEFT)

        ttk.Button(
            button_frame,
            text="Salvar Preset",
            command=self.save_preset,
            style="Settings.TButton",
        ).pack(side=tk.RIGHT, padx=(8, 0))

        ttk.Button(
            button_frame,
            text="Aplicar",
            command=self.apply_settings,
            style="Settings.TButton",
        ).pack(side=tk.RIGHT)

    # Tabs -------------------------------------------------------------
    def create_format_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=12, style="Settings.TFrame")
        self.notebook.add(frame, text="Formato")

        ttk.Label(
            frame,
            text="Formato de saída",
            style="Settings.TLabel",
        ).pack(anchor=tk.W)

        self.output_format_var = tk.StringVar(value=self.settings.output_format)
        for key, label in TRANSCRIPTION_OPTIONS["output_format"].items():
            ttk.Radiobutton(
                frame,
                text=label,
                value=key,
                variable=self.output_format_var,
                style="Settings.TCheckbutton",
                command=self.update_preview,
            ).pack(anchor=tk.W, pady=2)

    def create_timestamp_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=12, style="Settings.TFrame")
        self.notebook.add(frame, text="Timestamps")

        self.include_timestamps_var = tk.BooleanVar(value=self.settings.include_timestamps)
        ttk.Checkbutton(
            frame,
            text="Incluir marcas de tempo",
            variable=self.include_timestamps_var,
            style="Settings.TCheckbutton",
            command=self.update_preview,
        ).pack(anchor=tk.W, pady=(0, 8))

        ttk.Label(frame, text="Modo", style="Settings.TLabel").pack(anchor=tk.W)
        self.timestamp_mode_var = tk.StringVar(value=self.settings.timestamp_mode)
        mode_menu = ttk.OptionMenu(
            frame,
            self.timestamp_mode_var,
            self.settings.timestamp_mode,
            *TRANSCRIPTION_OPTIONS["timestamp_mode"].keys(),
            command=lambda *_: self.update_preview(),
        )
        mode_menu.pack(anchor=tk.W, pady=4)

        ttk.Label(frame, text="Formato", style="Settings.TLabel").pack(anchor=tk.W, pady=(8, 0))
        self.timestamp_format_var = tk.StringVar(value=self.settings.timestamp_format)
        fmt_menu = ttk.OptionMenu(
            frame,
            self.timestamp_format_var,
            self.settings.timestamp_format,
            *TRANSCRIPTION_OPTIONS["timestamp_format"].keys(),
            command=lambda *_: self.update_preview(),
        )
        fmt_menu.pack(anchor=tk.W, pady=4)

    def create_formatting_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=12, style="Settings.TFrame")
        self.notebook.add(frame, text="Formatação")

        self.paragraphs_var = tk.BooleanVar(value=self.settings.auto_paragraphs)
        ttk.Checkbutton(
            frame,
            text="Separar em parágrafos automaticamente",
            variable=self.paragraphs_var,
            style="Settings.TCheckbutton",
            command=self.update_preview,
        ).pack(anchor=tk.W, pady=2)

        self.speakers_var = tk.BooleanVar(value=self.settings.detect_speakers)
        ttk.Checkbutton(
            frame,
            text="Identificar diferentes falantes",
            variable=self.speakers_var,
            style="Settings.TCheckbutton",
        ).pack(anchor=tk.W, pady=2)

        self.punctuation_var = tk.BooleanVar(value=self.settings.punctuation)
        ttk.Checkbutton(
            frame,
            text="Adicionar pontuação automática",
            variable=self.punctuation_var,
            style="Settings.TCheckbutton",
        ).pack(anchor=tk.W, pady=2)

        self.capitalization_var = tk.BooleanVar(value=self.settings.capitalization)
        ttk.Checkbutton(
            frame,
            text="Capitalização automática",
            variable=self.capitalization_var,
            style="Settings.TCheckbutton",
        ).pack(anchor=tk.W, pady=2)

        ttk.Label(frame, text="Sensibilidade de parágrafo", style="Settings.TLabel").pack(
            anchor=tk.W, pady=(12, 0)
        )
        self.paragraph_sensitivity = tk.IntVar(value=self.settings.paragraph_sensitivity)
        ttk.Scale(
            frame,
            from_=0,
            to=100,
            variable=self.paragraph_sensitivity,
            orient=tk.HORIZONTAL,
            command=lambda *_: self.update_preview(),
        ).pack(fill=tk.X, pady=4)

    def create_language_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=12, style="Settings.TFrame")
        self.notebook.add(frame, text="Idioma")

        ttk.Label(frame, text="Detecção de idioma", style="Settings.TLabel").pack(anchor=tk.W)
        self.language_strategy_var = tk.StringVar(value=self.settings.language_strategy)
        strategy_menu = ttk.OptionMenu(
            frame,
            self.language_strategy_var,
            self.settings.language_strategy,
            *TRANSCRIPTION_OPTIONS["language_detection"].keys(),
            command=lambda *_: self.toggle_language_entry(),
        )
        strategy_menu.pack(anchor=tk.W, pady=4)

        ttk.Label(frame, text="Idioma manual", style="Settings.TLabel").pack(anchor=tk.W, pady=(8, 0))
        self.manual_language_var = tk.StringVar(value=self.settings.manual_language)
        self.manual_entry = ttk.Entry(frame, textvariable=self.manual_language_var)
        self.manual_entry.pack(anchor=tk.W, fill=tk.X)

        ttk.Label(frame, text="Opções de pós-processamento", style="Settings.TLabel").pack(
            anchor=tk.W, pady=(12, 0)
        )
        self.remove_noise_var = tk.BooleanVar(value=self.settings.remove_noise)
        ttk.Checkbutton(
            frame,
            text="Remover ruídos",
            variable=self.remove_noise_var,
            style="Settings.TCheckbutton",
        ).pack(anchor=tk.W)

        self.normalize_audio_var = tk.BooleanVar(value=self.settings.normalize_audio)
        ttk.Checkbutton(
            frame,
            text="Normalizar volume",
            variable=self.normalize_audio_var,
            style="Settings.TCheckbutton",
        ).pack(anchor=tk.W)

        self.toggle_language_entry()

    def create_quality_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=12, style="Settings.TFrame")
        self.notebook.add(frame, text="Qualidade")

        ttk.Label(frame, text="Balanceamento", style="Settings.TLabel").pack(anchor=tk.W)
        self.quality_var = tk.StringVar(value=self.settings.quality_preset)
        ttk.Radiobutton(
            frame,
            text="Rápido",
            value="fast",
            variable=self.quality_var,
            style="Settings.TCheckbutton",
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            frame,
            text="Equilibrado",
            value="balanced",
            variable=self.quality_var,
            style="Settings.TCheckbutton",
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            frame,
            text="Preciso",
            value="accurate",
            variable=self.quality_var,
            style="Settings.TCheckbutton",
        ).pack(anchor=tk.W)

    # Actions ----------------------------------------------------------
    def toggle_language_entry(self) -> None:
        state = tk.NORMAL if self.language_strategy_var.get() == "manual" else tk.DISABLED
        self.manual_entry.configure(state=state)
        self.update_preview()

    def update_preview(self) -> None:
        example_segments = [
            ("00:00:00", "Bem-vindo ao TextifyVoice."),
            ("00:00:05", "Esta é uma prévia das configurações de transcrição."),
        ]
        include_ts = self.include_timestamps_var.get()
        fmt = self.timestamp_format_var.get()
        lines = []
        for index, (timestamp, text) in enumerate(example_segments, start=1):
            if include_ts:
                lines.append(f"[{self._format_preview_timestamp(timestamp, fmt)}] {text}")
            else:
                lines.append(text)
        preview_text = "\n".join(lines)
        self.preview_widget.configure(state=tk.NORMAL)
        self.preview_widget.delete("1.0", tk.END)
        self.preview_widget.insert("1.0", preview_text)
        self.preview_widget.configure(state=tk.DISABLED)

    def _format_preview_timestamp(self, timestamp: str, mode: str) -> str:
        if mode == "seconds":
            return "5.0s"
        if mode == "minutes":
            return "00:05.0"
        if mode == "timecode":
            return "00:00:05:12"
        return timestamp

    def apply_settings(self) -> None:
        self.apply_settings_to_instance()
        self.main_gui.settings = TranscriptionSettings.from_dict(self.settings.to_dict())
        if hasattr(self.main_gui, "update_settings_badge"):
            self.main_gui.update_settings_badge()
        self.close()

    def save_preset(self) -> None:
        name = simpledialog.askstring("Salvar preset", "Nome do preset:", parent=self.window)
        if not name:
            return
        try:
            self.apply_settings_to_instance()
            self.settings.save_preset(name)
            self.preset_combo.configure(values=sorted(self.settings.available_presets().keys()))
            messagebox.showinfo("Preset salvo", f"Preset '{name}' salvo com sucesso.")
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
            messagebox.showinfo("Configurações importadas", "Configurações aplicadas com sucesso.")
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
            messagebox.showinfo("Configurações exportadas", "Arquivo salvo com sucesso.")
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
            messagebox.showinfo("Preset aplicado", f"Preset '{preset_name}' carregado.")
        except Exception as exc:
            messagebox.showerror("Erro", f"Não foi possível carregar o preset: {exc}")

    def close(self) -> None:
        if hasattr(self.main_gui, "settings_window") and self.main_gui.settings_window is self:
            self.main_gui.settings_window = None
        if self.window.winfo_exists():
            self.window.destroy()
