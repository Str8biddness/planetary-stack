"""
Psi Transformer Attention — Lightweight Attention for Fluid Hemisphere

Integrates ConsciousLlmAi's lightweight transformer into Synthesus Psi hemisphere:
- Pure NumPy scaled dot-product attention
- Multi-head attention mechanism
- Attention map extraction for explainable reasoning
- Pattern detection via attention entropy analysis

Provides deeper pattern recognition than simple sentiment analysis,
with visualizable attention weights for reasoning transparency.
"""

import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AttentionAnalysis:
    """Analysis results from attention processing."""
    attention_maps: List[np.ndarray] = field(default_factory=list)
    focus_tokens: List[int] = field(default_factory=list)
    entropy: float = 0.0
    pattern_detected: str = ""
    confidence: float = 0.0
    novelty_score: float = 0.0
    uncertainty: float = 0.0
    active_hypotheses: List[str] = field(default_factory=list)


class ScaledDotProductAttention:
    """
    Scaled dot-product attention from ConsciousLlmAi.
    O(n²) attention mechanism for pattern recognition.
    """
    
    def __init__(self, dropout: float = 0.1):
        self.dropout = dropout
        self.attention_weights = None
    
    def forward(
        self,
        query: np.ndarray,
        key: np.ndarray,
        value: np.ndarray,
        mask: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute scaled dot-product attention.
        
        Args:
            query: Query tensor (batch, heads, seq_len, d_k)
            key: Key tensor (batch, heads, seq_len, d_k)
            value: Value tensor (batch, heads, seq_len, d_k)
            mask: Optional attention mask
            
        Returns:
            (output, attention_weights)
        """
        d_k = query.shape[-1]
        
        # Scaled dot-product: Q @ K^T / sqrt(d_k)
        scores = np.matmul(query, key.transpose(0, 1, 3, 2)) / np.sqrt(d_k)
        
        if mask is not None:
            scores = scores + (mask * -1e9)
        
        # Softmax to get attention weights
        attention_weights = self.softmax(scores)
        self.attention_weights = attention_weights
        
        # Weighted sum of values
        output = np.matmul(attention_weights, value)
        
        return output, attention_weights
    
    @staticmethod
    def softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
        """Numerically stable softmax."""
        x_max = np.max(x, axis=axis, keepdims=True)
        exp_x = np.exp(x - x_max)
        return exp_x / np.sum(exp_x, axis=axis, keepdims=True)


class MultiHeadAttention:
    """Multi-head attention for parallel pattern recognition."""
    
    def __init__(self, d_model: int = 256, num_heads: int = 4, dropout: float = 0.1):
        assert d_model % num_heads == 0
        self.d_model = d_model
        self.num_heads = num_heads
        self.d_k = d_model // num_heads
        
        # Learnable weight matrices
        self.W_q = self._initialize_weights((d_model, d_model))
        self.W_k = self._initialize_weights((d_model, d_model))
        self.W_v = self._initialize_weights((d_model, d_model))
        self.W_o = self._initialize_weights((d_model, d_model))
        
        self.attention = ScaledDotProductAttention(dropout)
    
    def forward(
        self,
        query: np.ndarray,
        key: np.ndarray,
        value: np.ndarray,
        mask: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Multi-head attention forward pass.
        
        Returns:
            (output, attention_weights) where attention_weights shape is
            (batch, heads, seq_len, seq_len) for visualization
        """
        batch_size = query.shape[0]
        
        # Linear projections
        Q = np.matmul(query, self.W_q)
        K = np.matmul(key, self.W_k)
        V = np.matmul(value, self.W_v)
        
        # Split into heads
        Q = self._split_heads(Q, batch_size)
        K = self._split_heads(K, batch_size)
        V = self._split_heads(V, batch_size)
        
        # Apply attention
        attended, attention_weights = self.attention.forward(Q, K, V, mask)
        
        # Combine heads
        attended = self._combine_heads(attended, batch_size)
        
        # Final linear projection
        output = np.matmul(attended, self.W_o)
        
        return output, attention_weights
    
    def _split_heads(self, x: np.ndarray, batch_size: int) -> np.ndarray:
        """Split last dimension into (num_heads, d_k)."""
        x = x.reshape(batch_size, -1, self.num_heads, self.d_k)
        return x.transpose(0, 2, 1, 3)
    
    def _combine_heads(self, x: np.ndarray, batch_size: int) -> np.ndarray:
        """Combine heads back to (batch, seq_len, d_model)."""
        x = x.transpose(0, 2, 1, 3)
        return x.reshape(batch_size, -1, self.d_model)
    
    @staticmethod
    def _initialize_weights(shape: Tuple[int, ...]) -> np.ndarray:
        """Xavier/Glorot initialization."""
        limit = np.sqrt(6.0 / (shape[0] + shape[1]))
        return np.random.uniform(-limit, limit, shape)


class TransformerLayer:
    """Single transformer layer with attention + feedforward."""
    
    def __init__(self, d_model: int = 256, num_heads: int = 4, d_ff: int = 512, dropout: float = 0.1):
        self.mha = MultiHeadAttention(d_model, num_heads, dropout)
        
        # Feedforward weights
        self.ffn_w1 = np.random.randn(d_model, d_ff) * 0.02
        self.ffn_w2 = np.random.randn(d_ff, d_model) * 0.02
        
        # Layer normalization (simplified)
        self.ln1_scale = np.ones(d_model)
        self.ln1_shift = np.zeros(d_model)
        self.ln2_scale = np.ones(d_model)
        self.ln2_shift = np.zeros(d_model)
    
    def forward(self, x: np.ndarray, mask: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
        """
        Forward pass through transformer layer.
        
        Returns:
            (output, attention_weights)
        """
        # Self-attention with residual
        attn_output, attention_weights = self.mha.forward(x, x, x, mask)
        x = self._layer_norm(x + attn_output, self.ln1_scale, self.ln1_shift)
        
        # Feedforward with residual
        ffn_output = self._feedforward(x)
        x = self._layer_norm(x + ffn_output, self.ln2_scale, self.ln2_shift)
        
        return x, attention_weights
    
    def _feedforward(self, x: np.ndarray) -> np.ndarray:
        """Two-layer feedforward network with ReLU."""
        hidden = np.maximum(0, np.matmul(x, self.ffn_w1))  # ReLU
        return np.matmul(hidden, self.ffn_w2)
    
    def _layer_norm(self, x: np.ndarray, scale: np.ndarray, shift: np.ndarray) -> np.ndarray:
        """Simplified layer normalization."""
        mean = np.mean(x, axis=-1, keepdims=True)
        var = np.var(x, axis=-1, keepdims=True)
        x_norm = (x - mean) / np.sqrt(var + 1e-6)
        return scale * x_norm + shift


class SimpleTextEncoder:
    """Simple token-based text encoder."""
    
    def __init__(self, vocab_size: int = 10000, d_model: int = 256):
        self.vocab_size = vocab_size
        self.d_model = d_model
        # Random embeddings (in production, use proper tokenizer)
        self.embeddings = np.random.randn(vocab_size, d_model) * 0.02
    
    def encode(self, tokens: List[int]) -> np.ndarray:
        """Encode tokens to embeddings."""
        return np.array([self.embeddings[token % self.vocab_size] for token in tokens])


class PsiTransformerAttention:
    """
    Transformer-based attention system for Psi (Fluid) hemisphere.
    
    Replaces/supplements sentiment analysis with deep attention-based
    pattern recognition for the quad-brain architecture.
    """
    
    def __init__(
        self,
        num_layers: int = 3,
        d_model: int = 256,
        num_heads: int = 4,
        d_ff: int = 512,
    ):
        self.num_layers = num_layers
        self.d_model = d_model
        self.num_heads = num_heads
        
        logger.info(f"Initializing Psi Transformer Attention:")
        logger.info(f"  Layers: {num_layers}")
        logger.info(f"  Model dim: {d_model}")
        logger.info(f"  Attention heads: {num_heads}")
        
        # Transformer layers
        self.layers = [
            TransformerLayer(d_model, num_heads, d_ff)
            for _ in range(num_layers)
        ]
        
        # Text encoder
        self.text_encoder = SimpleTextEncoder(d_model=d_model)
        
        # Statistics
        self.total_parameters = self._count_parameters()
        logger.info(f"  Total parameters: ~{self.total_parameters / 1e6:.2f}M")
    
    def _count_parameters(self) -> int:
        """Count total parameters."""
        total = 0
        for layer in self.layers:
            total += layer.mha.W_q.size
            total += layer.mha.W_k.size
            total += layer.mha.W_v.size
            total += layer.mha.W_o.size
            total += layer.ffn_w1.size
            total += layer.ffn_w2.size
        return total
    
    def process(
        self,
        text_tokens: List[int],
        query_context: Optional[str] = None,
    ) -> AttentionAnalysis:
        """
        Process input through transformer and analyze attention patterns.
        
        Args:
            text_tokens: List of token IDs representing the input
            query_context: Optional query string for context
            
        Returns:
            AttentionAnalysis with patterns, focus tokens, and confidence
        """
        # Encode text
        text_emb = self.text_encoder.encode(text_tokens)
        x = text_emb.reshape(1, -1, self.d_model)
        
        # Forward through transformer layers
        all_attention_weights = []
        for layer in self.layers:
            x, attn_weights = layer.forward(x)
            all_attention_weights.append(attn_weights)
        
        # Analyze attention patterns
        analysis = self._analyze_attention(
            all_attention_weights,
            text_tokens,
            query_context,
        )
        
        return analysis
    
    def _analyze_attention(
        self,
        attention_maps: List[np.ndarray],
        tokens: List[int],
        query_context: Optional[str],
    ) -> AttentionAnalysis:
        """
        Analyze attention patterns to detect focus areas and patterns.
        
        This extracts explainable insights from the attention mechanism.
        """
        analysis = AttentionAnalysis()
        analysis.attention_maps = attention_maps
        
        # Get last layer attention (most refined)
        last_attention = attention_maps[-1]  # Shape: (batch, heads, seq, seq)
        
        # Average across heads
        avg_attention = np.mean(last_attention[0], axis=0)  # Shape: (seq, seq)
        
        # Calculate attention entropy (measure of focus vs dispersion)
        # High entropy = dispersed attention (uncertain)
        # Low entropy = focused attention (confident pattern)
        attention_probs = avg_attention + 1e-10  # Avoid log(0)
        attention_probs = attention_probs / np.sum(attention_probs, axis=-1, keepdims=True)
        entropy = -np.sum(attention_probs * np.log(attention_probs), axis=-1)
        analysis.entropy = float(np.mean(entropy))
        
        # Find focus tokens (tokens receiving most attention)
        # Sum attention received by each token
        token_attention = np.sum(avg_attention, axis=0)  # Attention received
        top_k = min(5, len(tokens))
        focus_indices = np.argsort(token_attention)[-top_k:][::-1]
        analysis.focus_tokens = [int(tokens[i]) for i in focus_indices if i < len(tokens)]
        
        # Detect patterns based on attention structure
        analysis.pattern_detected = self._detect_pattern(
            avg_attention,
            analysis.entropy,
            query_context,
        )
        
        # Calculate confidence based on attention sharpness
        max_attention = np.max(avg_attention)
        analysis.confidence = float(max_attention)
        
        # Novelty: high entropy = novel/uncertain input
        analysis.novelty_score = min(1.0, analysis.entropy / 2.0)
        
        # Uncertainty: inverse of confidence
        analysis.uncertainty = 1.0 - analysis.confidence
        
        # Generate hypotheses based on pattern
        analysis.active_hypotheses = self._generate_hypotheses(
            analysis.pattern_detected,
            analysis.confidence,
            query_context,
        )
        
        return analysis
    
    def _detect_pattern(
        self,
        attention_matrix: np.ndarray,
        entropy: float,
        query_context: Optional[str],
    ) -> str:
        """Detect pattern type from attention structure."""
        # Check for diagonal attention (self-referential)
        seq_len = attention_matrix.shape[0]
        diagonal_sum = np.sum([attention_matrix[i, i] for i in range(min(seq_len, 10))])
        diagonal_strength = diagonal_sum / min(seq_len, 10)
        
        # Check for uniform attention (broad focus)
        uniformness = 1.0 - np.std(attention_matrix)
        
        # Check for focused attention on specific tokens
        max_val = np.max(attention_matrix)
        
        # Pattern detection rules
        if max_val > 0.5 and entropy < 1.0:
            return "focused_attention"
        elif diagonal_strength > 0.3:
            return "self_referential"
        elif uniformness > 0.8:
            return "broad_sweep"
        elif entropy > 2.0:
            return "complex_distributed"
        else:
            return "standard_processing"
    
    def _generate_hypotheses(
        self,
        pattern: str,
        confidence: float,
        query_context: Optional[str],
    ) -> List[str]:
        """Generate hypotheses based on detected pattern."""
        hypotheses = []
        
        if pattern == "focused_attention":
            hypotheses.append(f"Strong pattern detected (confidence={confidence:.2f})")
            hypotheses.append("Input has clear focal points")
        elif pattern == "self_referential":
            hypotheses.append("Context-dependent processing detected")
            hypotheses.append("May require prior context for full understanding")
        elif pattern == "broad_sweep":
            hypotheses.append("Distributed attention - broad context considered")
            hypotheses.append("Complex input requiring holistic analysis")
        elif pattern == "complex_distributed":
            hypotheses.append("High entropy input - novel or complex pattern")
            hypotheses.append("Uncertainty elevated, multiple interpretations possible")
        
        if query_context:
            # Add query-specific hypothesis
            if "?" in query_context:
                hypotheses.append("Interrogative pattern - question detected")
            if any(word in query_context.lower() for word in ["why", "how", "explain"]):
                hypotheses.append("Explanatory reasoning required")
        
        return hypotheses
    
    def get_attention_visualization(
        self,
        layer_idx: int = -1,
        head_idx: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Get attention weights for visualization.
        
        Returns attention matrix that can be rendered as heatmap.
        """
        if not self.last_attention_maps or layer_idx >= len(self.last_attention_maps):
            return {"error": "No attention maps available"}
        
        attention = self.last_attention_maps[layer_idx]
        
        if head_idx is not None:
            # Specific head
            attn_matrix = attention[0, head_idx]  # (seq, seq)
        else:
            # Average all heads
            attn_matrix = np.mean(attention[0], axis=0)  # (seq, seq)
        
        return {
            "attention_matrix": attn_matrix.tolist(),
            "shape": attn_matrix.shape,
            "layer": layer_idx,
            "head": head_idx,
            "max_value": float(np.max(attn_matrix)),
            "min_value": float(np.min(attn_matrix)),
        }
    
    # Store attention maps from last forward pass
    last_attention_maps: List[np.ndarray] = []


# Singleton instance
_transformer_instance: Optional[PsiTransformerAttention] = None


def get_psi_transformer(
    num_layers: int = 3,
    d_model: int = 256,
    num_heads: int = 4,
) -> PsiTransformerAttention:
    """Get or create the Psi transformer singleton."""
    global _transformer_instance
    if _transformer_instance is None:
        _transformer_instance = PsiTransformerAttention(
            num_layers=num_layers,
            d_model=d_model,
            num_heads=num_heads,
        )
    return _transformer_instance
