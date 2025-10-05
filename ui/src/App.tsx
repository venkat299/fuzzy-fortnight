import React, { useMemo, useState } from 'react';
import { InterviewerDashboard } from './components/InterviewerDashboard';
import { CompetencyPillars } from './components/CompetencyPillars';

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
}

type AppState = 'interviewer-dashboard' | 'competency-pillars';

export default function App() {
  const [currentState, setCurrentState] = useState<AppState>('interviewer-dashboard');
  const [interviewData, setInterviewData] = useState<InterviewData | null>(null);
  const [matrix, setMatrix] = useState<CompetencyMatrix | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const normalizeMatrix = (payload: unknown, fallback: InterviewData): CompetencyMatrix => {
    if (!payload || typeof payload !== 'object') {
      return {
        jobTitle: fallback.jobTitle,
        experienceYears: fallback.experienceYears,
        competencyAreas: []
      };
    }
    const data = payload as Record<string, unknown>;
    const rawAreas = Array.isArray(data.competency_areas) ? data.competency_areas : [];
    const competencyAreas: CompetencyArea[] = rawAreas.map((item) => {
      if (!item || typeof item !== 'object') {
        return { name: '', skills: [] };
      }
      const entry = item as Record<string, unknown>;
      const skillsSource = Array.isArray(entry.skills) ? entry.skills : [];
      return {
        name: String(entry.name ?? ''),
        skills: skillsSource.map((skill) => String(skill ?? '')).filter((skill) => skill.trim().length > 0)
      };
    }).filter((area) => area.name.trim().length > 0 || area.skills.length > 0);
    return {
      jobTitle: String(data.job_title ?? fallback.jobTitle),
      experienceYears: String(data.experience_years ?? fallback.experienceYears),
      competencyAreas
    };
  };

  const handleSubmitInterview = async (data: InterviewData) => {
    setErrorMessage(null);
    setIsLoading(true);
    setInterviewData(data);
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
        const detail = errorPayload && typeof errorPayload.detail === 'string' ? errorPayload.detail : 'Failed to analyze job description.';
        throw new Error(detail);
      }
      const payload = await response.json();
      const normalized = normalizeMatrix(payload, data);
      setMatrix(normalized);
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

  const handleStartInterview = () => {
    alert('Interview functionality would be implemented here. This would start the actual AI-powered interview process.');
  };

  const dashboardInitialData = useMemo(() => interviewData ?? undefined, [interviewData]);

  switch (currentState) {
    case 'interviewer-dashboard':
      return (
        <InterviewerDashboard
          onSubmitInterview={handleSubmitInterview}
          initialData={dashboardInitialData}
          isLoading={isLoading}
          errorMessage={errorMessage}
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
        />
      );

    default:
      return (
        <InterviewerDashboard
          onSubmitInterview={handleSubmitInterview}
          initialData={dashboardInitialData}
          isLoading={isLoading}
          errorMessage={errorMessage}
        />
      );
  }
}
