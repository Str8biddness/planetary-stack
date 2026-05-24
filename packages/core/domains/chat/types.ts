// domains/chat/types.ts
// Chat domain types for Synthesus 3.0

export interface ChatTurn {
  speaker: 'user' | 'system';
  message: string;
  timestamp: Date;
  metadata?: Record<string, any>; // e.g., sentiment, topic tags
}

export interface ChatWorldState {
  domain: string;
  conversationId: string;
  history: ChatTurn[];
  inferredGoals: string[]; // e.g., ['clarify question', 'provide answer']
  topics: string[]; // bag-of-words or tags
  flags: {
    confusion: boolean;
    safety: boolean;
    frustration: boolean;
  };
  unresolvedQuestions: number;
  turnCount: number;
  timestamp: Date;
}

export interface ChatAction {
  type: 'ask_clarification' | 'answer_question' | 'summarize' | 'propose_plan' | 'escalate' | 'chitchat';
  target?: string; // e.g., specific question or topic
  content: string; // the response text
  description: string;
}

export interface ChatHistory {
  turns: ChatTurn[];
  summary?: string;
}

export interface ChatFocusTarget {
  id: string;
  type: 'topic' | 'goal' | 'question';
  importance: number; // 0-1
  urgency: number; // 0-1
  lastMentioned: Date;
}
