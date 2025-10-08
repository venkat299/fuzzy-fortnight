import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Pause, Play, Send, Square } from "lucide-react";
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
}

interface ChatMessage {
  id: string;
  speaker: "Candidate" | "Interviewer" | "System";
  content: string;
  tone: "neutral" | "positive";
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
  competency: string;
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

interface SessionData {
  persona: PersonaSettings;
  profile: CandidateProfileSummary;
  events: SessionEvent[];
  competencies: SessionCompetencyState[];
}

const EVENT_DELAY_MS = 1200;

const STAGE_LABELS: Record<StageLiteral, string> = {
  warmup: "Warmup",
  competency: "Competency loop",
  wrapup: "Wrap-up",
  complete: "Complete",
};

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

const normalizeSessionResponse = (payload: unknown): SessionData | null => {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const data = payload as Record<string, unknown>;
  const personaRaw = (data.persona ?? {}) as Record<string, unknown>;
  const persona: PersonaSettings = {
    name: String(personaRaw.name ?? ""),
    probingStyle: String(personaRaw.probing_style ?? ""),
    hintStyle: String(personaRaw.hint_style ?? ""),
    encouragement: String(personaRaw.encouragement ?? ""),
  };
  const profileRaw = (data.profile ?? {}) as Record<string, unknown>;
  const experiencesRaw = Array.isArray(profileRaw.highlighted_experiences)
    ? (profileRaw.highlighted_experiences as unknown[])
    : [];
  const profile: CandidateProfileSummary = {
    candidateName: String(profileRaw.candidate_name ?? ""),
    resumeSummary: String(profileRaw.resume_summary ?? ""),
    experienceYears: String(profileRaw.experience_years ?? ""),
    highlightedExperiences: experiencesRaw
      .map((item) => String(item ?? ""))
      .filter((entry) => entry.trim().length > 0),
  };
  const eventsRaw = Array.isArray(data.events) ? data.events : [];
  const events: SessionEvent[] = eventsRaw
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const entry = item as Record<string, unknown>;
      const eventId = Number(entry.event_id ?? Number.NaN);
      if (!Number.isFinite(eventId)) {
        return null;
      }
      const stage = String(entry.stage ?? "") as StageLiteral;
      const type = String(entry.event_type ?? "") as EventType;
      if (!(["warmup", "competency", "wrapup", "complete"] as const).includes(stage)) {
        return null;
      }
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
        ).includes(type)
      ) {
        return null;
      }
      const payloadValue = entry.payload;
      const payload =
        payloadValue && typeof payloadValue === "object"
          ? (payloadValue as Record<string, unknown>)
          : {};
      const competency = entry.competency;
      return {
        eventId,
        createdAt: String(entry.created_at ?? ""),
        stage,
        competency: competency === null || competency === undefined ? null : String(competency),
        eventType: type,
        payload,
      } satisfies SessionEvent;
    })
    .filter((entry): entry is SessionEvent => Boolean(entry));
  const competenciesRaw = Array.isArray(data.competencies) ? data.competencies : [];
  const competencies: SessionCompetencyState[] = competenciesRaw
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const entry = item as Record<string, unknown>;
      const competencyName = String(entry.competency ?? "");
      if (!competencyName) {
        return null;
      }
      const totalScore = Number(entry.total_score ?? 0);
      const rubricFilled = Boolean(entry.rubric_filled);
      const criteriaRaw = Array.isArray(entry.criteria) ? entry.criteria : [];
      const criteria: SessionCriterion[] = criteriaRaw
        .map((criterionItem) => {
          if (!criterionItem || typeof criterionItem !== "object") {
            return null;
          }
          const criterion = criterionItem as Record<string, unknown>;
          const name = String(criterion.criterion ?? "");
          if (!name) {
            return null;
          }
          return {
            competency: competencyName,
            criterion: name,
            weight: Number(criterion.weight ?? 0),
            latestScore: Number(criterion.latest_score ?? 0),
            rationale: String(criterion.rationale ?? ""),
          } satisfies SessionCriterion;
        })
        .filter((entry): entry is SessionCriterion => Boolean(entry));
      return {
        competency: competencyName,
        totalScore: Number.isFinite(totalScore) ? totalScore : 0,
        rubricFilled,
        criteria,
      } satisfies SessionCompetencyState;
    })
    .filter((entry): entry is SessionCompetencyState => Boolean(entry));
  return {
    persona,
    profile,
    events,
    competencies,
  } satisfies SessionData;
};

