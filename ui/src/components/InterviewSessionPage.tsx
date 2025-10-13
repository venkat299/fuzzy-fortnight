import React, { useCallback, useEffect, useMemo, useState } from "react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import type { InterviewAssignment } from "./InterviewerOverview";

interface RubricAnchor {
  level: number;
  text: string;
}

interface RubricCriterion {
  name: string;
  weight: number;
  anchors: RubricAnchor[];
}

interface RubricEntry {
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
  rubrics: RubricEntry[];
}

interface InterviewSessionPageProps {
  assignment: InterviewAssignment;
  rubric: InterviewRubricData;
  messages: ChatMessage[];
  autoGenerateEnabled: boolean;
  autoAnswerEnabled: boolean;
  candidateReplyLevel: number;
  draftMessage: string;
  isGeneratingDraft: boolean;
  isSendingDraft: boolean;
  onAutoGenerateToggle: (enabled: boolean) => void;
  onAutoAnswerToggle: (enabled: boolean) => void;
  onCandidateReplyLevelChange: (level: number) => void;
  onDraftChange: (value: string) => void;
  onSendCandidateReply: () => void;
  onBackToDashboard: () => void;
  onStartInterview: () => Promise<void>;
  isStarting: boolean;
  sessionError: string | null;
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
  rubric,
  messages,
  autoGenerateEnabled,
  autoAnswerEnabled,
  candidateReplyLevel,
  draftMessage,
  isGeneratingDraft,
  isSendingDraft,
  onAutoGenerateToggle,
  onAutoAnswerToggle,
  onCandidateReplyLevelChange,
  onDraftChange,
  onSendCandidateReply,
  onBackToDashboard,
  onStartInterview,
  isStarting,
  sessionError,
}: InterviewSessionPageProps) {
  const [localReplyLevel, setLocalReplyLevel] = useState(candidateReplyLevel);
  const chatMessages = useMemo(() => messages, [messages]);
  const hasStarted = chatMessages.length > 0;
  const startLabel = isStarting ? "Starting..." : hasStarted ? "Started" : "Start";

  useEffect(() => {
    setLocalReplyLevel(candidateReplyLevel);
  }, [candidateReplyLevel]);

  const handleReplyLevelChange = useCallback(
    (value: string) => {
      if (!autoAnswerEnabled) {
        return;
      }
      const parsed = Number.parseInt(value, 10);
      if (!Number.isFinite(parsed)) {
        return;
      }
      const level = Math.min(5, Math.max(1, Math.round(parsed)));
      setLocalReplyLevel(level);
      onCandidateReplyLevelChange(level);
    },
    [autoAnswerEnabled, onCandidateReplyLevelChange],
  );

  const criteriaRows = useMemo<CriterionRow[]>(() => {
    const rows: CriterionRow[] = [];
    rubric.rubrics.forEach((entry) => {
      const competencyName = entry.competency.trim();
      if (!competencyName) {
        return;
      }
      entry.criteria.forEach((criterion) => {
        const criterionName = criterion.name.trim();
        if (!criterionName) {
          return;
        }
        const weightValue = Number.isFinite(criterion.weight)
          ? Math.max(0, Math.round(criterion.weight * 1000) / 10)
          : 0;
        rows.push({
          competency: competencyName,
          criterion: criterionName,
          weight: weightValue,
          achievedLevel: 1,
          rawScore: 0,
        });
      });
    });
    return rows;
  }, [rubric]);

  const competencyScores = useMemo<CompetencySummary[]>(() => {
    const seen = new Set<string>();
    const scores: CompetencySummary[] = [];
    rubric.rubrics.forEach((entry) => {
      const name = entry.competency.trim();
      if (!name || seen.has(name)) {
        return;
      }
      seen.add(name);
      scores.push({ competency: name, score: 0 });
    });
    return scores;
  }, [rubric]);

  const firstCriterion = criteriaRows[0];
  const stageProgress = 0;
  const stageName = firstCriterion ? `Focus: ${firstCriterion.criterion}` : "Scenario kickoff";
  const activeCompetency = firstCriterion ? firstCriterion.competency : "—";
  const questionsAsked = 0;
  const timeElapsed = "00:00";
  const overallScore = 0;

  const formatWeight = (weight: number) => {
    if (Number.isInteger(weight)) {
      return `${weight}%`;
    }
    return `${weight.toFixed(1)}%`;
  };

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
                value={draftMessage}
                onChange={(event) => {
                  onDraftChange(event.target.value);
                }}
                disabled={isGeneratingDraft}
              />
              <Button
                type="button"
                className="lg:h-full lg:min-w-[9rem]"
                variant="secondary"
                onClick={() => {
                  onSendCandidateReply();
                }}
                disabled={
                  isSendingDraft || isGeneratingDraft || draftMessage.trim().length === 0
                }
              >
                <Send className="h-4 w-4" />
                {isSendingDraft ? "Sending..." : "Send"}
              </Button>
            </div>

            <div className="flex flex-wrap items-center justify-end gap-3">
              <Button
                type="button"
                size="lg"
                className="min-w-[9rem]"
                onClick={() => {
                  void onStartInterview();
                }}
                disabled={isStarting || hasStarted}
              >
                <Play className="h-4 w-4" />
                {startLabel}
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
              <div className="flex items-center gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                <div className="space-y-1">
                  <Label className="text-xs font-medium text-slate-700">
                    Auto-generate
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    {autoGenerateEnabled
                      ? isGeneratingDraft
                        ? "Generating..."
                        : "Enabled"
                      : "Disabled"}
                  </p>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant={autoGenerateEnabled ? "default" : "outline"}
                  onClick={() => {
                    onAutoGenerateToggle(!autoGenerateEnabled);
                  }}
                >
                  {autoGenerateEnabled ? "Disable" : "Enable"}
                </Button>
              </div>
              <div className="flex items-center gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                <div className="space-y-1">
                  <Label className="text-xs font-medium text-slate-700">
                    Auto-send
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    {autoAnswerEnabled ? "Enabled" : "Disabled"}
                  </p>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant={autoAnswerEnabled ? "default" : "outline"}
                  onClick={() => {
                    onAutoAnswerToggle(!autoAnswerEnabled);
                  }}
                >
                  {autoAnswerEnabled ? "Disable" : "Enable"}
                </Button>
                <div className="space-y-1">
                  <Label className="text-xs font-medium text-slate-700">
                    Reply level
                  </Label>
                  <div className="flex items-center gap-2">
                    <Select
                      value={String(localReplyLevel)}
                      onValueChange={handleReplyLevelChange}
                      disabled={!autoAnswerEnabled}
                    >
                      <SelectTrigger className="w-28">
                        <SelectValue aria-label={`Candidate reply level ${localReplyLevel}`} />
                      </SelectTrigger>
                      <SelectContent>
                        {[1, 2, 3, 4, 5].map((level) => (
                          <SelectItem key={level} value={String(level)}>
                            Level {level}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <span className="text-xs font-medium text-slate-700">
                      {autoAnswerEnabled ? `Level ${localReplyLevel}` : "Enable to adjust"}
                    </span>
                  </div>
                </div>
              </div>
            </div>
            {sessionError ? (
              <div className="w-full text-right">
                <p className="text-sm text-destructive">{sessionError}</p>
              </div>
            ) : null}
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
                    <TableCell>{formatWeight(row.weight)}</TableCell>
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
