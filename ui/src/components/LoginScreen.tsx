import React, { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { User, UserCheck } from 'lucide-react';

interface LoginScreenProps {
  onLogin: (userType: 'candidate' | 'interviewer', credentials: { email: string; password: string }) => void;
}

export function LoginScreen({ onLogin }: LoginScreenProps) {
  const [candidateForm, setCandidateForm] = useState({ email: '', password: '' });
  const [interviewerForm, setInterviewerForm] = useState({ email: '', password: '' });

  const handleCandidateLogin = (e: React.FormEvent) => {
    e.preventDefault();
    onLogin('candidate', candidateForm);
  };

  const handleInterviewerLogin = (e: React.FormEvent) => {
    e.preventDefault();
    onLogin('interviewer', interviewerForm);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle className="flex items-center justify-center gap-2">
            <UserCheck className="h-6 w-6" />
            AI Interview System
          </CardTitle>
          <CardDescription>
            Sign in to your account to continue
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="candidate" className="w-full">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="candidate" className="flex items-center gap-2">
                <User className="h-4 w-4" />
                Candidate
              </TabsTrigger>
              <TabsTrigger value="interviewer" className="flex items-center gap-2">
                <UserCheck className="h-4 w-4" />
                Interviewer
              </TabsTrigger>
            </TabsList>
            
            <TabsContent value="candidate">
              <form onSubmit={handleCandidateLogin} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="candidate-email">Email</Label>
                  <Input
                    id="candidate-email"
                    type="email"
                    placeholder="candidate@example.com"
                    value={candidateForm.email}
                    onChange={(e) => setCandidateForm({ ...candidateForm, email: e.target.value })}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="candidate-password">Password</Label>
                  <Input
                    id="candidate-password"
                    type="password"
                    value={candidateForm.password}
                    onChange={(e) => setCandidateForm({ ...candidateForm, password: e.target.value })}
                    required
                  />
                </div>
                <Button type="submit" className="w-full">
                  Sign in as Candidate
                </Button>
              </form>
            </TabsContent>
            
            <TabsContent value="interviewer">
              <form onSubmit={handleInterviewerLogin} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="interviewer-email">Email</Label>
                  <Input
                    id="interviewer-email"
                    type="email"
                    placeholder="interviewer@example.com"
                    value={interviewerForm.email}
                    onChange={(e) => setInterviewerForm({ ...interviewerForm, email: e.target.value })}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="interviewer-password">Password</Label>
                  <Input
                    id="interviewer-password"
                    type="password"
                    value={interviewerForm.password}
                    onChange={(e) => setInterviewerForm({ ...interviewerForm, password: e.target.value })}
                    required
                  />
                </div>
                <Button type="submit" className="w-full">
                  Sign in as Interviewer
                </Button>
              </form>
            </TabsContent>
          </Tabs>
          
          <div className="mt-6 pt-4 border-t border-gray-200">
            <p className="text-sm text-muted-foreground text-center">
              Demo credentials: Use any email/password combination
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}