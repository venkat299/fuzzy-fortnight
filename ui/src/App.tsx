import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { InterviewerDashboard } from './components/InterviewerDashboard';
import { CompetencyPillars } from './components/CompetencyPillars';
import { InterviewRubric } from './components/InterviewRubric';
import { InterviewerOverview } from './components/InterviewerOverview';
import { CandidateFormData, CandidateIntakeForm } from './components/CandidateIntakeForm';

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
  | 'competency-pillars'
  | 'interview-rubric';

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

  const handleCreateCandidate = async (data: CandidateFormData) => {
    setCandidateFormError(null);
    setIsCandidateSubmitting(true);
    try {
      const response = await fetch('/api/candidates', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          full_name: data.fullName,
          resume: data.resume,
          interview_id: data.interviewId,
          status: data.status
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
            setCurrentState('candidate-intake');
          }}
          isLoadingInterviews={isLoadingInterviews}
          isLoadingCandidates={isLoadingCandidates}
          interviewsError={interviewsError}
          candidatesError={candidatesError}
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
        <CandidateIntakeForm
          interviews={interviews.map((item) => ({ interviewId: item.interviewId, jobTitle: item.jobTitle }))}
          onSubmit={handleCreateCandidate}
          onCancel={() => {
            setCandidateFormError(null);
            setCurrentState('interviewer-overview');
          }}
          isSubmitting={isCandidateSubmitting}
          errorMessage={candidateFormError}
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
            setCurrentState('candidate-intake');
          }}
          isLoadingInterviews={isLoadingInterviews}
          isLoadingCandidates={isLoadingCandidates}
          interviewsError={interviewsError}
          candidatesError={candidatesError}
        />
      );
  }
}
