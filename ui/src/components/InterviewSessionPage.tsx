import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { ArrowLeft, Loader2, Pause, Play, Send, Square } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "./ui/card";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Textarea } from "./ui/textarea";
import { Label } from "./ui/label";
import { Progress } from "./ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/table";
import { ScrollArea } from "./ui/scroll-area";
import { Slider } from "./ui/slider";
import type { InterviewAssignment } from "./InterviewerOverview";

interface InterviewSessionPageProps {
  assignment: InterviewAssignment;
  onBackToDashboard: () => void;
  autoStart?: boolean;
  onAutoStartConsumed?: () => void;
}

interface ChatMessage {
  id: string;
  speaker: "Candidate" | "Interviewer" | "System";
  content: string;
  tone: "neutral" | "positive";
  pending?: boolean;
}

interface CriterionRow {
  competency: string;
  criterion: string;
  weight: number;
  achievedLevel: 1 | 2 | 3 | 4 | 5;
  rawScore: number;
}

interface CompetencySummary {
  competency: string;
  score: number;
}

type StageLiteral = "warmup" | "competency" | "wrapup" | "complete";

type EventType =
  | "stage_entered"
  | "question"
  | "answer"
  | "evaluation"
  | "hint"
  | "follow_up"
  | "checkpoint";

interface PersonaSettings {
  name: string;
  probingStyle: string;
  hintStyle: string;
  encouragement: string;
}

interface CandidateProfileSummary {
  candidateName: string;
  resumeSummary: string;
  experienceYears: string;
  highlightedExperiences: string[];
}

interface SessionEvent {
  eventId: number;
  createdAt: string;
  stage: StageLiteral;
  competency: string | null;
  eventType: EventType;
  payload: Record<string, unknown>;
}

interface SessionCriterion {
  criterion: string;
  weight: number;
  latestScore: number;
  rationale: string;
}

interface SessionCompetencyState {
  competency: string;
  totalScore: number;
  rubricFilled: boolean;
  criteria: SessionCriterion[];
}

interface SessionMeta {
  persona: PersonaSettings;
  profile: CandidateProfileSummary;
}

interface QuestionMetadata {
  stage: StageLiteral;
  competency: string | null;
  reasoning: string;
  escalation: string;
  followUpPrompt: string;
}

interface QuestionPayload {
  content: string;
  metadata: QuestionMetadata;
}

interface EvaluationCriterionPayload {
  criterion: string;
  score: number;
  weight: number;
  rationale: string;
}

interface EvaluationPayload {
  summary: string;
  totalScore: number;
  rubricFilled: boolean;
  criterionScores: EvaluationCriterionPayload[];
  hints: string[];
  followUpNeeded: boolean;
}

interface InteractiveSessionStart {
  sessionId: string;
  stage: StageLiteral;
  persona: PersonaSettings;
  profile: CandidateProfileSummary;
  question: QuestionPayload | null;
  events: SessionEvent[];
  competencies: SessionCompetencyState[];
  overallScore: number;
  questionsAsked: number;
  elapsedMs: number;
}

interface InteractiveTurnSnapshot {
  stage: StageLiteral;
  question: QuestionPayload | null;
  evaluation: EvaluationPayload | null;
  events: SessionEvent[];
  competencies: SessionCompetencyState[];
  overallScore: number;
  questionsAsked: number;
  elapsedMs: number;
  completed: boolean;
}

const STAGE_LABELS: Record<StageLiteral, string> = {
  warmup: "Warmup",
  competency: "Competency loop",
  wrapup: "Wrap-up",
  complete: "Complete",
};

const STAGE_PROGRESS: Record<StageLiteral, number> = {
  warmup: 10,
  competency: 60,
  wrapup: 90,
  complete: 100,
};

const QUESTION_ESCALATIONS = new Set([
  "broad",
  "why",
  "how",
  "challenge",
  "hint",
  "edge",
]);

const generateId = () =>
  typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2);

const formatElapsed = (ms: number) => {
  if (!Number.isFinite(ms) || ms <= 0) {
    return "00:00";
  }
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60)
    .toString()
    .padStart(2, "0");
  const seconds = (totalSeconds % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
};

const toDisplayWeight = (weight: number) => {
  if (!Number.isFinite(weight)) {
    return 0;
  }
  return weight <= 1 ? weight * 100 : weight;
};

const toLevel = (value: number): 1 | 2 | 3 | 4 | 5 => {
  const safe = Number.isFinite(value) ? value : 0;
  const rounded = Math.round(safe);
  const clamped = Math.min(5, Math.max(1, rounded || 1));
  return clamped as 1 | 2 | 3 | 4 | 5;
};

const normalizePersona = (input: unknown): PersonaSettings => {
  const raw = (input && typeof input === "object"
    ? input
    : {}) as Record<string, unknown>;
  return {
    name: String(raw.name ?? ""),
    probingStyle: String(raw.probing_style ?? raw.probingStyle ?? ""),
    hintStyle: String(raw.hint_style ?? raw.hintStyle ?? ""),
    encouragement: String(raw.encouragement ?? ""),
  };
};

