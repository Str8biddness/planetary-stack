// frontend/src/utils/security.ts
// Frontend security validation for multimodal inputs

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  sanitized?: string;
}

export interface SecurityConfig {
  maxImageSizeBytes: number;
  maxAudioSizeBytes: number;
  maxTextLength: number;
  allowedImageTypes: string[];
  allowedAudioTypes: string[];
  maxConcurrentUploads: number;
}

export const DEFAULT_SECURITY_CONFIG: SecurityConfig = {
  maxImageSizeBytes: 10 * 1024 * 1024, // 10MB
  maxAudioSizeBytes: 50 * 1024 * 1024, // 50MB
  maxTextLength: 10000,
  allowedImageTypes: ['image/jpeg', 'image/png', 'image/webp', 'image/gif'],
  allowedAudioTypes: ['audio/wav', 'audio/mp3', 'audio/ogg', 'audio/webm'],
  maxConcurrentUploads: 5,
};

export class SecurityValidator {
  private config: SecurityConfig;
  private uploadCount: number = 0;

  constructor(config: Partial<SecurityConfig> = {}) {
    this.config = { ...DEFAULT_SECURITY_CONFIG, ...config };
  }

  /**
   * Validate image file before upload
   */
  validateImageFile(file: File): ValidationResult {
    const errors: string[] = [];

    // Check size
    if (file.size > this.config.maxImageSizeBytes) {
      errors.push(
        `Image too large: ${(file.size / 1024 / 1024).toFixed(2)}MB exceeds ${(this.config.maxImageSizeBytes / 1024 / 1024)}MB limit`
      );
    }

    // Check MIME type
    if (!this.config.allowedImageTypes.includes(file.type)) {
      errors.push(`Unsupported image type: ${file.type}`);
    }

    // Check concurrent uploads
    if (this.uploadCount >= this.config.maxConcurrentUploads) {
      errors.push(`Too many concurrent uploads: ${this.config.maxConcurrentUploads} max`);
    }

    return {
      valid: errors.length === 0,
      errors,
    };
  }

  /**
   * Validate audio file before upload
   */
  validateAudioFile(file: File): ValidationResult {
    const errors: string[] = [];

    // Check size
    if (file.size > this.config.maxAudioSizeBytes) {
      errors.push(
        `Audio too large: ${(file.size / 1024 / 1024).toFixed(2)}MB exceeds ${(this.config.maxAudioSizeBytes / 1024 / 1024)}MB limit`
      );
    }

    // Check MIME type
    if (!this.config.allowedAudioTypes.includes(file.type)) {
      errors.push(`Unsupported audio type: ${file.type}`);
    }

    return {
      valid: errors.length === 0,
      errors,
    };
  }

  /**
   * Validate text input
   */
  validateText(text: string): ValidationResult {
    const errors: string[] = [];

    if (!text || text.trim().length === 0) {
      errors.push('Text cannot be empty');
      return { valid: false, errors };
    }

    if (text.length > this.config.maxTextLength) {
      errors.push(`Text too long: ${text.length} chars exceeds ${this.config.maxTextLength} limit`);
    }

    // XSS prevention - check for suspicious patterns
    const suspiciousPatterns = [
      /<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi,
      /javascript:/gi,
      /on\w+\s*=/gi,
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

    // Sanitize - remove control characters
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
   * Validate base64 image data
   */
  validateBase64Image(base64String: string): ValidationResult {
    const errors: string[] = [];

    // Check if valid base64 format
    if (!base64String.match(/^data:image\/[a-zA-Z]+;base64,/)) {
      errors.push('Invalid image data URI format');
      return { valid: false, errors };
    }

    // Extract base64 part
    const base64 = base64String.split(',')[1];
    
    // Estimate size (base64 is ~33% larger than binary)
    const estimatedSize = (base64.length * 3) / 4;
    
    if (estimatedSize > this.config.maxImageSizeBytes) {
      errors.push(`Image data too large: estimated ${(estimatedSize / 1024 / 1024).toFixed(2)}MB`);
    }

    return {
      valid: errors.length === 0,
      errors,
      sanitized: base64String,
    };
  }

  /**
   * Increment upload count
   */
  startUpload(): void {
    this.uploadCount++;
  }

  /**
   * Decrement upload count
   */
  endUpload(): void {
    if (this.uploadCount > 0) {
      this.uploadCount--;
    }
  }

  /**
   * Get current upload count
   */
  getUploadCount(): number {
    return this.uploadCount;
  }
}

// Singleton instance
let _validator: SecurityValidator | null = null;

export function getSecurityValidator(config?: Partial<SecurityConfig>): SecurityValidator {
  if (!_validator) {
    _validator = new SecurityValidator(config);
  }
  return _validator;
}

export function resetSecurityValidator(): void {
  _validator = null;
}

/**
 * Sanitize HTML content for display
 */
export function sanitizeHtml(html: string): string {
  // Remove script tags and event handlers
  return html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/on\w+\s*=["'][^"']*["']/gi, '')
    .replace(/javascript:/gi, '');
}

/**
 * Validate URL
 */
export function validateUrl(url: string, allowedSchemes: string[] = ['https']): ValidationResult {
  const errors: string[] = [];

  try {
    const parsed = new URL(url);

    if (!allowedSchemes.includes(parsed.protocol.replace(':', ''))) {
      errors.push(`URL scheme not allowed: ${parsed.protocol}`);
    }

    // Block private IPs
    const hostname = parsed.hostname;
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
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
