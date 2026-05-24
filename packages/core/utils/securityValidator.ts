// utils/securityValidator.ts
// Security validation and input sanitization for Synthesus 3.0
// Provides validation for multimodal inputs, rate limiting checks, and sanitization

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  sanitized?: any;
}

export interface MultimodalSecurityConfig {
  maxImageSizeBytes: number;
  maxAudioSizeBytes: number;
  maxTextLength: number;
  allowedImageTypes: string[];
  allowedAudioTypes: string[];
  maxConcurrentUploads: number;
}

export const DEFAULT_SECURITY_CONFIG: MultimodalSecurityConfig = {
  maxImageSizeBytes: 10 * 1024 * 1024, // 10MB
  maxAudioSizeBytes: 50 * 1024 * 1024, // 50MB
  maxTextLength: 10000,
  allowedImageTypes: ['image/jpeg', 'image/png', 'image/webp', 'image/gif'],
  allowedAudioTypes: ['audio/wav', 'audio/mp3', 'audio/ogg', 'audio/webm'],
  maxConcurrentUploads: 5,
};

// Track concurrent uploads per session
const uploadTracker: Map<string, number> = new Map();

export class SecurityValidator {
  private config: MultimodalSecurityConfig;

  constructor(config: Partial<MultimodalSecurityConfig> = {}) {
    this.config = { ...DEFAULT_SECURITY_CONFIG, ...config };
  }

  /**
   * Validate and sanitize base64 image data
   */
  validateImageInput(imageData: string, mimeType?: string): ValidationResult {
    const errors: string[] = [];

    // Check if it's a valid base64 string
    if (!this.isValidBase64(imageData)) {
      errors.push('Invalid base64 encoding');
      return { valid: false, errors };
    }

    // Check size
    const sizeBytes = this.estimateBase64Size(imageData);
    if (sizeBytes > this.config.maxImageSizeBytes) {
      errors.push(`Image too large: ${(sizeBytes / 1024 / 1024).toFixed(2)}MB exceeds ${(this.config.maxImageSizeBytes / 1024 / 1024)}MB limit`);
    }

    // Validate MIME type if provided
    if (mimeType && !this.config.allowedImageTypes.includes(mimeType)) {
      errors.push(`Unsupported image type: ${mimeType}. Allowed: ${this.config.allowedImageTypes.join(', ')}`);
    }

    // Sanitize - remove data URI prefix if present
    let sanitized = imageData;
    if (sanitized.includes(',')) {
      sanitized = sanitized.split(',')[1];
    }

    return {
      valid: errors.length === 0,
      errors,
      sanitized,
    };
  }

  /**
   * Validate and sanitize base64 audio data
   */
  validateAudioInput(audioData: string, mimeType?: string): ValidationResult {
    const errors: string[] = [];

    // Check if it's a valid base64 string
    if (!this.isValidBase64(audioData)) {
      errors.push('Invalid base64 encoding');
      return { valid: false, errors };
    }

    // Check size
    const sizeBytes = this.estimateBase64Size(audioData);
    if (sizeBytes > this.config.maxAudioSizeBytes) {
      errors.push(`Audio too large: ${(sizeBytes / 1024 / 1024).toFixed(2)}MB exceeds ${(this.config.maxAudioSizeBytes / 1024 / 1024)}MB limit`);
    }

    // Validate MIME type if provided
    if (mimeType && !this.config.allowedAudioTypes.includes(mimeType)) {
      errors.push(`Unsupported audio type: ${mimeType}. Allowed: ${this.config.allowedAudioTypes.join(', ')}`);
    }

    // Sanitize - remove data URI prefix if present
    let sanitized = audioData;
    if (sanitized.includes(',')) {
      sanitized = sanitized.split(',')[1];
    }

    return {
      valid: errors.length === 0,
      errors,
      sanitized,
    };
  }

  /**
   * Validate text input
   */
  validateTextInput(text: string): ValidationResult {
    const errors: string[] = [];

    if (!text || typeof text !== 'string') {
      errors.push('Text input must be a non-empty string');
      return { valid: false, errors };
    }

    // Check length
    if (text.length > this.config.maxTextLength) {
      errors.push(`Text too long: ${text.length} chars exceeds ${this.config.maxTextLength} limit`);
    }

    // Basic XSS prevention - flag suspicious patterns
    const suspiciousPatterns = [
      /<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi,
      /javascript:/gi,
      /on\w+\s*=/gi, // onclick=, onerror=, etc.
      /<iframe/gi,
      /<object/gi,
      /<embed/gi,
    ];

    for (const pattern of suspiciousPatterns) {
      if (pattern.test(text)) {
        errors.push('Text contains potentially dangerous content');
        break;
      }
    }

    // Sanitize - remove control characters except newlines
    const sanitized = text
      .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '')
      .trim();

