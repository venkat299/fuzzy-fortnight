import React from 'react';
import { ArrowLeft, CheckCircle2 } from 'lucide-react';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Separator } from './ui/separator';

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

interface InterviewRubricProps {
  data: InterviewRubricData;
  onBack: () => void;
}

export function InterviewRubric({ data, onBack }: InterviewRubricProps) {
  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-6">
      <div className="max-w-6xl mx-auto space-y-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <Button variant="ghost" onClick={onBack} className="mb-4 flex items-center gap-2">
              <ArrowLeft className="h-4 w-4" />
              Back to Competencies
            </Button>
            <h1>Interview Rubric</h1>
            <p className="text-muted-foreground">
              {data.jobTitle} • {data.experienceYears} years experience
            </p>
          </div>
          <Badge variant="secondary" className="flex items-center gap-2 h-9 text-sm">
            <CheckCircle2 className="h-4 w-4 text-green-600" />
            {data.status || 'ready'}
          </Badge>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Interview Overview</CardTitle>
            <CardDescription>
              Review the detailed verbal-only rubric for each competency area before starting the conversation.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-6 md:grid-cols-2">
            <div>
              <p className="text-sm text-muted-foreground mb-2">Interview ID</p>
              <p className="font-medium text-sm md:text-base">{data.interviewId}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground mb-2">Competency Count</p>
              <p className="font-medium text-sm md:text-base">{data.rubrics.length}</p>
            </div>
          </CardContent>
        </Card>

        {data.rubrics.map((rubric) => (
          <Card key={rubric.competency} className="shadow-sm">
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <CardTitle>{rubric.competency}</CardTitle>
                  <CardDescription>
                    Band {rubric.band} • Minimum passing score {rubric.minPassScore.toFixed(1)}
                  </CardDescription>
                </div>
                <Badge variant="outline">{rubric.band}</Badge>
              </div>
              {rubric.bandNotes.length > 0 && (
                <div className="mt-4 grid gap-2 text-sm text-muted-foreground">
                  {rubric.bandNotes.map((note) => (
                    <p key={note}>{note}</p>
                  ))}
                </div>
              )}
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="overflow-x-auto rounded-md border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50">
                    <tr>
                      <th className="px-4 py-3 text-left font-semibold">Criterion</th>
                      <th className="px-4 py-3 text-left font-semibold">Weight</th>
                      {[1, 2, 3, 4, 5].map((level) => (
                        <th key={level} className="px-4 py-3 text-left font-semibold">
                          Level {level}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rubric.criteria.map((criterion) => (
                      <tr key={criterion.name} className="border-t">
                        <td className="align-top px-4 py-3 font-medium">{criterion.name}</td>
                        <td className="align-top px-4 py-3 text-muted-foreground">{criterion.weight.toFixed(2)}</td>
                        {[1, 2, 3, 4, 5].map((level) => {
                          const anchor = criterion.anchors.find((item) => item.level === level);
                          return (
                            <td key={level} className="align-top px-4 py-3 text-muted-foreground">
                              {anchor ? anchor.text : '—'}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {rubric.evidence.length > 0 && (
                <div>
                  <h4 className="mb-2">Suggested verbal probes</h4>
                  <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                    {rubric.evidence.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}

              {rubric.redFlags.length > 0 && (
                <div>
                  <Separator className="my-4" />
                  <h4 className="mb-2">Red flags to watch for</h4>
                  <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                    {rubric.redFlags.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
