import React, { useMemo, useState } from "react";
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

export function InterviewSessionPage({
  assignment,
  onBackToDashboard,
}: InterviewSessionPageProps) {
  const [autoGenerate, setAutoGenerate] = useState(1);
  const [autoSend, setAutoSend] = useState(0);

  const chatMessages = useMemo<ChatMessage[]>(() => {
    return [
      {
        id: "1",
        speaker: "System",
        content:
          "Interview session initialized. Provide a warm introduction and outline the interview structure.",
        tone: "neutral",
      },
      {
        id: "2",
        speaker: "Interviewer",
        content: `Hi ${assignment.candidateName}, thanks for joining today. We will walk through a few scenario questions to understand your approach to ${assignment.jobTitle.toLowerCase()}.`,
        tone: "positive",
      },
      {
        id: "3",
        speaker: "Candidate",
        content:
          "Excited to be here! Looking forward to discussing my experience and learning more about the role.",
        tone: "positive",
      },
      {
        id: "4",
        speaker: "Interviewer",
        content:
          "Great. Let’s start with a situation where you owned a data project from end to end. How did you align the team on the success criteria?",
        tone: "neutral",
      },
    ];
  }, [assignment.candidateName, assignment.jobTitle]);

  const criteriaRows = useMemo<CriterionRow[]>(() => {
    return [
      {
        competency: "Communication",
        criterion: "Clarifies ambiguous requirements with stakeholders",
        weight: 20,
        achievedLevel: 3,
        rawScore: 12,
      },
      {
        competency: "Technical Depth",
        criterion: "Chooses appropriate modelling techniques for the problem",
        weight: 25,
        achievedLevel: 4,
        rawScore: 18,
      },
      {
        competency: "Execution",
        criterion:
          "Breaks work into measurable milestones with risks identified",
        weight: 25,
        achievedLevel: 3,
        rawScore: 15,
      },
      {
        competency: "Collaboration",
        criterion:
          "Drives alignment across functions with proactive communication",
        weight: 15,
        achievedLevel: 4,
        rawScore: 12,
      },
      {
        competency: "Ownership",
        criterion: "Reflects on outcomes and proposes clear next steps",
        weight: 15,
        achievedLevel: 2,
        rawScore: 7,
      },
    ];
  }, []);

  const competencyScores = useMemo<CompetencySummary[]>(() => {
    return [
      { competency: "Communication", score: 64 },
      { competency: "Technical Depth", score: 78 },
      { competency: "Execution", score: 70 },
      { competency: "Collaboration", score: 82 },
      { competency: "Ownership", score: 48 },
    ];
  }, []);

  const stageProgress = 42;
  const stageName = "Scenario Deep Dive";
  const activeCompetency = "Technical Depth";
  const questionsAsked = 4;
  const timeElapsed = "08:14";
  const overallScore = 67;

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
            <div className="rounded-lg border bg-background p-4">
              <ScrollArea className="h-[25rem] pr-4">
                <div className="flex flex-col gap-4">
                  {chatMessages.map((message) => (
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
                  ))}
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
              <Button type="button" size="lg" className="min-w-[9rem]">
                <Play className="h-4 w-4" />
                Start
              </Button>
              <Button
                type="button"
                size="lg"
                variant="secondary"
                className="min-w-[9rem]"
              >
                <Pause className="h-4 w-4" />
                Pause
              </Button>
              <Button
                type="button"
                size="lg"
                variant="destructive"
                className="min-w-[9rem]"
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
                      <Badge variant="outline">{entry.score}</Badge>
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
                  {overallScore}
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
