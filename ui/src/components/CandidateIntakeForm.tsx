import React, { useMemo, useState } from 'react';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from './ui/card';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Button } from './ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';

interface CandidateIntakeFormProps {
  interviews: { interviewId: string; jobTitle: string }[];
  onSubmit: (payload: CandidateFormData) => Promise<void>;
  onCancel: () => void;
  isSubmitting: boolean;
  errorMessage: string | null;
}

export interface CandidateFormData {
  fullName: string;
  resume: string;
  interviewId: string | null;
  status: string;
}

const STATUS_OPTIONS = ['Applied', 'Screening', 'Interviewing', 'Offer', 'Rejected'];

export function CandidateIntakeForm({
  interviews,
  onSubmit,
  onCancel,
  isSubmitting,
  errorMessage
}: CandidateIntakeFormProps) {
  const [formData, setFormData] = useState<CandidateFormData>({
    fullName: '',
    resume: '',
    interviewId: null,
    status: STATUS_OPTIONS[0]
  });

  const interviewOptions = useMemo(() => {
    if (interviews.length === 0) {
      return [];
    }
    return interviews.map((item) => ({
      value: item.interviewId,
      label: `${item.jobTitle || 'Untitled'} (${item.interviewId})`
    }));
  }, [interviews]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    await onSubmit(formData);
  };

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <div className="mx-auto max-w-3xl">
        <Card>
          <CardHeader>
            <CardTitle>Add candidate</CardTitle>
            <CardDescription>Record candidate details and link them to an interview.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-6" onSubmit={handleSubmit}>
              <div className="space-y-2">
                <Label htmlFor="candidate-name">Candidate name</Label>
                <Input
                  id="candidate-name"
                  value={formData.fullName}
                  onChange={(event) => setFormData((prev) => ({ ...prev, fullName: event.target.value }))}
                  placeholder="Jane Doe"
                  required
                  disabled={isSubmitting}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="candidate-status">Status</Label>
                <Select
                  value={formData.status}
                  onValueChange={(value) => setFormData((prev) => ({ ...prev, status: value }))}
                  disabled={isSubmitting}
                >
                  <SelectTrigger id="candidate-status">
                    <SelectValue placeholder="Select status" />
                  </SelectTrigger>
                  <SelectContent>
                    {STATUS_OPTIONS.map((status) => (
                      <SelectItem key={status} value={status}>
                        {status}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="candidate-interview">Assigned interview</Label>
                <Select
                  value={formData.interviewId ?? ''}
                  onValueChange={(value) =>
                    setFormData((prev) => ({ ...prev, interviewId: value.length > 0 ? value : null }))
                  }
                  disabled={isSubmitting || interviewOptions.length === 0}
                >
                  <SelectTrigger id="candidate-interview">
                    <SelectValue placeholder={interviewOptions.length === 0 ? 'No interviews available' : 'Choose interview'} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">Unassigned</SelectItem>
                    {interviewOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {interviewOptions.length === 0 && (
                  <p className="text-xs text-muted-foreground">Create an interview first to assign the candidate.</p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="candidate-resume">Resume / notes</Label>
                <Textarea
                  id="candidate-resume"
                  value={formData.resume}
                  onChange={(event) => setFormData((prev) => ({ ...prev, resume: event.target.value }))}
                  rows={6}
                  placeholder="Paste resume highlights, portfolio links, or recruiter notes."
                  required
                  disabled={isSubmitting}
                />
              </div>

              {errorMessage && <p className="text-sm text-red-600">{errorMessage}</p>}

              <div className="flex justify-end gap-3">
                <Button type="button" variant="ghost" onClick={onCancel} disabled={isSubmitting}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting ? 'Saving…' : 'Save candidate'}
                </Button>
              </div>
            </form>
          </CardContent>
          <CardFooter className="justify-end text-xs text-muted-foreground">
            Candidates are stored securely in the shared interview database.
          </CardFooter>
        </Card>
      </div>
    </div>
  );
}
