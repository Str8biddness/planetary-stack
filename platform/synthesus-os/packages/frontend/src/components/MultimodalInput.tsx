// frontend/src/components/MultimodalInput.tsx
// Multimodal input component with image and voice capture

import { useState, useRef, useCallback } from 'react';
import { amplificationClient } from '../api/amplificationClient';
import type { MultimodalQueryRequest } from '../api/amplificationClient';
import { SecurityValidator } from '../utils/security';

interface MultimodalInputProps {
  characterId: string;
  sessionId: string;
  onSend: (response: { text: string; amplificationInfo?: any }) => void;
  onError: (error: string) => void;
}

export function MultimodalInput({ characterId, sessionId, onSend, onError }: MultimodalInputProps) {
  const [text, setText] = useState('');
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [audioRecording, setAudioRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const securityValidator = useRef(new SecurityValidator());

  // Handle image file selection
  const handleImageSelect = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate file
    const validation = securityValidator.current.validateImageFile(file);
    if (!validation.valid) {
      onError(validation.errors.join(', '));
      return;
    }

    // Convert to base64
    const reader = new FileReader();
    reader.onload = (e) => {
      const base64 = e.target?.result as string;
      setImagePreview(base64);
    };
    reader.readAsDataURL(file);
  }, [onError]);

  // Start audio recording
  const startAudioRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };
      
      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        // Convert to base64 and store for upload
        const reader = new FileReader();
        reader.onload = (e) => {
          const base64 = e.target?.result as string;
          // Store for later use in query
          sessionStorage.setItem('pendingAudio', base64);
        };
        reader.readAsDataURL(audioBlob);
      };
      
      mediaRecorder.start();
      setAudioRecording(true);
    } catch (err) {
      onError('Failed to access microphone: ' + (err as Error).message);
    }
  }, [onError]);

  // Stop audio recording
  const stopAudioRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop());
    }
    setAudioRecording(false);
  }, []);

  // Clear image
  const clearImage = useCallback(() => {
    setImagePreview(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, []);

  // Send multimodal query
  const handleSend = useCallback(async () => {
    if (!text.trim() && !imagePreview) {
      onError('Please enter text or upload an image');
      return;
    }

    setIsProcessing(true);
    setUploadProgress(0);

    try {
      // Get pending audio if any
      const pendingAudio = sessionStorage.getItem('pendingAudio');
      sessionStorage.removeItem('pendingAudio');

      const request: MultimodalQueryRequest = {
        query: text.trim() || 'Describe what you see',
        character_id: characterId,
        session_id: sessionId,
      };

      // Add image if present
      if (imagePreview) {
        const mimeMatch = imagePreview.match(/^data:([^;]+);base64,/);
        if (mimeMatch) {
          request.imageMimeType = mimeMatch[1];
          request.base64Image = imagePreview;
        }
      }

      // Add audio if present
      if (pendingAudio) {
        const mimeMatch = pendingAudio.match(/^data:([^;]+);base64,/);
        if (mimeMatch) {
          request.audioMimeType = mimeMatch[1];
          request.base64Audio = pendingAudio;
        }
      }

      // Send to API
      const response = await amplificationClient.sendMultimodalQuery(request);
      
      // Call onSend callback
      onSend({
        text: response.response,
        amplificationInfo: response.amplification_info,
      });

      // Clear inputs
      setText('');
      setImagePreview(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (err) {
      onError('Failed to send message: ' + (err as Error).message);
    } finally {
      setIsProcessing(false);
      setUploadProgress(0);
    }
  }, [text, imagePreview, characterId, sessionId, onSend, onError]);

  return (
    <div className="multimodal-input">
      {/* Image Preview */}
      {imagePreview && (
        <div className="image-preview-container">
          <img src={imagePreview} alt="Preview" className="image-preview" />
          <button onClick={clearImage} className="clear-image-btn" title="Remove image">
            ×
          </button>
        </div>
      )}

      {/* Text Input */}
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Type your message... (or upload an image/voice)"
        disabled={isProcessing}
        rows={3}
        className="text-input"
      />

      {/* Progress Bar */}
      {isProcessing && uploadProgress > 0 && (
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${uploadProgress}%` }} />
        </div>
      )}

      {/* Action Buttons */}
      <div className="input-actions">
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleImageSelect}
          accept="image/jpeg,image/png,image/webp,image/gif"
          style={{ display: 'none' }}
        />
        
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isProcessing || !!imagePreview}
          className="upload-btn"
          title="Upload image"
        >
          📷 {imagePreview ? '1 image' : 'Add Image'}
        </button>

        <button
          onClick={audioRecording ? stopAudioRecording : startAudioRecording}
          disabled={isProcessing}
          className={`record-btn ${audioRecording ? 'recording' : ''}`}
          title={audioRecording ? 'Stop recording' : 'Record voice'}
        >
          {audioRecording ? '⏹ Stop' : '🎤 Voice'}
        </button>

        <button
          onClick={handleSend}
          disabled={isProcessing || (!text.trim() && !imagePreview)}
          className="send-btn"
        >
          {isProcessing ? 'Processing...' : 'Send'}
        </button>
      </div>
    </div>
  );
}
