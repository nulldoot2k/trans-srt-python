// statis/main.js - COMPLETE FIXED VERSION

let startTime = null;
let lastProcessed = 0;
let lastTime = null;
let estimatedTime = 'Đang tính...';
let selectedFile = null;
let currentProvider = 'groq';
let isTranslating = false;
let hasTranslated = false;
let progressInterval = null;

// ==================== INITIALIZATION ====================
window.onload = function() {
    loadSavedSettings();
    initializeEventListeners();
};

function initializeEventListeners() {
    const sourceLang = document.getElementById('sourceLang');
    const targetLang = document.getElementById('targetLang');
    
    if (sourceLang) {
        sourceLang.dataset.prevValue = sourceLang.value;
        sourceLang.addEventListener('change', sourceLangChanged);
    }
    
    if (targetLang) {
        targetLang.dataset.prevValue = targetLang.value;
    }
}

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

// ==================== SETTINGS ====================
function toggleSettings() {
    if (isTranslating) {
        showStatus('⚠️ Please wait for translation to complete', false);
        return;
    }
    
    const modal = document.getElementById('settingsModal');
    modal.classList.toggle('show');
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
    const saveBtn = document.querySelector('.btn-success');
    
    localStorage.setItem(`${currentProvider}_api_key`, apiKey);
    localStorage.setItem('provider', currentProvider);
    localStorage.setItem('useAI', useAI);
    
    if (useAI && !apiKey) {
        showSettingsStatus('⚠️ Please enter API key for AI mode', 'error');
        return;
    }
    
    saveBtn.disabled = true;
    saveBtn.textContent = '💾 Saving...';
    
    try {
        const response = await fetch('/save-api-key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                provider: currentProvider,
                api_key: apiKey
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            saveBtn.textContent = '✅ Saved!';
            showSettingsStatus('✅ API key saved successfully!', 'success');
            
            setTimeout(() => {
                toggleSettings();
                saveBtn.textContent = 'Save Settings';
                saveBtn.disabled = false;
            }, 2000);
        } else {
            saveBtn.textContent = '❌ Failed';
            showSettingsStatus(`❌ Error: ${result.error}`, 'error');
            
            setTimeout(() => {
                saveBtn.textContent = 'Save Settings';
                saveBtn.disabled = false;
            }, 3000);
        }
    } catch (error) {
        saveBtn.textContent = '⚠️ Partial Save';
        showSettingsStatus('⚠️ Saved locally only', 'warning');
        
        setTimeout(() => {
            saveBtn.textContent = 'Save Settings';
            saveBtn.disabled = false;
        }, 3000);
    }
}

// ==================== FILE HANDLING ====================
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
    hasTranslated = false;
    updateTranslateButton();
}

// ==================== LANGUAGE SELECTION ====================
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

