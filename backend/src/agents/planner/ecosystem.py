import re
from typing import Any, List, Optional, Tuple

from src.models.enums import TechnicalProblemType
from src.schemas.planner import (
    CandidateProfile,
    InterviewPlanCreate,
    TechnologyEnvironment,
)


def is_bug_problem_type(problem_type: Optional[Any]) -> bool:
    """Returns True if the problem type belongs to a bug/debugging category.
    
    When a problem is in a bug category (e.g. BUG_INVESTIGATION or DEBUGGING),
    the technical exercise focuses on hands-on code inspection and fixing in Monaco,
    making system design exercise generation unnecessary.
    """
    if not problem_type:
        return False
    val = problem_type.value if hasattr(problem_type, "value") else str(problem_type)
    val_upper = val.upper()
    return (
        val_upper in {
            TechnicalProblemType.BUG_INVESTIGATION.value,
            TechnicalProblemType.DEBUGGING.value,
            "BUG",
            "BUG_INVESTIGATION",
            "DEBUGGING",
            "BUG_FIX",
            "BUG_FIXING",
        }
        or "BUG" in val_upper
        or "DEBUG" in val_upper
    )


def detect_target_programming_language(
    job_spec: InterviewPlanCreate,
    profile: CandidateProfile,
) -> Tuple[str, str]:
    """Determines the primary programming language and standard file extension
    tailored to the target role description, technical focus, and candidate tech stack.
    
    Returns (language_name, file_extension), e.g. ("typescript", ".ts"), ("go", ".go"), ("python", ".py").
    """
    tech_focus_text = " ".join(job_spec.technical_focus or []).lower()
    job_title_text = (job_spec.job_title or "").lower()
    focus_corpus = f"{job_title_text} {tech_focus_text}"

    # Priority 0: Explicit recruiter / job focus overrides
    if re.search(r'\b(python|py)\b', focus_corpus):
        return "python", ".py"
    if re.search(r'\b(typescript|ts|javascript|js|node|react|vue|angular)\b', focus_corpus):
        return "typescript", ".ts"
    if re.search(r'\b(golang|go)\b', focus_corpus):
        return "go", ".go"
    if re.search(r'\b(java|spring|kotlin)\b', focus_corpus):
        return "java", ".java"
    if re.search(r'\b(rust)\b', focus_corpus):
        return "rust", ".rs"
    if re.search(r'\b(c\+\+|cpp)\b', focus_corpus):
        return "cpp", ".cpp"

    text_corpus = " ".join([
        job_spec.job_title or "",
        job_spec.description or "",
        " ".join(job_spec.technical_focus or []),
        " ".join(profile.skills or []),
        " ".join(profile.frameworks_and_tools or []),
    ]).lower()

    # Priority 1: TypeScript / JavaScript (using whole word boundaries to prevent 'ts' matching inside 'websockets'/'endpoints')
    if (
        re.search(r'\b(typescript|ts)\b', text_corpus)
        or any(k in text_corpus for k in ("react", "vue", "angular", "next.js", "frontend", "front-end"))
        or any(k in text_corpus for k in ("javascript", "node", "express", "fullstack", "full-stack"))
    ):
        return "typescript", ".ts"

    # Priority 2: Go / Golang
    if re.search(r'\b(golang|go|goroutine)\b', text_corpus):
        return "go", ".go"

    # Priority 3: Java
    if re.search(r'\b(java|spring|springboot|jvm|kotlin)\b', text_corpus):
        return "java", ".java"

    # Priority 4: Rust
    if re.search(r'\b(rust|cargo|tokio)\b', text_corpus):
        return "rust", ".rs"

    # Priority 5: C++
    if re.search(r'\b(c\+\+|cpp)\b', text_corpus):
        return "cpp", ".cpp"

    # Priority 6: Python (Machine learning, Data, Python backend, or default)
    return "python", ".py"


