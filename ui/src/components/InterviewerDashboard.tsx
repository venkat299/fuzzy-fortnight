import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Briefcase, Upload } from 'lucide-react';

interface InterviewData {
  jobTitle: string;
  jobDescription: string;
  experienceYears: string;
}

interface InterviewerDashboardProps {
  onSubmitInterview: (data: InterviewData) => Promise<void>;
  initialData?: InterviewData;
  isLoading: boolean;
  errorMessage: string | null;
}

export function InterviewerDashboard({ onSubmitInterview, initialData, isLoading, errorMessage }: InterviewerDashboardProps) {
  const [formData, setFormData] = useState<InterviewData>(initialData ?? {
    jobTitle: '',
    jobDescription: '',
    experienceYears: ''
  });

  useEffect(() => {
    if (initialData) {
      setFormData(initialData);
    }
  }, [initialData]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await onSubmitInterview(formData);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (event) => {
        const content = event.target?.result as string;
        setFormData({ ...formData, jobDescription: content });
      };
      reader.readAsText(file);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="flex items-center gap-2">
            <Briefcase className="h-8 w-8" />
            Interview Preparation
          </h1>
          <p className="text-muted-foreground">Identify key competencies for interview evaluation</p>
        </div>

        {/* Main Form */}
        <Card>
          <CardHeader>
            <CardTitle>Prepare New Interview</CardTitle>
            <CardDescription>
              Enter the job details to identify key competencies for evaluation
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Job Title */}
              <div className="space-y-2">
                <Label htmlFor="job-title">Job Title</Label>
                <Input
                  id="job-title"
                  placeholder="e.g., Senior Software Engineer"
                  value={formData.jobTitle}
                  onChange={(e) => setFormData({ ...formData, jobTitle: e.target.value })}
                  required
                />
              </div>

              {/* Years of Experience */}
              <div className="space-y-2">
                <Label htmlFor="experience">Required Years of Experience</Label>
                <Select
                  value={formData.experienceYears}
                  onValueChange={(value) => setFormData({ ...formData, experienceYears: value })}
                  required
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select experience level" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="0-1">0-1 years (Entry Level)</SelectItem>
                    <SelectItem value="2-3">2-3 years (Junior)</SelectItem>
                    <SelectItem value="4-6">4-6 years (Mid-Level)</SelectItem>
                    <SelectItem value="7-10">7-10 years (Senior)</SelectItem>
                    <SelectItem value="10+">10+ years (Principal/Lead)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Job Description */}
              <div className="space-y-2">
                <Label htmlFor="job-description">Job Description</Label>
                <div className="space-y-3">
                  {/* File Upload Option */}
                  <div className="flex items-center gap-3">
                    <Input
                      type="file"
                      accept=".txt,.doc,.docx"
                      onChange={handleFileUpload}
                      className="hidden"
                      id="file-upload"
                    />
                    <Label 
                      htmlFor="file-upload" 
                      className="flex items-center gap-2 px-4 py-2 border border-dashed border-gray-300 rounded-md cursor-pointer hover:bg-gray-50"
                    >
                      <Upload className="h-4 w-4" />
                      Upload Job Description
                    </Label>
                    <span className="text-sm text-muted-foreground">or paste below</span>
                  </div>
                  
                  {/* Text Area */}
                  <Textarea
                    id="job-description"
                    placeholder="Paste the complete job description here..."
                    value={formData.jobDescription}
                    onChange={(e) => setFormData({ ...formData, jobDescription: e.target.value })}
                    rows={8}
                    required
                  />
                </div>
              </div>

              {/* Submit Button */}
              <Button type="submit" className="w-full" size="lg" disabled={isLoading}>
                {isLoading ? 'Analyzing…' : 'Identify Competencies'}
              </Button>
            </form>
            {errorMessage && (
              <p className="mt-4 text-sm text-red-600" role="alert">
                {errorMessage}
              </p>
            )}
          </CardContent>
        </Card>

        {/* Instructions */}
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>How it works</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid md:grid-cols-3 gap-4">
              <div className="text-center">
                <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-2">
                  <span>1</span>
                </div>
                <p>Upload or paste the job description</p>
              </div>
              <div className="text-center">
                <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-2">
                  <span>2</span>
                </div>
                <p>AI analyzes the requirements</p>
              </div>
              <div className="text-center">
                <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-2">
                  <span>3</span>
                </div>
                <p>Get identified competencies</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}