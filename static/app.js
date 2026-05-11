document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const micButton = document.getElementById('micButton');
    const recordingIndicator = document.getElementById('recordingIndicator');
    const recordingStatus = document.getElementById('recordingStatus');
    const resultElement = document.getElementById('result');
    const apiKeyInput = document.getElementById('apiKey');
    const saveApiKeyButton = document.getElementById('saveApiKey');
    
    // Global variables
    let mediaRecorder = null;
    let audioChunks = [];
    let isRecording = false;
    let stream = null;
    
    // Check if browser supports MediaRecorder
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        alert('Your browser does not support audio recording. Please use a modern browser like Chrome, Firefox, or Edge.');
        micButton.disabled = true;
        return;
    }
    
    // Request microphone permissions on page load
    requestMicrophonePermission();
    
    async function requestMicrophonePermission() {
        try {
            // Just request permission, don't start recording yet
            stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            console.log("Microphone permission granted");
            
            // Immediately stop all tracks - we just wanted the permission
            stream.getTracks().forEach(track => track.stop());
            stream = null;
            
            // Enable the button now that we have permission
            micButton.disabled = false;
            recordingStatus.textContent = "Click to start recording";
        } catch (error) {
            console.error('Error accessing microphone:', error);
            recordingStatus.textContent = "Microphone access denied. Please check browser permissions.";
            micButton.disabled = true;
        }
    }
    
    // Handle mic button click
    micButton.addEventListener('click', function(event) {
        event.preventDefault();
        console.log("Mic button clicked");
        toggleRecording();
    });
    
    // Toggle recording state
    async function toggleRecording() {
        console.log("Toggle recording. Current state:", isRecording);
        if (!isRecording) {
            startRecording();
        } else {
            stopRecording();
        }
    }
    
    // Start recording
    async function startRecording() {
        try {
            console.log("Starting recording...");
            stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            
            // Show recording UI
            isRecording = true;
            micButton.classList.add('recording');
            recordingIndicator.classList.add('active');
            recordingStatus.textContent = 'Recording...';
            resultElement.textContent = 'Listening...';
            
            // Initialize MediaRecorder
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];
            
            // Collect audio chunks
            mediaRecorder.addEventListener('dataavailable', event => {
                console.log("Data available from recorder");
                audioChunks.push(event.data);
            });
            
            // Handle recording stop
            mediaRecorder.addEventListener('stop', () => {
                console.log("MediaRecorder stopped");
                processAudio();
                
                // Stop all tracks to release microphone
                if (stream) {
                    stream.getTracks().forEach(track => track.stop());
                    stream = null;
                }
            });
            
            // Start recording
            mediaRecorder.start();
            console.log("MediaRecorder started");
            
        } catch (error) {
            console.error('Error accessing microphone:', error);
            alert('Could not access your microphone. Please check permissions and try again.');
            resetRecordingState();
        }
    }
    
    // Stop recording
    function stopRecording() {
        console.log("Stopping recording...");
        if (mediaRecorder && isRecording) {
            mediaRecorder.stop();
            resetRecordingState();
            recordingStatus.textContent = 'Processing...';
        }
    }
    
    // Reset recording UI state
    function resetRecordingState() {
        console.log("Resetting recording state");
        isRecording = false;
        micButton.classList.remove('recording');
        recordingIndicator.classList.remove('active');
    }
    
    // Process recorded audio
    async function processAudio() {
        if (audioChunks.length === 0) {
            recordingStatus.textContent = 'No audio recorded. Try again.';
            return;
        }
        
        try {
            recordingStatus.textContent = 'Transcribing...';
            
            // Create audio blob
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            
            // Create form data to send to server
            const formData = new FormData();
            formData.append('file', audioBlob, 'recording.webm');
            
            console.log("Sending audio to server...");
            // Send to server for transcription
            const response = await fetch('/api/transcribe', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Transcription failed');
            }
            
            const data = await response.json();
            console.log("Transcription received:", data);
            
            // Display result
            resultElement.textContent = data.text || 'No transcription returned.';
            recordingStatus.textContent = 'Transcription complete. Click to record again.';
            
        } catch (error) {
            console.error('Error transcribing audio:', error);
            resultElement.textContent = 'Error: Could not transcribe audio.';
            recordingStatus.textContent = error.message || 'Transcription failed. Try again.';
        }
    }
    
});