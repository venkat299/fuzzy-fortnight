export type ChatTone = 'neutral' | 'positive';

export interface QuestionAnswer {
  question: string;
  answer: string;
  competency: string | null;
  criteria: string[];
  stage: string;
}

export interface SessionMessage {
  id: string;
  speaker: 'Candidate' | 'Interviewer' | 'System';
  content: string;
  tone: ChatTone;
  competency?: string | null;
  targetedCriteria: string[];
  projectAnchor: string;
}

export interface CompetencyScoreState {
  competency: string;
  score: number;
  notes: string[];
  rubricUpdates: string[];
  criterionLevels: Record<string, number>;
}

export interface EvaluatorStateSnapshot {
  summary: string;
  anchors: Record<string, string[]>;
  scores: Record<string, CompetencyScoreState>;
  rubricUpdates: Record<string, string[]>;
}

export interface SessionContextData {
  stage: string;
  interviewId: string;
  candidateName: string;
  jobTitle: string;
  resumeSummary: string;
  autoAnswerEnabled: boolean;
  candidateLevel: number;
  qaHistory: QuestionAnswer[];
  competency: string | null;
  competencyIndex: number;
  questionIndex: number;
  projectAnchor: string;
  competencyProjects: Record<string, string>;
  competencyCriteria: Record<string, string[]>;
  competencyCovered: Record<string, string[]>;
  competencyCriterionLevels: Record<string, Record<string, number>>;
  competencyQuestionCounts: Record<string, number>;
  competencyLowScores: Record<string, number>;
  targetedCriteria: string[];
  evaluator: EvaluatorStateSnapshot;
}
