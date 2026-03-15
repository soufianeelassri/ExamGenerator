import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { RadioGroup, RadioGroupItem } from "../components/ui/radio-group";
import { Label } from "../components/ui/label";
import { Input } from "../components/ui/input";
import { Textarea } from "../components/ui/textarea";
import { ArrowLeft, Send, FileText } from "lucide-react";
import { API } from "../lib/api";
import { getQuestionTypeLabel } from "../lib/utils";

export default function TakeExam() {
  const { examId } = useParams();
  const navigate = useNavigate();
  const [exam, setExam] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [answers, setAnswers] = useState({});

  useEffect(() => {
    (async () => {
      try {
        const response = await axios.get(`${API}/exams/${examId}`);
        setExam(response.data);
      } catch {
        toast.error("Sınav yüklenemedi");
        navigate('/');
      } finally {
        setLoading(false);
      }
    })();
  }, [examId, navigate]);

  const setAnswer = (questionId, value) => setAnswers((prev) => ({ ...prev, [questionId]: value }));

  const handleSubmit = async () => {
    const unanswered = exam.questions.length - Object.keys(answers).length;
    if (unanswered > 0 && !window.confirm(`${unanswered} soru cevaplanmadı. Yine de göndermek istiyor musunuz?`)) return;

    setSubmitting(true);
    try {
      const response = await axios.post(`${API}/exams/submit`, {
        exam_id: examId,
        answers: Object.entries(answers).map(([question_id, user_answer]) => ({ question_id, user_answer })),
      });
      toast.success("Sınav gönderildi!");
      navigate(`/results/${response.data.id}`);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Sınav gönderilemedi");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center"><div className="spinner" /></div>;
  }

  const renderOptions = (question) => (
    <RadioGroup value={answers[question.id] || ""} onValueChange={(v) => setAnswer(question.id, v)} className="space-y-3">
      {question.options?.map((option, i) => (
        <div key={i} className="flex items-center space-x-3 option-btn" data-testid={`option-${question.id}-${i}`}>
          <RadioGroupItem value={option} id={`${question.id}-${i}`} />
          <Label htmlFor={`${question.id}-${i}`} className="flex-1 cursor-pointer">{option}</Label>
        </div>
      ))}
    </RadioGroup>
  );

  const renderQuestionInput = (question) => {
    switch (question.question_type) {
      case "multiple_choice":
        return renderOptions(question);
      case "true_false":
        return (
          <RadioGroup value={answers[question.id] || ""} onValueChange={(v) => setAnswer(question.id, v)} className="space-y-3">
            {[["True", "Doğru"], ["False", "Yanlış"]].map(([value, label]) => (
              <div key={value} className="flex items-center space-x-3 option-btn" data-testid={`option-${value.toLowerCase()}-${question.id}`}>
                <RadioGroupItem value={value} id={`${question.id}-${value.toLowerCase()}`} />
                <Label htmlFor={`${question.id}-${value.toLowerCase()}`} className="flex-1 cursor-pointer">{label}</Label>
              </div>
            ))}
          </RadioGroup>
        );
      case "fill_blank":
        return <Input placeholder="Cevabınızı yazın..." value={answers[question.id] || ""} onChange={(e) => setAnswer(question.id, e.target.value)} className="mt-2" data-testid={`fill-blank-input-${question.id}`} />;
      case "open_ended":
        return <Textarea placeholder="Cevabınızı detaylı bir şekilde yazın..." value={answers[question.id] || ""} onChange={(e) => setAnswer(question.id, e.target.value)} className="mt-2 min-h-[120px]" data-testid={`open-ended-textarea-${question.id}`} />;
      case "image_based":
        return (
          <div className="space-y-4">
            {question.image_data && (
              <div className="flex justify-center">
                <img src={`data:image/jpeg;base64,${question.image_data}`} alt="Soru görseli" className="max-w-full h-auto rounded-lg shadow-md border" style={{ maxHeight: '400px' }} data-testid={`question-image-${question.id}`} />
              </div>
            )}
            {renderOptions(question)}
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen" style={{ background: 'linear-gradient(135deg, #e0e7ff 0%, #f3e8ff 100%)' }}>
      <header className="glass-card border-b sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="outline" onClick={() => navigate('/')} data-testid="back-to-dashboard">
              <ArrowLeft className="w-4 h-4" />
            </Button>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }}>
                <FileText className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold" style={{ color: '#667eea' }} data-testid="exam-title">{exam.title}</h1>
                <p className="text-sm text-gray-600">{exam.questions.length} Soru</p>
              </div>
            </div>
          </div>
          <Button className="btn-primary" onClick={handleSubmit} disabled={submitting} data-testid="submit-exam-button">
            <Send className="w-4 h-4 mr-2" />
            {submitting ? "Gönderiliyor..." : "Gönder"}
          </Button>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-8">
        <div className="space-y-6" data-testid="questions-container">
          {exam.questions.map((question, index) => (
            <Card key={question.id} className="glass-card border-none fade-in" data-testid={`question-card-${question.id}`}>
              <CardHeader>
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }}>
                    <span className="text-white font-bold">{index + 1}</span>
                  </div>
                  <div className="flex-1">
                    <CardTitle className="text-lg" data-testid={`question-text-${question.id}`}>{question.question_text}</CardTitle>
                    <CardDescription className="mt-2">
                      <span className="px-3 py-1 rounded-full text-xs font-semibold" style={{ background: 'rgba(102, 126, 234, 0.1)', color: '#667eea' }}>
                        {getQuestionTypeLabel(question.question_type)}
                      </span>
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent>{renderQuestionInput(question)}</CardContent>
            </Card>
          ))}
        </div>

        <div className="mt-8 flex justify-center">
          <Button className="btn-primary text-lg py-6 px-12" onClick={handleSubmit} disabled={submitting} data-testid="submit-exam-button-bottom">
            <Send className="w-5 h-5 mr-2" />
            {submitting ? "Gönderiliyor..." : "Sınavı Gönder"}
          </Button>
        </div>
      </div>
    </div>
  );
}
