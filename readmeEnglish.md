# TextifyVoice - Audio and Video Transcription with Whisper

**TextifyVoice** is an efficient application that integrates OpenAI’s Whisper ASR model with a straightforward and user-friendly graphical interface. This tool is designed to support seamless transcription of audio and video files, converting spoken content into written text with ease.

Originally, I leveraged the Whisper library locally on my computer, working with files solely through the command line. However, as the demand for video transcriptions using Whisper increased, I recognized that this needed to be extended beyond my use. This realization sparked the development of a more accessible solution for individuals less familiar with technology—particularly those uncomfortable with command-line interfaces. The result was a desktop application offering two main benefits: it’s free and can operate offline, eliminating the requirement for a constant internet connection.

The project was developed emphasizing object-oriented programming (OOP) principles and modularity to minimize code duplication and ensure components were decoupled to reduce the risk of major errors. Multithreading and multiprocessing were key in managing the Graphical User Interface (GUI) and the application’s internal processes, such as loading the Whisper models and handling file operations. This ensured that the interface remained responsive during resource-intensive tasks.

## Features

- **Audio and Video Transcription**: Effortlessly convert audio or video files into text.
- **User-Friendly Interface**: Transcribe files via a straightforward, easy-to-navigate GUI.
- **Support for Various Formats**: Works with formats such as MP3, MP4, WAV, AAC, FLAC, M4A, OGG, and more.
- **Customizable Model Selection**: Choose the appropriate transcription model based on your specific requirements.
- **Enhanced Audio Processing**: Utilizes FFmpeg for extracting audio tracks from video files.
- **Automatic File Saving**: Transcriptions are saved as `.docx` files in the same directory as the source files.
- **Process Cancellation**: Allows for the cancellation of ongoing model downloads and transcriptions.

## Requirements

- **Python 3.8 or higher** (Python 3.11 recommended) for module installation.
- **FFmpeg**: Necessary for processing video files. Ensure FFmpeg is installed and configured in your system PATH.
- **Internet Connection**: Required only for downloading models and updates.

### Hardware Requirements by Model:

| Model        | Transcription Time\* | Accuracy  | Required VRAM | Relative Speed |
| ------------ | -------------------- | --------- | ------------- | -------------- |
| **Tiny**     | 0.5 \* File Duration | Low       | \~1 GB        | \~32x          |
| **Base**     | 0.5 \* File Duration | Medium    | \~1 GB        | \~16x          |
| **Small**    | 0.7 \* File Duration | High      | \~2 GB        | \~6x           |
| **Medium**   | 1 \* File Duration   | Very High | \~5 GB        | \~2x           |
| **Large-V1** | 1.7 \* File Duration | Very High | \~10 GB       | 1x             |
| **Large-V2** | 1.7 \* File Duration | Very High | \~10 GB       | 1x             |
| **Large-V3** | 1.7 \* File Duration | Very High | \~10 GB       | 1x             |

\*Estimated transcription time is approximately 1.5 times the audio duration and may vary depending on hardware.

## Installation

**FFmpeg**

Two installation scripts are available: `install_ffmpeg_profile.ps1` (user-level installation) and `install_ffmpeg_adm.ps1` (administrator-level installation). These PowerShell scripts simplify the installation process for FFmpeg, which is essential for file conversion when using the application.

Manual installation instructions are available [here](https://www.wikihow.com/Install-FFmpeg-on-Windows).

### Pre-compiled Executable

1. **Download**: Obtain the latest version [here](https://github.com/finnzao/TextifyVoiceDesktopPy/releases/tag/v1).
2. **Installation**: Extract the downloaded archive.
3. **Execution**: Run `TextifyVoice.exe`.
4. **Configuration**: Set your preferences during the initial run.
5. **Usage**: Begin transcribing your files!

## Development

### Setup

1. **Clone the Repository**:

   ```bash
   git clone <https://github.com/finnzao/TextifyVoiceDesktopPy.git>
   ```

2. **Navigate to the Project Directory**:

   ```bash
   cd TextifyVoiceDesktopPy
   ```

3. **Create a Virtual Environment**:

   ```bash
   python -m venv venv
   ```

4. **Activate the Virtual Environment**:

   - **Windows**:
     ```bash
     venv\Scripts\activate
     ```
   - **Linux/macOS**:
     ```bash
     source venv/bin/activate
     ```

5. **Install Dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

### Running the Application

Run the application using the following command:

```bash
python main.py
```

### Compilation

To compile the project into an executable, use **`pyinstaller`**:

```bash
pyinstaller --windowed --hidden-import=whisper --icon="./bin/icon.ico" --add-data="./bin/ffmpeg.exe;bin" --add-data="config.json;." textifyVoiceModelDownload.py
```

### Compatibility

The project supports Windows, Linux, and macOS. If any bugs or issues arise, please feel free to submit an issue report.

