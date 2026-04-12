import os
import re
import uuid
import threading
import time
import json
import tempfile
import random
from flask import Flask, render_template, request, jsonify, send_file, after_this_request, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for the browser extension

# Use local downloads folder so user can see them while being downloaded
DOWNLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'downloads'))
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Store playlist download progress per session
playlist_progress = {}


def sanitize_filename(title):
    """Strip illegal characters from filenames to prevent OS errors."""
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', title)
    sanitized = sanitized.strip('. ')
    if not sanitized:
        sanitized = 'video'
    return sanitized[:200]


def format_duration(seconds):
    """Convert seconds to HH:MM:SS or MM:SS format."""
    if not seconds:
        return 'N/A'
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f'{hours}:{minutes:02d}:{secs:02d}'
    return f'{minutes}:{secs:02d}'


# --- Network Retry Settings ---
MAX_RETRIES = 6
RETRY_DELAY = 5  # seconds between retries

NETWORK_ERROR_KEYWORDS = [
    'timed out', 'timeout', 'connection reset', 'connection refused',
    'connection aborted', 'broken pipe', 'network is unreachable',
    'name resolution', 'dns', 'temporary failure', 'errno 11001',
    'urlopen error', 'incomplete read', 'connection error',
    'remotedisconnected', 'incompleteread', 'sslerror',
    'eof occurred', 'reset by peer', '429', 'too many requests',
    'rate-limit', 'rate limit', '10054', 'connectionreseterror'
]


def _is_network_error(error):
    """Check if an exception is a recoverable network error."""
    msg = str(error).lower()
    return any(kw in msg for kw in NETWORK_ERROR_KEYWORDS)


def delayed_delete(filepath, delay=5):
    """Delete a file after a delay in a background thread."""
    def _delete():
        time.sleep(delay)
        try:
            if os.path.exists(filepath):
                if os.path.isdir(filepath):
                    import shutil
                    shutil.rmtree(filepath, ignore_errors=True)
                else:
                    os.remove(filepath)
        except OSError:
            pass
    thread = threading.Thread(target=_delete, daemon=True)
    thread.start()


def categorize_formats(formats):
    """Categorize formats into video and audio lists, showing ALL qualities."""
    video_formats = []
    audio_formats = []

    seen_video = set()
    seen_audio = set()

    for f in formats:
        format_id = f.get('format_id', '')
        ext = f.get('ext', '')
        height = f.get('height')
        filesize = f.get('filesize') or f.get('filesize_approx')
        vcodec = f.get('vcodec', 'none')
        acodec = f.get('acodec', 'none')
        fps = f.get('fps')
        format_note = f.get('format_note', '')

        has_video = vcodec != 'none' and vcodec is not None
        has_audio = acodec != 'none' and acodec is not None

        size_str = ''
        if filesize:
            if filesize > 1024 * 1024 * 1024:
                size_str = f'{filesize / (1024*1024*1024):.1f} GB'
            elif filesize > 1024 * 1024:
                size_str = f'{filesize / (1024*1024):.1f} MB'
            elif filesize > 1024:
                size_str = f'{filesize / 1024:.1f} KB'

        # Audio-only formats
        if has_audio and not has_video:
            abr = f.get('abr', 0)
            audio_key = f'{ext}_{int(abr) if abr else 0}'
            if audio_key not in seen_audio and abr and abr > 0:
                seen_audio.add(audio_key)
                audio_formats.append({
                    'format_id': format_id,
                    'ext': ext.upper(),
                    'quality': f'{int(abr)}kbps',
                    'abr': abr or 0,
                    'size': size_str,
                })

        # Video formats — show ALL resolutions
        elif has_video and height:
            resolution = f'{height}p'
            needs_merge = not has_audio

            res_key = f'{height}_{ext}_{needs_merge}'
            if res_key not in seen_video:
                seen_video.add(res_key)

                category = 'standard' if has_audio else 'pro'

                video_formats.append({
                    'format_id': format_id,
                    'resolution': resolution,
                    'ext': ext.upper(),
                    'fps': fps,
                    'size': size_str,
                    'height': height,
                    'note': format_note,
                    'category': category,
                    'needs_merge': needs_merge,
                })

    standard = [v for v in video_formats if v['category'] == 'standard']
    pro = [v for v in video_formats if v['category'] == 'pro']

    standard.sort(key=lambda x: (x['height'], x.get('fps') or 0), reverse=True)
    pro.sort(key=lambda x: (x['height'], x.get('fps') or 0), reverse=True)
    audio_formats.sort(key=lambda x: x['abr'], reverse=True)

    return standard, pro, audio_formats


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/browse_folder', methods=['POST'])
def browse_folder():
    """Open a native OS folder picker dialog and return the selected path."""
    selected = [None]

    def _pick():
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            folder = filedialog.askdirectory(title='Select Download Folder')
            root.destroy()
            selected[0] = folder
        except Exception as e:
            print(f"[Warning] Native folder picker failed (headless environment?): {e}")
            selected[0] = None

    # tkinter must run on a separate thread in Flask
    t = threading.Thread(target=_pick)
    t.start()
    t.join(timeout=120)  # wait up to 2 minutes for user to pick

    if selected[0]:
        return jsonify({'folder': selected[0]})
    else:
        return jsonify({'folder': ''})