def detect_technology_ecosystem(
    job_spec: InterviewPlanCreate,
    profile: CandidateProfile,
) -> Tuple[str, str, TechnologyEnvironment]:
    """Detects the primary programming language, standard file extension, and calibrated 4-level technology environment:
    Level 1: Language
    Level 2: Framework
    Level 3: Domain Libraries (selective, anti-soup)
    Level 4: Infrastructure Dependencies
    """
    lang, ext = detect_target_programming_language(job_spec, profile)

    text_corpus = " ".join([
        job_spec.job_title or "",
        job_spec.description or "",
        " ".join(job_spec.technical_focus or []),
        " ".join(profile.skills or []),
        " ".join(profile.frameworks_and_tools or []),
    ]).lower()

    framework = None
    domain_libraries: List[str] = []
    infra_deps: List[str] = []

    # Level 2: Framework detection
    if lang == "python":
        if any(k in text_corpus for k in ("fastapi", "fast-api")):
            framework = "FastAPI"
        elif "django" in text_corpus:
            framework = "Django"
        elif "flask" in text_corpus:
            framework = "Flask"
        elif any(k in text_corpus for k in ("agent", "ai engineer", "applied ai", "rag", "llm", "langgraph")):
            framework = "FastAPI"
        else:
            framework = "FastAPI"
    elif lang == "typescript":
        if any(k in text_corpus for k in ("next.js", "nextjs", "next")):
            framework = "Next.js"
        elif "react" in text_corpus:
            framework = "React"
        elif "nest" in text_corpus or "nestjs" in text_corpus:
            framework = "NestJS"
        elif "express" in text_corpus:
            framework = "Express"
        elif "vue" in text_corpus:
            framework = "Vue"
        else:
            framework = "Express"
    elif lang == "go":
        if "gin" in text_corpus:
            framework = "Gin"
        elif "echo" in text_corpus:
            framework = "Echo"
        elif "chi" in text_corpus:
            framework = "Chi"
        else:
            framework = "Standard Library net/http"
    elif lang == "java":
        if "spring" in text_corpus:
            framework = "Spring Boot"
        else:
            framework = "Spring Boot"

    # Level 3: Domain Libraries (selective, anti-soup)
    if any(k in text_corpus for k in ("langgraph", "agent", "agents", "graph")):
        domain_libraries.append("LangGraph")
    if any(k in text_corpus for k in ("openai", "gemini", "anthropic", "llm", "ai sdk")):
        domain_libraries.append("OpenAI SDK")
    if any(k in text_corpus for k in ("pydantic", "validation")) or (lang == "python" and framework == "FastAPI"):
        domain_libraries.append("Pydantic")
    if any(k in text_corpus for k in ("websocket", "websockets", "ws", "socket")):
        domain_libraries.append("WebSockets")
    if any(k in text_corpus for k in ("sqlalchemy", "orm")) and lang == "python":
        domain_libraries.append("SQLAlchemy")
    if any(k in text_corpus for k in ("prisma", "typeorm")) and lang == "typescript":
        domain_libraries.append("Prisma")
    if any(k in text_corpus for k in ("redux", "zustand")) and lang == "typescript":
        domain_libraries.append("Zustand / Redux")

    # Level 4: Infrastructure Dependencies
    if "redis" in text_corpus:
        infra_deps.append("Redis")
    if any(k in text_corpus for k in ("postgres", "postgresql", "sql")):
        infra_deps.append("PostgreSQL")
    if any(k in text_corpus for k in ("vector", "pinecone", "weaviate", "qdrant", "chroma", "pgvector", "rag")):
        infra_deps.append("Vector Database")
    if any(k in text_corpus for k in ("kafka", "pubsub", "pub/sub", "event")):
        infra_deps.append("Kafka")
    if "celery" in text_corpus:
        infra_deps.append("Celery")
    if any(k in text_corpus for k in ("websocket", "websockets", "stream", "audio", "duplex")) and "WebSockets" not in domain_libraries:
        infra_deps.append("WebSocket Duplex Stream")

    # Enforce strict anti-soup limits: maximum 3 domain libraries, 2 infra dependencies
    domain_libraries = domain_libraries[:3]
    infra_deps = infra_deps[:2]

    ecosystem = TechnologyEnvironment(
        primary_language=lang,
        file_extension=ext,
        framework=framework,
        domain_libraries=domain_libraries,
        infrastructure_dependencies=infra_deps,
        selection_rationale="Baseline technology environment detected from candidate profile and job requirements",
    )
    return lang, ext, ecosystem
