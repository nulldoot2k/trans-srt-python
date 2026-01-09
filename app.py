# app.py - FIXED VERSION
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

# Setup logging - ONLY to console, no file
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
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
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
CACHE_MAX_SIZE = 1000

def cache_translation(func):
    """Decorator to cache translations"""
    @wraps(func)
    def wrapper(text, source_lang, target_lang, *args, **kwargs):
        cache_key = hashlib.md5(
            f"{text}:{source_lang}:{target_lang}".encode()
        ).hexdigest()
        
        if cache_key in translation_cache:
            logger.info(f"Cache hit")
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
    """Return masked API keys"""
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
    """Mask API key for security"""
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
        
        logger.info(f"Received save request - Provider: {provider}, Has key: {bool(api_key)}")
        
        if not provider:
            logger.error("Missing provider")
            return jsonify({'error': 'Missing provider'}), 400
        
        # Allow empty API key for non-AI mode
        # Only validate format if key is provided
        if api_key and not validate_api_key_format(provider, api_key):
            logger.error(f"Invalid API key format for {provider}")
            return jsonify({'error': f'Invalid API key format for {provider}'}), 400
        
        env_var_map = {
            'groq': 'GROQ_API_KEY',
            'gemini': 'GEMINI_API_KEY',
            'openai': 'OPENAI_API_KEY'
        }
        
        env_var_name = env_var_map.get(provider)
        if not env_var_name:
            logger.error(f"Invalid provider: {provider}")
            return jsonify({'error': 'Invalid provider'}), 400
        
        # Find or create .env file
        env_file = find_dotenv()
        if not env_file:
            env_file = os.path.join(os.getcwd(), '.env')
            logger.info(f"Creating .env file at: {env_file}")
        
        # Create file if it doesn't exist
        if not os.path.exists(env_file):
            with open(env_file, 'w') as f:
                f.write('# Auto-generated .env file\n')
        
        # Save to .env file
        if api_key:
            set_key(env_file, env_var_name, api_key)
            logger.info(f"Saved {env_var_name} to .env file")
        else:
            # Remove key if empty
            set_key(env_file, env_var_name, '')
            logger.info(f"Cleared {env_var_name} from .env file")
        
        # Reload environment variables
        load_dotenv(override=True)
        
        # Update os.environ directly
        if api_key:
            os.environ[env_var_name] = api_key
        elif env_var_name in os.environ:
            del os.environ[env_var_name]
        
        logger.info(f"✓ API key saved successfully for {provider}")
        
        return jsonify({
            'success': True,
            'message': f'{provider.upper()} API key saved',
            'masked_key': mask_api_key(api_key) if api_key else ''
        })
        
    except Exception as e:
        logger.error(f"Error saving API key: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

def validate_api_key_format(provider, key):
    """Basic validation of API key format"""
    if not key:
        return True  # Allow empty keys
    
    if len(key) < 20:
        logger.warning(f"Key too short for {provider}: {len(key)} chars")
        return False
    
    if provider == 'groq' and not key.startswith('gsk_'):
        logger.warning(f"Groq key must start with 'gsk_'")
        return False
    elif provider == 'openai' and not key.startswith('sk-'):
        logger.warning(f"OpenAI key must start with 'sk-'")
        return False
    # Gemini keys don't have a specific prefix
    
    return True

@app.route('/translate', methods=['POST'])
@limiter.limit("10 per minute")
def translate():
    temp_file_path = None
    try:
        file = request.files.get('file')
        source_lang = request.form.get('source_lang', 'auto')
        target_lang = request.form.get('target_lang')
        provider = request.form.get('provider', 'groq')
        api_key = request.form.get('api_key')
        use_ai_str = request.form.get('use_ai', 'true')
        use_ai = use_ai_str.lower() == 'true'
        
        # Validation
        if not file or not target_lang:
            return jsonify({'error': 'Missing required fields'}), 400
        
        if not file.filename.endswith('.srt'):
            return jsonify({'error': 'Only .srt files are allowed'}), 400
        
        if use_ai and not api_key:
            return jsonify({'error': 'API key required when using AI'}), 400
        
        # Read and validate content
        content = file.read().decode('utf-8')
        if len(content) > 5 * 1024 * 1024:  # 5MB text limit
            return jsonify({'error': 'File content too large'}), 400
        
        subtitles = parse_srt(content)
        
        if not subtitles:
            return jsonify({'error': 'No valid subtitles found'}), 400
        
        if len(subtitles) > 5000:
            return jsonify({'error': 'Too many subtitle entries (max 5000)'}), 400
        
        logger.info(f"Translating {len(subtitles)} subtitles to {target_lang} (AI: {use_ai})")
        
        # Translate
        translated = translate_subtitles(
            subtitles, 
            source_lang, 
            target_lang, 
            provider, 
            api_key if use_ai else None,
            use_ai
        )
        
        # Create output
        srt_content = create_srt(translated)
        
        # Save to temp file
        temp_file_path = tempfile.NamedTemporaryFile(
            mode='w', 
            suffix='.srt', 
            delete=False, 
            encoding='utf-8'
        )
        temp_file_path.write(srt_content)
        temp_file_path.close()
        
        original_name = os.path.splitext(file.filename)[0]
        output_name = f"{original_name}_{target_lang}.srt"
        
        # Preview
        preview = srt_content[:3000]
        if len(srt_content) > 3000:
            preview += "\n...\n(Preview - Click Download for full file)"

        logger.info(f"Translation completed: {output_name}")

        return jsonify({
            'success': True,
            'file_path': temp_file_path.name,
            'filename': output_name,
            'preview': preview
        })
        
    except Exception as e:
        logger.error(f"Translation error: {str(e)}")
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        return jsonify({'error': str(e)}), 500

@app.route('/download/<path:filepath>')
@limiter.limit("20 per minute")
def download(filepath):
    """Secure file download with cleanup"""
    try:
        if not os.path.exists(filepath) or not filepath.endswith('.srt'):
            return jsonify({'error': 'File not found'}), 404
        
        filename = request.args.get('filename', 'translated.srt')
        filename = os.path.basename(filename)
        
        return send_file(
            filepath, 
            as_attachment=True, 
            download_name=filename,
            mimetype='text/plain'
        )
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({'error': 'Download failed'}), 500
    finally:
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"Temp file cleaned")
        except Exception as e:
            logger.warning(f"Failed to cleanup temp file: {str(e)}")