// ==================== UI UPDATES ====================
function updateTranslateButton() {
    const btn = document.getElementById('translateBtn');
    const sourceLang = document.getElementById('sourceLang').value;
    const targetLang = document.getElementById('targetLang').value;

    if (hasTranslated) {
        btn.textContent = 'Translate Another File';
        btn.onclick = resetFullUI;
        btn.disabled = false;
    } else {
        btn.textContent = '🌐 Translate';
        btn.onclick = startTranslation;
        btn.disabled = !selectedFile || !targetLang || sourceLang === targetLang || isTranslating;
    }
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

function showSettingsStatus(message, type) {
    const oldStatus = document.querySelector('.settings-status');
    if (oldStatus) oldStatus.remove();
    
    const statusDiv = document.createElement('div');
    statusDiv.className = 'settings-status';
    statusDiv.textContent = message;
    
    const colors = {
        success: 'rgba(17, 153, 142, 0.3)',
        error: 'rgba(255, 107, 107, 0.3)',
        warning: 'rgba(243, 156, 18, 0.3)'
    };
    
    statusDiv.style.cssText = `
        background: ${colors[type] || colors.success};
        border: 1px solid ${type === 'success' ? 'rgba(56, 239, 125, 0.5)' : type === 'error' ? 'rgba(255, 107, 107, 0.5)' : 'rgba(243, 156, 18, 0.5)'};
        color: white;
        padding: 12px;
        border-radius: 8px;
        margin-top: 15px;
        text-align: center;
        font-weight: 600;
        animation: slideDown 0.3s ease;
    `;
    
    const saveBtn = document.querySelector('.btn-success');
    saveBtn.parentNode.insertBefore(statusDiv, saveBtn);
    
    setTimeout(() => {
        statusDiv.style.animation = 'slideUp 0.3s ease';
        setTimeout(() => statusDiv.remove(), 300);
    }, 5000);
}

// ==================== PROGRESS BAR ====================
function updateProgress(percent, statusText = "") {
    const container = document.getElementById('progressContainer');
    const fill = document.getElementById('progressFill');
    const percentEl = document.getElementById('progressPercent');
    const statusEl = document.getElementById('progressStatus');

    if (!fill || !percentEl || !statusEl) return;

    container.classList.remove('hidden');
    container.style.display = 'block';

    // Force browser redraw bar
    fill.style.transition = 'none';
    fill.offsetHeight;
    fill.style.transition = 'width 0.5s ease-out';

    const safePercent = Math.max(0, Math.min(100, Math.round(percent || 0)));
    fill.style.width = safePercent + '%';

    percentEl.textContent = safePercent + '%';

    // Status text động + dễ nhìn
    statusEl.textContent = statusText || 
        (safePercent < 5 ? "Đang chuẩn bị..." :
         safePercent < 30 ? "Bắt đầu dịch..." :
         safePercent < 70 ? "Đang dịch chính..." : "Hoàn thiện...");

    // Pulse nhẹ khi mới bắt đầu
    if (safePercent < 10) {
        fill.classList.add('pulse');
    } else {
        fill.classList.remove('pulse');
    }

    if (safePercent >= 100) {
        fill.classList.add('complete');
        statusEl.textContent = "✅ Dịch xong!";
        setTimeout(() => container.classList.add('hidden'), 1800);
    }
}

function startProgressPolling() {
    startTime = Date.now();
    lastTime = startTime;
    lastProcessed = 0;

    progressInterval = setInterval(async () => {
        try {
            const res = await fetch('/progress');
            const data = await res.json();

            // CHỈ DÙNG processed từ string "X/Y" làm nguồn chính
            let processed = 0;
            let total = 100;  // fallback
            let percent = 0;

            if (data.processed && typeof data.processed === 'string') {
                const parts = data.processed.split('/');
                if (parts.length === 2) {
                    processed = parseInt(parts[0].trim(), 10) || 0;
                    total = parseInt(parts[1].trim(), 10) || 100;
                    percent = total > 0 ? Math.round((processed / total) * 100) : 0;
                }
            }

            let statusText = data.status || "Đang xử lý...";
            if (data.processed) statusText += ` - ${data.processed}`;
            if (data.mode) statusText += ` [${data.mode}]`;

            // Tính thời gian còn lại (dựa trên tốc độ processed)
            const currentTime = Date.now();
            if (processed > lastProcessed && currentTime > lastTime) {
                const timeDiffSec = (currentTime - lastTime) / 1000;
                const processedDiff = processed - lastProcessed;
                const speed = processedDiff / timeDiffSec; // dòng/giây
                const remainingLines = total - processed;
                if (speed > 0.1) {  // tránh chia cho số quá nhỏ
                    const remainingSec = remainingLines / speed;
                    estimatedTime = remainingSec < 60 
                        ? `~${Math.round(remainingSec)} giây` 
                        : `~${Math.round(remainingSec / 60)} phút`;
                }
            }
            lastProcessed = processed;
            lastTime = currentTime;

            statusText += ` | ${estimatedTime} còn lại`;

            updateProgress(percent, statusText);

            if (percent >= 100 || processed >= total) {
                clearInterval(progressInterval);
                progressInterval = null;
                updateProgress(100, "Hoàn tất!");
            }
        } catch (e) {
            console.warn('Poll error:', e);
        }
    }, 600);
}

function stopProgressPolling() {
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
}

// ==================== TRANSLATION ====================
function resetTranslation() {
    document.getElementById('previewContainer').classList.add('hidden');
    removeFile();
    stopProgressPolling();
    document.getElementById('progressContainer').classList.add('hidden');
    document.getElementById('progressFill').style.width = '0%';
    hasTranslated = false;
    updateTranslateButton();
    showStatus('🔄 Ready to translate a new file', false);
}

async function startTranslation() {
    if (hasTranslated) {
        resetTranslation();
        return;
    }
    
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
    showStatus(useAI ? '🤖 Đang dịch bằng AI...' : '🌐 Đang dịch nhanh (free mode)...', true);
    updateProgress(0, "Chuẩn bị file...");
    
    startProgressPolling();

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

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Translation failed');
        }

        const result = await response.json();

        stopProgressPolling();
        updateProgress(100, "Hoàn tất!");
        
        document.getElementById('previewText').textContent = result.preview || 'Translation completed';
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

        showStatus('✅ Dịch xong! Xem preview và tải file bên dưới.', false);
        hasTranslated = true;
        updateTranslateButton();

    } catch (error) {
        console.error('Translation error:', error);
        showStatus(`❌ Lỗi: ${error.message}`, false);
        stopProgressPolling();
        document.getElementById('progressContainer').classList.add('hidden');
        
    } finally {
        unlockUI();
    }
}

