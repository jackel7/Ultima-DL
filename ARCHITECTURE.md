# Ultima-DL: Current Architecture & SaaS Migration Guide

If you are showing this document to another AI to ask for help turning this app into a web-hosted SaaS (Software as a Service), here is the exact technical breakdown of what the application is currently doing and why it is built as a **Local Desktop App** right now.

## 1. Core Technology Stack
* **Backend:** Python 3, Flask (Web framework)
* **Frontend:** Vanilla HTML5, CSS3, JavaScript (Single Page Application, no frameworks)
* **Extractor Engine:** `yt-dlp` (Extracts URLs, metadata, and downloads media)
* **Media Processor:** `FFmpeg` (Used for merging 4K video streams with audio streams)
* **OS Integration:** `tkinter` (Used to open native Windows folder-picker dialogs)

## 2. API Endpoints & How They Work

### A. Single Video Flow
* `POST /extract`
  * Accepts a YouTube URL.
  * Uses `yt-dlp` (`extract_info(download=False)`) to fetch the title, thumbnail, duration, and a massive list of all available formats.
  * Parses formats into three categories: `Standard` (Pre-merged Video+Audio, 144p-720p), `Pro` (Video-only streams up to 4K that require FFmpeg merging), and `Audio Only` (M4A/WebM converted to high-quality MP3).
* `POST /download`
  * Accepts a URL, a `format_id`, and a `category`.
  * Downloads the file using `yt-dlp`. If the category is `pro`, it tells `yt-dlp` to download `format_id+bestaudio/best` and merge them into an `.mp4` using `FFmpeg`.
  * Saves the file temporarily to a local `/downloads` folder on the server.
  * Streams the file to the user's browser using Flask's `send_file(as_attachment=True)`.
  * Runs a background thread (`delayed_delete()`) that deletes the file from the server's hard drive 5 seconds after the browser download completes.

### B. Playlist Flow (Highly Local-Dependent)
* `POST /extract_playlist`
  * Uses `yt-dlp` (`extract_flat=True`) to get just the titles, URLs, and indices of all videos in the playlist extremely quickly without extracting massive metadata for each video.
* `POST /browse_folder`
  * **(CRITICAL FOR MIGRATION)** This endpoint imports Python's `tkinter` and `filedialog`. It opens a native Windows GUI folder-picker dialog on the server's monitor.
  * Returns the absolute string path of the selected OS folder (e.g., `D:\YouTube Downloads`).
* `POST /download_playlist`
  * Accepts the playlist URL, the chosen quality preset (e.g., `1080`), and the absolute folder path chosen by the user.
  * Creates a unique `session_id`.
  * Spawns a background Python `threading.Thread` that iterates through every video in the playlist, downloading them **directly to the user's specified hard drive folder**.
  * Updates a global `playlist_progress[session_id]` dictionary with the current status, current video, and any errors.
* `GET /playlist_progress/<session_id>`
  * A Server-Sent Events (SSE) endpoint that streams the progress dictionary to the frontend in real-time.

---

## 3. What Needs to Change to Make this a Public SaaS

If another AI is helping you deploy this to a cloud server (like DigitalOcean, AWS, or Render), **they must help you rewrite the following:**

1. **Remove `tkinter`:** Cloud servers run headless Linux. You cannot pop open a folder window. The `POST /browse_folder` endpoint and the Browse button on the frontend must be deleted.
2. **Rewrite Playlist Downloads (The ZIP Method):** 
   * Since a cloud server cannot save files directly to the website visitor's local `D:\` drive, the server must download the entire playlist into a temporary folder on the cloud server.
   * The server must then use Python's `zipfile` module to compress that folder into a single `.zip` file.
   * The server must stream that `.zip` file to the user's browser (just like the Single Video flow).
   * The server must aggressively delete the `.zip` file and temporary folder afterward to prevent the server's hard drive from getting 100% full.
3. **Handle Server Infrastructure:** The AI must guide you to install `ffmpeg` on your Linux server, set up `Gunicorn` (WSGI HTTP server), and `Nginx` (Reverse Proxy).
4. **Proxy/Banning Risk:** The most difficult part of SaaS deployment: If 1,000 people use your website today, YouTube will see 1,000 downloads coming from your server's 1 single IP address. YouTube will IP-ban your server very quickly. The AI must explain how to use residential proxy rotators with `yt-dlp` to avoid this.
