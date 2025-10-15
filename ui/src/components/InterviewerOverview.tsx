import React, { useMemo } from "react";
import {
  ArrowRight,
  FilePlus2,
  UserPlus,
  Eye,
  Pencil,
  RefreshCcw,
  Play,
  FileText,
  Download,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "./ui/card";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/table";
import { Avatar, AvatarFallback } from "./ui/avatar";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./ui/tooltip";
import { Skeleton } from "./ui/skeleton";

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
  onStartInterview: (assignment: InterviewAssignment) => void;
  onRedoInterview: (assignment: InterviewAssignment) => void;
  onViewRubric: (interviewId: string) => void;
  onEditCandidate: (candidateId: string) => void;
  isLoadingInterviews: boolean;
  isLoadingCandidates: boolean;
  interviewsError: string | null;
  candidatesError: string | null;
  isProcessingInterview: boolean;
}

export interface InterviewAssignment {
  interviewId: string;
  jobTitle: string;
  candidateId: string;
  candidateName: string;
  status: "scheduled" | "finished";
}

const truncate = (value: string, max = 25) => {
  if (!value) {
    return "—";
  }
  return value.length <= max ? value : `${value.slice(0, max)}…`;
};

const formatDate = (value: string) => {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
};

const normalizeInterviewStatus = (status: string): "scheduled" | "finished" => {
  const normalized = status.trim().toLowerCase();
  if (normalized.includes("finish") || normalized.includes("complete")) {
    return "finished";
  }
  return "scheduled";
};

const makeInitials = (value: string, fallback = "—") => {
  if (!value) {
    return fallback;
  }
  const segments = value.trim().split(/\s+/);
  if (segments.length === 1) {
    return segments[0].slice(0, 2).toUpperCase();
  }
  return `${segments[0][0] ?? ""}${segments[segments.length - 1][0] ?? ""}`.toUpperCase();
};

const statusStyles = (status: string) => {
  const label = status || "—";
  const normalized = label.toLowerCase();
  if (
    normalized.includes("ready") ||
    normalized.includes("finish") ||
    normalized.includes("complete")
  ) {
    return {
      badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-100",
      dotClass: "bg-emerald-500",
      label,
    };
  }
  if (
    normalized.includes("pending") ||
    normalized.includes("draft") ||
    normalized.includes("schedule")
  ) {
    return {
      badgeClass: "bg-amber-50 text-amber-700 border-amber-100",
      dotClass: "bg-amber-500",
      label,
    };
  }
  if (normalized.includes("rejected") || normalized.includes("fail")) {
    return {
      badgeClass: "bg-rose-50 text-rose-700 border-rose-100",
      dotClass: "bg-rose-500",
      label,
    };
  }
  return {
    badgeClass: "bg-slate-100 text-slate-600 border-slate-200",
    dotClass: "bg-slate-400",
    label,
  };
};

const renderStatusBadge = (status: string) => {
  const { badgeClass, dotClass, label } = statusStyles(status);
  return (
    <Badge className={`relative pl-5 ${badgeClass}`}>
      <span
        className={`absolute left-2 top-1/2 size-1.5 -translate-y-1/2 rounded-full ${dotClass}`}
      />
      {label}
    </Badge>
  );
};

const renderSkeletonRows = (columns: number) =>
  Array.from({ length: 3 }).map((_, index) => (
    <TableRow key={`skeleton-${index}`} className="bg-transparent">
      <TableCell colSpan={columns} className="py-3">
        <Skeleton className="h-10 w-full rounded-md" />
      </TableCell>
    </TableRow>
  ));

