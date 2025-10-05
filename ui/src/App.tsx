import React, { useState } from 'react';
import { InterviewerDashboard } from './components/InterviewerDashboard';
import { CompetencyPillars } from './components/CompetencyPillars';

interface InterviewData {
  jobTitle: string;
  jobDescription: string;
  experienceYears: string;
}

type AppState = 'interviewer-dashboard' | 'competency-pillars';

export default function App() {
  const [currentState, setCurrentState] = useState<AppState>('interviewer-dashboard');
  const [interviewData, setInterviewData] = useState<InterviewData | null>(null);

  const handleSubmitInterview = (data: InterviewData) => {
    setInterviewData(data);
    setCurrentState('competency-pillars');
  };

  const handleBackToDashboard = () => {
    setCurrentState('interviewer-dashboard');
  };

  const handleStartInterview = () => {
    // This would typically navigate to the actual interview interface
    alert('Interview functionality would be implemented here. This would start the actual AI-powered interview process.');
  };

  // Render based on current state
  switch (currentState) {
    case 'interviewer-dashboard':
      return (
        <InterviewerDashboard
          onSubmitInterview={handleSubmitInterview}
        />
      );
    
    case 'competency-pillars':
      if (!interviewData) {
        setCurrentState('interviewer-dashboard');
        return null;
      }
      return (
        <CompetencyPillars
          interviewData={interviewData}
          onBack={handleBackToDashboard}
          onStartInterview={handleStartInterview}
        />
      );
    
    default:
      return (
        <InterviewerDashboard
          onSubmitInterview={handleSubmitInterview}
        />
      );
  }
}