const normalizeProfile = (input: unknown): CandidateProfileSummary => {
  const raw = (input && typeof input === "object"
    ? input
    : {}) as Record<string, unknown>;
  const experiencesRaw = Array.isArray(raw.highlighted_experiences)
    ? raw.highlighted_experiences
    : Array.isArray(raw.highlightedExperiences)
      ? raw.highlightedExperiences
      : [];
  const experiences = experiencesRaw
    .map((item) => String(item ?? ""))
    .filter((entry) => entry.trim().length > 0);
  return {
    candidateName: String(raw.candidate_name ?? raw.candidateName ?? ""),
    resumeSummary: String(raw.resume_summary ?? raw.resumeSummary ?? ""),
    experienceYears: String(raw.experience_years ?? raw.experienceYears ?? ""),
    highlightedExperiences: experiences,
  };
};

const normalizeStage = (stage: unknown): StageLiteral => {
  const value = String(stage ?? "");
  if (
    (["warmup", "competency", "wrapup", "complete"] as const).includes(
      value as StageLiteral,
    )
  ) {
    return value as StageLiteral;
  }
  return "warmup";
};

const normalizeEvents = (payload: unknown): SessionEvent[] => {
  if (!Array.isArray(payload)) {
    return [];
  }
  const events: SessionEvent[] = [];
  payload.forEach((item) => {
    if (!item || typeof item !== "object") {
      return;
    }
    const raw = item as Record<string, unknown>;
    const eventId = Number(raw.event_id ?? raw.eventId ?? Number.NaN);
    if (!Number.isFinite(eventId)) {
      return;
    }
    const stage = normalizeStage(raw.stage);
    const eventType = String(
      raw.event_type ?? raw.eventType ?? "",
    ) as EventType;
    if (
      !(
        [
          "stage_entered",
          "question",
          "answer",
          "evaluation",
          "hint",
          "follow_up",
          "checkpoint",
        ] as const
      ).includes(eventType)
    ) {
      return;
    }
    const competencyRaw = raw.competency;
    const competency =
      competencyRaw === null || competencyRaw === undefined
        ? null
        : String(competencyRaw);
    const createdAt = String(raw.created_at ?? raw.createdAt ?? "");
    const payloadValue =
      raw.payload && typeof raw.payload === "object"
        ? (raw.payload as Record<string, unknown>)
        : {};
    events.push({
      eventId,
      createdAt,
      stage,
      competency,
      eventType,
      payload: payloadValue,
    });
  });
  return events.sort((a, b) => a.eventId - b.eventId);
};

const normalizeCompetencies = (payload: unknown): SessionCompetencyState[] => {
  if (!Array.isArray(payload)) {
    return [];
  }
  const states: SessionCompetencyState[] = [];
  payload.forEach((item) => {
    if (!item || typeof item !== "object") {
      return;
    }
    const raw = item as Record<string, unknown>;
    const name = String(raw.competency ?? raw.name ?? "");
    if (!name) {
      return;
    }
    const criteriaRaw = Array.isArray(raw.criteria) ? raw.criteria : [];
    const criteria: SessionCriterion[] = criteriaRaw
      .map((criterionRaw) => {
        if (!criterionRaw || typeof criterionRaw !== "object") {
          return null;
        }
        const criterion = criterionRaw as Record<string, unknown>;
        const label = String(criterion.criterion ?? "");
        if (!label) {
          return null;
        }
        return {
          criterion: label,
          weight: Number(criterion.weight ?? 0),
          latestScore: Number(criterion.latest_score ?? criterion.latestScore ?? 0),
          rationale: String(criterion.rationale ?? ""),
        };
      })
      .filter((entry): entry is SessionCriterion => Boolean(entry));
    states.push({
      competency: name,
      totalScore: Number(raw.total_score ?? raw.totalScore ?? 0),
      rubricFilled: Boolean(raw.rubric_filled ?? raw.rubricFilled ?? false),
      criteria,
    });
  });
  return states;
};

const normalizeQuestion = (payload: unknown): QuestionPayload | null => {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const raw = payload as Record<string, unknown>;
  const content = String(raw.content ?? raw.question ?? "");
  if (!content) {
    return null;
  }
  const metaRaw = raw.metadata;
  const meta =
    metaRaw && typeof metaRaw === "object"
      ? (metaRaw as Record<string, unknown>)
      : {};
  const stage = normalizeStage(meta.stage);
  const competencyRaw = meta.competency;
  const competency =
    competencyRaw === null || competencyRaw === undefined
      ? null
      : String(competencyRaw);
  const reasoning = String(meta.reasoning ?? "");
  const escalation = String(meta.escalation ?? "").toLowerCase();
  const followUp = String(
    meta.follow_up_prompt ?? meta.followUpPrompt ?? "",
  );
  return {
    content,
    metadata: {
      stage,
      competency,
      reasoning,
      escalation: QUESTION_ESCALATIONS.has(escalation)
        ? escalation
        : "broad",
      followUpPrompt: followUp,
    },
  };
};

