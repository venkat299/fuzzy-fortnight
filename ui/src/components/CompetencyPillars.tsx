import React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { ArrowLeft } from 'lucide-react';

interface CompetencyPillar {
  name: string;
  skills: string[];
}

interface CompetencyMatrix {
  jobTitle: string;
  experienceYears: string;
  competencyAreas: CompetencyPillar[];
  interviewId: string;
}

interface CompetencyPillarsProps {
  matrix: CompetencyMatrix;
  onBack: () => void;
  onStartInterview: (interviewId: string) => void;
  isProceeding: boolean;
  errorMessage: string | null;
}

export function CompetencyPillars({ matrix, onBack, onStartInterview, isProceeding, errorMessage }: CompetencyPillarsProps) {
  const competencyPillars = matrix.competencyAreas;
  const handleProceed = () => {
    if (!matrix.interviewId) {
      return;
    }
    onStartInterview(matrix.interviewId);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <Button variant="ghost" onClick={onBack} className="mb-4 flex items-center gap-2">
              <ArrowLeft className="h-4 w-4" />
              Back to Interview Setup
            </Button>
            <h1>Competency Pillars</h1>
            <p className="text-muted-foreground">
              {matrix.jobTitle} • {matrix.experienceYears} years experience
            </p>
          </div>
          <Button onClick={handleProceed} size="lg" disabled={isProceeding || !matrix.interviewId}>
            {isProceeding ? 'Loading Rubric…' : 'Start Interview'}
          </Button>
        </div>

        {/* Summary Card */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle>Interview Summary</CardTitle>
            <CardDescription>
              Based on the job requirements, we've identified {competencyPillars.length} key competency areas to evaluate.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {competencyPillars.map((pillar) => (
                <Badge key={pillar.name} variant="secondary" className="flex items-center gap-1">
                  {pillar.name}
                </Badge>
              ))}
            </div>
            {errorMessage && (
              <p className="mt-4 text-sm text-red-600" role="alert">
                {errorMessage}
              </p>
            )}
          </CardContent>
        </Card>

        {/* Competency Pillars Grid */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6">
          {competencyPillars.map((pillar) => (
            <Card key={pillar.name} className="h-full">
              <CardHeader>
                <CardTitle>{pillar.name}</CardTitle>
              </CardHeader>
              <CardContent>
                {/* Key Skills */}
                <div>
                  <h4 className="mb-2">Key Skills to Evaluate</h4>
                  <div className="flex flex-wrap gap-1">
                    {pillar.skills.map((skill) => (
                      <Badge key={skill} variant="outline" className="text-xs">
                        {skill}
                      </Badge>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Action Buttons */}
        <div className="mt-8 flex gap-4 justify-center">
          <Button variant="outline" onClick={onBack}>
            Modify Interview Setup
          </Button>
          <Button onClick={handleProceed} size="lg" disabled={isProceeding || !matrix.interviewId}>
            {isProceeding ? 'Loading Rubric…' : 'Proceed to Interview'}
          </Button>
        </div>
      </div>
    </div>
  );
}