    return {
      valid: errors.length === 0,
      errors,
      sanitized,
    };
  }

  /**
   * Validate URL for external resources
   */
  validateUrl(url: string, allowedSchemes: string[] = ['https']): ValidationResult {
    const errors: string[] = [];

    try {
      const parsed = new URL(url);

      // Check scheme
      if (!allowedSchemes.includes(parsed.protocol.replace(':', ''))) {
        errors.push(`URL scheme not allowed: ${parsed.protocol}. Allowed: ${allowedSchemes.join(', ')}`);
      }

      // Block localhost and private IPs in production
      const hostname = parsed.hostname;
      if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname.startsWith('192.168.') || hostname.startsWith('10.')) {
        errors.push('Private network URLs not allowed');
      }

    } catch {
      errors.push('Invalid URL format');
    }

    return {
      valid: errors.length === 0,
      errors,
    };
  }

  /**
   * Check rate limiting for uploads
   */
  checkUploadRateLimit(sessionId: string): ValidationResult {
    const errors: string[] = [];
    const current = uploadTracker.get(sessionId) || 0;

    if (current >= this.config.maxConcurrentUploads) {
      errors.push(`Rate limit exceeded: ${this.config.maxConcurrentUploads} concurrent uploads allowed`);
    }

    return {
      valid: errors.length === 0,
      errors,
    };
  }

  /**
   * Track upload start
   */
  startUpload(sessionId: string): void {
    const current = uploadTracker.get(sessionId) || 0;
    uploadTracker.set(sessionId, current + 1);
  }

  /**
   * Track upload completion
   */
  endUpload(sessionId: string): void {
    const current = uploadTracker.get(sessionId) || 0;
    if (current > 0) {
      uploadTracker.set(sessionId, current - 1);
    }
  }

  /**
   * Validate complete multimodal query
   */
  validateMultimodalQuery(query: {
    text?: string;
    base64Image?: string;
    base64Audio?: string;
    imageUrl?: string;
    audioUrl?: string;
  }, sessionId: string): ValidationResult {
    const errors: string[] = [];
    const sanitized: any = {};

    // Check rate limiting
    const rateLimit = this.checkUploadRateLimit(sessionId);
    if (!rateLimit.valid) {
      errors.push(...rateLimit.errors);
    }

    // Validate text if present
    if (query.text) {
      const textValidation = this.validateTextInput(query.text);
      if (!textValidation.valid) {
        errors.push(...textValidation.errors);
      } else if (textValidation.sanitized) {
        sanitized.text = textValidation.sanitized;
      }
    }

    // Validate image if present
    if (query.base64Image) {
      const imageValidation = this.validateImageInput(query.base64Image);
      if (!imageValidation.valid) {
        errors.push(...imageValidation.errors);
      } else if (imageValidation.sanitized) {
        sanitized.base64Image = imageValidation.sanitized;
      }
    }

    if (query.imageUrl) {
      const urlValidation = this.validateUrl(query.imageUrl);
      if (!urlValidation.valid) {
        errors.push(...urlValidation.errors);
      }
    }

    // Validate audio if present
    if (query.base64Audio) {
      const audioValidation = this.validateAudioInput(query.base64Audio);
      if (!audioValidation.valid) {
        errors.push(...audioValidation.errors);
      } else if (audioValidation.sanitized) {
        sanitized.base64Audio = audioValidation.sanitized;
      }
    }

    if (query.audioUrl) {
      const urlValidation = this.validateUrl(query.audioUrl);
      if (!urlValidation.valid) {
        errors.push(...urlValidation.errors);
      }
    }

    return {
      valid: errors.length === 0,
      errors,
      sanitized: Object.keys(sanitized).length > 0 ? sanitized : undefined,
    };
  }

  /**
   * Clean up old upload tracking entries (call periodically)
   */
  cleanupUploadTracking(): void {
    uploadTracker.clear();
  }

  // Private helpers
  private isValidBase64(str: string): boolean {
    // Remove data URI prefix if present
    const base64 = str.includes(',') ? str.split(',')[1] : str;

    // Check if it's valid base64
    const base64Regex = /^[A-Za-z0-9+/]*={0,2}$/;
    if (!base64Regex.test(base64)) {
      return false;
    }

    // Try to validate length (should be multiple of 4)
    if (base64.length % 4 !== 0) {
      return false;
    }

    return true;
  }

  private estimateBase64Size(base64String: string): number {
    // Remove data URI prefix if present
    const base64 = base64String.includes(',') ? base64String.split(',')[1] : base64String;
    // Base64 encoding increases size by ~33%
    return Math.ceil((base64.length * 3) / 4);
  }
}

// Singleton instance
let _securityValidator: SecurityValidator | null = null;

export function getSecurityValidator(config?: Partial<MultimodalSecurityConfig>): SecurityValidator {
  if (!_securityValidator) {
    _securityValidator = new SecurityValidator(config);
  }
  return _securityValidator;
}

export function resetSecurityValidator(): void {
  _securityValidator = null;
}