const normalizeEvaluation = (payload: unknown): EvaluationPayload | null => {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const raw = payload as Record<string, unknown>;
  const summary = String(raw.summary ?? "");
  const totalScore = Number(raw.total_score ?? raw.totalScore ?? 0);
  const rubricFilled = Boolean(raw.rubric_filled ?? raw.rubricFilled ?? false);
  const followUpNeeded = Boolean(
    raw.follow_up_needed ?? raw.followUpNeeded ?? false,
  );
  const hintsRaw = Array.isArray(raw.hints) ? raw.hints : [];
  const hints = hintsRaw
    .map((item) => String(item ?? "").trim())
    .filter((item) => item.length > 0);
  const criteriaRaw = Array.isArray(raw.criterion_scores)
    ? raw.criterion_scores
    : Array.isArray(raw.criterionScores)
      ? raw.criterionScores
      : [];
  const criterionScores: EvaluationCriterionPayload[] = criteriaRaw
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const entry = item as Record<string, unknown>;
      const criterion = String(entry.criterion ?? "");
      if (!criterion) {
        return null;
      }
      return {
        criterion,
        score: Number(entry.score ?? 0),
        weight: Number(entry.weight ?? 0),
        rationale: String(entry.rationale ?? ""),
      };
    })
    .filter((entry): entry is EvaluationCriterionPayload => Boolean(entry));
  return {
    summary,
    totalScore,
    rubricFilled,
    criterionScores,
    hints,
    followUpNeeded,
  };
};

const normalizeStartResponse = (payload: unknown): InteractiveSessionStart | null => {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const data = payload as Record<string, unknown>;
  const sessionId = String(data.session_id ?? data.sessionId ?? "");
  if (!sessionId) {
    return null;
  }
  return {
    sessionId,
    stage: normalizeStage(data.stage),
    persona: normalizePersona(data.persona),
    profile: normalizeProfile(data.profile),
    question: normalizeQuestion(data.question),
    events: normalizeEvents(data.events),
    competencies: normalizeCompetencies(data.competencies),
    overallScore: Number(data.overall_score ?? data.overallScore ?? 0),
    questionsAsked: Number(data.questions_asked ?? data.questionsAsked ?? 0),
    elapsedMs: Number(data.elapsed_ms ?? data.elapsedMs ?? 0),
  };
};

const normalizeTurnResponse = (payload: unknown): InteractiveTurnSnapshot | null => {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const data = payload as Record<string, unknown>;
  return {
    stage: normalizeStage(data.stage),
    question: normalizeQuestion(data.question),
    evaluation: normalizeEvaluation(data.evaluation),
    events: normalizeEvents(data.events),
    competencies: normalizeCompetencies(data.competencies),
    overallScore: Number(data.overall_score ?? data.overallScore ?? 0),
    questionsAsked: Number(data.questions_asked ?? data.questionsAsked ?? 0),
    elapsedMs: Number(data.elapsed_ms ?? data.elapsedMs ?? 0),
    completed: Boolean(data.completed),
  };
};

const deriveActiveCompetency = (events: SessionEvent[]): string | null => {
  let result: string | null = null;
  events.forEach((event) => {
    if (event.eventType === "stage_entered") {
      if (event.stage === "competency" && event.competency) {
        result = event.competency;
      } else if (event.stage !== "competency") {
        result = "—";
      }
    } else if (event.eventType === "question" && event.competency) {
      result = event.competency;
    }
  });
  return result;
};