export function InterviewerOverview({
  interviews,
  candidates,
  onCreateInterview,
  onAddCandidate,
  onStartInterview,
  onRedoInterview,
  onViewRubric,
  onEditCandidate,
  isLoadingInterviews,
  isLoadingCandidates,
  interviewsError,
  candidatesError,
  isProcessingInterview,
}: InterviewerOverviewProps) {
  const assignments = useMemo<InterviewAssignment[]>(() => {
    return candidates
      .filter((candidate) => Boolean(candidate.interviewId))
      .map((candidate) => {
        const interview = interviews.find(
          (item) => item.interviewId === candidate.interviewId,
        );
        if (!candidate.interviewId) {
          return null;
        }
        return {
          interviewId: candidate.interviewId,
          jobTitle: interview?.jobTitle ?? "—",
          candidateId: candidate.candidateId,
          candidateName: candidate.fullName || "—",
          status: normalizeInterviewStatus(candidate.status || ""),
        };
      })
      .filter((entry): entry is InterviewAssignment => Boolean(entry));
  }, [candidates, interviews]);

  return (
    <TooltipProvider delayDuration={120}>
      <div className="min-h-screen bg-slate-50 p-6">
        <div className="mx-auto flex max-w-6xl flex-col gap-8">
          <header className="flex flex-col gap-3">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
              Interviewer workspace
            </p>
            <h1 className="text-4xl font-semibold leading-tight text-slate-900">
              Dashboard
            </h1>
            <p className="max-w-2xl text-sm text-slate-600">
              Quickly launch new interviews, monitor candidates in flight, and
              jump back into active rubrics without losing context.
            </p>
          </header>

          <section className="grid gap-6 md:grid-cols-2">
            <Card className="group relative overflow-hidden border-none bg-gradient-to-br from-white via-sky-50 to-white shadow-sm ring-1 ring-sky-100/80 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lg">
              <div className="pointer-events-none absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-sky-100/60 to-transparent opacity-80 group-hover:opacity-100" />
              <CardHeader className="space-y-3">
                <CardTitle className="flex items-center gap-3 text-lg font-semibold text-slate-900">
                  <span className="flex size-10 items-center justify-center rounded-full bg-sky-500/10 text-sky-600">
                    <FilePlus2 className="h-5 w-5" />
                  </span>
                  Add JD / Interview
                </CardTitle>
                <CardDescription className="text-sm text-slate-600">
                  Launch a new interview by analyzing a job description and
                  generating the supporting rubric.
                </CardDescription>
              </CardHeader>
              <CardFooter className="pt-0">
                <Button
                  onClick={onCreateInterview}
                  className="inline-flex items-center gap-2 rounded-full px-5 py-2 text-sm font-semibold shadow-sm transition-all duration-200 hover:shadow-md"
                >
                  Go to preparation
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </CardFooter>
            </Card>

            <Card className="group relative overflow-hidden border-none bg-gradient-to-br from-white via-emerald-50 to-white shadow-sm ring-1 ring-emerald-100/70 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lg">
              <div className="pointer-events-none absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-emerald-100/60 to-transparent opacity-80 group-hover:opacity-100" />
              <CardHeader className="space-y-3">
                <CardTitle className="flex items-center gap-3 text-lg font-semibold text-slate-900">
                  <span className="flex size-10 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-600">
                    <UserPlus className="h-5 w-5" />
                  </span>
                  Add candidate details
                </CardTitle>
                <CardDescription className="text-sm text-slate-600">
                  Capture candidate information, upload resumes, and associate
                  upcoming interviews.
                </CardDescription>
              </CardHeader>
              <CardFooter className="pt-0">
                <Button
                  variant="secondary"
                  onClick={onAddCandidate}
                  className="inline-flex items-center gap-2 rounded-full px-5 py-2 text-sm font-semibold shadow-sm transition-all duration-200 hover:shadow-md"
                >
                  Add candidate
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </CardFooter>
            </Card>
          </section>

          <section className="space-y-6">
            <div>
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-2xl font-semibold text-slate-900">
                  Interviews
                </h2>
                {isLoadingInterviews && (
                  <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
                    Loading…
                  </span>
                )}
              </div>
              <Card className="overflow-hidden border-none bg-white/75 shadow-sm ring-1 ring-slate-200/60 backdrop-blur-sm">
                <CardContent className="p-0">
                  {interviews.length === 0 ? (
                    isLoadingInterviews ? (
                      <div className="space-y-3 p-6">
                        {Array.from({ length: 3 }).map((_, index) => (
                          <Skeleton
                            key={`interview-skeleton-${index}`}
                            className="h-12 w-full rounded-xl"
                          />
                        ))}
                      </div>
                    ) : (
                      <div className="p-6 text-sm text-muted-foreground">
                        {interviewsError ?? "No interviews recorded yet."}
                      </div>
                    )
                  ) : (
                    <Table className="[&_thead]:bg-slate-50">
                      <TableHeader>
                        <TableRow>
                          <TableHead>Job title</TableHead>
                          <TableHead>Experience</TableHead>
                          <TableHead>Description</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead>Created</TableHead>
                          <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {interviews.map((item, index) => (
                          <TableRow
                            key={item.interviewId}
                            className="even:bg-slate-50/70 odd:bg-white transition-all duration-200"
                          >
                            <TableCell>
                              <div className="flex items-center gap-3">
                                <Avatar className="size-10 border border-slate-200/80 bg-white shadow-sm">
                                  <AvatarFallback className="bg-sky-100 text-sm font-semibold text-sky-700">
                                    {makeInitials(item.jobTitle || "Role")}
                                  </AvatarFallback>
                                </Avatar>
                                <div className="flex flex-col">
                                  <span className="font-medium text-slate-900">
                                    {item.jobTitle || "Untitled role"}
                                  </span>
                                  <span className="text-xs text-slate-500">
                                    Interview #{index + 1}
                                  </span>
                                </div>
                              </div>
                            </TableCell>
                            <TableCell className="text-sm text-slate-600">
                              {item.experienceYears || "—"}
                            </TableCell>
                            <TableCell className="max-w-[320px]">
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <span className="block cursor-help text-sm text-slate-500 line-clamp-2">
                                    {item.jobDescription
                                      ? truncate(item.jobDescription, 25)
                                      : "—"}
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent
                                  side="top"
                                  className="max-w-xs text-sm leading-relaxed"
                                >
                                  {item.jobDescription ||
                                    "No description available."}
                                </TooltipContent>
                              </Tooltip>
                            </TableCell>
                            <TableCell>
                              {renderStatusBadge(item.status)}
                            </TableCell>
                            <TableCell className="text-sm text-slate-600">
                              {formatDate(item.createdAt)}
                            </TableCell>
                            <TableCell className="flex justify-end">
                            <Button
                              size="sm"
                              variant="outline"
                              className="inline-flex items-center gap-1.5 rounded-full px-3"
                              onClick={() => onViewRubric(item.interviewId)}
                            >
                              <Eye className="h-3.5 w-3.5" />
                              View rubric
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              className="ml-2 inline-flex items-center gap-1.5 rounded-full px-3"
                              asChild
                            >
                              <a
                                href={`/api/interviews/${item.interviewId}/rubric.pdf`}
                                target="_blank"
                                rel="noreferrer"
                              >
                                <Download className="h-3.5 w-3.5" />
                                Download rubric
                              </a>
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                        {isLoadingInterviews && renderSkeletonRows(6)}
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
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-2xl font-semibold text-slate-900">
                  Candidates
                </h2>
                {isLoadingCandidates && (
                  <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
                    Loading…
                  </span>
                )}
              </div>
              <Card className="overflow-hidden border-none bg-white/75 shadow-sm ring-1 ring-slate-200/60 backdrop-blur-sm">
                <CardContent className="p-0">
                  {candidates.length === 0 ? (
                    isLoadingCandidates ? (
                      <div className="space-y-3 p-6">
                        {Array.from({ length: 3 }).map((_, index) => (
                          <Skeleton
                            key={`candidate-skeleton-${index}`}
                            className="h-12 w-full rounded-xl"
                          />
                        ))}
                      </div>
                    ) : (
                      <div className="p-6 text-sm text-muted-foreground">
                        {candidatesError ?? "No candidates captured yet."}
                      </div>
                    )
                  ) : (
                    <Table className="[&_thead]:bg-slate-50">
                      <TableHeader>
                        <TableRow>
                          <TableHead>Name</TableHead>
                          <TableHead>Resume</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead>Created</TableHead>
                          <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {candidates.map((candidate) => (
                          <TableRow
                            key={candidate.candidateId}
                            className="even:bg-slate-50/70 odd:bg-white transition-all duration-200"
                          >
                            <TableCell>
                              <div className="flex items-center gap-3">
                                <Avatar className="size-10 border border-slate-200/80 bg-white shadow-sm">
                                  <AvatarFallback className="bg-emerald-100 text-sm font-semibold text-emerald-700">
                                    {makeInitials(
                                      candidate.fullName ||
                                        candidate.candidateId,
                                    )}
                                  </AvatarFallback>
                                </Avatar>
                                <div className="flex flex-col">
                                  <span className="font-medium text-slate-900">
                                    {candidate.fullName || "Unnamed candidate"}
                                  </span>
                                  <span className="text-xs text-slate-500">
                                    {candidate.status
                                      ? `Status: ${candidate.status}`
                                      : "Status unknown"}
                                  </span>
                                </div>
                              </div>
                            </TableCell>
                            <TableCell className="max-w-[320px]">
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <span className="block cursor-help text-sm text-slate-500 line-clamp-2">
                                    {candidate.resume
                                      ? truncate(candidate.resume, 25)
                                      : "—"}
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent
                                  side="top"
                                  className="max-w-xs text-sm leading-relaxed"
                                >
                                  {candidate.resume || "No resume captured."}
                                </TooltipContent>
                              </Tooltip>
                            </TableCell>
                            <TableCell>
                              {renderStatusBadge(candidate.status)}
                            </TableCell>
                            <TableCell className="text-sm text-slate-600">
                              {formatDate(candidate.createdAt)}
                            </TableCell>
                            <TableCell className="flex justify-end">
                              <Button
                                size="sm"
                                variant="outline"
                                className="inline-flex items-center gap-1.5 rounded-full px-3"
                                onClick={() =>
                                  onEditCandidate(candidate.candidateId)
                                }
                              >
                                <Pencil className="h-3.5 w-3.5" />
                                Edit
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))}
                        {isLoadingCandidates && renderSkeletonRows(5)}
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

          <section className="space-y-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-2xl font-semibold text-slate-900">
                Interview assignments
              </h2>
            </div>
            <Card className="overflow-hidden border-none bg-white/75 shadow-sm ring-1 ring-slate-200/60 backdrop-blur-sm">
              <CardContent className="p-0">
                {assignments.length === 0 ? (
                  <div className="p-6 text-sm text-muted-foreground">
                    No candidate interview assignments yet.
                  </div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Job title</TableHead>
                        <TableHead>Candidate</TableHead>
                        <TableHead>Interview status</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {assignments.map((entry) => (
                        <TableRow
                          key={`${entry.interviewId}-${entry.candidateId}`}
                          className="even:bg-slate-50/70 odd:bg-white transition-all duration-200"
                        >
                          <TableCell className="font-medium text-slate-900">
                            {entry.jobTitle || "—"}
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center gap-3">
                              <Avatar className="size-9 border border-slate-200/80 bg-white shadow-sm">
                                <AvatarFallback className="bg-slate-100 text-xs font-semibold text-slate-600">
                                  {makeInitials(
                                    entry.candidateName || entry.candidateId,
                                  )}
                                </AvatarFallback>
                              </Avatar>
                              <span className="text-sm text-slate-600">
                                {entry.candidateName}
                              </span>
                            </div>
                          </TableCell>
                          <TableCell>
                            {renderStatusBadge(entry.status)}
                          </TableCell>
                          <TableCell className="flex justify-end gap-2">
                            <Button
                              size="sm"
                              className="inline-flex items-center gap-1.5 rounded-full px-3"
                              onClick={() => onStartInterview(entry)}
                              disabled={isProcessingInterview}
                            >
                              <Play className="h-3.5 w-3.5" />
                              Start interview
                            </Button>
                            <Button
                              size="sm"
                              variant="secondary"
                              className="inline-flex items-center gap-1.5 rounded-full px-3"
                              onClick={() => onRedoInterview(entry)}
                              disabled={isProcessingInterview}
                            >
                              <RefreshCcw className="h-3.5 w-3.5" />
                              Redo interview
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              className="inline-flex items-center gap-1.5 rounded-full px-3"
                              asChild
                            >
                              <a
                                href={`/api/interviews/${entry.interviewId}/sessions/${entry.candidateId}/report`}
                                target="_blank"
                                rel="noreferrer"
                              >
                                <FileText className="h-3.5 w-3.5" />
                                View report
                              </a>
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              className="inline-flex items-center gap-1.5 rounded-full px-3"
                              asChild
                            >
                              <a
                                href={`/api/interviews/${entry.interviewId}/sessions/${entry.candidateId}/report.pdf`}
                                target="_blank"
                                rel="noreferrer"
                              >
                                <Download className="h-3.5 w-3.5" />
                                Download PDF
                              </a>
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </section>
        </div>
      </div>
    </TooltipProvider>
  );
}
