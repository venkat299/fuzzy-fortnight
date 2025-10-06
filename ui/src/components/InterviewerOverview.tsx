import React from 'react';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { ArrowRight, FilePlus2, UserPlus } from 'lucide-react';

interface InterviewOverviewItem {
  interviewId: string;
  jobTitle: string;
  jobDescription: string;
  experienceYears: string;
  status: string;
  createdAt: string;
}

interface CandidateOverviewItem {
  candidateId: string;
  fullName: string;
  resume: string;
  interviewId: string | null;
  status: string;
  createdAt: string;
}

interface InterviewerOverviewProps {
  interviews: InterviewOverviewItem[];
  candidates: CandidateOverviewItem[];
  onCreateInterview: () => void;
  onAddCandidate: () => void;
  isLoadingInterviews: boolean;
  isLoadingCandidates: boolean;
  interviewsError: string | null;
  candidatesError: string | null;
}

const truncate = (value: string, max = 120) => {
  if (!value) {
    return '—';
  }
  return value.length <= max ? value : `${value.slice(0, max)}…`;
};

const formatDate = (value: string) => {
  if (!value) {
    return '—';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short'
  }).format(date);
};

const statusVariant = (status: string) => {
  const normalized = status.toLowerCase();
  if (normalized.includes('ready') || normalized.includes('completed')) {
    return 'default' as const;
  }
  if (normalized.includes('pending') || normalized.includes('draft')) {
    return 'secondary' as const;
  }
  if (normalized.includes('rejected') || normalized.includes('failed')) {
    return 'destructive' as const;
  }
  return 'outline' as const;
};

export function InterviewerOverview({
  interviews,
  candidates,
  onCreateInterview,
  onAddCandidate,
  isLoadingInterviews,
  isLoadingCandidates,
  interviewsError,
  candidatesError
}: InterviewerOverviewProps) {
  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <div className="mx-auto flex max-w-6xl flex-col gap-8">
        <header className="flex flex-col gap-2">
          <p className="text-sm font-medium text-sky-600">Interviewer workspace</p>
          <h1 className="text-3xl font-semibold text-slate-900">Dashboard</h1>
          <p className="text-sm text-muted-foreground">Quickly launch new interviews and track candidates in one place.</p>
        </header>

        <section className="grid gap-4 md:grid-cols-2">
          <Card className="border-dashed">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <FilePlus2 className="h-5 w-5 text-sky-600" />
                Add JD / Interview
              </CardTitle>
              <CardDescription>Launch a new interview by analyzing a job description.</CardDescription>
            </CardHeader>
            <CardFooter>
              <Button onClick={onCreateInterview} className="inline-flex items-center gap-2">
                Go to preparation
                <ArrowRight className="h-4 w-4" />
              </Button>
            </CardFooter>
          </Card>

          <Card className="border-dashed">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <UserPlus className="h-5 w-5 text-emerald-600" />
                Add candidate details
              </CardTitle>
              <CardDescription>Capture candidate information and assign interviews.</CardDescription>
            </CardHeader>
            <CardFooter>
              <Button variant="secondary" onClick={onAddCandidate} className="inline-flex items-center gap-2">
                Add candidate
                <ArrowRight className="h-4 w-4" />
              </Button>
            </CardFooter>
          </Card>
        </section>

        <section className="space-y-4">
          <div>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-slate-900">Interviews</h2>
              {isLoadingInterviews && <span className="text-xs text-muted-foreground">Loading…</span>}
            </div>
            <Card>
              <CardContent className="p-0">
                {interviews.length === 0 ? (
                  <div className="p-6 text-sm text-muted-foreground">
                    {interviewsError ?? 'No interviews recorded yet.'}
                  </div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>ID</TableHead>
                        <TableHead>Job title</TableHead>
                        <TableHead>Experience</TableHead>
                        <TableHead>Description</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Created</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {interviews.map((item) => (
                        <TableRow key={item.interviewId}>
                          <TableCell className="font-mono text-xs text-muted-foreground">{item.interviewId}</TableCell>
                          <TableCell className="font-medium">{item.jobTitle || '—'}</TableCell>
                          <TableCell className="text-sm text-muted-foreground">{item.experienceYears || '—'}</TableCell>
                          <TableCell className="max-w-[260px] whitespace-normal text-sm text-muted-foreground">
                            {truncate(item.jobDescription)}
                          </TableCell>
                          <TableCell>
                            <Badge variant={statusVariant(item.status)} className="capitalize">
                              {item.status || '—'}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-sm text-muted-foreground">{formatDate(item.createdAt)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
                {interviewsError && interviews.length > 0 && (
                  <div className="border-t border-dashed border-slate-200 bg-slate-50 px-4 py-2 text-xs text-red-600">
                    {interviewsError}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <div>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-slate-900">Candidates</h2>
              {isLoadingCandidates && <span className="text-xs text-muted-foreground">Loading…</span>}
            </div>
            <Card>
              <CardContent className="p-0">
                {candidates.length === 0 ? (
                  <div className="p-6 text-sm text-muted-foreground">
                    {candidatesError ?? 'No candidates captured yet.'}
                  </div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>ID</TableHead>
                        <TableHead>Name</TableHead>
                        <TableHead>Resume</TableHead>
                        <TableHead>Interview</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Created</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {candidates.map((candidate) => (
                        <TableRow key={candidate.candidateId}>
                          <TableCell className="font-mono text-xs text-muted-foreground">{candidate.candidateId}</TableCell>
                          <TableCell className="font-medium">{candidate.fullName || '—'}</TableCell>
                          <TableCell className="max-w-[260px] whitespace-normal text-sm text-muted-foreground">
                            {truncate(candidate.resume)}
                          </TableCell>
                          <TableCell className="font-mono text-xs text-muted-foreground">
                            {candidate.interviewId ?? '—'}
                          </TableCell>
                          <TableCell>
                            <Badge variant={statusVariant(candidate.status)} className="capitalize">
                              {candidate.status || '—'}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-sm text-muted-foreground">{formatDate(candidate.createdAt)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
                {candidatesError && candidates.length > 0 && (
                  <div className="border-t border-dashed border-slate-200 bg-slate-50 px-4 py-2 text-xs text-red-600">
                    {candidatesError}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </section>
      </div>
    </div>
  );
}