def parse_srt(content):
    """Parse SRT content into structured data"""
    blocks = re.split(r'\n\s*\n', content.strip())
    subtitles = []
    
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            try:
                index = lines[0].strip()
                timestamp = lines[1].strip()
                text = '\n'.join(lines[2:])
                
                if not re.match(r'\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}', timestamp):
                    logger.warning(f"Invalid timestamp: {timestamp}")
                    continue
                
                subtitles.append({
                    'index': index,
                    'timestamp': timestamp,
                    'text': text,
                    'translated': ''
                })
            except Exception as e:
                logger.warning(f"Failed to parse block: {str(e)}")
                continue
    
    return subtitles

def create_srt(subtitles):
    """Create SRT format from translated subtitles"""
    lines = []
    for sub in subtitles:
        lines.append(sub['index'])
        lines.append(sub['timestamp'])
        lines.append(sub['translated'])
        lines.append('')
    return '\n'.join(lines)

def translate_with_google(texts, source_lang, target_lang):
    """Fixed Google Translate - Process one by one to avoid batch split issues"""
    translations = []
    
    # Language mapping
    lang_map = {
        'English': 'en', 'Vietnamese': 'vi', 'Chinese': 'zh-cn',
        'Japanese': 'ja', 'Korean': 'ko', 'Thai': 'th',
        'French': 'fr', 'Spanish': 'es', 'German': 'de',
        'Russian': 'ru', 'Portuguese': 'pt', 'Italian': 'it'
    }
    src = lang_map.get(source_lang, 'auto') if source_lang != 'auto' else 'auto'
    tgt = target_lang
    
    url = 'https://translate.google.com/translate_a/single'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    # Process each text individually to avoid batch split issues
    for i, text in enumerate(texts):
        params = {
            'client': 'gtx',
            'sl': src,
            'tl': tgt,
            'dt': 't',
            'q': text
        }
        
        max_retries = 3
        success = False
        
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    translated = ''.join([s[0] for s in data[0] if s[0]])
                    translations.append(translated)
                    success = True
                    break
                    
                elif response.status_code == 429:  # Rate limit
                    wait_time = (2 ** attempt) * 0.5
                    logger.warning(f"Rate limited, waiting {wait_time}s")
                    time.sleep(wait_time)
                else:
                    raise Exception(f"HTTP {response.status_code}")
                    
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Translation failed for text {i+1}: {str(e)}")
                    translations.append(text)  # Use original text as fallback
                    success = True
                    break
        
        if not success:
            translations.append(text)
        
        # Small delay to avoid rate limiting
        if i < len(texts) - 1:  # Don't sleep after last item
            time.sleep(0.1)
    
    return translations