const translateEvents = (events: SessionEvent[]): ChatMessage[] => {
  const messages: ChatMessage[] = [];
  events.forEach((event) => {
    if (event.eventType === "stage_entered") {
      let content = "";
      if (event.stage === "competency" && event.competency) {
        content = `Shifting focus to ${event.competency}.`;
      } else if (event.stage === "wrapup") {
        content = "Moving into wrap-up.";
      } else if (event.stage === "warmup") {
        content = "Beginning warmup.";
      }
      if (content) {
        messages.push({
          id: generateId(),
          speaker: "System",
          content,
          tone: "neutral",
        });
      }
      return;
    }
    if (event.eventType === "question") {
      const question = String(event.payload.question ?? event.payload.content ?? "").trim();
      if (question) {
        messages.push({
          id: generateId(),
          speaker: "Interviewer",
          content: question,
          tone: "neutral",
        });
      }
      return;
    }
    if (event.eventType === "answer") {
      const answer = String(event.payload.answer ?? "").trim();
      if (answer) {
        messages.push({
          id: generateId(),
          speaker: "Candidate",
          content: answer,
          tone: "positive",
        });
      }
      return;
    }
    if (event.eventType === "hint") {
      const hint = String(event.payload.hint ?? "").trim();
      if (hint) {
        messages.push({
          id: generateId(),
          speaker: "System",
          content: `Hint: ${hint}`,
          tone: "neutral",
        });
      }
      return;
    }
    if (event.eventType === "follow_up") {
      const message = String(
        event.payload.message ?? "Evaluator suggests a follow-up.",
      ).trim();
      messages.push({
        id: generateId(),
        speaker: "System",
        content: message,
        tone: "neutral",
      });
      return;
    }
    if (event.eventType === "checkpoint") {
      const savedAt = String(event.payload.saved_at ?? event.payload.savedAt ?? "");
      const message = savedAt
        ? `Checkpoint saved at ${savedAt}.`
        : "Checkpoint saved.";
      messages.push({
        id: generateId(),
        speaker: "System",
        content: message,
        tone: "neutral",
      });
      return;
    }
    if (event.eventType === "evaluation") {
      const summary = String(event.payload.summary ?? "").trim();
      if (summary) {
        messages.push({
          id: generateId(),
          speaker: "System",
          content: summary,
          tone: "neutral",
        });
      }
      const hintsRaw = Array.isArray(event.payload.hints)
        ? event.payload.hints
        : [];
      hintsRaw
        .map((hint) => String(hint ?? "").trim())
        .filter((hint) => hint.length > 0)
        .forEach((hint) => {
          messages.push({
            id: generateId(),
            speaker: "System",
            content: `Coaching hint: ${hint}`,
            tone: "neutral",
          });
        });
    }
  });
  return messages;
};

