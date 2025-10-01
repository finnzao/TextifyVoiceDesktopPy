"""Advanced transcription settings utilities and presets."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional


TRANSCRIPTION_OPTIONS: Dict[str, Dict[str, str]] = {
    "output_format": {
        "docx": "Documento Word (.docx)",
        "txt": "Texto Simples (.txt)",
        "srt": "Legendas (.srt)",
        "vtt": "WebVTT (.vtt)",
        "json": "JSON estruturado",
    },
    "timestamp_mode": {
        "none": "Sem marcas de tempo",
        "segment": "Marca de tempo por segmento",
        "word": "Marca de tempo por palavra",
        "paragraph": "Marca de tempo por parágrafo",
    },
    "timestamp_format": {
        "seconds": "Segundos (120.5s)",
        "minutes": "Minutos:Segundos (02:00.5)",
        "full": "Horas:Minutos:Segundos (00:02:00.5)",
        "timecode": "Timecode (00:02:00:15)",
    },
    "formatting": {
        "paragraphs": "Separar em parágrafos automaticamente",
        "speakers": "Identificar diferentes falantes (diarização)",
        "punctuation": "Adicionar pontuação automática",
        "capitalization": "Capitalização automática",
    },
    "language_detection": {
        "auto": "Detectar idioma automaticamente",
        "manual": "Especificar idioma manualmente",
        "multi": "Suportar múltiplos idiomas no mesmo arquivo",
    },
}


def _default_presets_path() -> str:
    base_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "config")
    if not os.path.exists(base_dir):
        os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "transcription_presets.json")


@dataclass
class TranscriptionSettings:
    """Container for advanced transcription settings with preset utilities."""

    output_format: str = "docx"
    include_timestamps: bool = False
    timestamp_mode: str = "segment"
    timestamp_format: str = "minutes"
    auto_paragraphs: bool = True
    detect_speakers: bool = False
    punctuation: bool = True
    capitalization: bool = True
    language_strategy: str = "auto"
    manual_language: str = "pt"
    quality_preset: str = "balanced"
    paragraph_sensitivity: int = 50
    remove_noise: bool = False
    normalize_audio: bool = False
    presets_file: str = field(default_factory=_default_presets_path, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data.pop("presets_file", None)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TranscriptionSettings":
        instance = cls()
        for key, value in data.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        return instance

    def save_preset(self, name: str) -> None:
        name = name.strip()
        if not name:
            raise ValueError("O nome do preset não pode estar vazio.")
        presets = self._load_presets()
        presets[name] = self.to_dict()
        self._write_presets(presets)

    def load_preset(self, name: str) -> None:
        presets = self._load_presets()
        if name not in presets:
            raise KeyError(f"Preset '{name}' não encontrado.")
        loaded = presets[name]
        for key, value in loaded.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def export_config(self, filepath: str) -> None:
        with open(filepath, "w", encoding="utf-8") as fp:
            json.dump(self.to_dict(), fp, indent=4, ensure_ascii=False)

    def import_config(self, filepath: str) -> None:
        with open(filepath, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        loaded = self.from_dict(data)
        for field_name, value in loaded.to_dict().items():
            setattr(self, field_name, value)

    def available_presets(self) -> Dict[str, Dict[str, Any]]:
        return self._load_presets()

    def summary(self) -> str:
        parts = [TRANSCRIPTION_OPTIONS["output_format"].get(self.output_format, self.output_format)]
        if self.include_timestamps:
            parts.append(TRANSCRIPTION_OPTIONS["timestamp_mode"].get(
                self.timestamp_mode, self.timestamp_mode))
        else:
            parts.append("Sem timestamps")
        parts.append({
            "fast": "Rápido",
            "balanced": "Equilibrado",
            "accurate": "Preciso",
        }.get(self.quality_preset, self.quality_preset))
        return " • ".join(parts)

    # Internal helpers -------------------------------------------------
    def _load_presets(self) -> Dict[str, Dict[str, Any]]:
        if os.path.exists(self.presets_file):
            try:
                with open(self.presets_file, "r", encoding="utf-8") as fp:
                    return json.load(fp)
            except json.JSONDecodeError:
                return {}
        return {}

    def _write_presets(self, presets: Dict[str, Dict[str, Any]]) -> None:
        with open(self.presets_file, "w", encoding="utf-8") as fp:
            json.dump(presets, fp, indent=4, ensure_ascii=False)


DEFAULT_PRESETS: Dict[str, Dict[str, Any]] = {
    "Entrevista": {
        "output_format": "docx",
        "include_timestamps": True,
        "timestamp_mode": "segment",
        "timestamp_format": "full",
        "auto_paragraphs": True,
        "detect_speakers": True,
        "punctuation": True,
        "capitalization": True,
        "language_strategy": "auto",
        "quality_preset": "accurate",
    },
    "Aula": {
        "output_format": "txt",
        "include_timestamps": False,
        "timestamp_mode": "segment",
        "timestamp_format": "minutes",
        "auto_paragraphs": True,
        "detect_speakers": False,
        "punctuation": True,
        "capitalization": True,
        "language_strategy": "auto",
        "quality_preset": "balanced",
    },
    "Reunião": {
        "output_format": "docx",
        "include_timestamps": True,
        "timestamp_mode": "segment",
        "timestamp_format": "minutes",
        "auto_paragraphs": True,
        "detect_speakers": True,
        "punctuation": True,
        "capitalization": True,
        "language_strategy": "auto",
        "quality_preset": "balanced",
    },
    "Podcast": {
        "output_format": "srt",
        "include_timestamps": True,
        "timestamp_mode": "segment",
        "timestamp_format": "full",
        "auto_paragraphs": False,
        "detect_speakers": False,
        "punctuation": True,
        "capitalization": True,
        "language_strategy": "auto",
        "quality_preset": "fast",
    },
}


def ensure_default_presets(settings: Optional[TranscriptionSettings] = None) -> None:
    target = settings or TranscriptionSettings()
    presets = target._load_presets()
    missing = False
    for name, data in DEFAULT_PRESETS.items():
        if name not in presets:
            presets[name] = data
            missing = True
    if missing:
        target._write_presets(presets)


ensure_default_presets()
