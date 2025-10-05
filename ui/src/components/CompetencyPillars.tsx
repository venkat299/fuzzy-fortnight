import React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Separator } from './ui/separator';
import { ArrowLeft, Brain, Code, Users, Lightbulb, MessageSquare } from 'lucide-react';

interface CompetencyPillar {
  id: string;
  name: string;
  description: string;
  icon: React.ReactNode;
  skills: string[];
}

interface InterviewData {
  jobTitle: string;
  jobDescription: string;
  experienceYears: string;
}

interface CompetencyPillarsProps {
  interviewData: InterviewData;
  onBack: () => void;
  onStartInterview: () => void;
}

export function CompetencyPillars({ interviewData, onBack, onStartInterview }: CompetencyPillarsProps) {
  // Generate competency pillars based on job description
  const generateCompetencyPillars = (jobData: InterviewData): CompetencyPillar[] => {
    // Always return exactly 5 competency pillars
    const corePillars: CompetencyPillar[] = [
      {
        id: 'technical',
        name: 'Technical Competency',
        description: 'Core technical skills and knowledge required for the role',
        icon: <Code className="h-5 w-5" />,
        skills: ['Programming Languages', 'System Design', 'Problem Solving', 'Code Quality']
      },
      {
        id: 'leadership',
        name: 'Leadership & Collaboration',
        description: 'Ability to lead teams and work effectively with others',
        icon: <Users className="h-5 w-5" />,
        skills: ['Team Leadership', 'Cross-functional Collaboration', 'Mentoring', 'Conflict Resolution']
      },
      {
        id: 'innovation',
        name: 'Innovation & Creativity',
        description: 'Capacity for creative thinking and driving innovation',
        icon: <Lightbulb className="h-5 w-5" />,
        skills: ['Creative Problem Solving', 'Process Improvement', 'Innovation Mindset', 'Adaptability']
      },
      {
        id: 'communication',
        name: 'Communication & Influence',
        description: 'Effective communication and stakeholder management',
        icon: <MessageSquare className="h-5 w-5" />,
        skills: ['Stakeholder Management', 'Presentation Skills', 'Written Communication', 'Influence']
      },
      {
        id: 'learning',
        name: 'Learning & Growth',
        description: 'Continuous learning and professional development',
        icon: <Brain className="h-5 w-5" />,
        skills: ['Continuous Learning', 'Adaptability', 'Growth Mindset', 'Self-Reflection']
      }
    ];

    return corePillars;
  };

  const competencyPillars = generateCompetencyPillars(interviewData);

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
              {interviewData.jobTitle} • {interviewData.experienceYears} years experience
            </p>
          </div>
          <Button onClick={onStartInterview} size="lg">
            Start Interview
          </Button>
        </div>

        {/* Summary Card */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle>Interview Summary</CardTitle>
            <CardDescription>
              Based on the job requirements, we've identified 5 key competency areas to evaluate.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {competencyPillars.map((pillar) => (
                <Badge key={pillar.id} variant="secondary" className="flex items-center gap-1">
                  {pillar.icon}
                  {pillar.name}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Competency Pillars Grid */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6">
          {competencyPillars.map((pillar) => (
            <Card key={pillar.id} className="h-full">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  {pillar.icon}
                  {pillar.name}
                </CardTitle>
                <CardDescription>{pillar.description}</CardDescription>
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
          <Button onClick={onStartInterview} size="lg">
            Proceed to Interview
          </Button>
        </div>
      </div>
    </div>
  );
}