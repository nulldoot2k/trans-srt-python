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
        showSettingsStatus('⚠️ Please enter API key for AI mode', 'error');
        return;
    }
    
    // Disable button and show loading
    saveBtn.disabled = true;
    saveBtn.textContent = '💾 Saving...';
    
    // Save to backend .env file
    try {
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
            saveBtn.textContent = '✅ Saved Successfully!';
            saveBtn.style.background = 'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)';
            showSettingsStatus(`✅ API key saved to .env file successfully!`, 'success');
            
            // Auto close after 2 seconds
            setTimeout(() => {
                toggleSettings();
                saveBtn.textContent = 'Save Settings';
                saveBtn.disabled = false;
            }, 2000);
        } else {
            console.error('Save failed:', result);
            saveBtn.textContent = '❌ Save Failed';
            saveBtn.style.background = 'linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%)';
            showSettingsStatus(`❌ Error: ${result.error || 'Failed to save'}`, 'error');
            
            // Reset button after 3 seconds
            setTimeout(() => {
                saveBtn.textContent = 'Save Settings';
                saveBtn.style.background = 'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)';
                saveBtn.disabled = false;
            }, 3000);
        }
    } catch (error) {
        console.error('Network error:', error);
        saveBtn.textContent = '⚠️ Partial Save';
        saveBtn.style.background = 'linear-gradient(135deg, #f39c12 0%, #f1c40f 100%)';
        showSettingsStatus('⚠️ Saved locally only (server connection failed)', 'warning');
        
        // Reset button after 3 seconds
        setTimeout(() => {
            saveBtn.textContent = 'Save Settings';
            saveBtn.style.background = 'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)';
            saveBtn.disabled = false;
        }, 3000);
    }
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

function updateProgress(percent, statusText = "") {
    const container = document.getElementById('progressContainer');
    const fill = document.getElementById('progressFill');
    const percentEl = document.getElementById('progressPercent');
    const statusEl = document.getElementById('progressStatus');

    container.classList.remove('hidden');
    
    // Tránh nhảy số quá nhanh gây khó chịu
    const current = parseInt(fill.style.width) || 0;
    if (percent > current || percent === 100) {
        fill.style.width = percent + '%';
        percentEl.textContent = percent + '%';
        
        if (statusText) {
            statusEl.textContent = statusText;
        } else if (percent >= 95) {
            statusEl.textContent = "Sắp xong rồi...";
        } else if (percent >= 70) {
            statusEl.textContent = "Đang hoàn thiện...";
        } else if (percent >= 30) {
            statusEl.textContent = "Đang dịch phần chính...";
        }
    }
    
    // Hiệu ứng hoàn thành đẹp mắt
    if (percent >= 100) {
        setTimeout(() => {
            fill.style.background = 'linear-gradient(90deg, #00ff9d, #00c6ff)';
            statusEl.textContent = "Hoàn tất!";
            setTimeout(() => container.classList.add('hidden'), 1800);
        }, 600);
    }
}

let progressInterval = null;

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
    showStatus(useAI ? '🤖 Đang dịch bằng AI...' : '🌐 Đang dịch nhanh (free mode)...', true);

    // Khởi tạo progress
    updateProgress(0, "Chuẩn bị file...");
    
    // Biến toàn cục để quản lý interval
    let progressInterval = null;

    // Hàm polling tiến trình (đặt ở đây để tiện quản lý)
    function startProgressPolling() {
        if (progressInterval) clearInterval(progressInterval);
        
        let lastPercent = 0;
        
        progressInterval = setInterval(async () => {
            try {
                const res = await fetch('/progress');
                const data = await res.json();
                
                const percent = Math.min(data.progress || 0, 100);
                
                // Chỉ cập nhật khi thay đổi >= 1% hoặc đạt 100% để tránh nhấp nháy
                if (Math.abs(percent - lastPercent) >= 1 || percent === 100 || percent === 0) {
                    let statusText = data.status || (percent < 30 ? "Đang đọc và phân tích file..." :
                                                     percent < 70 ? "Đang dịch nội dung..." :
                                                     percent < 95 ? "Đang hoàn thiện định dạng..." : "Sắp xong rồi!");
                    
                    if (data.processed) {
                        statusText += ` (${data.processed})`;
                    }
                    
                    updateProgress(percent, statusText);
                    lastPercent = percent;
                }
            } catch (e) {
                console.warn('Progress poll error:', e);
            }
        }, 2000);
    }

    // Bắt đầu polling ngay
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

        // Dừng polling và hoàn tất progress
        if (progressInterval) {
            clearInterval(progressInterval);
            progressInterval = null;
        }

        updateProgress(100, "Hoàn tất! Đang chuẩn bị file tải về...");
        
        setTimeout(() => {
            document.getElementById('progressContainer').classList.add('hidden');
            document.getElementById('progressFill').style.width = '0%';
        }, 1500);
        
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

        showStatus('✅ Dịch xong! Xem preview và tải file bên dưới.', false);

    } catch (error) {
        console.error('Translation error:', error);
        showStatus(`❌ Lỗi: ${error.message}`, false);
        
        if (progressInterval) {
            clearInterval(progressInterval);
            progressInterval = null;
        }
        
        document.getElementById('progressContainer').classList.add('hidden');
        document.getElementById('progressFill').style.width = '0%';
        
    } finally {
        unlockUI();
    }
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
    updateProgress(0);

    let progressInterval = null;

    progressInterval = setInterval(async () => {
        try {
            const res = await fetch('/progress');
            const data = await res.json();
            
            const percent = Math.min(data.progress || 0, 100);
            
            // Dòng bạn đang hỏi nằm ở đây ↓
            updateProgress(
                percent, 
                `${data.status || 'Đang xử lý...'} ${data.processed ? `(${data.processed})` : ''}`
            );
            
        } catch (e) {
            console.warn('Progress fetch failed:', e);
        }
    }, 800);

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

        clearInterval(progressInterval);
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
        clearInterval(progressInterval);
        
        document.getElementById('progressContainer').classList.add('hidden');
        document.getElementById('progressFill').style.width = '0%';
    } finally {
        unlockUI();
    }
}

function showSettingsStatus(message, type) {
    // Remove old status if exists
    const oldStatus = document.querySelector('.settings-status');
    if (oldStatus) oldStatus.remove();
    
    // Create status element
    const statusDiv = document.createElement('div');
    statusDiv.className = 'settings-status';
    statusDiv.textContent = message;
    
    // Style based on type
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
    
    // Insert before Save button
    const saveBtn = document.querySelector('.btn-success');
    saveBtn.parentNode.insertBefore(statusDiv, saveBtn);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        statusDiv.style.animation = 'slideUp 0.3s ease';
        setTimeout(() => statusDiv.remove(), 300);
    }, 5000);
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
