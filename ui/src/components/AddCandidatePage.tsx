import React, { useMemo, useState } from 'react';
import { ArrowLeft, Check, LayoutDashboard, Upload, X } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Badge } from './ui/badge';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList
} from './ui/command';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';

interface InterviewOption {
  interviewId: string;
  jobTitle: string;
  jobDescription: string;
}

export interface AddCandidateFormData {
  fullName: string;
  resume: string;
  interviewIds: string[];
}

interface AddCandidatePageProps {
  interviews: InterviewOption[];
  onSave: (payload: AddCandidateFormData) => Promise<void>;
  onBackToDashboard: () => void;
  isSaving: boolean;
  errorMessage: string | null;
}

export function AddCandidatePage({
  interviews,
  onSave,
  onBackToDashboard,
  isSaving,
  errorMessage
}: AddCandidatePageProps) {
  const [fullName, setFullName] = useState('');
  const [resume, setResume] = useState('');
  const [resumeFileName, setResumeFileName] = useState<string | null>(null);
  const [selectedInterviewIds, setSelectedInterviewIds] = useState<string[]>([]);
  const [isPopoverOpen, setIsPopoverOpen] = useState(false);

  const interviewOptions = useMemo(
    () =>
      interviews.map((item) => ({
        value: item.interviewId,
        label: `${item.jobTitle || 'Untitled role'} (${item.interviewId})`,
        description: item.jobDescription
      })),
    [interviews]
  );

  const selectedOptions = useMemo(
    () =>
      selectedInterviewIds
        .map((id) => interviewOptions.find((option) => option.value === id))
        .filter((option): option is typeof interviewOptions[number] => Boolean(option)),
    [selectedInterviewIds, interviewOptions]
  );

  const toggleInterview = (id: string) => {
    setSelectedInterviewIds((prev) => {
      if (prev.includes(id)) {
        return prev.filter((value) => value !== id);
      }
      return [...prev, id];
    });
  };

  const removeInterview = (id: string) => {
    setSelectedInterviewIds((prev) => prev.filter((value) => value !== id));
  };

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    const reader = new FileReader();
    reader.onload = (loadEvent) => {
      const content = loadEvent.target?.result;
      if (typeof content === 'string') {
        setResume(content);
        setResumeFileName(file.name);
      }
    };
    reader.readAsText(file);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    await onSave({
      fullName: fullName.trim(),
      resume: resume.trim(),
      interviewIds: selectedInterviewIds
    });
  };

  const primaryInterview = selectedOptions[0];

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="flex flex-wrap items-center gap-3 justify-between">
          <Button
            type="button"
            variant="ghost"
            className="inline-flex items-center gap-2"
            onClick={onBackToDashboard}
            disabled={isSaving}
          >
            <ArrowLeft className="h-4 w-4" />
            Back to dashboard
          </Button>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <LayoutDashboard className="h-4 w-4" />
            Manage candidates from the interviewer dashboard
          </div>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Add candidate</CardTitle>
            <CardDescription>
              Upload resume details, capture candidate information, and link to relevant interviews.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-6" onSubmit={handleSubmit}>
              <div className="space-y-2">
                <Label htmlFor="candidate-name">Candidate name</Label>
                <Input
                  id="candidate-name"
                  placeholder="Jane Doe"
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  required
                  disabled={isSaving}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="resume-upload">Resume content</Label>
                <div className="flex flex-wrap items-center gap-3">
                  <Input
                    id="resume-upload"
                    type="file"
                    accept=".txt,.md,.pdf,.doc,.docx"
                    className="hidden"
                    onChange={handleFileUpload}
                    disabled={isSaving}
                  />
                  <Label
                    htmlFor="resume-upload"
                    className="flex cursor-pointer items-center gap-2 rounded-md border border-dashed border-muted-foreground/40 px-4 py-2 text-sm font-medium hover:bg-muted"
                  >
                    <Upload className="h-4 w-4" />
                    Upload resume file
                  </Label>
                  {resumeFileName && (
                    <span className="text-sm text-muted-foreground">Loaded: {resumeFileName}</span>
                  )}
                </div>
                <Textarea
                  id="resume-notes"
                  value={resume}
                  onChange={(event) => setResume(event.target.value)}
                  placeholder="Paste resume content or recruiter notes if no file is available."
                  rows={8}
                  required
                  disabled={isSaving}
                />
              </div>

              <div className="space-y-3">
                <div>
                  <Label>Link to interview job descriptions</Label>
                  <p className="text-xs text-muted-foreground">
                    Select one or more interviews to associate this candidate with the appropriate job descriptions.
                    The first selection will be assigned on save.
                  </p>
                </div>

                <Popover open={isPopoverOpen} onOpenChange={setIsPopoverOpen}>
                  <PopoverTrigger asChild>
                    <Button
                      type="button"
                      variant="outline"
                      role="combobox"
                      aria-expanded={isPopoverOpen}
                      className="w-full justify-between"
                      disabled={isSaving || interviewOptions.length === 0}
                    >
                      {selectedOptions.length > 0
                        ? `${selectedOptions.length} interview${selectedOptions.length > 1 ? 's' : ''} selected`
                        : interviewOptions.length > 0
                          ? 'Search interviews to link'
                          : 'No interviews available'}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent align="start" className="w-[min(28rem,90vw)] p-0">
                    <Command>
                      <CommandInput placeholder="Search job titles or IDs..." />
                      <CommandEmpty>No interviews found.</CommandEmpty>
                      <CommandList>
                        <CommandGroup>
                          {interviewOptions.map((option) => {
                            const isSelected = selectedInterviewIds.includes(option.value);
                            return (
                              <CommandItem
                                key={option.value}
                                value={`${option.label} ${option.value}`}
                                onSelect={() => toggleInterview(option.value)}
                              >
                                <Check className={`h-4 w-4 ${isSelected ? 'opacity-100' : 'opacity-0'}`} />
                                <div className="flex flex-col text-left">
                                  <span className="font-medium">{option.label}</span>
                                  {option.description && (
                                    <span className="text-xs text-muted-foreground line-clamp-2">
                                      {option.description}
                                    </span>
                                  )}
                                </div>
                              </CommandItem>
                            );
                          })}
                        </CommandGroup>
                      </CommandList>
                    </Command>
                  </PopoverContent>
                </Popover>

                {selectedOptions.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {selectedOptions.map((option) => (
                      <Badge key={option.value} variant="secondary" className="flex items-center gap-2">
                        {option.label}
                        <button
                          type="button"
                          className="rounded-full bg-secondary/60 p-0.5 hover:bg-secondary"
                          onClick={() => removeInterview(option.value)}
                          disabled={isSaving}
                          aria-label={`Remove ${option.label}`}
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                )}

                {primaryInterview ? (
                  <p className="text-xs text-muted-foreground">
                    Primary interview assignment:{' '}
                    <span className="font-medium text-foreground">{primaryInterview.label}</span>
                  </p>
                ) : (
                  <p className="text-xs text-muted-foreground">Candidate will remain unassigned until an interview is selected.</p>
                )}
              </div>

              {errorMessage && <p className="text-sm text-red-600">{errorMessage}</p>}

              <div className="flex justify-end">
                <Button type="submit" disabled={isSaving}>
                  {isSaving ? 'Saving…' : 'Save candidate'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