export function InterviewSessionPage({
  assignment,
  onBackToDashboard,
}: InterviewSessionPageProps) {
  const [autoGenerate, setAutoGenerate] = useState(1);
  const [autoSend, setAutoSend] = useState(0);
  const [sessionData, setSessionData] = useState<SessionData | null>(null);
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
  const [isFetching, setIsFetching] = useState(false);
  const [currentEventIndex, setCurrentEventIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const eventsRef = useRef<SessionEvent[]>([]);
  const weightMapRef = useRef<Map<string, number>>(new Map());
  const competencyOrderRef = useRef<string[]>([]);
  const timeoutRef = useRef<number | null>(null);
  const startTimeRef = useRef<number>(0);
  const elapsedAccumulatorRef = useRef<number>(0);
  const [timerRunning, setTimerRunning] = useState(false);

  const timeElapsed = useMemo(() => formatElapsed(elapsedMs), [elapsedMs]);

  const clearPlaybackTimeout = useCallback(() => {
    if (timeoutRef.current !== null) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  const beginTimer = useCallback(() => {
    elapsedAccumulatorRef.current = 0;
    startTimeRef.current = Date.now();
    setElapsedMs(0);
    setTimerRunning(true);
  }, []);

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

  useEffect(() => {
    eventsRef.current = events;
  }, [events]);

  useEffect(() => {
    if (!sessionData) {
      weightMapRef.current.clear();
      competencyOrderRef.current = [];
      setCriterionRows([]);
      setCompetencyScores([]);
      setOverallScore(0);
      return;
    }
    weightMapRef.current.clear();
    competencyOrderRef.current = sessionData.competencies.map(
      (entry) => entry.competency,
    );
    const initialRows: CriterionRow[] = [];
    sessionData.competencies.forEach((competency) => {
      competency.criteria.forEach((criterion) => {
        const weightDisplay = Number(toDisplayWeight(criterion.weight).toFixed(1));
        weightMapRef.current.set(
          `${competency.competency}::${criterion.criterion}`,
          weightDisplay,
        );
        const latestScore = Number.isFinite(criterion.latestScore)
          ? criterion.latestScore
          : 0;
        const rawScore = Number(
          (latestScore * (weightDisplay / 100)).toFixed(2),
        );
        initialRows.push({
          competency: competency.competency,
          criterion: criterion.criterion,
          weight: weightDisplay,
          achievedLevel: toLevel(latestScore),
          rawScore,
        });
      });
    });
    setCriterionRows(initialRows);
    const competencySummaries = sessionData.competencies.map((entry) => ({
      competency: entry.competency,
      score: Number(entry.totalScore.toFixed(1)),
    }));
    setCompetencyScores(competencySummaries);
    if (competencySummaries.length > 0) {
      const aggregate = competencySummaries.reduce(
        (sum, item) => sum + item.score,
        0,
      );
      setOverallScore(
        Number((aggregate / competencySummaries.length).toFixed(1)),
      );
    } else {
      setOverallScore(0);
    }
  }, [sessionData]);

  const processEvent = useCallback(
    (event: SessionEvent, index: number, total: number) => {
      if (total > 0) {
        const progress = Math.min(100, Math.round(((index + 1) / total) * 100));
        setStageProgress(progress);
      }
      setStageName(STAGE_LABELS[event.stage] ?? STAGE_LABELS.warmup);
      if (event.stage === "competency" && event.competency) {
        setActiveCompetency(event.competency);
      }
      if (event.stage === "wrapup") {
        setActiveCompetency("—");
      }
      const messages: ChatMessage[] = [];
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
      }
      if (event.eventType === "question") {
        const questionText = String(event.payload.question ?? "").trim();
        if (questionText) {
          messages.push({
            id: generateId(),
            speaker: "Interviewer",
            content: questionText,
            tone: "neutral",
          });
          setQuestionsAsked((prev) => prev + 1);
          if (event.competency) {
            setActiveCompetency(event.competency);
          }
        }
      }
      if (event.eventType === "answer") {
        const answerText = String(event.payload.answer ?? "").trim();
        if (answerText) {
          messages.push({
            id: generateId(),
            speaker: "Candidate",
            content: answerText,
            tone: "positive",
          });
        }
      }
      if (event.eventType === "hint") {
        const hintText = String(event.payload.hint ?? "").trim();
        if (hintText) {
          messages.push({
            id: generateId(),
            speaker: "System",
            content: `Hint: ${hintText}`,
            tone: "neutral",
          });
        }
      }
      if (event.eventType === "follow_up") {
        const followUpText = String(
          event.payload.message ?? "Evaluator suggests a follow-up.",
        ).trim();
        messages.push({
          id: generateId(),
          speaker: "System",
          content: followUpText,
          tone: "neutral",
        });
      }
      if (event.eventType === "checkpoint") {
        const savedAt = String(event.payload.saved_at ?? "");
        const checkpointMessage = savedAt
          ? `Checkpoint saved at ${savedAt}.`
          : "Checkpoint saved.";
        messages.push({
          id: generateId(),
          speaker: "System",
          content: checkpointMessage,
          tone: "neutral",
        });
      }
      if (event.eventType === "evaluation" && event.competency) {
        const evaluation = event.payload;
        const summary = typeof evaluation.summary === "string" ? evaluation.summary : "";
        if (summary.trim()) {
          messages.push({
            id: generateId(),
            speaker: "System",
            content: summary,
            tone: "neutral",
          });
        }
        const hints = Array.isArray(evaluation.hints)
          ? (evaluation.hints as unknown[])
          : [];
        hints
          .map((item) => String(item ?? "").trim())
          .filter((hint) => hint.length > 0)
          .forEach((hint) => {
            messages.push({
              id: generateId(),
              speaker: "System",
              content: `Coaching hint: ${hint}`,
              tone: "neutral",
            });
          });
        const totalScore = Number(evaluation.total_score ?? 0);
        setCompetencyScores((previous) => {
          const map = new Map(previous.map((item) => [item.competency, item.score]));
          map.set(event.competency as string, Number(totalScore.toFixed(1)));
          const order = competencyOrderRef.current;
          const ordered = (order.length ? order : Array.from(map.keys())).map((name) => ({
            competency: name,
            score: map.get(name) ?? 0,
          }));
          if (ordered.length > 0) {
            const aggregate = ordered.reduce((sum, entry) => sum + entry.score, 0);
            setOverallScore(Number((aggregate / ordered.length).toFixed(1)));
          } else {
            setOverallScore(0);
          }
          return ordered;
        });
        const criterionScores = Array.isArray(evaluation.criterion_scores)
          ? (evaluation.criterion_scores as Array<Record<string, unknown>>)
          : [];
        if (criterionScores.length > 0) {
          setCriterionRows((previous) => {
            const map = new Map(
              previous.map((row) => [`${row.competency}::${row.criterion}`, row]),
            );
            criterionScores.forEach((scoreEntry) => {
              const criterionName = String(scoreEntry.criterion ?? "").trim();
              if (!criterionName) {
                return;
              }
              const key = `${event.competency as string}::${criterionName}`;
              const storedWeight = weightMapRef.current.get(key) ?? 0;
              const weightDisplay = Number(storedWeight.toFixed(1));
              const scoreValue = Number(scoreEntry.score ?? 0);
              const rawScore = Number(
                (scoreValue * (weightDisplay / 100)).toFixed(2),
              );
              map.set(key, {
                competency: event.competency as string,
                criterion: criterionName,
                weight: weightDisplay,
                achievedLevel: toLevel(scoreValue),
                rawScore,
              });
            });
            const order = competencyOrderRef.current;
            const sorted = Array.from(map.values()).sort((a, b) => {
              const indexA = order.indexOf(a.competency);
              const indexB = order.indexOf(b.competency);
              if (indexA !== indexB) {
                const safeA = indexA === -1 ? Number.MAX_SAFE_INTEGER : indexA;
                const safeB = indexB === -1 ? Number.MAX_SAFE_INTEGER : indexB;
                return safeA - safeB;
              }
              return a.criterion.localeCompare(b.criterion);
            });
            return sorted;
          });
        }
      }
      if (messages.length > 0) {
        setDisplayedMessages((previous) => [...previous, ...messages]);
      }
    },
    [],
  );

  useEffect(() => {
    if (!isPlaying) {
      clearPlaybackTimeout();
      return;
    }
    if (events.length === 0) {
      clearPlaybackTimeout();
      setIsPlaying(false);
      setStatus("complete");
      pauseTimer();
      return;
    }
    if (currentEventIndex >= events.length) {
      clearPlaybackTimeout();
      setIsPlaying(false);
      setStatus("complete");
      setStageProgress(100);
      setStageName(STAGE_LABELS.complete);
      pauseTimer();
      return;
    }
    timeoutRef.current = window.setTimeout(() => {
      const event = events[currentEventIndex];
      processEvent(event, currentEventIndex, events.length);
      setCurrentEventIndex((value) => value + 1);
    }, EVENT_DELAY_MS);
    return () => {
      clearPlaybackTimeout();
    };
  }, [
    isPlaying,
    events,
    currentEventIndex,
    processEvent,
    clearPlaybackTimeout,
    pauseTimer,
  ]);

  const startSession = useCallback(async () => {
    clearPlaybackTimeout();
    setIsFetching(true);
    setErrorMessage(null);
    try {
      const response = await fetch("/api/interview-sessions/run", {
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
            : "Failed to run interview session.";
        throw new Error(detail);
      }
      const payload = await response.json();
      const normalized = normalizeSessionResponse(payload);
      if (!normalized) {
        throw new Error("Invalid session response.");
      }
      const introMessages: ChatMessage[] = [
        {
          id: generateId(),
          speaker: "System",
          content: `Interview persona: ${normalized.persona.name}. ${normalized.persona.probingStyle}`,
          tone: "neutral",
        },
      ];
      if (normalized.profile.resumeSummary) {
        const summary = normalized.profile.resumeSummary.length > 200
          ? `${normalized.profile.resumeSummary.slice(0, 197)}…`
          : normalized.profile.resumeSummary;
        introMessages.push({
          id: generateId(),
          speaker: "System",
          content: `Resume context: ${summary}`,
          tone: "neutral",
        });
      }
      setSessionData(normalized);
      setEvents(normalized.events);
      setDisplayedMessages(introMessages);
      setStageProgress(0);
      setStageName(STAGE_LABELS.warmup);
      setActiveCompetency("—");
      setQuestionsAsked(0);
      setOverallScore(0);
      setCurrentEventIndex(0);
      setStatus("running");
      setIsPlaying(true);
      beginTimer();
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to run interview session.";
      setErrorMessage(message);
      setStatus("idle");
      setSessionData(null);
      setEvents([]);
      setDisplayedMessages([]);
      setStageProgress(0);
      setStageName(STAGE_LABELS.warmup);
      setActiveCompetency("—");
      setQuestionsAsked(0);
      setOverallScore(0);
      setCurrentEventIndex(0);
      resetTimer();
    } finally {
      setIsFetching(false);
    }
  }, [
    assignment.candidateId,
    assignment.interviewId,
    beginTimer,
    clearPlaybackTimeout,
    resetTimer,
  ]);

  const handleStart = useCallback(() => {
    if (status === "paused") {
      setStatus("running");
      setIsPlaying(true);
      resumeTimer();
      return;
    }
    if (status === "running" || isFetching) {
      return;
    }
    void startSession();
  }, [status, isFetching, startSession, resumeTimer]);

  const handlePause = useCallback(() => {
    if (status !== "running") {
      return;
    }
    clearPlaybackTimeout();
    setIsPlaying(false);
    setStatus("paused");
    pauseTimer();
  }, [status, clearPlaybackTimeout, pauseTimer]);

  const handleStop = useCallback(() => {
    clearPlaybackTimeout();
    setIsPlaying(false);
    setStatus("stopped");
    setSessionData(null);
    setEvents([]);
    setDisplayedMessages([]);
    setCriterionRows([]);
    setCompetencyScores([]);
    setStageProgress(0);
    setStageName(STAGE_LABELS.warmup);
    setActiveCompetency("—");
    setQuestionsAsked(0);
    setOverallScore(0);
    setCurrentEventIndex(0);
    setErrorMessage(null);
    resetTimer();
  }, [clearPlaybackTimeout, resetTimer]);

  const startButtonLabel = status === "paused" ? "Resume" : "Start";
  const startButtonText = isFetching ? "Starting..." : startButtonLabel;
  const isStartDisabled = isFetching || status === "running";
  const isPauseDisabled = status !== "running";
  const isStopDisabled = status === "idle";

  const renderLevelBadges = (achieved: CriterionRow["achievedLevel"]) => {
    return (
      <div className="flex flex-wrap gap-1">
        {[1, 2, 3, 4, 5].map((level) => {
          const isActive = level === achieved;
          return (
            <Badge
              key={level}
              variant={isActive ? "default" : "outline"}
              className="px-2 py-0 text-xs"
            >
              Level {level}
            </Badge>
          );
        })}
      </div>
    );
  };

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
            {sessionData && (
              <div className="pt-1 text-xs text-slate-500">
                Persona: {sessionData.persona.name}
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
                    displayedMessages.map((message) => (
                      <div
                        key={message.id}
                        className={`rounded-lg border p-3 text-sm leading-relaxed ${
                          message.speaker === "Candidate"
                            ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                            : message.speaker === "Interviewer"
                              ? "border-sky-200 bg-sky-50 text-sky-900"
                              : "border-slate-200 bg-slate-50 text-slate-700"
                        }`}
                      >
                        <div className="mb-2 flex items-center justify-between gap-2">
                          <span className="font-medium">{message.speaker}</span>
                          <Badge
                            variant={
                              message.tone === "positive"
                                ? "secondary"
                                : "outline"
                            }
                          >
                            {message.tone}
                          </Badge>
                        </div>
                        <p>{message.content}</p>
                      </div>
                    ))
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
              />
              <Button
                type="button"
                className="lg:h-full lg:min-w-[9rem]"
                variant="secondary"
              >
                <Send className="h-4 w-4" />
                Send
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
                  value: stageName,
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
                {criteriaRows.map((row) => (
                  <TableRow key={`${row.competency}-${row.criterion}`}>
                    <TableCell className="font-medium">
                      {row.competency}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {row.criterion}
                    </TableCell>
                    <TableCell>{row.weight}%</TableCell>
                    <TableCell>
                      {renderLevelBadges(row.achievedLevel)}
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