export function InterviewSessionPage({
  assignment,
  onBackToDashboard,
  autoStart = false,
  onAutoStartConsumed,
}: InterviewSessionPageProps) {
  const [autoGenerate, setAutoGenerate] = useState(1);
  const [autoSend, setAutoSend] = useState(0);
  const [sessionMeta, setSessionMeta] = useState<SessionMeta | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [displayedMessages, setDisplayedMessages] = useState<ChatMessage[]>([]);
  const [criterionRows, setCriterionRows] = useState<CriterionRow[]>([]);
  const [competencyScores, setCompetencyScores] = useState<CompetencySummary[]>([]);
  const [stageProgress, setStageProgress] = useState(0);
  const [stageName, setStageName] = useState<string>(STAGE_LABELS.warmup);
  const [activeCompetency, setActiveCompetency] = useState<string>("—");
  const [questionsAsked, setQuestionsAsked] = useState(0);
  const [overallScore, setOverallScore] = useState(0);
  const [status, setStatus] = useState<"idle" | "running" | "paused" | "stopped" | "complete">("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isFetchingStart, setIsFetchingStart] = useState(false);
  const [isSendingTurn, setIsSendingTurn] = useState(false);
  const [draftAnswer, setDraftAnswer] = useState("");
  const [elapsedMs, setElapsedMs] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const competencyOrderRef = useRef<string[]>([]);
  const startTimeRef = useRef<number>(0);
  const elapsedAccumulatorRef = useRef<number>(0);
  const [timerRunning, setTimerRunning] = useState(false);

  const timeElapsed = useMemo(() => formatElapsed(elapsedMs), [elapsedMs]);

  const appendMessages = useCallback((incoming: ChatMessage[]) => {
    if (incoming.length === 0) {
      return;
    }
    setDisplayedMessages((previous) => {
      const next = [...previous];
      incoming.forEach((message) => {
        if (message.speaker === "Candidate") {
          const index = next.findIndex(
            (item) =>
              item.pending &&
              item.speaker === "Candidate" &&
              item.content === message.content,
          );
          if (index !== -1) {
            next[index] = { ...message, pending: false };
            return;
          }
          const fallbackIndex = next.findIndex(
            (item) => item.pending && item.speaker === "Candidate",
          );
          if (fallbackIndex !== -1) {
            next[fallbackIndex] = { ...message, pending: false };
            return;
          }
        }
        next.push({ ...message, pending: false });
      });
      return next;
    });
  }, []);

  const appendQuestionMessage = useCallback((question: QuestionPayload | null) => {
    if (!question || !question.content?.trim()) {
      return;
    }
    const content = question.content.trim();
    setDisplayedMessages((previous) => {
      const exists = previous.some(
        (item) => item.speaker === "Interviewer" && item.content === content,
      );
      if (exists) {
        return previous;
      }
      return [
        ...previous,
        {
          id: generateId(),
          speaker: "Interviewer",
          content,
          tone: "neutral",
          pending: false,
        },
      ];
    });
  }, []);

  const updateElapsed = useCallback(
    (ms: number) => {
      const safe = Math.max(0, Math.floor(ms));
      elapsedAccumulatorRef.current = safe;
      setElapsedMs(safe);
      if (timerRunning) {
        startTimeRef.current = Date.now();
      }
    },
    [timerRunning],
  );

  const beginTimer = useCallback(() => {
    elapsedAccumulatorRef.current = 0;
    startTimeRef.current = Date.now();
    setElapsedMs(0);
    setTimerRunning(true);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [displayedMessages.length]);

  const pauseTimer = useCallback(() => {
    if (!timerRunning) {
      return;
    }
    elapsedAccumulatorRef.current += Date.now() - startTimeRef.current;
    setElapsedMs(elapsedAccumulatorRef.current);
    setTimerRunning(false);
  }, [timerRunning]);

  const resumeTimer = useCallback(() => {
    startTimeRef.current = Date.now();
    setTimerRunning(true);
  }, []);

  const resetTimer = useCallback(() => {
    elapsedAccumulatorRef.current = 0;
    setElapsedMs(0);
    setTimerRunning(false);
  }, []);

  useEffect(() => {
    if (!timerRunning) {
      return;
    }
    const interval = window.setInterval(() => {
      const elapsed =
        elapsedAccumulatorRef.current + (Date.now() - startTimeRef.current);
      setElapsedMs(elapsed);
    }, 1000);
    return () => {
      window.clearInterval(interval);
    };
  }, [timerRunning]);

  const applyStage = useCallback((stage: StageLiteral) => {
    setStageName(STAGE_LABELS[stage] ?? STAGE_LABELS.warmup);
    setStageProgress(STAGE_PROGRESS[stage] ?? 0);
    if (stage === "wrapup" || stage === "complete" || stage === "warmup") {
      setActiveCompetency("—");
    }
  }, []);

const applyCompetencySnapshot = useCallback((snapshot: SessionCompetencyState[]) => {
    competencyOrderRef.current = snapshot.map((entry) => entry.competency);
    const order = new Map(
      competencyOrderRef.current.map((name, index) => [name, index]),
    );
    const rows: CriterionRow[] = [];
    snapshot.forEach((competency) => {
      competency.criteria.forEach((criterion) => {
        const weightDisplay = Number(toDisplayWeight(criterion.weight).toFixed(1));
        const rawScore = Number(
          (criterion.latestScore * (weightDisplay / 100)).toFixed(2),
        );
        rows.push({
          competency: competency.competency,
          criterion: criterion.criterion,
          weight: weightDisplay,
          achievedLevel: toLevel(criterion.latestScore),
          rawScore,
        });
      });
    });
    rows.sort((a, b) => {
      const indexA = order.get(a.competency) ?? Number.MAX_SAFE_INTEGER;
      const indexB = order.get(b.competency) ?? Number.MAX_SAFE_INTEGER;
      if (indexA !== indexB) {
        return indexA - indexB;
      }
      return a.criterion.localeCompare(b.criterion);
    });
    setCriterionRows(rows);
    const summaries = snapshot.map((entry) => ({
      competency: entry.competency,
      score: Number(entry.totalScore.toFixed(1)),
    }));
    setCompetencyScores(summaries);
  }, []);

  const applyEvents = useCallback(
    (incoming: SessionEvent[], options?: { reset?: boolean }) => {
      if (options?.reset) {
        const sorted = [...incoming].sort((a, b) => a.eventId - b.eventId);
        setEvents(sorted);
        const messages = translateEvents(sorted).map((message) => ({
          ...message,
          pending: false,
        }));
        setDisplayedMessages(messages);
        const active = deriveActiveCompetency(sorted);
        if (active !== null) {
          setActiveCompetency(active);
        }
        return;
      }
      if (incoming.length === 0) {
        return;
      }
      const sorted = [...incoming].sort((a, b) => a.eventId - b.eventId);
      let appended: SessionEvent[] = [];
      setEvents((previous) => {
        const existing = new Set(previous.map((event) => event.eventId));
        appended = sorted.filter((event) => !existing.has(event.eventId));
        if (!appended.length) {
          return previous;
        }
        return [...previous, ...appended].sort((a, b) => a.eventId - b.eventId);
      });
      if (!appended.length) {
        return;
      }
      const messages = translateEvents(appended);
      appendMessages(messages);
      const active = deriveActiveCompetency(appended);
      if (active !== null) {
        setActiveCompetency(active);
      }
    },
    [appendMessages],
  );

  const applyStartSnapshot = useCallback(
    (snapshot: InteractiveSessionStart) => {
      setSessionMeta({
        persona: snapshot.persona,
        profile: snapshot.profile,
      });
      setSessionId(snapshot.sessionId);
      setStatus(snapshot.stage === "complete" ? "complete" : "running");
      setQuestionsAsked(snapshot.questionsAsked);
      applyStage(snapshot.stage);
      applyCompetencySnapshot(snapshot.competencies);
      setOverallScore(Number(snapshot.overallScore.toFixed(1)));
      updateElapsed(snapshot.elapsedMs);
      applyEvents(snapshot.events, { reset: true });
      appendQuestionMessage(snapshot.question);
      setErrorMessage(null);
      setDraftAnswer("");
      if (snapshot.stage === "complete") {
        resetTimer();
        setStatus("complete");
      } else {
        resetTimer();
        beginTimer();
      }
    },
    [appendQuestionMessage, applyCompetencySnapshot, applyEvents, applyStage, beginTimer, resetTimer, updateElapsed],
  );

  const applyTurnSnapshot = useCallback(
    (snapshot: InteractiveTurnSnapshot) => {
      applyStage(snapshot.stage);
      applyCompetencySnapshot(snapshot.competencies);
      applyEvents(snapshot.events);
      appendQuestionMessage(snapshot.question);
      setQuestionsAsked(snapshot.questionsAsked);
      setOverallScore(Number(snapshot.overallScore.toFixed(1)));
      updateElapsed(snapshot.elapsedMs);
      if (snapshot.completed || snapshot.stage === "complete") {
        setStatus("complete");
        pauseTimer();
        setActiveCompetency("—");
      } else if (status !== "paused") {
        setStatus("running");
      }
    },
    [appendQuestionMessage, applyCompetencySnapshot, applyEvents, applyStage, pauseTimer, status, updateElapsed],
  );

  const startSession = useCallback(async () => {
    if (isFetchingStart || status === "running") {
      return;
    }
    setIsFetchingStart(true);
    setErrorMessage(null);
    try {
      const response = await fetch("/api/interview-sessions/start", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          interview_id: assignment.interviewId,
          candidate_id: assignment.candidateId,
        }),
      });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null);
        const detail =
          errorPayload && typeof errorPayload.detail === "string"
            ? errorPayload.detail
            : "Failed to start interview session.";
        throw new Error(detail);
      }
      const payload = await response.json();
      const normalized = normalizeStartResponse(payload);
      if (!normalized) {
        throw new Error("Invalid session response.");
      }
      applyStartSnapshot(normalized);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to start interview session.";
      setErrorMessage(message);
      setSessionMeta(null);
      setSessionId(null);
      setEvents([]);
      setDisplayedMessages([]);
      setCriterionRows([]);
      setCompetencyScores([]);
      setStageProgress(0);
      setStageName(STAGE_LABELS.warmup);
      setActiveCompetency("—");
      setQuestionsAsked(0);
      setOverallScore(0);
      setStatus("idle");
      resetTimer();
    } finally {
      setIsFetchingStart(false);
    }
  }, [
    applyStartSnapshot,
    assignment.candidateId,
    assignment.interviewId,
    isFetchingStart,
    resetTimer,
    status,
  ]);

  const submitTurn = useCallback(async (answerText: string) => {
    const currentSessionId = sessionId;
    if (!currentSessionId || !answerText) {
      return;
    }
    setIsSendingTurn(true);
    setErrorMessage(null);
    try {
      const response = await fetch("/api/interview-sessions/turn", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          session_id: currentSessionId,
          answer: answerText,
          auto_send: Boolean(autoSend),
          auto_generate: Boolean(autoGenerate),
        }),
      });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null);
        const detail =
          errorPayload && typeof errorPayload.detail === "string"
            ? errorPayload.detail
            : "Failed to process answer.";
        throw new Error(detail);
      }
      const payload = await response.json();
      const normalized = normalizeTurnResponse(payload);
      if (!normalized) {
        throw new Error("Invalid turn response.");
      }
      applyTurnSnapshot(normalized);
      setDisplayedMessages((previous) =>
        previous.map((item) =>
          item.pending &&
          item.speaker === "Candidate" &&
          item.content === answerText
            ? { ...item, pending: false }
            : item,
        ),
      );
      setDraftAnswer("");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to process answer.";
      setErrorMessage(message);
      setDisplayedMessages((previous) => {
        const next = [...previous];
        const index = next.findIndex(
          (item) =>
            item.pending &&
            item.speaker === "Candidate" &&
            item.content === answerText,
        );
        if (index !== -1) {
          next.splice(index, 1);
        }
        return next;
      });
      setDraftAnswer(answerText);
    } finally {
      setIsSendingTurn(false);
    }
  }, [applyTurnSnapshot, autoGenerate, autoSend, sessionId]);

  useEffect(() => {
    if (!autoStart) {
      return;
    }
    if (status !== "idle" || isFetchingStart) {
      return;
    }
    void startSession();
    onAutoStartConsumed?.();
  }, [autoStart, isFetchingStart, onAutoStartConsumed, startSession, status]);

  const handleStart = useCallback(() => {
    if (status === "paused") {
      setStatus("running");
      resumeTimer();
      return;
    }
    if (status === "running" || isFetchingStart) {
      return;
    }
    void startSession();
  }, [isFetchingStart, resumeTimer, startSession, status]);

  const handlePause = useCallback(() => {
    if (status !== "running") {
      return;
    }
    pauseTimer();
    setStatus("paused");
  }, [pauseTimer, status]);

  const handleStop = useCallback(() => {
    setSessionMeta(null);
    setSessionId(null);
    setEvents([]);
    setDisplayedMessages([]);
    setCriterionRows([]);
    setCompetencyScores([]);
    setStageProgress(0);
    setStageName(STAGE_LABELS.warmup);
    setActiveCompetency("—");
    setQuestionsAsked(0);
    setOverallScore(0);
    setStatus("stopped");
    setErrorMessage(null);
    setDraftAnswer("");
    resetTimer();
  }, [resetTimer]);

  const handleSend = useCallback(() => {
    const answer = draftAnswer.trim();
    if (!sessionId || !answer || isSendingTurn) {
      return;
    }
    const pendingMessage: ChatMessage = {
      id: generateId(),
      speaker: "Candidate",
      content: answer,
      tone: "positive",
      pending: true,
    };
    setDisplayedMessages((previous) => [...previous, pendingMessage]);
    setDraftAnswer("");
    void submitTurn(answer);
  }, [draftAnswer, isSendingTurn, sessionId, submitTurn]);

  const isPreparingSession = isFetchingStart && status === "idle";
  const stageDisplayName = isPreparingSession ? "Preparing session…" : stageName;
  const startButtonLabel = status === "paused" ? "Resume" : "Start";
  const startButtonText = isFetchingStart ? "Starting..." : startButtonLabel;
  const isStartDisabled = isFetchingStart || status === "running";
  const isPauseDisabled = status !== "running";
  const isStopDisabled = status === "idle";
  const isSendDisabled =
    !sessionId ||
    status !== "running" ||
    isSendingTurn ||
    draftAnswer.trim().length === 0;

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <div className="mx-auto flex max-w-6xl flex-col gap-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <Button
            type="button"
            variant="ghost"
            className="inline-flex items-center gap-2"
            onClick={onBackToDashboard}
          >
            <ArrowLeft className="h-4 w-4" />
            Back to dashboard
          </Button>
          <div className="text-right text-sm text-muted-foreground">
            <div className="text-xs uppercase tracking-wide text-slate-500">
              Active interview
            </div>
            <div className="text-base font-semibold text-slate-900">
              {assignment.jobTitle}
            </div>
            <div className="text-sm text-slate-700">
              {assignment.candidateName}
            </div>
            <div className="font-mono text-xs text-muted-foreground">
              {assignment.interviewId}
            </div>
            {sessionMeta && (
              <div className="pt-1 text-xs text-slate-500">
                Persona: {sessionMeta.persona.name}
              </div>
            )}
          </div>
        </div>

        <Card className="overflow-hidden">
          <CardHeader>
            <CardTitle>Interview session</CardTitle>
            <CardDescription>
              Monitor the conversation, capture notes, and drive the candidate
              experience.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {errorMessage && (
              <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                {errorMessage}
              </div>
            )}
            <div className="rounded-lg border bg-background p-4">
              <ScrollArea className="h-[25rem] pr-4">
                <div className="flex flex-col gap-4">
                  {displayedMessages.length > 0 ? (
                    <>
                      {displayedMessages.map((message) => {
                        const baseClass =
                          message.speaker === "Candidate"
                            ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                            : message.speaker === "Interviewer"
                              ? "border-sky-200 bg-sky-50 text-sky-900"
                              : "border-slate-200 bg-slate-50 text-slate-700";
                        const pendingClass = message.pending ? "opacity-70" : "";
                        return (
                          <div
                            key={message.id}
                            className={`rounded-lg border p-3 text-sm leading-relaxed ${baseClass} ${pendingClass}`}
                          >
                            <div className="mb-2 flex items-center justify-between gap-2">
                              <span className="font-medium">{message.speaker}</span>
                              {message.pending ? (
                                <Badge variant="outline" className="flex items-center gap-1">
                                  <Loader2 className="h-3 w-3 animate-spin" />
                                  Sending…
                                </Badge>
                              ) : (
                                <Badge
                                  variant={
                                    message.tone === "positive" ? "secondary" : "outline"
                                  }
                                >
                                  {message.tone}
                                </Badge>
                              )}
                            </div>
                            <p>{message.content}</p>
                          </div>
                        );
                      })}
                      <div ref={messagesEndRef} />
                    </>
                  ) : isPreparingSession ? (
                    <div className="rounded-md border border-dashed border-sky-200 bg-sky-50 p-6 text-center text-sm text-sky-700">
                      Preparing the simulated interview… this may take up to a minute
                      while the AI generates the session.
                    </div>
                  ) : (
                    <div className="rounded-md border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-muted-foreground">
                      Session idle — press Start to launch the interview.
                    </div>
                  )}
                </div>
              </ScrollArea>
            </div>

            <div className="flex flex-col gap-3 lg:flex-row">
              <Textarea
                placeholder="Draft prompts, capture coaching notes, or summarize key evidence..."
                className="flex-1"
                rows={4}
                value={draftAnswer}
                onChange={(event) => setDraftAnswer(event.target.value)}
                disabled={!sessionId || status === "complete"}
              />
              <Button
                type="button"
                className="lg:h-full lg:min-w-[9rem]"
                variant="secondary"
                onClick={handleSend}
                disabled={isSendDisabled}
              >
                <Send className="h-4 w-4" />
                {isSendingTurn ? "Sending..." : "Send"}
              </Button>
            </div>

            <div className="flex flex-wrap items-center justify-end gap-3">
              <Button
                type="button"
                size="lg"
                className="min-w-[9rem]"
                onClick={handleStart}
                disabled={isStartDisabled}
              >
                <Play className="h-4 w-4" />
                {startButtonText}
              </Button>
              <Button
                type="button"
                size="lg"
                variant="secondary"
                className="min-w-[9rem]"
                onClick={handlePause}
                disabled={isPauseDisabled}
              >
                <Pause className="h-4 w-4" />
                Pause
              </Button>
              <Button
                type="button"
                size="lg"
                variant="destructive"
                className="min-w-[9rem]"
                onClick={handleStop}
                disabled={isStopDisabled}
              >
                <Square className="h-4 w-4" />
                Stop
              </Button>
              <div className="flex items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                <div className="space-y-1">
                  <Label className="text-xs font-medium text-slate-700">
                    Auto-generate
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    {autoGenerate === 1 ? "On" : "Off"}
                  </p>
                </div>
                <Slider
                  className="w-24"
                  min={0}
                  max={1}
                  step={1}
                  value={[autoGenerate]}
                  onValueChange={(value) => setAutoGenerate(value[0] ?? 0)}
                />
              </div>
              <div className="flex items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                <div className="space-y-1">
                  <Label className="text-xs font-medium text-slate-700">
                    Auto-send
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    {autoSend === 1 ? "On" : "Off"}
                  </p>
                </div>
                <Slider
                  className="w-24"
                  min={0}
                  max={1}
                  step={1}
                  value={[autoSend]}
                  onValueChange={(value) => setAutoSend(value[0] ?? 0)}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Live progress</CardTitle>
            <CardDescription>
              Track the flow of the interview and current focus area.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Progress value={stageProgress} className="h-3" />
            <div className="flex gap-4 overflow-x-auto pb-1">
              {[
                {
                  label: "Stage",
                  value: stageDisplayName,
                },
                {
                  label: "Competency",
                  value: activeCompetency,
                },
                {
                  label: "Questions asked",
                  value: questionsAsked.toString(),
                },
                {
                  label: "Time elapsed",
                  value: timeElapsed,
                },
              ].map((item) => (
                <div
                  key={item.label}
                  className="min-w-[12rem] rounded-md border border-slate-200 bg-slate-50 p-3"
                >
                  <p className="text-xs uppercase text-muted-foreground">
                    {item.label}
                  </p>
                  <p className="text-sm font-semibold text-slate-900">
                    {item.value}
                  </p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Competency criteria scores</CardTitle>
            <CardDescription>
              Live scoring per criterion with achieved level snapshots.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Competency</TableHead>
                  <TableHead>Criterion</TableHead>
                  <TableHead>Weight</TableHead>
                  <TableHead>Achieved level</TableHead>
                  <TableHead className="text-right">Raw score</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {criterionRows.map((row) => (
                  <TableRow key={`${row.competency}-${row.criterion}`}>
                    <TableCell className="font-medium">
                      {row.competency}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {row.criterion}
                    </TableCell>
                    <TableCell>{row.weight.toFixed(1)}%</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {[1, 2, 3, 4, 5].map((level) => {
                          const isActive = level === row.achievedLevel;
                          return (
                            <Badge
                              key={`${row.competency}-${row.criterion}-level-${level}`}
                              variant={isActive ? "default" : "outline"}
                              className="px-2 py-0 text-xs"
                            >
                              Level {level}
                            </Badge>
                          );
                        })}
                      </div>
                    </TableCell>
                    <TableCell className="text-right font-semibold">
                      {row.rawScore.toFixed(1)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Competency pillar scores</CardTitle>
            <CardDescription>
              Aggregate scoring per competency pillar.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Competency pillar</TableHead>
                  <TableHead className="text-right">Score</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {competencyScores.map((entry) => (
                  <TableRow key={entry.competency}>
                    <TableCell className="font-medium">
                      {entry.competency}
                    </TableCell>
                    <TableCell className="text-right">
                      <Badge variant="outline">{entry.score.toFixed(1)}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Overall score</CardTitle>
            <CardDescription>
              Snapshot of the candidate&apos;s current standing.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-baseline justify-between gap-4">
              <div>
                <p className="text-xs uppercase text-muted-foreground">
                  Current overall
                </p>
                <p className="text-5xl font-semibold text-slate-900">
                  {overallScore.toFixed(1)}
                </p>
              </div>
              <div className="rounded-md border border-slate-200 bg-slate-50 p-4 text-sm text-muted-foreground">
                Scores update dynamically as evidence is captured. Use this
                section to validate calibration decisions before submitting
                final feedback.
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
