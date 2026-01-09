# app.py - PHIÊN BẢN HOÀN CHỈNH & ỔN ĐỊNH (SRT Translator - 2026)

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

# Setup logging
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

# Security configs
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(32))

# Rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# API endpoints
GROQ_API = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
OPENAI_API = "https://api.openai.com/v1/chat/completions"

# Translation cache
translation_cache = {}
CACHE_MAX_SIZE = 5000

# Global progress (thread-safe cho frontend poll)
current_progress = 0
progress_lock = threading.Lock()
current_mode = "Google Free"
total_subtitles = 0
processed_subtitles = 0

# Rotate User-Agents để tránh bị Google block
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0',
]

def cache_translation(func):
    @wraps(func)
    def wrapper(text, source_lang, target_lang, *args, **kwargs):
        cache_key = hashlib.md5(f"{text}:{source_lang}:{target_lang}".encode()).hexdigest()
        if cache_key in translation_cache:
            return translation_cache[cache_key]
        result = func(text, source_lang, target_lang, *args, **kwargs)
        if len(translation_cache) >= CACHE_MAX_SIZE:
            translation_cache.pop(next(iter(translation_cache)))
        translation_cache[cache_key] = result
        return result
    return wrapper

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

        env_file = find_dotenv() or os.path.join(os.getcwd(), '.env')
        if not os.path.exists(env_file):
            with open(env_file, 'w') as f:
                f.write('# Auto-generated .env file\n')

        set_key(env_file, env_var_name, api_key or '')
        load_dotenv(override=True)

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
        current_progress = 0  # Reset progress
        current_mode = "Google Free"
        total_subtitles = 0
        processed_subtitles = 0

    temp_file_path = None
    subtitles = []  # Khai báo default để tránh UnboundLocalError nếu exception trước assignment

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
        processed_subtitles = 0

        translated_subs = translate_subtitles(subtitles, source_lang, target_lang, provider, api_key, use_ai)

        translated_content = build_srt(translated_subs)

        with tempfile.NamedTemporaryFile(delete=False, suffix='.srt') as temp_file:
            temp_file.write(translated_content.encode('utf-8'))
            temp_file_path = temp_file.name

        original_filename = file.filename.rsplit('.', 1)[0]
        translated_filename = f"{original_filename}_{target_lang}.srt"

        preview_lines = '\n'.join([sub['translated'] for sub in translated_subs[:5]])

        return jsonify({
            'preview': preview_lines,
            'file_path': os.path.basename(temp_file_path),
            'filename': translated_filename
        })

    except Exception as e:
        logger.error(f"Translation error: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

@app.route('/download/<path:file_path>', methods=['GET'])
def download(file_path):
    try:
        full_path = os.path.join(tempfile.gettempdir(), file_path)
        if not os.path.exists(full_path):
            return jsonify({'error': 'File not found'}), 404

        filename = request.args.get('filename', 'translated.srt')

        response = send_file(full_path, as_attachment=True, download_name=filename)
        response.headers['X-Delete-After'] = 'true'
        return response
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            os.unlink(full_path)
        except:
            pass

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

def google_translate_single(session, text, source_lang, target_lang):
    url = 'https://translate.google.com/translate_a/single'
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
            return ''.join([s[0] for s in data[0] if s[0]]).strip()
        return text
    except:
        return text

def translate_with_google_smart(texts, source_lang, target_lang):
    global current_progress, processed_subtitles
    
    total = len(texts)
    translations = [text for text in texts]  # default là gốc
    session = requests.Session()
    session.headers.update({'User-Agent': random.choice(USER_AGENTS)})
    
    success = 0
    for i in range(0, total, 5):  # Giảm xuống 5 dòng/lần để ít bị block
        batch = texts[i:i+5]
        for idx, text in enumerate(batch, start=i):
            try:
                translated = google_translate_single(session, text, source_lang, target_lang)
                if translated != text and len(translated) > 0:  # Kiểm tra có thay đổi không
                    translations[idx] = translated
                    success += 1
                processed_subtitles += 1
                with progress_lock:
                    current_progress = int((processed_subtitles / total) * 100)
                time.sleep(random.uniform(3.0, 7.0))  # Tăng delay lên 3–7 giây
            except Exception as e:
                logger.warning(f"Google fail line {idx+1}: {e}")
    
    logger.info(f"Google success rate: {success}/{total} lines ({success/total*100:.1f}%)")
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
    
    translated = []
    total_subtitles = len(subtitles)
    processed_subtitles = 0
    
    if use_ai:
        # Tăng batch size để nhanh hơn (Groq chịu được ~20-30, OpenAI ~10-15)
        batch_size = 20 if provider == 'groq' else 12 if provider == 'openai' else 8
        
        for i in range(0, len(subtitles), batch_size):
            batch = subtitles[i:i + batch_size]
            texts = [sub['text'] for sub in batch]
            try:
                results = translate_batch(texts, source_lang, target_lang, provider, api_key)
                for j, sub in enumerate(batch):
                    sub['translated'] = results[j] if j < len(results) else sub['text']
                translated.extend(batch)
            except Exception as e:
                logger.warning(f"Batch failed, fallback to original: {e}")
                translated.extend(batch)  # giữ nguyên nếu lỗi
            
            processed_subtitles += len(batch)
            with progress_lock:
                current_progress = int((processed_subtitles / total_subtitles) * 100)
            
            time.sleep(0.3)  # giảm delay, Groq rất nhanh
    else:
        # Google Free mode
        texts = [sub['text'] for sub in subtitles]
        results = translate_with_google_smart(texts, source_lang, target_lang)
        for j, sub in enumerate(subtitles):
            sub['translated'] = results[j]
            processed_subtitles += 1
            with progress_lock:
                current_progress = int((processed_subtitles / total_subtitles) * 100)
    
    with progress_lock:
        current_progress = 100
    return subtitles  # trả về subtitles đã sửa trực tiếp

# ==================== ERROR HANDLERS ====================
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