@app.route('/extract', methods=['POST'])
def extract():
    """Extract video metadata and available formats from a URL."""
    import yt_dlp

    data = request.get_json()
    url = data.get('url', '').strip()

    if not url:
        return jsonify({'error': 'Please enter a valid URL.'}), 400

    ydl_opts = {
        'nocheckcertificate': True,
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'ignoreerrors': False,
        'noplaylist': True,
        'socket_timeout': 30,
        'extractor_args': {'youtube': ['player_client=android,tv,web']},
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            if info is None:
                return jsonify({'error': 'Could not extract video information.'}), 400

            title = info.get('title', 'Unknown Title')
            thumbnail = info.get('thumbnail', '')
            channel = info.get('uploader', info.get('channel', 'Unknown Channel'))
            duration = format_duration(info.get('duration'))

            standard, pro, audio = categorize_formats(info.get('formats', []))

            return jsonify({
                'title': title,
                'thumbnail': thumbnail,
                'channel': channel,
                'duration': duration,
                'standard': standard,
                'pro': pro,
                'audio': audio,
            })

    except Exception as e:
        error_msg = str(e).lower()
        if 'private' in error_msg or 'sign in' in error_msg or 'age' in error_msg or 'restricted' in error_msg:
            return jsonify({'error': 'This video is restricted. Please try a public video.'}), 403
        elif 'not a valid url' in error_msg or 'unsupported url' in error_msg:
            return jsonify({'error': 'Invalid URL. Please enter a valid YouTube link.'}), 400
        else:
            return jsonify({'error': f'Could not process this video. {str(e)[:200]}'}), 500


@app.route('/extract_playlist', methods=['POST'])
def extract_playlist():
    """Extract playlist metadata — list of video titles."""
    import yt_dlp

    data = request.get_json()
    url = data.get('url', '').strip()

    if not url:
        return jsonify({'error': 'Please enter a valid URL.'}), 400

    ydl_opts = {
        'nocheckcertificate': True,
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': True,
        'socket_timeout': 30,
        'ignoreerrors': True,
        'extractor_args': {'youtube': ['player_client=android,tv,web']},
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            if info is None:
                return jsonify({'error': 'Could not extract playlist info.'}), 400

            entries = info.get('entries', [])
            if not entries:
                return jsonify({'error': 'No videos found in this playlist.'}), 400

            playlist_title = info.get('title', 'Playlist')
            videos = []
            for i, entry in enumerate(entries):
                if entry is None:
                    continue
                videos.append({
                    'index': i + 1,
                    'title': entry.get('title', f'Video {i+1}'),
                    'url': entry.get('url') or entry.get('webpage_url', ''),
                    'duration': format_duration(entry.get('duration')),
                })

            quality_presets = [
                {'id': 'best', 'label': 'Best Quality', 'desc': 'Highest available'},
                {'id': 'm4a', 'label': '🔥 Original M4A', 'desc': 'Best Sound / Small Size (~3MB)'},
                {'id': 'audio', 'label': '🎵 MP3 Audio', 'desc': 'Standard MP3 (~3.5MB)'},
                {'id': '2160', 'label': '4K (2160p)', 'desc': 'Ultra HD'},
                {'id': '1440', 'label': '1440p', 'desc': 'Quad HD'},
                {'id': '1080', 'label': '1080p', 'desc': 'Full HD'},
                {'id': '720', 'label': '720p', 'desc': 'HD'},
                {'id': '480', 'label': '480p', 'desc': 'Standard'},
                {'id': '360', 'label': '360p', 'desc': 'Low'},
                {'id': '240', 'label': '240p', 'desc': 'Very Low'},
            ]

            return jsonify({
                'playlist_title': playlist_title,
                'count': len(videos),
                'videos': videos,
                'quality_presets': quality_presets,
            })

    except Exception as e:
        return jsonify({'error': f'Could not extract playlist. {str(e)[:200]}'}), 500


# Store single video download progress
single_progress = {}

@app.route('/start_download', methods=['POST'])
def start_download():
    """Start a single video/audio download and return a session_id."""
    data = request.get_json()
    url = data.get('url', '').strip()
    format_id = data.get('format_id', '')
    category = data.get('category', 'standard')

    if not url or not format_id:
        return jsonify({'error': 'Missing URL or format selection.'}), 400

    session_id = str(uuid.uuid4())[:12]
    single_progress[session_id] = {
        'status': 'starting',
        'percent': '0%',
        'done': False,
        'error': None,
        'file_path': None,
        'safe_title': None
    }
    
    threading.Thread(
        target=_single_download_worker,
        args=(url, format_id, category, session_id),
        daemon=True
    ).start()
    
    return jsonify({'session_id': session_id})

def _single_download_worker(url, format_id, category, session_id):
    import yt_dlp
    prog = single_progress[session_id]
    
    unique_id = session_id[:8]
    temp_template = os.path.join(DOWNLOAD_DIR, f'{unique_id}_%(title)s.%(ext)s')

    def progress_hook(d):
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '0%')
            p = re.sub(r'\x1b[^m]*m', '', p).strip()  # remove ansi formatting
            prog['percent'] = p
            prog['status'] = f"Downloading... {p}"

    ydl_opts = {
        'nocheckcertificate': True,
        'quiet': True,
        'no_warnings': True,
        'outtmpl': temp_template,
        'restrictfilenames': True,
        'noplaylist': True,
        'socket_timeout': 30,
        'progress_hooks': [progress_hook],
        'extractor_args': {'youtube': ['player_client=android,tv,web']},
    }

    if category == 'pro':
        ydl_opts['format'] = f'{format_id}+bestaudio/best'
        ydl_opts['merge_output_format'] = 'mp4'
    elif category == 'm4a':
        ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio'
        # Crucially: we do NOT use FFmpegExtractAudio post-processor so we preserve the pure 100% original quality
    elif category == 'audio':
        ydl_opts['format'] = format_id
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }]
    else:
        ydl_opts['format'] = format_id

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # Clean up any partial files from previous attempts
            if attempt > 1:
                for f in os.listdir(DOWNLOAD_DIR):
                    if f.startswith(unique_id):
                        try:
                            os.remove(os.path.join(DOWNLOAD_DIR, f))
                        except OSError:
                            pass

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                prog['status'] = 'Fetching info...' if attempt == 1 else f'Retrying... (attempt {attempt}/{MAX_RETRIES})'
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise Exception("Download returned None (rate limit or unavailable)")
                prog['status'] = 'Finalizing file...'
                title = sanitize_filename(info.get('title', 'video'))

                downloaded_file = None
                for f in os.listdir(DOWNLOAD_DIR):
                    if f.startswith(unique_id):
                        downloaded_file = os.path.join(DOWNLOAD_DIR, f)
                        break

                if not downloaded_file or not os.path.exists(downloaded_file):
                    raise Exception('Download failed. File not found.')

                ext = os.path.splitext(downloaded_file)[1]
                if category == 'audio' and ext != '.mp3':
                    ext = '.mp3'
                elif category == 'pro' and ext != '.mp4':
                    ext = '.mp4'

                safe_title = f'{title}{ext}'

                prog['file_path'] = downloaded_file
                prog['safe_title'] = safe_title
                prog['done'] = True
                prog['status'] = 'complete'
                last_error = None
                break  # Success

        except Exception as e:
            last_error = e
            error_clean = re.sub(r'\x1b[^m]*m', '', str(e))
            error_msg = error_clean.lower()
            if 'private' in error_msg or 'sign in' in error_msg or 'age' in error_msg or 'bot' in error_msg:
                break

            if attempt < MAX_RETRIES and (_is_network_error(e) or '429' in error_msg or 'rate' in error_msg or '10054' in error_msg):
                backoff = RETRY_DELAY * (2 ** (attempt - 1))
                if backoff > 60:
                    backoff = 60
                prog['status'] = f'Network drop. Waiting {backoff}s for internet... ({attempt}/{MAX_RETRIES})'
                prog['percent'] = '0%'
                time.sleep(backoff)
                continue
            else:
                break

    # Handle final failure after all retries
    if last_error:
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(unique_id):
                try:
                    os.remove(os.path.join(DOWNLOAD_DIR, f))
                except OSError:
                    pass

        error_clean = re.sub(r'\x1b[^m]*m', '', str(last_error))
        error_msg = error_clean.lower()
        if 'private' in error_msg or 'sign in' in error_msg or 'age' in error_msg or 'bot' in error_msg:
            prog['error'] = 'YouTube blocked this download (Sign-in / Bot Check required).'
        elif _is_network_error(last_error):
            prog['error'] = f'Network error after {MAX_RETRIES} attempts. Check your connection and try again.'
        else:
            prog['error'] = f'Download failed. {error_clean[:200]}'
        prog['done'] = True

    def _cleanup():
        time.sleep(3600)  # Keep session alive for 1 hour so they can download it
        single_progress.pop(session_id, None)
    threading.Thread(target=_cleanup, daemon=True).start()

