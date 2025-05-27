/**
 * Sistem Pengenalan Wajah - Main JavaScript
 */
$(document).ready(function() {
    // Element references
    const startBtn = $('#start-btn');
    const resetBtn = $('#reset-btn');
    const countdownOverlay = $('#countdown-overlay');
    const processingOverlay = $('#processing-overlay');
    const countdownElement = $('#countdown');
    const resultContainer = $('#result-container');
    const initialState = $('#initial-state');
    const resultImage = $('#result-image');
    const resultMessage = $('#result-message');
    const statusMessage = $('#status-message');
    const healthCheck = $('#health-check');
    const healthModal = new bootstrap.Modal('#healthModal');

    // Start recognition process
    startBtn.on('click', function() {
        // Reset UI
        resultContainer.addClass('d-none');
        initialState.removeClass('d-none');
        statusMessage.addClass('d-none').removeClass('alert-success alert-danger alert-warning');
        
        // Start countdown
        startCountdown(3, function() {
            // Show processing overlay after countdown
            countdownOverlay.addClass('d-none');
            processingOverlay.removeClass('d-none');
            
            // Make API call to start recognition
            $.ajax({
                url: '/api/start_recognition',
                method: 'POST',
                success: function(response) {
                    if (response.status === 'processing') {
                        // Poll for results
                        pollForResults();
                    } else {
                        // Handle error
                        showError(response.message || 'Terjadi kesalahan saat memulai proses pengenalan.');
                    }
                },
                error: function() {
                    showError('Gagal terhubung ke server. Silakan coba lagi.');
                }
            });
        });
    });

    // Reset the view
    resetBtn.on('click', function() {
        // Hide result and show initial state
        resultContainer.addClass('d-none');
        initialState.removeClass('d-none');
        startBtn.removeClass('d-none');
        resetBtn.addClass('d-none');
    });

    // Health check
    healthCheck.on('click', function(e) {
        e.preventDefault();
        
        // Reset health status
        $('#camera-status, #faces-count, #esp32-status').text('Memeriksa...');
        
        // Show modal
        healthModal.show();
        
        // Get health status
        $.ajax({
            url: '/health',
            method: 'GET',
            success: function(response) {
                try {
                    const data = typeof response === 'string' ? JSON.parse(response) : response;
                    
                    // Update status
                    $('#camera-status').text(data.camera_connected ? 'Terhubung' : 'Tidak terhubung')
                        .addClass(data.camera_connected ? 'text-success' : 'text-danger');
                    
                    $('#faces-count').text(data.known_faces_count + ' wajah');
                    
                    $('#esp32-status').text(data.status === 'healthy' ? 'Terhubung' : 'Tidak terhubung')
                        .addClass(data.status === 'healthy' ? 'text-success' : 'text-danger');
                } catch (e) {
                    showError('Gagal memproses status sistem.');
                }
            },
            error: function() {
                showError('Gagal mendapatkan status sistem.');
            }
        });
    });

    /**
     * Start countdown from specified number
     * @param {number} seconds - Seconds to countdown from
     * @param {Function} callback - Function to call when countdown finishes
     */
    function startCountdown(seconds, callback) {
        countdownElement.text(seconds);
        countdownOverlay.removeClass('d-none');
        
        const interval = setInterval(function() {
            seconds--;
            countdownElement.text(seconds);
            
            if (seconds <= 0) {
                clearInterval(interval);
                if (callback) callback();
            }
        }, 1000);
    }

    /**
     * Poll for recognition results
     */
    function pollForResults() {
        const pollInterval = setInterval(function() {
            $.ajax({
                url: '/api/check_result',
                method: 'GET',
                success: function(response) {
                    // If no result yet, continue polling
                    if (!response.status) {
                        return;
                    }
                    
                    // Stop polling and hide processing overlay
                    clearInterval(pollInterval);
                    processingOverlay.addClass('d-none');
                    
                    // Handle result
                    if (response.status === 'success') {
                        showResult(response);
                    } else if (response.status === 'unknown') {
                        showUnknownPerson(response);
                    } else {
                        showError(response.message || 'Terjadi kesalahan saat proses pengenalan.');
                    }
                },
                error: function() {
                    clearInterval(pollInterval);
                    processingOverlay.addClass('d-none');
                    showError('Gagal terhubung ke server. Silakan coba lagi.');
                }
            });
        }, 1000); // Check every second
    }

    /**
     * Show successful recognition
     * @param {Object} result - Recognition result
     */
    function showResult(result) {
        // Set result image
        if (result.face_data) {
            resultImage.attr('src', 'data:image/jpeg;base64,' + result.face_data);
        }
        
        // Update result message
        resultMessage.removeClass('alert-info alert-danger alert-warning').addClass('alert-success');
        resultMessage.text(result.message);
        
        // Show result
        initialState.addClass('d-none');
        resultContainer.removeClass('d-none');
        startBtn.addClass('d-none');
        resetBtn.removeClass('d-none');
        
        // Redirect ke halaman peminjaman jika ada URL redirect
        if (result.redirect_url) {
            // Tunda redirect beberapa detik untuk memberi pengguna kesempatan melihat hasil pengenalan
            setTimeout(function() {
                window.location.href = result.redirect_url;
            }, 1500);
        }
    }

    /**
     * Show unknown person result
     * @param {Object} result - Recognition result
     */
    function showUnknownPerson(result) {
        // Set result image
        if (result.face_data) {
            resultImage.attr('src', 'data:image/jpeg;base64,' + result.face_data);
        }
        
        // Update result message
        resultMessage.removeClass('alert-info alert-success alert-danger').addClass('alert-warning');
        resultMessage.text(result.message);
        
        // Show result
        initialState.addClass('d-none');
        resultContainer.removeClass('d-none');
        startBtn.addClass('d-none');
        resetBtn.removeClass('d-none');
    }

    /**
     * Show error message
     * @param {string} message - Error message to display
     */
    function showError(message) {
        statusMessage.removeClass('d-none alert-success alert-warning').addClass('alert-danger');
        statusMessage.text(message);
        processingOverlay.addClass('d-none');
    }
}); 