def translate_batch(texts, source_lang, target_lang, provider, api_key, retry_count=0):
    """AI-powered batch translation with retry logic"""
    combined = '\n'.join([f"[{i+1}] {text}" for i, text in enumerate(texts)])
    
    prompt = f"""You are a professional subtitle translator.

CRITICAL RULES:
- Maintain exact tone and emotion (casual/formal/childish/aggressive/romantic)
- Use natural expressions, not literal translations
- Preserve cultural nuances
- Respond ONLY in format: [1] translation, [2] translation, etc.

Translate from {source_lang} to {target_lang}:

{combined}"""

    max_retries = 3
    retry_delay = (2 ** retry_count) * 0.5

    try:
        if provider == 'groq':
            response = requests.post(
                GROQ_API,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'llama-3.3-70b-versatile',
                    'messages': [{'role': 'user', 'content': prompt}],
                    'temperature': 0.3,
                    'max_tokens': 2000
                },
                timeout=30
            )
        elif provider == 'gemini':
            response = requests.post(
                f"{GEMINI_API}?key={api_key}",
                headers={'Content-Type': 'application/json'},
                json={
                    'contents': [{'parts': [{'text': prompt}]}],
                    'generationConfig': {
                        'temperature': 0.3,
                        'maxOutputTokens': 2000
                    }
                },
                timeout=30
            )
        else:  # openai
            response = requests.post(
                OPENAI_API,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'gpt-4o-mini',
                    'messages': [{'role': 'user', 'content': prompt}],
                    'temperature': 0.3,
                    'max_tokens': 2000
                },
                timeout=30
            )
        
        response_data = response.json()
        
        if 'error' in response_data:
            error_msg = response_data['error'].get('message', 'Unknown error')
            raise Exception(f"{provider.upper()} API Error: {error_msg}")
        
        # Extract result based on provider
        if provider == 'groq' or provider == 'openai':
            result = response_data.get('choices', [{}])[0].get('message', {}).get('content', '')
        else:  # gemini
            result = response_data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        
        # Parse translations
        translations = []
        for line in result.split('\n'):
            match = re.match(r'\[(\d+)\]\s*(.*)', line.strip())
            if match:
                translations.append(match.group(2))
        
        # If mismatch, use original texts as fallback
        if len(translations) != len(texts):
            logger.warning(f"Translation count mismatch: expected {len(texts)}, got {len(translations)}")
            return texts  # Return original texts as fallback
        
        return translations
        
    except requests.exceptions.Timeout:
        if retry_count < max_retries:
            logger.warning(f"Timeout, retrying ({retry_count + 1}/{max_retries})")
            time.sleep(retry_delay)
            return translate_batch(texts, source_lang, target_lang, provider, api_key, retry_count + 1)
        raise Exception("Translation timeout after retries")
    
    except Exception as e:
        error_msg = str(e)
        if 'rate limit' in error_msg.lower() and retry_count < max_retries:
            wait = retry_delay
            match = re.search(r'try again in ([\d.]+)s', error_msg)
            if match:
                wait = float(match.group(1)) + 1
            logger.warning(f"Rate limited, waiting {wait}s")
            time.sleep(wait)
            return translate_batch(texts, source_lang, target_lang, provider, api_key, retry_count + 1)
        raise e

def translate_subtitles(subtitles, source_lang, target_lang, provider, api_key, use_ai=True):
    """Main translation function"""
    translated = []
    
    if use_ai:
        batch_size = 5 if provider == 'groq' else 8
        total_batches = (len(subtitles) + batch_size - 1) // batch_size
        
        for i in range(0, len(subtitles), batch_size):
            batch = subtitles[i:i + batch_size]
            texts = [sub['text'] for sub in batch]
            
            try:
                translations = translate_batch(texts, source_lang, target_lang, provider, api_key)
                
                for j, sub in enumerate(batch):
                    trans = translations[j] if j < len(translations) else sub['text']
                    translated.append({**sub, 'translated': trans})
                
                batch_num = (i // batch_size) + 1
                logger.info(f"Batch {batch_num}/{total_batches} completed")
                
                time.sleep(0.5 if provider == 'groq' else 0.2)
                
            except Exception as e:
                logger.error(f"Batch {i//batch_size + 1} failed: {str(e)}")
                for sub in batch:
                    translated.append({**sub, 'translated': sub['text']})
    else:
        # Fast non-AI translation - FIXED
        texts = [sub['text'] for sub in subtitles]
        translations = translate_with_google(texts, source_lang, target_lang)
        
        for j in range(len(subtitles)):
            trans = translations[j] if j < len(translations) else subtitles[j]['text']
            translated.append({**subtitles[j], 'translated': trans})
    
    return translated

@app.errorhandler(429)
def ratelimit_handler(e):
    logger.warning(f"Rate limit exceeded: {get_remote_address()}")
    return jsonify({'error': 'Rate limit exceeded. Please try again later.'}), 429

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal server error: {str(e)}")
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_ENV') == 'development'
    port = int(os.getenv('PORT', 5000))
    
    if debug_mode:
        logger.warning("Running in DEBUG mode - DO NOT use in production!")
    
    app.run(
        debug=debug_mode,
        host='0.0.0.0',
        port=port
    )