@app.route('/single_progress/<session_id>')
def get_single_progress(session_id):
    def generate():
        while True:
            prog = single_progress.get(session_id)
            if not prog:
                data = json.dumps({'error': 'Session not found', 'done': True})
                yield f'data: {data}\n\n'
                break
                
            data = json.dumps({
                'status': prog['status'],
                'percent': prog['percent'],
                'done': prog['done'],
                'error': prog['error']
            })
            yield f'data: {data}\n\n'
            
            if prog['done']:
                break
            time.sleep(1)
    return Response(generate(), mimetype='text/event-stream')

@app.route('/download_file/<session_id>')
def download_file(session_id):
    """Deliver the actual file to the browser once it is fully created."""
    prog = single_progress.get(session_id)
    if not prog or not prog.get('file_path'):
        return jsonify({'error': 'File not ready or expired.'}), 404
        
    file_path = prog['file_path']
    safe_title = prog['safe_title']
    
    @after_this_request
    def cleanup(response):
        delayed_delete(file_path)
        single_progress.pop(session_id, None)
        return response

    return send_file(
        file_path,
        as_attachment=True,
        download_name=safe_title,
        mimetype='application/octet-stream'
    )


@app.route('/download_playlist', methods=['POST'])
def download_playlist():
    """Start a playlist download to a local folder. Returns a session_id for progress tracking."""
    import yt_dlp

    data = request.get_json()
    url = data.get('url', '').strip()
    quality = data.get('quality', 'best')
    folder = data.get('folder', '').strip()
    selected_indices = data.get('indices', []) # List of 1-based indices to download
    print(f"[DEBUG] download_playlist called! indices received: {selected_indices}")

    if not url:
        return jsonify({'error': 'Missing playlist URL.'}), 400

    if not folder:
        return jsonify({'error': 'Please specify a download folder.'}), 400

    # Normalize and validate folder path
    folder = os.path.normpath(folder)
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception as e:
        return jsonify({'error': f'Cannot create folder: {str(e)[:100]}'}), 400

    session_id = str(uuid.uuid4())[:12]
    playlist_progress[session_id] = {
        'status': 'starting',
        'current': 0,
        'total': 0,
        'current_title': '',
        'completed': [],
        'errors': [],
        'done': False,
    }

    # Start download in background thread
    thread = threading.Thread(
        target=_download_playlist_worker,
        args=(url, quality, folder, session_id, selected_indices),
        daemon=True
    )
    thread.start()

    return jsonify({'session_id': session_id})