function resetFullUI() {
    // Ẩn và reset progress bar hoàn toàn
    const progressContainer = document.getElementById('progressContainer');
    if (progressContainer) {
        progressContainer.classList.add('hidden');
        progressContainer.style.display = 'none'; // force ẩn
        progressContainer.style.opacity = '0';
        document.getElementById('progressFill').style.width = '0%';
        document.getElementById('progressPercent').textContent = '0%';
        document.getElementById('progressStatus').textContent = '';
    }

    // Dừng polling nếu còn chạy
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }

    // Xóa file đã chọn
    selectedFile = null;
    document.getElementById('fileInput').value = '';
    document.getElementById('uploadArea').classList.remove('hidden');
    document.getElementById('fileSelected').classList.add('hidden');
    document.getElementById('fileName').textContent = '';

    // Reset icon step 1
    document.getElementById('step1Icon').textContent = '👉';
    document.getElementById('step1Icon').parentNode.style.color = 'white';

    // Reset icon step 2 (nếu cần)
    document.getElementById('step2Icon').textContent = '👉';
    document.getElementById('step2Icon').parentNode.style.color = 'white';

    // Ẩn preview và download
    document.getElementById('previewContainer').classList.add('hidden');
    document.getElementById('previewText').textContent = '';

    // Xóa status message
    const status = document.getElementById('status');
    if (status) status.classList.add('hidden');

    // Reset trạng thái
    hasTranslated = false;
    isTranslating = false;

    // Update nút về trạng thái ban đầu
    updateTranslateButton();
}

// ==================== UI LOCK/UNLOCK ====================
function lockUI() {
    isTranslating = true;
    
    const translateBtn = document.getElementById('translateBtn');
    translateBtn.disabled = true;
    translateBtn.textContent = '⏳ Translating...';
    translateBtn.style.opacity = '0.7';
    
    document.getElementById('sourceLang').disabled = true;
    document.getElementById('targetLang').disabled = true;
    document.getElementById('fileInput').disabled = true;
    
    const removeBtn = document.querySelector('.remove-btn');
    if (removeBtn) {
        removeBtn.disabled = true;
        removeBtn.style.opacity = '0.5';
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
    }
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
    }
    
    updateTranslateButton();
}
