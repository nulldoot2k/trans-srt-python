# app.py - OPTIMIZED VERSION

from flask import Flask, render_template, request, jsonify, send_file
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import re
import requests
from dotenv import load_dotenv, set_key, find_dotenv
import tempfile
import time
import hashlib
import logging
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import random
import threading
import atexit
from datetime import datetime, timedelta
from collections import deque
import redis
from urllib.parse import quote

# ==================== CONFIGURATION ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__,
            template_folder='statis',
            static_folder='statis',
            static_url_path='/statis')

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(32))

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# ==================== REDIS SETUP ====================
try:
    redis_client = redis.Redis(
        host=os.getenv('REDIS_HOST', 'localhost'),
        port=int(os.getenv('REDIS_PORT', 6379)),
        db=0,
        decode_responses=True,
        socket_timeout=2,
        socket_connect_timeout=2
    )
    redis_client.ping()
    REDIS_AVAILABLE = True
    logger.info("✅ Redis connected successfully")
except Exception as e:
    logger.warning(f"⚠️ Redis not available, using in-memory cache: {e}")
    redis_client = None
    REDIS_AVAILABLE = False

# Fallback in-memory cache
MEMORY_CACHE = {}
CACHE_MAX_SIZE = 5000
CACHE_TTL = 7 * 24 * 3600  # 7 days

# ==================== API ENDPOINTS ====================
GROQ_API = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
OPENAI_API = "https://api.openai.com/v1/chat/completions"

# ==================== GOOGLE TRANSLATE CONFIG ====================
lang_map = {
    'auto': 'auto', 'en': 'en', 'vi': 'vi', 'zh': 'zh-CN',
    'zh-cn': 'zh-CN', 'zh-tw': 'zh-TW', 'ja': 'ja', 'ko': 'ko',
    'th': 'th', 'fr': 'fr', 'de': 'de', 'es': 'es', 'pt': 'pt',
    'ru': 'ru', 'ar': 'ar', 'hi': 'hi', 'id': 'id', 'it': 'it',
    'nl': 'nl', 'pl': 'pl', 'tr': 'tr', 'uk': 'uk',
}

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
]