def _download_playlist_worker(url, quality, folder, session_id, selected_indices):
    """Background worker that downloads each video and updates progress."""
    import yt_dlp

    progress = playlist_progress[session_id]

    # First, extract playlist to get video list
    extract_opts = {
        'nocheckcertificate': True,
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': True,
        'socket_timeout': 30,
        'ignoreerrors': True,
    }

    try:
        with yt_dlp.YoutubeDL(extract_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            entries = info.get('entries', []) or []
            playlist_title = sanitize_filename(info.get('title', 'Playlist'))

        # Filter entries based on selected_indices AND skip unavailable videos
        if selected_indices:
            entries_to_download = [(i, e) for i, e in enumerate(entries) if e is not None and (i + 1) in selected_indices]
        else:
            entries_to_download = [(i, e) for i, e in enumerate(entries) if e is not None]

        if not entries_to_download:
             progress['status'] = 'error'
             progress['errors'].append('No valid videos found or selected.')
             progress['done'] = True
             return

        progress['total'] = len(entries_to_download)
        progress['status'] = 'downloading'
        
        # Create subfolder with playlist name
        save_dir = os.path.join(folder, playlist_title)
        os.makedirs(save_dir, exist_ok=True)

        # Build format string
        if quality == 'audio':
            format_str = 'bestaudio/best'
        elif quality == 'best':
            format_str = 'bestvideo+bestaudio/best'
        else:
            format_str = f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best'

        # Download each video one by one
        current_download_idx = 0
        for i, entry in entries_to_download:
            if progress.get('canceled'):
                progress['status'] = 'Canceled'
                progress['errors'].append('Playlist download canceled by user.')
                break
                
            current_download_idx += 1
            video_url = entry.get('url') or entry.get('webpage_url', '')
            video_title = entry.get('title', f'Video {i+1}')

            if not video_url:
                progress['errors'].append(f'#{i+1}: No URL found')
                progress['current'] = current_download_idx
                continue

            progress['current'] = current_download_idx
            progress['current_title'] = video_title
            progress['status'] = f'Downloading {current_download_idx}/{len(entries_to_download)}'

            def _cancel_hook(d):
                if progress.get('canceled'):
                    raise Exception('Download Canceled By User')

            ydl_opts = {
                'nocheckcertificate': True,
                'quiet': True,
                'no_warnings': True,
                'outtmpl': os.path.join(save_dir, f'{i+1:03d}_%(title)s.%(ext)s'),
                'restrictfilenames': True,
                'noplaylist': True,
                'socket_timeout': 30,
                'format': format_str,
                'ignoreerrors': False,
                'progress_hooks': [_cancel_hook],
                'extractor_args': {'youtube': ['player_client=android,tv,web']},
            }

            if quality == 'm4a':
                ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio'
            elif quality != 'audio':
                ydl_opts['merge_output_format'] = 'mp4'
            else:
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '128',
                }]

            video_success = False
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    if attempt > 1:
                        progress['status'] = f'Retrying #{i+1} (attempt {attempt}/{MAX_RETRIES})'
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(video_url, download=True)
                        if info is None:
                            raise Exception("Download returned None (rate limit or unavailable)")
                        progress['completed'].append(video_title)
                        video_success = True
                        break
                except Exception as e:
                    error_clean = re.sub(r'\x1b[^m]*m', '', str(e))
                    error_msg = error_clean.lower()
                    if attempt < MAX_RETRIES and (_is_network_error(e) or '429' in error_msg or 'rate' in error_msg or '10054' in error_msg):
                        backoff = RETRY_DELAY * (2 ** (attempt - 1))
                        if backoff > 60:
                            backoff = 60
                        progress['status'] = f'No internet! Waiting {backoff}s for connection to return... (attempt {attempt}/{MAX_RETRIES})'
                        time.sleep(backoff)
                        continue
                    
                    if 'bot' in error_msg or 'sign in' in error_msg:
                        progress['errors'].append(f'#{i+1} {video_title}: YouTube Bot Blocked (Try again later)')
                    else:
                        progress['errors'].append(f'#{i+1} {video_title}: {error_clean[:150]}')
                    break
            
            # If we have downloaded a batch of 30 videos, take a larger human-like break
            if current_download_idx % 30 == 0 and current_download_idx < len(entries_to_download):
                progress['status'] = f'Cooldown pause to avoid bot detection... (resuming soon)'
                time.sleep(random.uniform(15.0, 25.0))
            else:
                # Use a random delay between 4 and 9 seconds to simulate human click times
                time.sleep(random.uniform(4.0, 9.0))

        progress['status'] = 'complete'
        progress['done'] = True
        progress['save_dir'] = save_dir

    except Exception as e:
        progress['status'] = 'error'
        progress['errors'].append(str(e)[:200])
        progress['done'] = True

    # Clean up progress after 5 minutes
    def _cleanup():
        time.sleep(300)
        playlist_progress.pop(session_id, None)
    threading.Thread(target=_cleanup, daemon=True).start()


@app.route('/playlist_progress/<session_id>')
def get_playlist_progress(session_id):
    """SSE endpoint that streams playlist download progress."""
    def generate():
        while True:
            progress = playlist_progress.get(session_id)
            if progress is None:
                data = json.dumps({'error': 'Session not found', 'done': True})
                yield f'data: {data}\n\n'
                break

            data = json.dumps({
                'status': progress['status'],
                'current': progress['current'],
                'total': progress['total'],
                'current_title': progress['current_title'],
                'completed_count': len(progress['completed']),
                'error_count': len(progress['errors']),
                'errors': progress['errors'][-3:],  # last 3 errors
                'done': progress['done'],
                'save_dir': progress.get('save_dir', ''),
            })
            yield f'data: {data}\n\n'

            if progress['done']:
                break

            time.sleep(1)

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/cancel_playlist/<session_id>', methods=['POST'])
def cancel_playlist(session_id):
    if session_id in playlist_progress:
        playlist_progress[session_id]['canceled'] = True
        return jsonify({'status': 'canceling'})
    return jsonify({'error': 'Session not found'}), 404


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
