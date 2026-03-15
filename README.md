# ExamGenerator

AI-powered exam generator that creates questions from PDF documents using Google Gemini AI.

## Features

- Upload PDF documents and generate exam questions automatically
- Multiple question types: multiple choice, true/false, fill-in-the-blank, open-ended, image-based
- Configurable difficulty levels (easy, medium, hard) and question count (5-50)
- User authentication with JWT
- Interactive exam-taking interface with instant scoring and feedback

## Tech Stack

- **Backend:** FastAPI, MongoDB (Motor), Google Gemini AI, PyPDF2/PyMuPDF
- **Frontend:** React 19, Tailwind CSS, Radix UI, React Router, Axios

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- MongoDB
- Google AI API key

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create `backend/.env`:

```env
MONGO_URL=mongodb://localhost:27017
DB_NAME=exam_generator
GOOGLE_AI_KEY=your_api_key_here
CORS_ORIGINS=*
```

Start the server:

```bash
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
```

Create `frontend/.env`:

```env
REACT_APP_BACKEND_URL=http://localhost:8000
```

Start the dev server:

```bash
npm start
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register new user |
| POST | `/api/auth/login` | Login |
| POST | `/api/exams/create` | Create exam from PDF |
| GET | `/api/exams` | List user exams |
| GET | `/api/exams/:id` | Get exam details |
| DELETE | `/api/exams/:id` | Delete exam |
| POST | `/api/exams/submit` | Submit exam answers |
| GET | `/api/results` | List exam results |
| GET | `/api/results/:id` | Get result details |

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