# ==================== RATE LIMITING ====================
class RateLimiter:
    """Smart rate limiter để tránh bị Google chặn"""
    def __init__(self, max_requests=15, time_window=1.0):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()
        self.lock = threading.Lock()
    
    def acquire(self):
        with self.lock:
            now = time.time()
            # Xóa requests cũ
            while self.requests and self.requests[0] < now - self.time_window:
                self.requests.popleft()
            
            if len(self.requests) >= self.max_requests:
                sleep_time = self.time_window - (now - self.requests[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    self.requests.popleft()
            
            self.requests.append(time.time())

# Global rate limiter - 15 req/s (an toàn với Google)
google_limiter = RateLimiter(max_requests=15, time_window=1.0)

# ==================== PROGRESS TRACKING ====================
current_progress = 0
progress_lock = threading.Lock()
current_mode = "Google Free"
total_subtitles = 0
processed_subtitles = 0

# ==================== CACHING LAYER ====================
def get_cache_key(text, source_lang, target_lang):
    """Tạo cache key deterministic"""
    normalized = text.strip().lower()
    return hashlib.md5(f"{normalized}:{source_lang}:{target_lang}".encode()).hexdigest()

def get_from_cache(text, source_lang, target_lang):
    """Lấy từ Redis hoặc memory cache"""
    cache_key = get_cache_key(text, source_lang, target_lang)
    
    if REDIS_AVAILABLE:
        try:
            cached = redis_client.get(f"trans:{cache_key}")
            if cached:
                return cached
        except Exception as e:
            logger.warning(f"Redis get error: {e}")
    
    # Fallback to memory
    return MEMORY_CACHE.get(cache_key)

def save_to_cache(text, source_lang, target_lang, translation):
    """Lưu vào Redis + memory cache"""
    cache_key = get_cache_key(text, source_lang, target_lang)
    
    if REDIS_AVAILABLE:
        try:
            redis_client.setex(f"trans:{cache_key}", CACHE_TTL, translation)
        except Exception as e:
            logger.warning(f"Redis set error: {e}")
    
    # Always save to memory as backup
    if len(MEMORY_CACHE) >= CACHE_MAX_SIZE:
        MEMORY_CACHE.pop(next(iter(MEMORY_CACHE)))
    MEMORY_CACHE[cache_key] = translation

# ==================== GOOGLE TRANSLATE ENGINE ====================
def google_translate_single(session, text, source_lang, target_lang, retry=0):
    """
    Single translation với smart retry
    """
    # Check cache first
    cached = get_from_cache(text, source_lang, target_lang)
    if cached:
        return cached, True  # (result, from_cache)
    
    # Rate limiting
    google_limiter.acquire()
    
    url = 'https://translate.googleapis.com/translate_a/single'
    params = {
        'client': 'gtx',
        'sl': 'auto' if source_lang == 'auto' else lang_map.get(source_lang, 'auto'),
        'tl': target_lang,
        'dt': 't',
        'ie': 'UTF-8',
        'oe': 'UTF-8',
        'q': text
    }
    
    try:
        resp = session.get(url, params=params, timeout=8)
        
        if resp.status_code == 200:
            data = resp.json()
            result = ''.join([s[0] for s in data[0] if s[0]]).strip()
            
            if result:
                save_to_cache(text, source_lang, target_lang, result)
                return result, False
            return text, False
        
        elif resp.status_code == 429:
            # Rate limited - wait longer
            if retry < 3:
                wait_time = (2 ** retry) * 5  # 5s, 10s, 20s
                logger.warning(f"Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
                return google_translate_single(session, text, source_lang, target_lang, retry + 1)
        
        resp.raise_for_status()
        return text, False
        
    except requests.exceptions.Timeout:
        if retry < 2:
            time.sleep(1)
            return google_translate_single(session, text, source_lang, target_lang, retry + 1)
        return text, False
        
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return text, False

def translate_with_google_parallel(texts, source_lang, target_lang):
    """
    OPTIMIZED parallel translation với:
    - Smart rate limiting
    - Redis caching
    - Adaptive worker pool
    - Batch processing
    """
    global current_progress, processed_subtitles
    
    total = len(texts)
    translations = [""] * total
    processed_subtitles = 0
    
    # Pre-check cache để giảm workload
    cache_hits = 0
    cache_misses = []
    
    for i, text in enumerate(texts):
        cached = get_from_cache(text, source_lang, target_lang)
        if cached:
            translations[i] = cached
            cache_hits += 1
            processed_subtitles += 1
        else:
            cache_misses.append(i)
    
    logger.info(f"Cache stats: {cache_hits}/{total} hits ({cache_hits/total*100:.1f}%)")
    
    if cache_hits > 0:
        with progress_lock:
            current_progress = int((processed_subtitles / total) * 100)
    
    if not cache_misses:
        logger.info("✅ All translations from cache!")
        return translations
    
    # Chỉ dịch những dòng chưa có trong cache
    def translate_single_with_retry(index):
        text = texts[index]
        session = requests.Session()
        session.headers.update({
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9'
        })
        
        translated, from_cache = google_translate_single(session, text, source_lang, target_lang)
        
        # Update progress
        with progress_lock:
            global processed_subtitles
            processed_subtitles += 1
            current_progress = int((processed_subtitles / total) * 100)
        
        return index, translated
    
    # Adaptive workers: ít hơn nếu ít dòng cần dịch
    max_workers = min(10, max(3, len(cache_misses) // 10))
    logger.info(f"Using {max_workers} workers for {len(cache_misses)} items")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(translate_single_with_retry, i): i 
            for i in cache_misses
        }
        
        for future in as_completed(futures):
            try:
                index, translated = future.result()
                translations[index] = translated
            except Exception as e:
                index = futures[future]
                logger.error(f"Thread error at line {index+1}: {e}")
                translations[index] = texts[index]
    
    success_count = sum(1 for t in translations if t)
    logger.info(f"Translation complete: {success_count}/{total} success")
    
    return translations

# ==================== AI BATCH TRANSLATION ====================
def translate_batch(texts, source_lang, target_lang, provider, api_key, retry_count=0):
    combined = '\n'.join([f"[{i+1}] {text}" for i, text in enumerate(texts)])
    prompt = f"""You are a professional subtitle translator.

CRITICAL RULES:
- Maintain exact tone and emotion (casual/formal/childish/aggressive/romantic)
- Use natural expressions, not literal translations
- Preserve cultural nuances
- Keep context from previous lines
- Respond ONLY in format: [1] translation, [2] translation, etc.

Translate from {source_lang} to {target_lang}:

{combined}"""

    try:
        if provider == 'groq':
            resp = requests.post(GROQ_API, headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                                 json={'model': 'llama-3.3-70b-versatile', 'messages': [{'role': 'user', 'content': prompt}],
                                       'temperature': 0.3, 'max_tokens': 2000}, timeout=30)
        elif provider == 'gemini':
            resp = requests.post(f"{GEMINI_API}?key={api_key}", headers={'Content-Type': 'application/json'},
                                 json={'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': {'temperature': 0.3, 'maxOutputTokens': 2000}},
                                 timeout=30)
        else:
            resp = requests.post(OPENAI_API, headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                                 json={'model': 'gpt-4o-mini', 'messages': [{'role': 'user', 'content': prompt}],
                                       'temperature': 0.3, 'max_tokens': 2000}, timeout=30)

        data = resp.json()
        if 'error' in data:
            raise Exception(data['error'].get('message', 'API error'))

        if provider in ['groq', 'openai']:
            result = data.get('choices', [{}])[0].get('message', {}).get('content', '')
        else:
            result = data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')

        translations = []
        for line in result.split('\n'):
            m = re.match(r'\[(\d+)\]\s*(.*)', line.strip())
            if m:
                translations.append(m.group(2))

        return translations if len(translations) == len(texts) else texts

    except Exception as e:
        if retry_count < 3 and ('rate limit' in str(e).lower() or 'timeout' in str(e).lower()):
            time.sleep((2 ** retry_count) * 2)
            return translate_batch(texts, source_lang, target_lang, provider, api_key, retry_count + 1)
        raise e

def translate_subtitles(subtitles, source_lang, target_lang, provider, api_key, use_ai=True):
    global current_progress, current_mode, total_subtitles, processed_subtitles
    
    total_subtitles = len(subtitles)
    processed_subtitles = 0
    
    if use_ai:
        current_mode = "AI"
        batch_size = 20 if provider == 'groq' else 12 if provider == 'openai' else 8
        
        for i in range(0, len(subtitles), batch_size):
            batch = subtitles[i:i + batch_size]
            texts = [sub['text'] for sub in batch]
            try:
                results = translate_batch(texts, source_lang, target_lang, provider, api_key)
                for j, sub in enumerate(batch):
                    sub['translated'] = results[j] if j < len(results) else sub['text']
            except Exception as e:
                logger.warning(f"Batch failed, using original: {e}")
                for sub in batch:
                    sub['translated'] = sub['text']
            
            processed_subtitles += len(batch)
            with progress_lock:
                current_progress = int((processed_subtitles / total_subtitles) * 100)
            
            time.sleep(0.3)
    else:
        current_mode = "Google Free"
        texts = [sub['text'] for sub in subtitles]
        results = translate_with_google_parallel(texts, source_lang, target_lang)
        
        for j, sub in enumerate(subtitles):
            sub['translated'] = results[j]
    
    with progress_lock:
        current_progress = 100
    
    return subtitles

# ==================== FLASK ROUTES ====================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get-api-keys', methods=['GET'])
@limiter.limit("10 per minute")
def get_api_keys():
    try:
        keys = {
            'groq': mask_api_key(os.getenv('GROQ_API_KEY', '')),
            'gemini': mask_api_key(os.getenv('GEMINI_API_KEY', '')),
            'openai': mask_api_key(os.getenv('OPENAI_API_KEY', ''))
        }
        return jsonify(keys)
    except Exception as e:
        logger.error(f"Error getting API keys: {str(e)}")
        return jsonify({'error': 'Failed to retrieve keys'}), 500

def mask_api_key(key):
    if not key or len(key) < 8:
        return ''
    return f"{key[:4]}...{key[-4:]}"

def update_env_variable(var_name, var_value):
    """
    Cập nhật chính xác 1 biến trong .env file
    - Giữ nguyên các biến khác
    - Giữ nguyên comments
    - Tạo file mới nếu chưa tồn tại
    """
    env_file = find_dotenv() or os.path.join(os.getcwd(), '.env')
    
    # Đọc nội dung hiện tại
    lines = []
    var_found = False
    
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    
    # Cập nhật hoặc thêm biến
    new_lines = []
    for line in lines:
        stripped = line.strip()
        
        # Nếu là dòng của biến cần update
        if stripped and not stripped.startswith('#'):
            if '=' in stripped:
                current_var = stripped.split('=', 1)[0].strip()
                if current_var == var_name:
                    # Tìm thấy -> update value
                    if var_value:
                        new_lines.append(f'{var_name}={var_value}\n')
                    else:
                        new_lines.append(f'{var_name}=\n')
                    var_found = True
                    continue
        
        # Giữ nguyên các dòng khác
        new_lines.append(line)
    
    # Nếu chưa tồn tại -> thêm vào cuối
    if not var_found:
        if var_value:
            new_lines.append(f'{var_name}={var_value}\n')
        else:
            new_lines.append(f'{var_name}=\n')
    
    # Ghi lại file
    with open(env_file, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    logger.info(f"✅ Updated {var_name} in .env")

@app.route('/save-api-key', methods=['POST'])
@limiter.limit("5 per minute")
def save_api_key():
    try:
        data = request.json
        provider = data.get('provider')
        api_key = data.get('api_key', '').strip()

        if not provider:
            return jsonify({'error': 'Missing provider'}), 400
        if api_key and not validate_api_key_format(provider, api_key):
            return jsonify({'error': f'Invalid API key format for {provider}'}), 400

        env_var_map = {'groq': 'GROQ_API_KEY', 'gemini': 'GEMINI_API_KEY', 'openai': 'OPENAI_API_KEY'}
        env_var_name = env_var_map.get(provider)
        if not env_var_name:
            return jsonify({'error': 'Invalid provider'}), 400

        # Dùng helper function để update chính xác
        update_env_variable(env_var_name, api_key)
        
        # Reload environment variables
        load_dotenv(override=True)

        # Cập nhật runtime environment
        if api_key:
            os.environ[env_var_name] = api_key
        elif env_var_name in os.environ:
            del os.environ[env_var_name]

        return jsonify({
            'success': True,
            'message': f'{provider.upper()} API key saved',
            'masked_key': mask_api_key(api_key) if api_key else ''
        })
    except Exception as e:
        logger.error(f"Error saving API key: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

def validate_api_key_format(provider, key):
    if not key:
        return True
    if len(key) < 20:
        return False
    if provider == 'groq' and not key.startswith('gsk_'):
        return False
    if provider == 'openai' and not key.startswith('sk-'):
        return False
    return True

@app.route('/progress', methods=['GET'])
@limiter.limit("200 per minute")
def get_progress():
    global current_progress, current_mode, total_subtitles, processed_subtitles
    with progress_lock:
        processed_str = ""
        if total_subtitles > 0:
            processed_str = f"{processed_subtitles}/{total_subtitles}"
        
        return jsonify({
            'progress': current_progress,
            'status': 'Đang xử lý...' if current_progress < 100 else 'Hoàn tất!',
            'mode': current_mode,
            'processed': processed_str
        })

@app.route('/translate', methods=['POST'])
@limiter.limit("10 per minute")
def translate():
    global current_progress, current_mode, total_subtitles, processed_subtitles
    
    with progress_lock:
        current_progress = 0
        current_mode = "Google Free"
        total_subtitles = 0
        processed_subtitles = 0

    try:
        file = request.files.get('file')
        source_lang = request.form.get('source_lang', 'auto')
        target_lang = request.form.get('target_lang')
        provider = request.form.get('provider', 'groq')
        api_key = request.form.get('api_key')
        use_ai = request.form.get('use_ai', 'true').lower() == 'true'

        if not file or not target_lang:
            return jsonify({'error': 'Missing required fields'}), 400
        if not file.filename.endswith('.srt'):
            return jsonify({'error': 'Only .srt files are allowed'}), 400

        content = file.read().decode('utf-8')
        subtitles = parse_srt(content)

        if not subtitles:
            return jsonify({'error': 'No valid subtitles found'}), 400
        if len(subtitles) > 50000:
            return jsonify({'error': 'Too many subtitle entries (max 50000)'}), 400

        logger.info(f"Translating {len(subtitles)} subtitles → {target_lang} (AI: {use_ai})")

        current_mode = "AI" if use_ai else "Google Free"
        total_subtitles = len(subtitles)

        translated_subs = translate_subtitles(subtitles, source_lang, target_lang, provider, api_key, use_ai)
        translated_content = build_srt(translated_subs)

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.srt', dir=tempfile.gettempdir())
        temp_file.write(translated_content.encode('utf-8'))
        temp_file.close()

        original_filename = file.filename.rsplit('.', 1)[0]
        translated_filename = f"{original_filename}_{target_lang}.srt"
        preview_lines = '\n'.join([sub['translated'] for sub in translated_subs[:5]])

        return jsonify({
            'preview': preview_lines,
            'file_path': os.path.basename(temp_file.name),
            'filename': translated_filename
        })

    except Exception as e:
        logger.error(f"Translation error: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/download/<path:file_path>', methods=['GET'])
def download(file_path):
    try:
        full_path = os.path.join(tempfile.gettempdir(), file_path)
        if not os.path.exists(full_path):
            logger.error(f"File not found: {full_path}")
            return jsonify({'error': 'File not found'}), 404

        filename = request.args.get('filename', 'translated.srt')
        response = send_file(full_path, as_attachment=True, download_name=filename)
        return response
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            if os.path.exists(full_path):
                os.unlink(full_path)
                logger.info(f"Deleted temp file: {full_path}")
        except Exception as e:
            logger.warning(f"Failed to delete temp file: {e}")

def parse_srt(content):
    subtitles = []
    lines = content.split('\n')
    i = 0
    while i < len(lines):
        if lines[i].strip().isdigit():
            index = lines[i].strip()
            i += 1
            if i < len(lines) and '-->' in lines[i]:
                timing = lines[i].strip()
                i += 1
                text = ''
                while i < len(lines) and lines[i].strip():
                    text += lines[i].strip() + '\n'
                    i += 1
                subtitles.append({'index': index, 'timing': timing, 'text': text.strip()})
            else:
                i += 1
        else:
            i += 1
    return subtitles

def build_srt(subtitles):
    srt = ''
    for sub in subtitles:
        translated_text = sub.get('translated') or sub.get('text') or ''
        srt += sub.get('index', '') + '\n'
        srt += sub.get('timing', '') + '\n'
        srt += translated_text + '\n\n'
    return srt

def cleanup_old_temp_files():
    """Xóa file temp cũ hơn 1 giờ"""
    temp_dir = tempfile.gettempdir()
    now = time.time()
    
    for filename in os.listdir(temp_dir):
        if filename.endswith('.srt'):
            filepath = os.path.join(temp_dir, filename)
            try:
                if os.path.getmtime(filepath) < now - 3600:
                    os.unlink(filepath)
                    logger.info(f"Cleaned up old temp file: {filename}")
            except Exception as e:
                logger.warning(f"Failed to cleanup {filename}: {e}")

atexit.register(cleanup_old_temp_files)

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({'error': 'Rate limit exceeded. Please try again later.'}), 429

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal server error: {str(e)}")
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_ENV') == 'development'
    port = int(os.getenv('PORT', 5000))
    app.run(debug=debug_mode, host='0.0.0.0', port=port, threaded=True)
