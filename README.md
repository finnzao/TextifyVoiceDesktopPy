# TextifyVoice - Transcrição de Áudio e Vídeo com Whisper



### 🌐 *English version of the README available here [here](https://github.com/finnzao/TextifyVoiceDesktopPy/releases/tag/v1).*


**TextifyVoice** é uma aplicação prática que combina o modelo Whisper ASR da OpenAI com uma interface gráfica simples e intuitiva. Ela serve como uma ferramenta versátil para transcrição de áudio e vídeo, permitindo ao usuário converter facilmente linguagem falada em texto escrito.

Inicialmente, eu utilizava a biblioteca Whisper localmente no meu computador, manipulando os arquivos apenas por meio do prompt de comando. No entanto, conforme as solicitações para uso do Whisper em transcrições de vídeos se tornaram frequentes, percebi que essa necessidade era compartilhada por outras pessoas. Dessa forma, surgiu a ideia de criar uma maneira mais acessível para aqueles que não têm contato frequente com tecnologia—especialmente para quem se sente intimidado ao utilizar o prompt de comando. A solução foi desenvolver uma aplicação desktop com duas principais vantagens: ser gratuita e possibilitar transcrições sem a necessidade de conexão com a internet.

O desenvolvimento seguiu uma lógica de Programação Orientada a Objetos (POO) e modularidade, principalmente para evitar a repetição de código, com um desacoplamento que previne erros críticos na aplicação. O uso de multithreading e multiprocessing foi fundamental para a administração da Interface Gráfica do Usuário (GUI) e dos processamentos internos da aplicação, como o carregamento dos modelos Whisper e a manipulação de arquivos, evitando que a interface trave durante a execução dessas tarefas internas.

## Funcionalidades

- **Transcrição de Áudio e Vídeo**: Converta arquivos de áudio ou vídeo em texto com facilidade.
- **Interface Gráfica Intuitiva**: Selecione e transcreva arquivos através de uma interface amigável.
- **Suporte a Múltiplos Formatos**: Compatível com formatos como MP3, MP4, WAV, AAC, FLAC, M4A, OGG, entre outros.
- **Download de Modelos Personalizável**: Escolha entre diferentes modelos de transcrição com base em suas necessidades.
- **Processamento de Áudio Otimizado**: Utiliza FFmpeg para extrair trilhas sonoras de arquivos de vídeo.
- **Salvamento Automático**: As transcrições são salvas em arquivos `.docx` no mesmo diretório dos arquivos originais.
- **Cancelamento de Processos**: Possibilidade de cancelar downloads de modelos e transcrições em andamento.

## Requisitos

- **Python 3.8 ou superior** (Recomendado Python 3.11) para instalação como módulo.
- **FFmpeg**: Necessário para processar arquivos de vídeo. Certifique-se de que o FFmpeg está instalado e configurado no PATH do sistema.
- **Conexão com a Internet**: Necessária *apenas* para download dos modelos e atualizações.

### Requisitos de Hardware por Modelo:

| Modelo | Tempo de Transcrição* | Precisão | VRAM Requerida | Velocidade Relativa |
| --- | --- | --- | --- | --- |
| **Tiny** | 0,5 * TempoArquivo | Baixa | ~1 GB | ~32x |
| **Base** | 0,5 * TempoArquivo | Média | ~1 GB | ~16x |
| **Small** | 0,7 * TempoArquivo | Alta | ~2 GB | ~6x |
| **Medium** | 1 *  TempoArquivo | Muito Alta | ~5 GB | ~2x |
| **Large-V1** | 1,7 * TempoArquivo | Muito Alta | ~10 GB | 1x |
| **Large-V2** | 1,7 * TempoArquivo | Muito Alta | ~10 GB | 1x |
| **Large-V3** | 1,7 * TempoArquivo | Muito Alta | ~10 GB | 1x |

\*O tempo estimado para a transcrição acima é de aproximadamente 1,50 vezes a duração do áudio, podendo variar conforme o hardware utilizado.

## Instalação

**FFmpeg** 

Existem dois arquivos para instalação, `install_ffmpeg_profile.ps1` (instalação a nível de usuário atual) e `install_ffmpeg_adm.ps1` (instalação a nível de administrador). Esses scripts em PowerShell foram criados para facilitar o processo de instalação do FFmpeg, um programa essencial para a conversão de arquivos durante o uso da aplicação.

Também existe uma maneira de instalar manualmente [LINK](https://www.wikihow.com/Install-FFmpeg-on-Windows).

### Executável Pré-compilado

1. **Download**: Baixe a versão mais recente [aqui](https://github.com/finnzao/TextifyVoiceDesktopPy/releases/tag/v1).
2. **Instalação**: Extraia o arquivo baixado.
3. **Execução**: Execute o arquivo `TextifyVoice.exe`.
4. **Configuração**: Na primeira execução, configure as preferências conforme suas necessidades.
5. **Uso**: Comece a transcrever seus arquivos!



## Desenvolvimento

### Configuração

1. **Clone o Repositório**:
    
    ```bash
    git clone <https://github.com/finnzao/TextifyVoiceDesktopPy.git>
    
    ```
    
2. **Entre no Diretório do Projeto**:
    
    ```bash
    cd TextifyVoiceDesktopPy
    
    ```
    
3. **Crie um Ambiente Virtual**:
    
    ```bash
    python -m venv venv
    
    ```
    
4. **Ative o Ambiente Virtual**:
    - **Windows**:
        
        ```bash
        venv\\Scripts\\activate
        
        ```
        
    - **Linux/macOS**:
        
        ```bash
        source venv/bin/activate
        
        ```
        
5. **Instale as Dependências**:
    
    ```bash
    pip install -r requirements.txt
    
    ```
    

### Executando o Aplicativo

Execute o aplicativo usando o seguinte comando:

```bash
python main.py
```

### Compilação

Para compilar o projeto em um executável utilize **`pyinstaller`**:

```bash
pyinstaller --windowed --hidden-import=whisper --icon="./bin/icon.ico" --add-data="./bin/ffmpeg.exe;bin" --add-data="config.json;." textifyVoiceModelDownload.py
```

### Compatibilidade

O projeto é compatível com Windows, Linux e macOS. Caso encontre algum bug ou problema, sinta-se à vontade para criar uma issue.