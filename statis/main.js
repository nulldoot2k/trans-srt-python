// statis/main.js - FIXED VERSION

let selectedFile = null;
let currentProvider = 'groq';
let isTranslating = false;

window.onload = function() {
    loadSavedSettings();
};

async function loadSavedSettings() {
    const provider = localStorage.getItem('provider') || 'groq';
    currentProvider = provider;
    document.getElementById('provider').value = provider;
    
    try {
        const response = await fetch('/get-api-keys');
        const keys = await response.json();
        
        if (keys[currentProvider]) {
            document.getElementById('apiKey').value = keys[currentProvider];
            localStorage.setItem(`${currentProvider}_api_key`, keys[currentProvider]);
        } else {
            const localKey = localStorage.getItem(`${currentProvider}_api_key`) || '';
            document.getElementById('apiKey').value = localKey;
        }
    } catch (error) {
        console.error('Failed to load API keys from .env:', error);
        const localKey = localStorage.getItem(`${currentProvider}_api_key`) || '';
        document.getElementById('apiKey').value = localKey;
    }
    
    updateHelpText();

    const useAICheckbox = document.getElementById('useAI');
    if (useAICheckbox) {
        const useAI = localStorage.getItem('useAI') !== 'false';
        useAICheckbox.checked = useAI;
    }
}

function toggleSettings() {
    if (isTranslating) {
        showStatus('⚠️ Please wait for translation to complete', false);
        return;
    }
    
    const panel = document.getElementById('settingsPanel');
    panel.classList.toggle('show');
}

function providerChanged() {
    currentProvider = document.getElementById('provider').value;
    const savedKey = localStorage.getItem(`${currentProvider}_api_key`) || '';
    document.getElementById('apiKey').value = savedKey;
    localStorage.setItem('provider', currentProvider);
    updateHelpText();
}

function updateHelpText() {
    const helpTexts = {
        groq: 'Get your free key at console.groq.com',
        gemini: 'Get your free key at aistudio.google.com/apikey',
        openai: 'Get your key at platform.openai.com'
    };
    document.getElementById('helpText').textContent = helpTexts[currentProvider];
}

function togglePasswordVisibility() {
    const apiKeyInput = document.getElementById('apiKey');
    const eyeIcon = document.getElementById('eyeIcon');
    
    if (apiKeyInput.type === 'password') {
        apiKeyInput.type = 'text';
        eyeIcon.textContent = '👁️‍🗨️';
    } else {
        apiKeyInput.type = 'password';
        eyeIcon.textContent = '👁️';
    }
}

async function saveApiKey() {
    const apiKey = document.getElementById('apiKey').value.trim();
    const useAI = document.getElementById('useAI') ? document.getElementById('useAI').checked : true;
    
    console.log('Saving settings:', {
        provider: currentProvider,
        hasKey: !!apiKey,
        useAI: useAI
    });
    
    // Save to localStorage first
    localStorage.setItem(`${currentProvider}_api_key`, apiKey);
    localStorage.setItem('provider', currentProvider);
    localStorage.setItem('useAI', useAI);
    
    if (useAI && !apiKey) {
        showStatus('⚠️ Please enter API key for AI mode', false);
        return;
    }
    
    // Save to backend .env file
    try {
        showStatus('💾 Saving...', true);
        
        const response = await fetch('/save-api-key', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                provider: currentProvider,
                api_key: apiKey
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            console.log('Save successful:', result);
            showStatus('✅ Settings saved to .env file', false);
        } else {
            console.error('Save failed:', result);
            showStatus(`❌ Error: ${result.error || 'Failed to save'}`, false);
            return;
        }
    } catch (error) {
        console.error('Network error:', error);
        showStatus('⚠️ Saved locally only (server error)', false);
    }
    
    setTimeout(() => {
        toggleSettings();
    }, 1500);
}

function handleFileSelect(event) {
    if (isTranslating) {
        event.target.value = '';
        showStatus('⚠️ Cannot change file during translation', false);
        return;
    }
    
    const file = event.target.files[0];
    if (file && file.name.endsWith('.srt')) {
        selectedFile = file;
        document.getElementById('fileName').textContent = file.name;
        document.getElementById('uploadArea').classList.add('hidden');
        document.getElementById('fileSelected').classList.remove('hidden');
        document.getElementById('step1Icon').textContent = '✅';
        updateTranslateButton();
    } else if (file) {
        showStatus('❌ Please select a valid .srt file', false);
        event.target.value = '';
    }
}

function removeFile() {
    if (isTranslating) {
        showStatus('⚠️ Cannot remove file during translation', false);
        return;
    }
    
    selectedFile = null;
    document.getElementById('fileInput').value = '';
    document.getElementById('uploadArea').classList.remove('hidden');
    document.getElementById('fileSelected').classList.add('hidden');
    document.getElementById('step1Icon').textContent = '👉';
    document.getElementById('previewContainer').classList.add('hidden');
    updateTranslateButton();
}

function targetLangChanged() {
    if (isTranslating) {
        showStatus('⚠️ Cannot change language during translation', false);
        setTimeout(() => {
            const prevLang = document.getElementById('targetLang').dataset.prevValue || '';
            document.getElementById('targetLang').value = prevLang;
        }, 0);
        return;
    }
    
    const targetLang = document.getElementById('targetLang').value;
    document.getElementById('targetLang').dataset.prevValue = targetLang;
    
    const hasLang = targetLang !== '';
    document.getElementById('step2Icon').textContent = hasLang ? '✅' : '👉';
    updateTranslateButton();
}

