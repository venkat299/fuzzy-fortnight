import React, { useMemo, useState } from "react";
import { ArrowLeft, Pause, Play, Send, Square } from "lucide-react";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Textarea } from "./ui/textarea";
import { Switch } from "./ui/switch";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "./ui/card";
import { Progress } from "./ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/table";
import type { InterviewAssignment } from "./InterviewerOverview";

interface InterviewSessionPageProps {
  assignment: InterviewAssignment;
  onBackToDashboard: () => void;
}

type MessageType = "system" | "interviewer" | "candidate";

type MessageSentiment = "neutral" | "positive" | "negative";

interface Message {
  id: string;
  type: MessageType;
  content: string;
  sentiment: MessageSentiment;
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
  const [messages, setMessages] = useState<Message[]>(() => [
    {
      id: "1",
      type: "system",
      content: "Beginning warmup.",
      sentiment: "neutral",
    },
    {
      id: "2",
      type: "interviewer",
      content:
        "I'm really excited to hear about your work with data pipelines and system optimization—how did you and your team decide what problems were worth solving through automation, and what made a difference in the end?",
      sentiment: "neutral",
    },
    {
      id: "3",
      type: "candidate",
      content:
        "Great question! We started by analyzing our most time-consuming manual processes and identified three key areas: data validation, report generation, and system monitoring. The breakthrough came when we automated the validation pipeline, which reduced processing time by 60%.",
      sentiment: "positive",
    },
  ]);
  const [inputValue, setInputValue] = useState("");
  const [isStarted, setIsStarted] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [autoGenerate, setAutoGenerate] = useState(true);
  const [autoSend, setAutoSend] = useState(false);

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

  const resolveSpeakerLabel = (type: MessageType) => {
    switch (type) {
      case "candidate":
        return "Candidate";
      case "interviewer":
        return "Interviewer";
      default:
        return "System";
    }
  };

  const handleSend = () => {
    if (!inputValue.trim()) {
      return;
    }

    const newMessage: Message = {
      id: Date.now().toString(),
      type: "interviewer",
      content: inputValue,
      sentiment: "neutral",
    };

    setMessages((previous) => [...previous, newMessage]);
    setInputValue("");
  };

  const handleStart = () => {
    setIsStarted(true);
    setIsPaused(false);
  };

  const handlePause = () => {
    setIsPaused(true);
  };

  const handleStop = () => {
    setIsStarted(false);
    setIsPaused(false);
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

  const chatContent = (
    <div className="rounded-3xl bg-white px-6 py-10 shadow-sm sm:p-12">
      <div className="mx-auto max-w-4xl space-y-10">
        <header className="space-y-2">
          <h1>Interview session</h1>
          <p className="text-muted-foreground">
            Monitor the conversation, capture notes, and drive the candidate
            experience.
          </p>
        </header>

        <div className="space-y-8">
          {messages.map((message) => {
            if (message.type === "system") {
              return (
                <div key={message.id} className="flex justify-center">
                  <div className="rounded-full bg-muted px-4 py-1.5 text-center">
                    <p className="text-sm font-medium text-muted-foreground">
                      {message.content}
                    </p>
                  </div>
                </div>
              );
            }

            const isCandidate = message.type === "candidate";

            return (
              <div key={message.id} className="flex">
                <div
                  className={`flex w-full flex-col gap-3 ${
                    isCandidate ? "items-end text-right" : "items-start"
                  }`}
                >
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    {isCandidate ? (
                      <>
                        <Badge variant="outline" className="text-xs font-medium">
                          {message.sentiment}
                        </Badge>
                        <span className="font-medium">
                          {resolveSpeakerLabel(message.type)}
                        </span>
                      </>
                    ) : (
                      <>
                        <span className="font-medium">
                          {resolveSpeakerLabel(message.type)}
                        </span>
                        <Badge variant="outline" className="text-xs font-medium">
                          {message.sentiment}
                        </Badge>
                      </>
                    )}
                  </div>
                  <div
                    className="max-w-[680px] rounded-2xl px-6 py-4 text-base leading-relaxed text-foreground shadow-[0_12px_40px_-24px_rgba(16,24,40,0.45)]"
                    style={{
                      backgroundColor: isCandidate ? "#DAC7F4" : "#CFE9D8",
                    }}
                  >
                    {message.content}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <div className="space-y-4">
          <Textarea
            placeholder="Draft prompts, capture coaching notes, or summarize key evidence..."
            value={inputValue}
            onChange={(event) => setInputValue(event.target.value)}
            rows={6}
            className="resize-none"
          />

          <div className="flex justify-end">
            <Button
              variant="ghost"
              size="sm"
              onClick={handleSend}
              className="flex items-center gap-2"
            >
              <Send className="h-4 w-4" />
              Send
            </Button>
          </div>
        </div>

        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <Button
              onClick={handleStart}
              disabled={isStarted && !isPaused}
              variant={isStarted && !isPaused ? "secondary" : "default"}
              className="flex items-center gap-2"
            >
              <Play className="h-4 w-4" />
              Start
            </Button>

            <Button
              onClick={handlePause}
              disabled={!isStarted || isPaused}
              variant="outline"
              className="flex items-center gap-2"
            >
              <Pause className="h-4 w-4" />
              Pause
            </Button>

            <Button
              onClick={handleStop}
              disabled={!isStarted}
              variant="destructive"
              className="flex items-center gap-2"
            >
              <Square className="h-4 w-4" />
              Stop
            </Button>
          </div>

          <div className="flex flex-wrap items-center gap-6">
            <div className="flex items-center gap-2">
              <Switch
                checked={autoGenerate}
                onCheckedChange={setAutoGenerate}
              />
              <span className="whitespace-nowrap text-sm">Auto-generate</span>
            </div>

            <div className="flex items-center gap-2">
              <Switch checked={autoSend} onCheckedChange={setAutoSend} />
              <span className="whitespace-nowrap text-sm">Auto-send</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <div className="mx-auto flex max-w-6xl flex-col gap-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
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

        {chatContent}

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
                  className="min-w-[12rem] rounded-md border border-slate-200 bg-white p-3"
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
                    <TableCell>{renderLevelBadges(row.achievedLevel)}</TableCell>
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
              <div className="rounded-md border border-slate-200 bg-white p-4 text-sm text-muted-foreground">
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
