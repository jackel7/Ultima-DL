<div align="center">
  <h1>⚡ Ultima-DL</h1>
  <p><b>The Ultimate High-Performance YouTube Video & Playlist Downloader</b></p>
  <p><i>A beautifully dark-themed local desktop tool with 4K video merging & real-time progress tracking.</i></p>
</div>

---

## 💻 Why Ultima-DL?
Unlike web-hosted downloaders, Ultima-DL runs directly on your machine. This gives it two massive superpowers:
1. **Unrestricted 4K Downloading:** It uses FFmpeg behind the scenes to merge YouTube's raw 4K video and audio streams seamlessly.
2. **Native Folder Selection:** Want to download a 50-video playlist? Just click "Browse" in the app, pick a folder on your computer using your native OS window, and watch as the files save directly to your hard drive with a real-time progress bar.

---

## 🚀 Quick Start (Windows)
To use this app, you only need Python and FFmpeg on your machine. 

If you are on Windows, open your Terminal (Command Prompt or PowerShell) and copy-paste these commands to install everything you need instantly:

### Step 1: Install Dependencies (Python & FFmpeg)
```bash
winget install Python.Python.3.11
winget install gyan.ffmpeg
```
*(⚠️ **Important:** After running these commands, close your terminal and open a brand new one before moving to Step 2!)*

### Step 2: Download the App
Clone this repository to your computer:
```bash
git clone https://github.com/jackel7/Ultima-DL.git
cd Ultima-DL
```

### Step 3: Install Required Libraries
Install the required python libraries (`flask` and `yt-dlp`):
```bash
pip install flask yt-dlp
```
*(Alternatively, you can run `pip install -r requirements.txt`)*

### Step 4: Run the App
Start the app easily:
**Just double click the `Ultima-DL.bat` file!** It will automatically install missing libraries, start the local server, and pop open the UI in your web browser!

*(Alternatively, you can manually run `python app.py` and open `http://127.0.0.1:5000` in your browser)*

*(Note: Keep the black terminal window open while you are downloading videos!)*

---

## ✨ Features
* **🎬 Single Video Mode:** Download exactly the resolution you want (144p up to 4K), or extract high-quality audio (MP3).
* **📋 Advanced Playlist Mode:** Extract entire playlists, selectively check/uncheck specific videos, and seamlessly download massive 400+ video queues with built-in anti-bot IP-evasion cooldowns!
* **🛑 Download Control:** Cancel any active playlist downloads instantly with the click of a button.
* **⚡ Pro Video Merging:** Uses `FFmpeg` to seamlessly multiplex separated YouTube streams into one perfect `.mp4`.
* **👀 Real-Time Progress:** Beautiful custom UI that live-tracks background downloads and auto-recovers from dropped connections.

---

<div align="center">
  <b>Developed by <a href="https://github.com/jackel7">Jackel</a></b><br>
  <b>Connect with me <a href="https://www.linkedin.com/in/muhammad-ali-naeem-93898b308/">Linkedin</a></b><br>

  
  <i>Flutter Developer</i>
</div>
