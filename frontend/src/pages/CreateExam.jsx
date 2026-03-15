import { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Input } from "../components/ui/input";
import { ArrowLeft, Upload, FileText, Loader2 } from "lucide-react";
import { API } from "../lib/api";

const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20MB

export default function CreateExam() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [pdfFile, setPdfFile] = useState(null);
  const [examConfig, setExamConfig] = useState({
    exam_type: "mixed",
    difficulty: "medium",
    num_questions: 10,
  });

  const updateConfig = (field, value) => setExamConfig((prev) => ({ ...prev, [field]: value }));

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (file.type !== "application/pdf") {
      toast.error("Lütfen sadece PDF dosyası seçin");
      return;
    }
    if (file.size > MAX_FILE_SIZE) {
      toast.error("Dosya boyutu 20MB'dan küçük olmalı");
      return;
    }
    setPdfFile(file);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!pdfFile) {
      toast.error("Lütfen bir PDF dosyası seçin");
      return;
    }

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("pdf", pdfFile);
      formData.append("exam_type", examConfig.exam_type);
      formData.append("difficulty", examConfig.difficulty);
      formData.append("num_questions", examConfig.num_questions);

      const response = await axios.post(`${API}/exams/create`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success("Sınav başarıyla oluşturuldu!");
      navigate(`/exam/${response.data.id}`);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Sınav oluşturulamadı");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen" style={{ background: 'linear-gradient(135deg, #e0e7ff 0%, #f3e8ff 100%)' }}>
      <header className="glass-card border-b">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center gap-4">
          <Button variant="outline" onClick={() => navigate('/')} data-testid="back-button">
            <ArrowLeft className="w-4 h-4" />
          </Button>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }}>
              <FileText className="w-6 h-6 text-white" />
            </div>
            <h1 className="text-2xl font-bold" style={{ color: '#667eea' }}>Yeni Sınav Oluştur</h1>
          </div>
        </div>
      </header>

      <div className="max-w-3xl mx-auto px-6 py-8">
        <Card className="glass-card border-none shadow-2xl fade-in">
          <CardHeader>
            <CardTitle className="text-2xl">Sınav Ayarları</CardTitle>
            <CardDescription>PDF yükleyin ve sınav özelliklerini belirleyin</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* PDF Upload */}
              <div className="space-y-2">
                <Label>PDF Dosyası</Label>
                <div className="pdf-preview" onClick={() => document.getElementById('pdf-input').click()} data-testid="pdf-upload-area">
                  <input id="pdf-input" type="file" accept=".pdf" onChange={handleFileChange} className="hidden" data-testid="pdf-file-input" />
                  {pdfFile ? (
                    <div className="flex items-center justify-center gap-3">
                      <FileText className="w-12 h-12" style={{ color: '#667eea' }} />
                      <div className="text-left">
                        <p className="font-semibold text-gray-800" data-testid="pdf-file-name">{pdfFile.name}</p>
                        <p className="text-sm text-gray-600">{(pdfFile.size / 1024 / 1024).toFixed(2)} MB</p>
                      </div>
                    </div>
                  ) : (
                    <div>
                      <Upload className="w-12 h-12 mx-auto mb-3 text-gray-400" />
                      <p className="text-gray-600 font-medium">PDF dosyasını sürükleyin veya tıklayın</p>
                      <p className="text-sm text-gray-500 mt-2">Maksimum dosya boyutu: 20MB</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Exam Type */}
              <div className="space-y-2">
                <Label>Sınav Türü</Label>
                <Select value={examConfig.exam_type} onValueChange={(v) => updateConfig("exam_type", v)}>
                  <SelectTrigger data-testid="exam-type-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="multiple_choice">Çoktan Seçmeli</SelectItem>
                    <SelectItem value="true_false">Doğru/Yanlış</SelectItem>
                    <SelectItem value="fill_blank">Boşluk Doldurma</SelectItem>
                    <SelectItem value="open_ended">Klasik</SelectItem>
                    <SelectItem value="image_based">Görsel Tabanlı</SelectItem>
                    <SelectItem value="mixed">Karışık</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Difficulty */}
              <div className="space-y-2">
                <Label>Zorluk Seviyesi</Label>
                <Select value={examConfig.difficulty} onValueChange={(v) => updateConfig("difficulty", v)}>
                  <SelectTrigger data-testid="difficulty-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="easy">Kolay</SelectItem>
                    <SelectItem value="medium">Orta</SelectItem>
                    <SelectItem value="hard">Zor</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Question Count */}
              <div className="space-y-2">
                <Label>Soru Sayısı</Label>
                <Input type="number" min="5" max="50" value={examConfig.num_questions} onChange={(e) => updateConfig("num_questions", parseInt(e.target.value))} data-testid="num-questions-input" />
                <p className="text-sm text-gray-600">Minimum 5, maksimum 50 soru</p>
              </div>

              <Button type="submit" className="w-full btn-primary text-lg py-6" disabled={loading || !pdfFile} data-testid="create-exam-submit">
                {loading ? (
                  <>
                    <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                    Sınav Oluşturuluyor...
                  </>
                ) : (
                  "Sınav Oluştur"
                )}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
