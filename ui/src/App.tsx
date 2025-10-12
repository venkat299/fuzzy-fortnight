import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { InterviewerDashboard } from './components/InterviewerDashboard';
import { CompetencyPillars } from './components/CompetencyPillars';
import { InterviewRubric } from './components/InterviewRubric';
import { InterviewerOverview, type InterviewAssignment } from './components/InterviewerOverview';
import { AddCandidateFormData, AddCandidatePage } from './components/AddCandidatePage';
import { InterviewSessionPage } from './components/InterviewSessionPage';

interface InterviewData {
  jobTitle: string;
  jobDescription: string;
  experienceYears: string;
}

interface CompetencyArea {
  name: string;
  skills: string[];
}

interface CompetencyMatrix {
  jobTitle: string;
  experienceYears: string;
  competencyAreas: CompetencyArea[];
  interviewId: string;
}

interface RubricAnchor {
  level: number;
  text: string;
}

interface RubricCriterion {
  name: string;
  weight: number;
  anchors: RubricAnchor[];
}

interface Rubric {
  competency: string;
  band: string;
  bandNotes: string[];
  criteria: RubricCriterion[];
  redFlags: string[];
  evidence: string[];
  minPassScore: number;
}

interface InterviewRubricData {
  interviewId: string;
  jobTitle: string;
  experienceYears: string;
  status: string;
  rubrics: Rubric[];
}

type ChatTone = "neutral" | "positive";

interface QuestionAnswer {
  question: string;
  answer: string;
}

interface SessionMessage {
  id: string;
  speaker: "Candidate" | "Interviewer" | "System";
  content: string;
  tone: ChatTone;
}

interface SessionContextData {
  stage: string;
  interviewId: string;
  candidateName: string;
  jobTitle: string;
  resumeSummary: string;
  autoAnswerEnabled: boolean;
  candidateLevel: number;
  qaHistory: QuestionAnswer[];
}

interface SessionLaunchData {
  rubric: InterviewRubricData;
  context: SessionContextData;
  messages: SessionMessage[];
}

interface SessionProgressData {
  context: SessionContextData;
  messages: SessionMessage[];
}

interface DashboardInterview {
  interviewId: string;
  jobTitle: string;
  jobDescription: string;
  experienceYears: string;
  status: string;
  createdAt: string;
}

interface DashboardCandidate {
  candidateId: string;
  fullName: string;
  resume: string;
  interviewId: string | null;
  status: string;
  createdAt: string;
}

type AppState =
  | 'interviewer-overview'
  | 'interviewer-dashboard'
  | 'candidate-intake'
  | 'candidate-edit'
  | 'competency-pillars'
  | 'interview-session'
  | 'interview-rubric';

const DEFAULT_CANDIDATE_STATUS = 'Applied';

