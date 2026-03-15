import { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import axios from "axios";
import { Toaster } from "./components/ui/sonner";
import AuthPage from "./pages/AuthPage";
import Dashboard from "./pages/Dashboard";
import CreateExam from "./pages/CreateExam";
import TakeExam from "./pages/TakeExam";
import ResultsPage from "./pages/ResultsPage";
import ResultDetail from "./pages/ResultDetail";
import "./App.css";

axios.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token && config.url.includes("/api/")) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

function ProtectedRoute({ children }) {
  return localStorage.getItem("token") ? children : <Navigate to="/auth" />;
}

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setIsAuthenticated(!!localStorage.getItem("token"));
    setLoading(false);
  }, []);

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center">Yükleniyor...</div>;
  }

  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route
            path="/auth"
            element={!isAuthenticated ? <AuthPage setIsAuthenticated={setIsAuthenticated} /> : <Navigate to="/" />}
          />
          <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/create" element={<ProtectedRoute><CreateExam /></ProtectedRoute>} />
          <Route path="/exam/:examId" element={<ProtectedRoute><TakeExam /></ProtectedRoute>} />
          <Route path="/results" element={<ProtectedRoute><ResultsPage /></ProtectedRoute>} />
          <Route path="/results/:resultId" element={<ProtectedRoute><ResultDetail /></ProtectedRoute>} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" />
    </div>
  );
}

export default App;
