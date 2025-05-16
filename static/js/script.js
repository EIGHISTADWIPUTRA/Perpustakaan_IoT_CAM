// Cache DOM elements
const elements = {
    videoStream: $('#video-stream'),
    countdownOverlay: $('#countdown-overlay'),
    countdownElement: $('#countdown'),
    processingOverlay: $('#processing-overlay'),
    startBtn: $('#start-btn'),
    resetBtn: $('#reset-btn'),
    statusMessage: $('#status-message'),
    resultContainer: $('#result-container'),
    resultImage: $('#result-image'),
    resultMessage: $('#result-message')
};

// Constants
const COUNTDOWN_DURATION = 3;
const RESULT_CHECK_INTERVAL = 500;
const MAX_RETRIES = 3;

// State management
const state = {
    isProcessing: false,
    retryCount: 0,
    resultCheckInterval: null
};

// Initialize application
$(document).ready(function() {
    initializeEventListeners();
});

// Event listeners
function initializeEventListeners() {
    elements.startBtn.on('click', handleStartClick);
    elements.resetBtn.on('click', handleResetClick);
}

// Event handlers
function handleStartClick() {
    if (state.isProcessing) return;
    
    elements.countdownOverlay.removeClass('hidden');
    startCountdown();
}

function handleResetClick() {
    resetApp();
}

// Countdown functionality
function startCountdown() {
    let count = COUNTDOWN_DURATION;
    elements.countdownElement.text(count);
    
    const interval = setInterval(() => {
        count--;
        elements.countdownElement.text(count);
        
        if (count <= 0) {
            clearInterval(interval);
            elements.countdownOverlay.addClass('hidden');
            startRecognition();
        }
    }, 1000);
}

// Face recognition process
async function startRecognition() {
    try {
        state.isProcessing = true;
        elements.processingOverlay.removeClass('hidden');
        
        const response = await $.ajax({
            url: '/start_recognition',
            type: 'POST',
            timeout: 10000
        });
        
        if (response.status === 'processing') {
            checkResult();
        } else {
            throw new Error(response.message || 'Gagal memulai proses pengenalan wajah');
        }
    } catch (error) {
        handleError(error);
    }
}

// Check recognition result
function checkResult() {
    state.resultCheckInterval = setInterval(async () => {
        try {
            const result = await $.ajax({
                url: '/check_result',
                type: 'GET',
                timeout: 5000
            });
            
            if (result.status !== null) {
                clearInterval(state.resultCheckInterval);
                showResult(result);
            }
        } catch (error) {
            handleError(error);
        }
    }, RESULT_CHECK_INTERVAL);
}

// Display recognition result
function showResult(result) {
    elements.processingOverlay.addClass('hidden');
    elements.videoStream.addClass('hidden');
    
    if (result.status === 'success' || result.status === 'unknown') {
        if (result.face_data) {
            elements.resultImage.attr('src', `data:image/jpeg;base64,${result.face_data}`);
            elements.resultContainer.removeClass('hidden');
        }
        
        elements.resultMessage.text(result.message);
        elements.statusMessage.text('');
    } else if (result.status === 'error' || result.status === 'timeout') {
        showError(result.message);
    }
    
    elements.startBtn.addClass('hidden');
    elements.resetBtn.removeClass('hidden');
    state.isProcessing = false;
}

// Error handling
function handleError(error) {
    console.error('Error:', error);
    
    if (state.retryCount < MAX_RETRIES) {
        state.retryCount++;
        showError(`Mencoba ulang (${state.retryCount}/${MAX_RETRIES})...`);
        setTimeout(startRecognition, 1000);
    } else {
        showError(error.message || 'Gagal terhubung dengan server');
        elements.processingOverlay.addClass('hidden');
        state.isProcessing = false;
        state.retryCount = 0;
    }
}

// Display error message
function showError(message) {
    elements.statusMessage.text(message);
    elements.statusMessage.css('color', 'red');
}

// Reset application
function resetApp() {
    if (state.resultCheckInterval) {
        clearInterval(state.resultCheckInterval);
    }
    
    state.isProcessing = false;
    state.retryCount = 0;
    window.location.reload();
}
