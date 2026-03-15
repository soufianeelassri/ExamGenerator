import json
import io
import os
import base64
import random
import logging
import tempfile
import uuid
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal
from contextlib import asynccontextmanager

import jwt
from passlib.context import CryptContext
from fastapi import FastAPI, APIRouter, HTTPException, Depends, File, UploadFile, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from PyPDF2 import PdfReader
from pdf2image import convert_from_path
from PIL import Image
import google.generativeai as genai

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).parent
from dotenv import load_dotenv
load_dotenv(ROOT_DIR / '.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# MongoDB
MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']

# Security
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.environ.get("SECRET_KEY", "exam-generator-secret-key-2025")
ALGORITHM = "HS256"
security = HTTPBearer()

# Google AI
GOOGLE_AI_KEY = os.environ.get("GOOGLE_AI_KEY")

# Gemini model fallback order
GEMINI_MODELS = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-pro-latest"]

# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.mongo_client = AsyncIOMotorClient(MONGO_URL)
    app.state.db = app.state.mongo_client[DB_NAME]
    yield
    # Shutdown
    app.state.mongo_client.close()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api")


def get_db():
    return app.state.db


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: EmailStr
    full_name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Question(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question_text: str
    question_type: Literal["multiple_choice", "true_false", "fill_blank", "open_ended", "image_based"]
    options: Optional[List[str]] = None
    correct_answer: str
    explanation: Optional[str] = None
    image_data: Optional[str] = None


class ExamCreate(BaseModel):
    exam_type: Literal["multiple_choice", "true_false", "fill_blank", "open_ended", "image_based", "mixed"]
    difficulty: Literal["easy", "medium", "hard"]
    num_questions: int = Field(ge=5, le=50)


class Exam(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    title: str
    exam_type: str
    difficulty: str
    questions: List[Question]
    pdf_name: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExamAnswer(BaseModel):
    question_id: str
    user_answer: str


class ExamSubmission(BaseModel):
    exam_id: str
    answers: List[ExamAnswer]


class ExamResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    exam_id: str
    user_id: str
    score: float
    total_questions: int
    correct_answers: int
    answers: List[ExamAnswer]
    feedback: List[dict]
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta = timedelta(days=7)) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        user = await get_db().users.find_one({"id": user_id}, {"_id": 0})
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ---------------------------------------------------------------------------
# PDF & AI helpers
# ---------------------------------------------------------------------------

def extract_text_from_pdf(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    return "".join(page.extract_text() or "" for page in reader.pages)


def _pil_image_to_base64(img: Image.Image) -> str:
    max_size = 1024
    img = img.convert("RGB")
    if img.width > max_size or img.height > max_size:
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode()


def _extract_images_with_pdf2image(pdf_path: str, target_count: int) -> List[dict]:
    try:
        pages = convert_from_path(pdf_path, dpi=200, fmt="jpeg")
        if not pages or len(pages) < target_count:
            logger.warning("pdf2image produced %s pages, need %s", len(pages) if pages else 0, target_count)
            return []
        selected = random.sample(range(len(pages)), target_count)
        logger.info("Selected pages via pdf2image: %s", sorted(selected))
        return [{"page_index": i, "image_data": _pil_image_to_base64(pages[i])} for i in selected]
    except Exception:
        logger.exception("Error extracting images using pdf2image")
        return []


def extract_images_from_pdf(pdf_path: str, target_count: int) -> List[dict]:
    if target_count <= 0:
        raise HTTPException(status_code=400, detail="Number of requested questions must be positive")

    try:
        import fitz

        doc = fitz.open(pdf_path)
        try:
            total_pages = len(doc)
            if total_pages == 0:
                raise HTTPException(status_code=400, detail="PDF does not contain any pages")
            if total_pages < target_count:
                raise HTTPException(
                    status_code=400,
                    detail=f"PDF contains only {total_pages} pages, cannot create {target_count} image-based questions.",
                )

            selected = random.sample(range(total_pages), target_count)
            logger.info("Selected pages via PyMuPDF: %s", sorted(selected))
            zoom = fitz.Matrix(2.0, 2.0)
            return [
                {
                    "page_index": i,
                    "image_data": _pil_image_to_base64(Image.open(io.BytesIO(doc[i].get_pixmap(matrix=zoom).tobytes("png")))),
                }
                for i in selected
            ]
        finally:
            doc.close()
    except HTTPException:
        raise
    except ImportError:
        logger.warning("PyMuPDF is not available, falling back to pdf2image")
    except Exception:
        logger.exception("PyMuPDF extraction failed, falling back to pdf2image")

    images = _extract_images_with_pdf2image(pdf_path, target_count)
    if not images:
        raise HTTPException(
            status_code=500,
            detail="Failed to extract sufficient images from PDF.",
        )
    return images


def _get_random_sections(text: str, num_sections: int = 5) -> str:
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    if len(paragraphs) <= num_sections:
        return text
    return '\n\n'.join(random.sample(paragraphs, num_sections))


def _create_gemini_model() -> genai.GenerativeModel:
    genai.configure(api_key=GOOGLE_AI_KEY)
    for name in GEMINI_MODELS:
        try:
            model = genai.GenerativeModel(name)
            logger.info("Using Gemini model: %s", name)
            return model
        except Exception:
            logger.warning("Model %s unavailable, trying next", name)
    raise HTTPException(status_code=500, detail="No available Gemini models found")


DIFFICULTY_TR = {"easy": "kolay", "medium": "orta", "hard": "zor"}

TYPE_INSTRUCTIONS = {
    "multiple_choice": {
        "instruction": "SADECE çoktan seçmeli sorular oluştur. Her soru için 5 seçenek (A, B, C, D, E) hazırla. Doğru cevap harfini belirt.",
        "question_type": "multiple_choice",
    },
    "true_false": {
        "instruction": "SADECE doğru/yanlış soruları oluştur. Cevap 'Doğru' veya 'Yanlış' olmalı.",
        "question_type": "true_false",
    },
    "fill_blank": {
        "instruction": "SADECE boşluk doldurma soruları oluştur. Boşluğu göstermek için '___' kullan. Doğru cevabı ver.",
        "question_type": "fill_blank",
    },
    "open_ended": {
        "instruction": "SADECE açık uçlu sorular oluştur. Detaylı cevaplar gerektiren sorular hazırla. Örnek doğru cevap ver.",
        "question_type": "open_ended",
    },
    "mixed": {
        "instruction": "Farklı türlerde sorular oluştur: çoktan seçmeli, doğru/yanlış, boşluk doldurma ve açık uçlu soruların karışımını yap.",
        "question_type": "mixed",
    },
}


def _parse_ai_response(response_text: str) -> list:
    text = response_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    data = json.loads(text)
    return data if isinstance(data, list) else [data]


async def generate_image_based_exam(pdf_path: str, difficulty: str, num_questions: int) -> List[Question]:
    images = extract_images_from_pdf(pdf_path, num_questions)
    model = _create_gemini_model()
    difficulty_tr = DIFFICULTY_TR.get(difficulty, difficulty)

    questions: List[Question] = []
    for idx, page_image in enumerate(images):
        prompt = f"""Sen uzman bir sınav oluşturucususun. Sana verilen görseli analiz ederek {difficulty_tr} zorluk seviyesinde SADECE bir adet görsel tabanlı çoktan seçmeli sınav sorusu üret.

Kurallar:
- Soru ve seçenekler görseldeki içerikten türetilmeli, görselde yer almayan bilgileri kullanma.
- Soru metninde "Görsel {idx}" gibi ifadeler kullanma; görseldeki unsurları betimleyerek anlat.
- 5 seçenek (A, B, C, D, E) oluştur ve her birini görsele göre mantıklı yap.
- "correct_answer" değeri sadece doğru seçeneğin harfi olsun.
- Kısa ve gerekçeli bir "explanation" ekle.

Sadece aşağıdaki JSON nesnesini döndür:
{{
  "question_text": "...",
  "question_type": "image_based",
  "options": ["A. ...", "B. ...", "C. ...", "D. ...", "E. ..."],
  "correct_answer": "A",
  "explanation": "..."
}}

JSON nesnesinin önüne veya arkasına başka metin ekleme."""

        response = model.generate_content([
            prompt,
            {"mime_type": "image/jpeg", "data": page_image["image_data"]},
        ])

        parsed = _parse_ai_response(response.text)
        q = parsed[0] if isinstance(parsed, list) else parsed
        questions.append(Question(
            question_text=q["question_text"],
            question_type="image_based",
            options=q.get("options"),
            correct_answer=q["correct_answer"],
            explanation=q.get("explanation"),
            image_data=page_image["image_data"],
        ))

    return questions


async def generate_exam_with_ai(pdf_text: str, exam_type: str, difficulty: str, num_questions: int) -> List[Question]:
    model = _create_gemini_model()
    difficulty_tr = DIFFICULTY_TR.get(difficulty, difficulty)
    instruction = TYPE_INSTRUCTIONS[exam_type]
    content = _get_random_sections(pdf_text)[:4000]

    type_constraint = ""
    if exam_type != "mixed":
        type_constraint = f"""
- TÜM sorular {instruction["question_type"]} türünde olmalı
- Her soru için question_type alanını "{instruction["question_type"]}" olarak ayarla."""

    prompt = f"""Sen uzman bir sınav oluşturucususun. Verilen içeriğe dayalı olarak yüksek kaliteli sınav soruları oluştur.

Aşağıdaki içeriğe dayalı olarak {num_questions} adet {difficulty_tr} zorluk seviyesinde sınav sorusu oluştur.

{instruction["instruction"]}

ÖNEMLİ: İçerikten farklı bölümlerden sorular oluştur. Her soru farklı bir konu veya kavramdan gelsin.

İçerik:
{content}

ÖNEMLİ:{type_constraint}
- Sadece aşağıdaki yapıda geçerli bir JSON dizisi döndür:
[
  {{
    "question_text": "Soru metni burada",
    "question_type": "{instruction["question_type"] if exam_type != "mixed" else '"multiple_choice" veya "true_false" veya "fill_blank" veya "open_ended"'}",
    "options": ["A. Seçenek 1", "B. Seçenek 2", "C. Seçenek 3", "D. Seçenek 4", "E. Seçenek 5"] (sadece multiple_choice için),
    "correct_answer": "Doğru cevap",
    "explanation": "Cevabın kısa açıklaması"
  }}
]

JSON dizisinden önce veya sonra herhangi bir metin ekleme.
Tüm soruları ve açıklamaları Türkçe dilinde oluştur."""

    logger.info("Creating exam — type: %s, difficulty: %s, questions: %s", exam_type, difficulty, num_questions)
    response = model.generate_content(prompt)
    questions_data = _parse_ai_response(response.text)
    logger.info("Generated %s questions, types: %s", len(questions_data), [q.get("question_type") for q in questions_data])

    return [
        Question(
            question_text=q["question_text"],
            question_type=q["question_type"],
            options=q.get("options"),
            correct_answer=q["correct_answer"],
            explanation=q.get("explanation"),
        )
        for q in questions_data
    ]


# ---------------------------------------------------------------------------
# Routes — Auth
# ---------------------------------------------------------------------------

@api_router.post("/auth/register", response_model=dict)
async def register(user_data: UserCreate):
    db = get_db()
    if await db.users.find_one({"email": user_data.email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(email=user_data.email, full_name=user_data.full_name)
    user_doc = user.model_dump()
    user_doc["password_hash"] = hash_password(user_data.password)
    user_doc["created_at"] = user_doc["created_at"].isoformat()
    await db.users.insert_one(user_doc)

    return {
        "token": create_access_token({"sub": user.id}),
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name},
    }


@api_router.post("/auth/login", response_model=dict)
async def login(credentials: UserLogin):
    db = get_db()
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return {
        "token": create_access_token({"sub": user["id"]}),
        "user": {"id": user["id"], "email": user["email"], "full_name": user["full_name"]},
    }


# ---------------------------------------------------------------------------
# Routes — Exams
# ---------------------------------------------------------------------------

@api_router.post("/exams/create", response_model=Exam)
async def create_exam(
    pdf: UploadFile = File(...),
    exam_type: str = Form("mixed"),
    difficulty: str = Form("medium"),
    num_questions: int = Form(10),
    current_user: dict = Depends(get_current_user),
):
    db = get_db()
    logger.info("Create exam — type: %s, difficulty: %s, questions: %s", exam_type, difficulty, num_questions)

    if not pdf.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await pdf.read())
        tmp_path = tmp.name

    try:
        if exam_type == "image_based":
            questions = await generate_image_based_exam(tmp_path, difficulty, num_questions)
        else:
            pdf_text = extract_text_from_pdf(tmp_path)
            if not pdf_text.strip():
                raise HTTPException(status_code=400, detail="Could not extract text from PDF")
            questions = await generate_exam_with_ai(pdf_text, exam_type, difficulty, num_questions)

        exam = Exam(
            user_id=current_user["id"],
            title=f"Exam from {pdf.filename}",
            exam_type=exam_type,
            difficulty=difficulty,
            questions=questions,
            pdf_name=pdf.filename,
        )
        exam_doc = exam.model_dump()
        exam_doc["created_at"] = exam_doc["created_at"].isoformat()
        exam_doc["questions"] = [q.model_dump() for q in questions]
        await db.exams.insert_one(exam_doc)
        return exam
    finally:
        os.unlink(tmp_path)


@api_router.get("/exams", response_model=List[Exam])
async def get_exams(current_user: dict = Depends(get_current_user)):
    db = get_db()
    exams = await db.exams.find({"user_id": current_user["id"]}, {"_id": 0}).to_list(1000)
    for exam in exams:
        if isinstance(exam["created_at"], str):
            exam["created_at"] = datetime.fromisoformat(exam["created_at"])
    return exams


@api_router.get("/exams/{exam_id}", response_model=Exam)
async def get_exam(exam_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    exam = await db.exams.find_one({"id": exam_id, "user_id": current_user["id"]}, {"_id": 0})
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if isinstance(exam["created_at"], str):
        exam["created_at"] = datetime.fromisoformat(exam["created_at"])
    return exam


@api_router.delete("/exams/{exam_id}")
async def delete_exam(exam_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    exam = await db.exams.find_one({"id": exam_id, "user_id": current_user["id"]}, {"_id": 0})
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    result = await db.exams.delete_one({"id": exam_id, "user_id": current_user["id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Exam not found")

    await db.exam_results.delete_many({"exam_id": exam_id})
    return {"message": "Exam deleted successfully"}


# ---------------------------------------------------------------------------
# Routes — Submissions & Results
# ---------------------------------------------------------------------------

@api_router.post("/exams/submit", response_model=ExamResult)
async def submit_exam(submission: ExamSubmission, current_user: dict = Depends(get_current_user)):
    db = get_db()
    exam = await db.exams.find_one({"id": submission.exam_id, "user_id": current_user["id"]}, {"_id": 0})
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    questions_by_id = {q["id"]: q for q in exam["questions"]}
    correct_count = 0
    feedback = []

    for answer in submission.answers:
        question = questions_by_id.get(answer.question_id)
        if not question:
            continue
        is_correct = answer.user_answer.strip().lower() == question["correct_answer"].strip().lower()
        if is_correct:
            correct_count += 1
        feedback.append({
            "question_id": answer.question_id,
            "is_correct": is_correct,
            "correct_answer": question["correct_answer"],
            "user_answer": answer.user_answer,
            "explanation": question.get("explanation", ""),
        })

    total = len(exam["questions"])
    score = (correct_count / total) * 100 if total > 0 else 0

    result = ExamResult(
        exam_id=submission.exam_id,
        user_id=current_user["id"],
        score=score,
        total_questions=total,
        correct_answers=correct_count,
        answers=submission.answers,
        feedback=feedback,
    )
    result_doc = result.model_dump()
    result_doc["submitted_at"] = result_doc["submitted_at"].isoformat()
    result_doc["answers"] = [a.model_dump() for a in submission.answers]
    await db.exam_results.insert_one(result_doc)
    return result


@api_router.get("/results", response_model=List[ExamResult])
async def get_results(current_user: dict = Depends(get_current_user)):
    db = get_db()
    results = await db.exam_results.find({"user_id": current_user["id"]}, {"_id": 0}).to_list(1000)
    for r in results:
        if isinstance(r["submitted_at"], str):
            r["submitted_at"] = datetime.fromisoformat(r["submitted_at"])
    return results


@api_router.get("/results/{result_id}", response_model=ExamResult)
async def get_result(result_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    result = await db.exam_results.find_one({"id": result_id, "user_id": current_user["id"]}, {"_id": 0})
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    if isinstance(result["submitted_at"], str):
        result["submitted_at"] = datetime.fromisoformat(result["submitted_at"])
    return result


# ---------------------------------------------------------------------------
# Mount router
# ---------------------------------------------------------------------------

app.include_router(api_router)
