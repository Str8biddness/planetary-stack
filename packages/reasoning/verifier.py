"""
Verifier - Answer Verification and Quality Assurance
"""

from __future__ import annotations

import re
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from .utils import extract_sentences

class VerificationStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    NEEDS_REVISION = "needs_revision"
    UNCERTAIN = "uncertain"

@dataclass
class VerificationIssue:
    issue_id: str
    severity: int  # 0=info, 1=warning, 2=error
    category: str
    description: str
    suggestion: str = ""

@dataclass
class VerificationResult:
    status: VerificationStatus
    score: float
    issues: List[VerificationIssue] = field(default_factory=list)
    revision_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

class AnswerVerifier:
    """
    Verifies synthesized answers for correctness and quality.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self.min_score = self.config.get("min_score", 0.7)
        self.max_answer_length = self.config.get("max_answer_length", 2000)
        self.hallucination_keywords = self.config.get("hallucination_keywords", ["i don't know", "unsure", "as an ai"])
        self.stop_words = self.config.get("stop_words", {
            "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", 
            "of", "to", "in", "with", "for", "on", "at", "by", "from", "it"
        })
    
    def verify(
        self,
        answer: str,
        query: str,
        context: Optional[List[str]] = None,
        revision_count: int = 0
    ) -> VerificationResult:
        if not answer: 
            return VerificationResult(status=VerificationStatus.FAILED, score=0.0)
        
        issues = []
        
        # 1. Factual check (Keyword overlap and grounding)
        overlap = 0.0
        if context:
            answer_words = set(re.findall(r'\w+', answer.lower()))
            context_words = set(re.findall(r'\w+', " ".join(context).lower()))
            
            # Filter stop words for more robust grounding check
            content_answer_words = {w for w in answer_words if w not in self.stop_words}
            content_context_words = {w for w in context_words if w not in self.stop_words}
            
            if content_answer_words:
                overlap = len(content_answer_words & content_context_words) / len(content_answer_words)
            else:
                overlap = 0.0
            
            if overlap < 0.2:
                severity = 2 if overlap > 0.05 else 3 # Extra severe if near zero
                issues.append(VerificationIssue(
                    issue_id="grounding_low", 
                    severity=severity, 
                    category="factual", 
                    description=f"Answer appears disconnected from context (overlap: {overlap:.2f})",
                    suggestion="Ensure answer is grounded in retrieved facts rather than general training data"
                ))
        
        # 2. Hallucination/Safety keyword check
        for kw in self.hallucination_keywords:
            if kw in answer.lower():
                issues.append(VerificationIssue(
                    issue_id="hallucination_kw",
                    severity=1,
                    category="hallucination",
                    description=f"Potential hallucination or refusal found: '{kw}'",
                    suggestion="Review for model refusals or uncertainty markers"
                ))

        # 3. Length check
        if len(answer) > self.max_answer_length:
            issues.append(VerificationIssue(
                issue_id="length_exceeded",
                severity=1,
                category="quality",
                description="Answer length exceeds recommended production threshold",
                suggestion=f"Summarize or truncate to stay below {self.max_answer_length} characters"
            ))
            
        # 4. Consistency check (Internal contradiction)
        # Placeholder for more complex NLP logic
        
        # Calculate final score (production weighting)
        base_score = 1.0
        for issue in issues:
            if issue.severity >= 3: base_score -= 0.7 # Critical failure
            elif issue.severity == 2: base_score -= 0.4
            elif issue.severity == 1: base_score -= 0.15
            
        score = max(0.0, base_score)
        
        if score >= self.min_score:
            status = VerificationStatus.PASSED
        elif score >= 0.4:
            status = VerificationStatus.NEEDS_REVISION
        else:
            status = VerificationStatus.FAILED
        
        return VerificationResult(
            status=status, 
            score=score, 
            issues=issues, 
            revision_count=revision_count,
            metadata={"overlap": overlap if context else None}
        )

    def generate_revision(self, answer: str, result: VerificationResult) -> str:
        """Improve answer based on verification results."""
        if result.status == VerificationStatus.PASSED:
            return answer
        
        revised = answer
        for issue in result.issues:
            if issue.category == "factual":
                revised = f"[VERIFIED CONTEXT NEEDED] {revised}"
        return revised