export default function App() {
  const [currentState, setCurrentState] = useState<AppState>('interviewer-overview');
  const [interviewData, setInterviewData] = useState<InterviewData | null>(null);
  const [matrix, setMatrix] = useState<CompetencyMatrix | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [rubricData, setRubricData] = useState<InterviewRubricData | null>(null);
  const [isProceeding, setIsProceeding] = useState(false);
  const [interviews, setInterviews] = useState<DashboardInterview[]>([]);
  const [candidates, setCandidates] = useState<DashboardCandidate[]>([]);
  const [isLoadingInterviews, setIsLoadingInterviews] = useState(false);
  const [isLoadingCandidates, setIsLoadingCandidates] = useState(false);
  const [interviewsError, setInterviewsError] = useState<string | null>(null);
  const [candidatesError, setCandidatesError] = useState<string | null>(null);
  const [candidateFormError, setCandidateFormError] = useState<string | null>(null);
  const [isCandidateSubmitting, setIsCandidateSubmitting] = useState(false);
  const [currentSession, setCurrentSession] = useState<InterviewAssignment | null>(null);
  const [sessionRubric, setSessionRubric] = useState<InterviewRubricData | null>(null);
  const [sessionMessages, setSessionMessages] = useState<SessionMessage[]>([]);
  const [autoAnswerEnabled, setAutoAnswerEnabled] = useState(false);
  const [candidateReplyLevel, setCandidateReplyLevel] = useState(1);
  const [qaHistory, setQaHistory] = useState<QuestionAnswer[]>([]);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [isStartingWarmup, setIsStartingWarmup] = useState(false);
  const [candidateToEdit, setCandidateToEdit] = useState<DashboardCandidate | null>(null);

  const normalizeMatrix = (payload: unknown, fallback: InterviewData): CompetencyMatrix => {
    if (!payload || typeof payload !== 'object') {
      return {
        jobTitle: fallback.jobTitle,
        experienceYears: fallback.experienceYears,
        competencyAreas: [],
        interviewId: ''
      };
    }
    const data = payload as Record<string, unknown>;
    const rawAreas = Array.isArray(data.competency_areas) ? data.competency_areas : [];
    const competencyAreas: CompetencyArea[] = rawAreas
      .map((item) => {
        if (!item || typeof item !== 'object') {
          return { name: '', skills: [] };
        }
        const entry = item as Record<string, unknown>;
        const skillsSource = Array.isArray(entry.skills) ? entry.skills : [];
        return {
          name: String(entry.name ?? ''),
          skills: skillsSource.map((skill) => String(skill ?? '')).filter((skill) => skill.trim().length > 0)
        };
      })
      .filter((area) => area.name.trim().length > 0 || area.skills.length > 0);
    return {
      jobTitle: String(data.job_title ?? fallback.jobTitle),
      experienceYears: String(data.experience_years ?? fallback.experienceYears),
      competencyAreas,
      interviewId: String(data.interview_id ?? '').trim()
    };
  };

  const normalizeInterviews = (payload: unknown): DashboardInterview[] => {
    if (!Array.isArray(payload)) {
      return [];
    }
    return payload
      .map((item) => {
        if (!item || typeof item !== 'object') {
          return null;
        }
        const row = item as Record<string, unknown>;
        const interviewId = String(row.interview_id ?? '').trim();
        if (!interviewId) {
          return null;
        }
        return {
          interviewId,
          jobTitle: String(row.job_title ?? ''),
          jobDescription: String(row.job_description ?? ''),
          experienceYears: String(row.experience_years ?? ''),
          status: String(row.status ?? ''),
          createdAt: String(row.created_at ?? '')
        } satisfies DashboardInterview;
      })
      .filter((entry): entry is DashboardInterview => Boolean(entry));
  };

  const normalizeCandidates = (payload: unknown): DashboardCandidate[] => {
    if (!Array.isArray(payload)) {
      return [];
    }
    return payload
      .map((item) => {
        if (!item || typeof item !== 'object') {
          return null;
        }
        const row = item as Record<string, unknown>;
        const candidateId = String(row.candidate_id ?? '').trim();
        if (!candidateId) {
          return null;
        }
        return {
          candidateId,
          fullName: String(row.full_name ?? ''),
          resume: String(row.resume ?? ''),
          interviewId: row.interview_id != null ? String(row.interview_id) : null,
          status: String(row.status ?? ''),
          createdAt: String(row.created_at ?? '')
        } satisfies DashboardCandidate;
      })
      .filter((entry): entry is DashboardCandidate => Boolean(entry));
  };

  const normalizeRubric = (payload: unknown): InterviewRubricData | null => {
    if (!payload || typeof payload !== 'object') {
      return null;
    }
    const source = payload as Record<string, unknown>;
    const rubricsSource = Array.isArray(source.rubrics) ? source.rubrics : [];
    const rubrics: Rubric[] = rubricsSource
      .map((entry) => {
        if (!entry || typeof entry !== 'object') {
          return null;
        }
        const row = entry as Record<string, unknown>;
        const criteria = Array.isArray(row.criteria)
          ? row.criteria
              .map((criterion) => {
                if (!criterion || typeof criterion !== 'object') {
                  return null;
                }
                const criterionRow = criterion as Record<string, unknown>;
                const anchors = Array.isArray(criterionRow.anchors)
                  ? criterionRow.anchors
                      .map((anchor) => {
                        if (!anchor || typeof anchor !== 'object') {
                          return null;
                        }
                        const anchorRow = anchor as Record<string, unknown>;
                        return {
                          level: Number(anchorRow.level ?? 0),
                          text: String(anchorRow.text ?? '')
                        };
                      })
                      .filter((anchor): anchor is RubricAnchor => Boolean(anchor && anchor.text.trim().length > 0))
                  : [];
                return {
                  name: String(criterionRow.name ?? ''),
                  weight: Number(criterionRow.weight ?? 0),
                  anchors
                };
              })
              .filter((criterion): criterion is RubricCriterion => Boolean(criterion && criterion.name.trim().length > 0))
          : [];
        return {
          competency: String(row.competency ?? ''),
          band: String(row.band ?? ''),
          bandNotes: Array.isArray(row.band_notes)
            ? row.band_notes.map((note) => String(note ?? '')).filter((note) => note.trim().length > 0)
            : [],
          criteria,
          redFlags: Array.isArray(row.red_flags)
            ? row.red_flags.map((item) => String(item ?? '')).filter((item) => item.trim().length > 0)
            : [],
          evidence: Array.isArray(row.evidence)
            ? row.evidence.map((item) => String(item ?? '')).filter((item) => item.trim().length > 0)
            : [],
          minPassScore: Number(row.min_pass_score ?? 0)
        };
      })
      .filter((rubric): rubric is Rubric => Boolean(rubric && rubric.competency.trim().length > 0));

    const interviewId = String(source.interview_id ?? '').trim();
    if (!interviewId) {
      return null;
    }

    return {
      interviewId,
      jobTitle: String(source.job_title ?? ''),
      experienceYears: String(source.experience_years ?? ''),
      status: String(source.status ?? ''),
      rubrics
    };
  };

  const mapSpeaker = (value: string): SessionMessage['speaker'] => {
    const normalized = value.toLowerCase();
    if (normalized.includes('candidate')) {
      return 'Candidate';
    }
    if (normalized.includes('system')) {
      return 'System';
    }
    return 'Interviewer';
  };

  const parseSessionContext = (contextSource: unknown, fallback: InterviewRubricData): SessionContextData | null => {
    if (!contextSource || typeof contextSource !== 'object') {
      return null;
    }
    const contextRow = contextSource as Record<string, unknown>;
    const autoAnswerEnabled =
      typeof contextRow.auto_answer_enabled === 'boolean'
        ? contextRow.auto_answer_enabled
        : String(contextRow.auto_answer_enabled ?? '').toLowerCase() === 'true';
    let candidateLevel = Number(contextRow.candidate_level ?? 1);
    if (!Number.isFinite(candidateLevel)) {
      candidateLevel = 1;
    }
    candidateLevel = Math.min(5, Math.max(1, Math.round(candidateLevel)));
    const historySource = Array.isArray(contextRow.qa_history) ? contextRow.qa_history : [];
    const history: QuestionAnswer[] = historySource
      .map((item) => {
        if (!item || typeof item !== 'object') {
          return null;
        }
        const row = item as Record<string, unknown>;
        const question = String(row.question ?? '').trim();
        const answer = String(row.answer ?? '').trim();
        if (!question && !answer) {
          return null;
        }
        return { question, answer } satisfies QuestionAnswer;
      })
      .filter((entry): entry is QuestionAnswer => Boolean(entry));
    return {
      stage: String(contextRow.stage ?? 'warmup'),
      interviewId: String(contextRow.interview_id ?? fallback.interviewId),
      candidateName: String(contextRow.candidate_name ?? ''),
      jobTitle: String(contextRow.job_title ?? fallback.jobTitle),
      resumeSummary: String(contextRow.resume_summary ?? ''),
      autoAnswerEnabled,
      candidateLevel,
      qaHistory: history,
    };
  };

  const parseSessionMessages = (source: unknown): SessionMessage[] => {
    const messagesSource = Array.isArray(source) ? source : [];
    return messagesSource
      .map((entry, index) => {
        if (!entry || typeof entry !== 'object') {
          return null;
        }
        const row = entry as Record<string, unknown>;
        const content = String(row.content ?? '').trim();
        if (!content) {
          return null;
        }
        const speakerValue = String(row.speaker ?? '').trim();
        const toneValue = typeof row.tone === 'string' ? row.tone.toLowerCase() : '';
        const tone: ChatTone = toneValue === 'positive' ? 'positive' : 'neutral';
        return {
          id: String(index + 1),
          speaker: mapSpeaker(speakerValue),
          content,
          tone,
        } satisfies SessionMessage;
      })
      .filter((message): message is SessionMessage => Boolean(message));
  };

  const normalizeSessionLaunch = (payload: unknown): SessionLaunchData | null => {
    if (!payload || typeof payload !== 'object') {
      return null;
    }
    const source = payload as Record<string, unknown>;
    const rubricPayload = source.rubric;
    const rubric = normalizeRubric(rubricPayload);
    if (!rubric) {
      return null;
    }
    const context = parseSessionContext(source.context, rubric);
    if (!context) {
      return null;
    }
    const messages = parseSessionMessages(source.messages);
    return { rubric, context, messages };
  };

  const normalizeSessionProgress = (payload: unknown, fallback: InterviewRubricData | null): SessionProgressData | null => {
    if (!payload || typeof payload !== 'object' || !fallback) {
      return null;
    }
    const source = payload as Record<string, unknown>;
    const context = parseSessionContext(source.context, fallback);
    if (!context) {
      return null;
    }
    const messages = parseSessionMessages(source.messages);
    return { context, messages };
  };

  const fetchInterviews = useCallback(async () => {
    setIsLoadingInterviews(true);
    setInterviewsError(null);
    try {
      const response = await fetch('/api/interviews');
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null);
        const detail =
          errorPayload && typeof errorPayload.detail === 'string'
            ? errorPayload.detail
            : 'Failed to load interviews.';
        throw new Error(detail);
      }
      const payload = await response.json();
      setInterviews(normalizeInterviews(payload));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load interviews.';
      setInterviewsError(message);
    } finally {
      setIsLoadingInterviews(false);
    }
  }, []);

  const fetchCandidates = useCallback(async () => {
    setIsLoadingCandidates(true);
    setCandidatesError(null);
    try {
      const response = await fetch('/api/candidates');
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null);
        const detail =
          errorPayload && typeof errorPayload.detail === 'string'
            ? errorPayload.detail
            : 'Failed to load candidates.';
        throw new Error(detail);
      }
      const payload = await response.json();
      setCandidates(normalizeCandidates(payload));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load candidates.';
      setCandidatesError(message);
    } finally {
      setIsLoadingCandidates(false);
    }
  }, []);

  useEffect(() => {
    fetchInterviews();
    fetchCandidates();
  }, [fetchInterviews, fetchCandidates]);

  const handleSubmitInterview = async (data: InterviewData) => {
    setErrorMessage(null);
    setIsLoading(true);
    setInterviewData(data);
    setRubricData(null);
    try {
      const response = await fetch('/api/competency-matrix', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          jobTitle: data.jobTitle,
          jobDescription: data.jobDescription,
          experienceYears: data.experienceYears
        })
      });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null);
        const detail =
          errorPayload && typeof errorPayload.detail === 'string'
            ? errorPayload.detail
            : 'Failed to analyze job description.';
        throw new Error(detail);
      }
      const payload = await response.json();
      const normalized = normalizeMatrix(payload, data);
      setMatrix(normalized);
      fetchInterviews();
      setCurrentState('competency-pillars');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to analyze job description.';
      setErrorMessage(message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleBackToDashboard = () => {
    setCurrentState('interviewer-dashboard');
  };

  const handleStartInterview = async (interviewId: string) => {
    setErrorMessage(null);
    setIsProceeding(true);
    try {
      const response = await fetch(`/api/interviews/${interviewId}/rubric`);
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null);
        const detail =
          errorPayload && typeof errorPayload.detail === 'string'
            ? errorPayload.detail
            : 'Failed to load interview rubric.';
        throw new Error(detail);
      }
      const payload = await response.json();
      const normalized = normalizeRubric(payload);
      if (!normalized) {
        throw new Error('Received an invalid rubric response.');
      }
      setRubricData(normalized);
      setCurrentState('interview-rubric');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load interview rubric.';
      setErrorMessage(message);
    } finally {
      setIsProceeding(false);
    }
  };

  const handleCreateCandidate = async (data: AddCandidateFormData) => {
    setCandidateFormError(null);
    setIsCandidateSubmitting(true);
    try {
      const primaryInterviewId = data.interviewIds[0] ?? null;
      const response = await fetch('/api/candidates', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          full_name: data.fullName,
          resume: data.resume,
          interview_id: primaryInterviewId,
          status: DEFAULT_CANDIDATE_STATUS
        })
      });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null);
        const detail =
          errorPayload && typeof errorPayload.detail === 'string'
            ? errorPayload.detail
            : 'Failed to save candidate.';
        throw new Error(detail);
      }
      await fetchCandidates();
      setCurrentState('interviewer-overview');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save candidate.';
      setCandidateFormError(message);
    } finally {
      setIsCandidateSubmitting(false);
    }
  };

  const handleEditCandidate = (candidateId: string) => {
    const target = candidates.find((candidate) => candidate.candidateId === candidateId) ?? null;
    setCandidateFormError(null);
    if (!target) {
      setCandidateFormError('Candidate not found.');
      return;
    }
    setCandidateToEdit(target);
    setCurrentState('candidate-edit');
  };

  const handleUpdateCandidate = async (data: AddCandidateFormData) => {
    if (!candidateToEdit) {
      return;
    }
    setCandidateFormError(null);
    setIsCandidateSubmitting(true);
    try {
      setCandidates((previous) =>
        previous.map((entry) =>
          entry.candidateId === candidateToEdit.candidateId
            ? {
                ...entry,
                fullName: data.fullName,
                resume: data.resume,
                interviewId: data.interviewIds[0] ?? null
              }
            : entry
        )
      );
      setCandidateToEdit(null);
      setCurrentState('interviewer-overview');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to update candidate.';
      setCandidateFormError(message);
    } finally {
      setIsCandidateSubmitting(false);
    }
  };

  const handleAutoAnswerToggle = useCallback((enabled: boolean) => {
    setAutoAnswerEnabled(enabled);
  }, []);

  const handleCandidateReplyLevelChange = useCallback((level: number) => {
    const clamped = Math.min(5, Math.max(1, Math.round(level)));
    setCandidateReplyLevel(clamped);
  }, []);

  const startSession = async (assignment: InterviewAssignment) => {
    setCandidateFormError(null);
    setErrorMessage(null);
    setInterviewsError(null);
    setIsProceeding(true);
    setSessionRubric(null);
    setSessionMessages([]);
    setQaHistory([]);
    setSessionError(null);
    try {
      const requestHistory: QuestionAnswer[] = [];
      const response = await fetch(`/api/interviews/${assignment.interviewId}/session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          candidate_id: assignment.candidateId,
          auto_answer_enabled: autoAnswerEnabled,
          candidate_level: candidateReplyLevel,
          qa_history: requestHistory
        })
      });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null);
        const detail =
          errorPayload && typeof errorPayload.detail === 'string'
            ? errorPayload.detail
            : 'Failed to launch interview session.';
        throw new Error(detail);
      }
      const payload = await response.json();
      const normalized = normalizeSessionLaunch(payload);
      if (!normalized) {
        throw new Error('Received an invalid session response.');
      }
      setSessionRubric(normalized.rubric);
      setSessionMessages(normalized.messages);
      setAutoAnswerEnabled(normalized.context.autoAnswerEnabled);
      setCandidateReplyLevel(normalized.context.candidateLevel);
      setQaHistory(normalized.context.qaHistory);
      setSessionError(null);
      setCurrentSession(assignment);
      setCurrentState('interview-session');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to launch interview session.';
      setInterviewsError(message);
    } finally {
      setIsProceeding(false);
    }
  };

  const beginWarmup = useCallback(async () => {
    if (!currentSession || !sessionRubric) {
      return;
    }
    setSessionError(null);
    setIsStartingWarmup(true);
    try {
      const response = await fetch(`/api/interviews/${currentSession.interviewId}/session/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          candidate_id: currentSession.candidateId,
          auto_answer_enabled: autoAnswerEnabled,
          candidate_level: candidateReplyLevel,
          qa_history: qaHistory
        })
      });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null);
        const detail =
          errorPayload && typeof errorPayload.detail === 'string'
            ? errorPayload.detail
            : 'Failed to start warmup.';
        throw new Error(detail);
      }
      const payload = await response.json();
      const normalized = normalizeSessionProgress(payload, sessionRubric);
      if (!normalized) {
        throw new Error('Received an invalid warmup response.');
      }
      setSessionMessages(normalized.messages);
      setAutoAnswerEnabled(normalized.context.autoAnswerEnabled);
      setCandidateReplyLevel(normalized.context.candidateLevel);
      setQaHistory(normalized.context.qaHistory);
      setSessionError(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to start warmup.';
      setSessionError(message);
    } finally {
      setIsStartingWarmup(false);
    }
  }, [
    autoAnswerEnabled,
    candidateReplyLevel,
    currentSession,
    normalizeSessionProgress,
    qaHistory,
    sessionRubric
  ]);

  const launchInterviewFromDashboard = (assignment: InterviewAssignment) => {
    void startSession(assignment);
  };

  const closeInterviewSession = () => {
    setCurrentSession(null);
    setSessionRubric(null);
    setSessionMessages([]);
    setQaHistory([]);
    setSessionError(null);
    setIsStartingWarmup(false);
    setAutoAnswerEnabled(false);
    setCandidateReplyLevel(3);
    setCurrentState('interviewer-overview');
  };

  const dashboardInitialData = useMemo(() => interviewData ?? undefined, [interviewData]);

  switch (currentState) {
    case 'interviewer-overview':
      return (
        <InterviewerOverview
          interviews={interviews}
          candidates={candidates}
          onCreateInterview={() => {
            setErrorMessage(null);
            setCurrentState('interviewer-dashboard');
          }}
          onAddCandidate={() => {
            setCandidateFormError(null);
            setCandidateToEdit(null);
            setCurrentState('candidate-intake');
          }}
          onStartInterview={launchInterviewFromDashboard}
          onRedoInterview={launchInterviewFromDashboard}
          onViewRubric={(interviewId) => {
            setCandidateFormError(null);
            void handleStartInterview(interviewId);
          }}
          onEditCandidate={handleEditCandidate}
          isLoadingInterviews={isLoadingInterviews}
          isLoadingCandidates={isLoadingCandidates}
          interviewsError={interviewsError}
          candidatesError={candidatesError}
          isProcessingInterview={isProceeding}
        />
      );

    case 'interviewer-dashboard':
      return (
        <InterviewerDashboard
          onSubmitInterview={handleSubmitInterview}
          initialData={dashboardInitialData}
          isLoading={isLoading}
          errorMessage={errorMessage}
          onBack={() => {
            setErrorMessage(null);
            setCurrentState('interviewer-overview');
          }}
        />
      );

    case 'candidate-intake':
      return (
        <AddCandidatePage
          interviews={interviews.map((item) => ({
            interviewId: item.interviewId,
            jobTitle: item.jobTitle,
            jobDescription: item.jobDescription
          }))}
          onSave={handleCreateCandidate}
          onBackToDashboard={() => {
            setCandidateFormError(null);
            setCandidateToEdit(null);
            setCurrentState('interviewer-overview');
          }}
          isSaving={isCandidateSubmitting}
          errorMessage={candidateFormError}
          initialCandidate={null}
          mode="create"
        />
      );

    case 'candidate-edit':
      if (!candidateToEdit) {
        setCurrentState('interviewer-overview');
        return null;
      }
      return (
        <AddCandidatePage
          interviews={interviews.map((item) => ({
            interviewId: item.interviewId,
            jobTitle: item.jobTitle,
            jobDescription: item.jobDescription
          }))}
          onSave={handleUpdateCandidate}
          onBackToDashboard={() => {
            setCandidateFormError(null);
            setCandidateToEdit(null);
            setCurrentState('interviewer-overview');
          }}
          isSaving={isCandidateSubmitting}
          errorMessage={candidateFormError}
          initialCandidate={{
            fullName: candidateToEdit.fullName,
            resume: candidateToEdit.resume,
            interviewIds: candidateToEdit.interviewId ? [candidateToEdit.interviewId] : []
          }}
          mode="edit"
        />
      );

    case 'competency-pillars':
      if (!matrix) {
        setCurrentState('interviewer-dashboard');
        return null;
      }
      return (
        <CompetencyPillars
          matrix={matrix}
          onBack={handleBackToDashboard}
          onStartInterview={handleStartInterview}
          isProceeding={isProceeding}
          errorMessage={errorMessage}
        />
      );

    case 'interview-session':
      if (!currentSession || !sessionRubric) {
        return null;
      }
      return (
        <InterviewSessionPage
          assignment={currentSession}
          rubric={sessionRubric}
          messages={sessionMessages}
          autoAnswerEnabled={autoAnswerEnabled}
          candidateReplyLevel={candidateReplyLevel}
          onAutoAnswerToggle={handleAutoAnswerToggle}
          onCandidateReplyLevelChange={handleCandidateReplyLevelChange}
          onBackToDashboard={closeInterviewSession}
          onStartInterview={beginWarmup}
          isStarting={isStartingWarmup}
          sessionError={sessionError}
        />
      );

    case 'interview-rubric':
      if (!rubricData) {
        setCurrentState('interviewer-dashboard');
        return null;
      }
      return (
        <InterviewRubric
          data={rubricData}
          onBack={() => {
            setErrorMessage(null);
            setCurrentState('competency-pillars');
          }}
          onBackToDashboard={() => {
            setErrorMessage(null);
            setCurrentState('interviewer-overview');
          }}
        />
      );

    default:
      return (
        <InterviewerOverview
          interviews={interviews}
          candidates={candidates}
          onCreateInterview={() => {
            setErrorMessage(null);
            setCurrentState('interviewer-dashboard');
          }}
          onAddCandidate={() => {
            setCandidateFormError(null);
            setCandidateToEdit(null);
            setCurrentState('candidate-intake');
          }}
          onStartInterview={launchInterviewFromDashboard}
          onRedoInterview={launchInterviewFromDashboard}
          onViewRubric={(interviewId) => {
            setCandidateFormError(null);
            void handleStartInterview(interviewId);
          }}
          onEditCandidate={handleEditCandidate}
          isLoadingInterviews={isLoadingInterviews}
          isLoadingCandidates={isLoadingCandidates}
          interviewsError={interviewsError}
          candidatesError={candidatesError}
          isProcessingInterview={isProceeding}
        />
      );
  }
}
