# Ultima-DL ⚡

**The Ultimate YouTube Downloader** (Local Desktop Tool)

Ultima-DL is a high-performance, dark-themed YouTube video and playlist downloader. Designed to run locally on your machine, it grants you direct access to your native file system and leverages FFmpeg to merge ultra-high-quality 4K videos at maximum speed.

---

## 🚀 Quick Start (Windows)

You need **Python 3.8+** and **FFmpeg** to use this app. 

If you are on Windows, open your Terminal (PowerShell or Command Prompt) and run these two commands to install everything instantly:

**1. Install Python:**
```bash
winget install Python.Python.3.11
```

**2. Install FFmpeg (Required for 4K video merging & Audio extraction):**
```bash
winget install gyan.ffmpeg
```

*(Note: After installing, close your terminal and open a new one so the changes take effect!)*

---

## 💻 How to Run the App

1. **Open your terminal inside the project folder.**
   *(If on Windows, you can click the address bar in File Explorer, type `cmd`, and press Enter).*
2. **Install the required Python packages:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Start the Flask server:**
   ```bash
   python app.py
   ```
4. **Open your web browser and navigate to:** **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

*(Leave the terminal window open while you are downloading videos!)*

---

## 🏗 Technical Architecture

This application is built as a lightweight, highly efficient local web service. 

* **Backend Engine:** Python 3 + **[Flask](https://flask.palletsprojects.com/)**
  * Serves the frontend API endpoints and handles concurrent background threads for playlist downloads.
* **Extraction Core:** **[yt-dlp](https://github.com/yt-dlp/yt-dlp)**
  * A powerful command-line audio/video downloader. It bypassing throttles and safely extracts video metadata, duration, formats, and playlist indices.
* **Media Processor:** **FFmpeg**
  * When users select "Pro" formats (1080p, 1440p, 4K), YouTube serves the video and audio as two separate streams. The Flask backend commands yt-dlp to download both and uses FFmpeg to merge them flawlessly into an MP4.
* **Frontend:** Vanilla HTML5, CSS3, JavaScript (Single Page Application)
  * Implements a premium "YouTube-Dark" theme. Uses Server-Sent Events (SSE) to stream live download progress bars directly from the Python backend to the UI.
* **OS Integration:** **tkinter**
  * Used explicitly for the `POST /browse_folder` endpoint, allowing the web app to trigger a native Windows folder-picker dialog for playlist directory selection.

---

## ✨ Features
* **🎬 Single Video:** Download precisely the resolution you want (144p up to 4K), or extract high-quality audio.
* **📋 Playlist Downloading:** Paste a playlist link, choose a single quality preset, pick a folder on your PC, and download the entire playlist automatically.
* **📂 Native Folder Selection:** The app opens an actual Windows folder window to let you easily pick where to save your local files.

---