function sourceLangChanged() {
    if (isTranslating) {
        showStatus('⚠️ Cannot change language during translation', false);
        setTimeout(() => {
            const prevLang = document.getElementById('sourceLang').dataset.prevValue || 'auto';
            document.getElementById('sourceLang').value = prevLang;
        }, 0);
        return;
    }
    
    const sourceLang = document.getElementById('sourceLang').value;
    document.getElementById('sourceLang').dataset.prevValue = sourceLang;
}

function updateTranslateButton() {
    const hasFile = selectedFile !== null;
    const hasLang = document.getElementById('targetLang').value !== '';
    document.getElementById('translateBtn').disabled = !(hasFile && hasLang) || isTranslating;
}

function showStatus(message, isProgress) {
    const status = document.getElementById('status');
    status.textContent = message;
    status.classList.remove('hidden');
    
    if (!isProgress) {
        setTimeout(() => {
            if (status.textContent === message) {
                status.classList.add('hidden');
            }
        }, 3000);
    }
}

function updateProgress(percent) {
    document.getElementById('progressContainer').classList.remove('hidden');
    document.getElementById('progressFill').style.width = percent + '%';
}

function lockUI() {
    isTranslating = true;
    
    document.getElementById('translateBtn').disabled = true;
    document.getElementById('sourceLang').disabled = true;
    document.getElementById('targetLang').disabled = true;
    document.getElementById('fileInput').disabled = true;
    
    const removeBtn = document.querySelector('.remove-btn');
    if (removeBtn) {
        removeBtn.disabled = true;
        removeBtn.style.opacity = '0.5';
        removeBtn.style.cursor = 'not-allowed';
    }
    
    const uploadArea = document.getElementById('uploadArea');
    if (uploadArea) {
        uploadArea.style.pointerEvents = 'none';
        uploadArea.style.opacity = '0.6';
    }
    
    const settingsBtn = document.querySelector('.settings-btn');
    if (settingsBtn) {
        settingsBtn.disabled = true;
        settingsBtn.style.opacity = '0.5';
        settingsBtn.style.cursor = 'not-allowed';
    }
    
    const translateBtn = document.getElementById('translateBtn');
    translateBtn.style.opacity = '0.7';
    translateBtn.style.cursor = 'wait';
}

function unlockUI() {
    isTranslating = false;
    
    document.getElementById('sourceLang').disabled = false;
    document.getElementById('targetLang').disabled = false;
    document.getElementById('fileInput').disabled = false;
    
    const removeBtn = document.querySelector('.remove-btn');
    if (removeBtn) {
        removeBtn.disabled = false;
        removeBtn.style.opacity = '1';
        removeBtn.style.cursor = 'pointer';
    }
    
    const uploadArea = document.getElementById('uploadArea');
    if (uploadArea) {
        uploadArea.style.pointerEvents = 'auto';
        uploadArea.style.opacity = '1';
    }
    
    const settingsBtn = document.querySelector('.settings-btn');
    if (settingsBtn) {
        settingsBtn.disabled = false;
        settingsBtn.style.opacity = '1';
        settingsBtn.style.cursor = 'pointer';
    }
    
    const translateBtn = document.getElementById('translateBtn');
    translateBtn.style.opacity = '1';
    translateBtn.style.cursor = 'pointer';
    
    updateTranslateButton();
}

async function startTranslation() {
    const useAI = document.getElementById('useAI') ? document.getElementById('useAI').checked : true;
    let apiKey = useAI ? (document.getElementById('apiKey').value.trim() || localStorage.getItem(`${currentProvider}_api_key`) || '') : '';
    
    if (useAI && !apiKey) {
        showStatus('❌ Please enter API key in settings', false);
        return;
    }

    const sourceLang = document.getElementById('sourceLang').value || 'auto';
    const targetLang = document.getElementById('targetLang').value;
    
    lockUI();
    
    document.getElementById('previewContainer').classList.add('hidden');
    showStatus(useAI ? '🤖 Translating with AI...' : '🌐 Translating fast (free mode)...', true);
    updateProgress(10);

    try {
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('source_lang', sourceLang);
        formData.append('target_lang', targetLang);
        formData.append('provider', currentProvider);
        formData.append('api_key', apiKey);
        formData.append('use_ai', useAI ? 'true' : 'false');

        const response = await fetch('/translate', {
            method: 'POST',
            body: formData
        });

        updateProgress(60);

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Translation failed');
        }

        const result = await response.json();
        
        updateProgress(100);
        
        setTimeout(() => {
            document.getElementById('progressContainer').classList.add('hidden');
            document.getElementById('progressFill').style.width = '0%';
        }, 500);
        
        document.getElementById('previewText').textContent = result.preview || 'Translation completed (no preview)';
        document.getElementById('previewContainer').classList.remove('hidden');
        
        document.getElementById('downloadBtn').onclick = function() {
            const a = document.createElement('a');
            a.href = `/download/${encodeURIComponent(result.file_path)}?filename=${encodeURIComponent(result.filename)}`;
            a.download = result.filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            showStatus('✅ File downloaded!', false);
        };

        showStatus('✅ Translation completed! Preview below.', false);

    } catch (error) {
        console.error('Translation error:', error);
        showStatus(`❌ Error: ${error.message}`, false);
        
        document.getElementById('progressContainer').classList.add('hidden');
        document.getElementById('progressFill').style.width = '0%';
    } finally {
        unlockUI();
    }
}

window.addEventListener('DOMContentLoaded', function() {
    const sourceLang = document.getElementById('sourceLang');
    const targetLang = document.getElementById('targetLang');
    
    if (sourceLang) {
        sourceLang.dataset.prevValue = sourceLang.value;
        sourceLang.addEventListener('change', sourceLangChanged);
    }
    
    if (targetLang) {
        targetLang.dataset.prevValue = targetLang.value;
    }
});
