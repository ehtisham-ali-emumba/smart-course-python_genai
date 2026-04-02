#!/usr/bin/env python3
"""Seed a Python course with PDF-only lessons.

This script mirrors the existing shell seed flow and uses the same API endpoints,
but creates a Python course and uploads only PDF lessons (no audio/video).

Usage:
  python3 course-seed/seed_python_course.py
    python3 course-seed/seed_python_course.py --base-url http://localhost:8000
    python3 course-seed/seed_python_course.py --skip-course-publish
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    print("[ERROR] Missing dependency: requests")
    print("Install it with: pip install requests")
    sys.exit(1)


class Colors:
    GREEN = "\033[0;32m"
    BLUE = "\033[0;34m"
    RED = "\033[0;31m"
    YELLOW = "\033[1;33m"
    NC = "\033[0m"


def log_info(message: str) -> None:
    print(f"{Colors.BLUE}[INFO]{Colors.NC} {message}")


def log_success(message: str) -> None:
    print(f"{Colors.GREEN}[SUCCESS]{Colors.NC} {message}")


def log_error(message: str) -> None:
    print(f"{Colors.RED}[ERROR]{Colors.NC} {message}")


def log_step(message: str) -> None:
    print(f"{Colors.YELLOW}[STEP]{Colors.NC} {message}")


@dataclass
class LessonSeed:
    title: str
    duration_minutes: int
    order: int
    pdf_file: str


@dataclass
class ModuleSeed:
    title: str
    description: str
    order: int
    lessons: list[LessonSeed]


MODULES: list[ModuleSeed] = [
    ModuleSeed(
        title="Module 1: Python Fundamentals",
        description=(
            "Learn Python basics including variables, data types, control flow, "
            "functions, collections, and exception handling."
        ),
        order=1,
        lessons=[
            LessonSeed(
                title="Python Basics: Variables, Data Types, and Control Flow",
                duration_minutes=45,
                order=1,
                pdf_file="py_m1_l1_basics.pdf",
            ),
            LessonSeed(
                title="Python Functions, Scope, and Lambda Expressions",
                duration_minutes=30,
                order=2,
                pdf_file="py_m1_l2_functions.pdf",
            ),
            LessonSeed(
                title="Working with Lists, Tuples, Dictionaries, and Sets",
                duration_minutes=35,
                order=3,
                pdf_file="py_m1_l3_collections.pdf",
            ),
            LessonSeed(
                title="Error Handling and Debugging in Python",
                duration_minutes=25,
                order=4,
                pdf_file="py_m1_l4_debugging.pdf",
            ),
        ],
    ),
    ModuleSeed(
        title="Module 2: Intermediate Python",
        description=(
            "Dive into files and I/O, modules and packages, HTTP requests, "
            "virtual environments, and modern Python workflows."
        ),
        order=2,
        lessons=[
            LessonSeed(
                title="Asynchronous Concepts and Concurrency in Python",
                duration_minutes=50,
                order=1,
                pdf_file="py_m2_l1_async.pdf",
            ),
            LessonSeed(
                title="File Handling and Data Processing",
                duration_minutes=35,
                order=2,
                pdf_file="py_m2_l2_file_io.pdf",
            ),
            LessonSeed(
                title="HTTP APIs in Python with requests",
                duration_minutes=30,
                order=3,
                pdf_file="py_m2_l3_http.pdf",
            ),
            LessonSeed(
                title="Modules, Packages, and Virtual Environments",
                duration_minutes=35,
                order=4,
                pdf_file="py_m2_l4_packages.pdf",
            ),
        ],
    ),
    ModuleSeed(
        title="Module 3: Advanced Python",
        description=(
            "Master object-oriented design, testing, performance tuning, and "
            "building production-ready Python services."
        ),
        order=3,
        lessons=[
            LessonSeed(
                title="Design Patterns and Best Practices in Python",
                duration_minutes=55,
                order=1,
                pdf_file="py_m3_l1_patterns.pdf",
            ),
            LessonSeed(
                title="Object-Oriented Programming in Python",
                duration_minutes=40,
                order=2,
                pdf_file="py_m3_l2_oop.pdf",
            ),
            LessonSeed(
                title="Testing Python Applications: pytest and unittest",
                duration_minutes=35,
                order=3,
                pdf_file="py_m3_l3_testing.pdf",
            ),
            LessonSeed(
                title="Building and Deploying Python Backend Services",
                duration_minutes=40,
                order=4,
                pdf_file="py_m3_l4_services.pdf",
            ),
        ],
    ),
]


class SeedClient:
    def __init__(self, base_url: str, access_token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {access_token}"})

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}{path}",
            json=payload,
            timeout=60,
        )
        return _decode_response(response)

    def put_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.put(
            f"{self.base_url}{path}",
            json=payload,
            timeout=60,
        )
        return _decode_response(response)

    def patch_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.patch(
            f"{self.base_url}{path}",
            json=payload,
            timeout=60,
        )
        return _decode_response(response)

    def get_json(self, path: str) -> dict[str, Any]:
        response = self.session.get(f"{self.base_url}{path}", timeout=60)
        return _decode_response(response)


def _decode_response(response: requests.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        data = {"raw": response.text}

    if response.status_code >= 400:
        raise RuntimeError(
            f"HTTP {response.status_code}: {json.dumps(data, ensure_ascii=True)}"
        )
    return data


def login(base_url: str, email: str, password: str) -> str:
    response = requests.post(
        f"{base_url.rstrip('/')}/auth/login",
        json={"email": email, "password": password},
        timeout=60,
    )
    data = _decode_response(response)
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"Missing access token in login response: {data}")
    return token


def create_course(client: SeedClient, slug_prefix: str) -> str:
    slug = f"{slug_prefix}-{int(time.time())}"
    payload = {
        "title": "Python Mastery: From Fundamentals to Advanced",
        "slug": slug,
        "description": (
            "A comprehensive Python course covering fundamentals, data structures, "
            "functions, OOP, testing, API usage, and backend service development."
        ),
        "category": "Programming",
        "level": "beginner",
        "language": "en",
        "duration_hours": 24.0,
        "price": 79.99,
        "currency": "USD",
        "max_students": 100,
    }
    data = client.post_json("/courses", payload)
    course_id = data.get("id")
    if not course_id:
        raise RuntimeError(f"Course ID missing from response: {data}")
    return course_id


def init_course_content(client: SeedClient, course_id: str) -> None:
    payload = {
        "modules": [],
        "metadata": {
            "total_modules": 0,
            "total_lessons": 0,
            "total_duration_hours": 0,
            "tags": ["python", "programming", "backend"],
        },
    }
    data = client.put_json(f"/courses/{course_id}/content", payload)
    if not data.get("course_id"):
        raise RuntimeError(f"Course content init failed: {data}")


def create_module(client: SeedClient, course_id: str, module: ModuleSeed) -> str:
    payload = {
        "title": module.title,
        "description": module.description,
        "order": module.order,
        "is_published": True,
        "lessons": [],
    }
    data = client.post_json(f"/courses/{course_id}/content/modules", payload)

    for module_data in data.get("modules", []):
        if module_data.get("order") == module.order:
            module_id = module_data.get("module_id")
            if module_id:
                return module_id
    raise RuntimeError(f"Could not locate module_id for order={module.order}: {data}")


def create_pdf_lesson(
    client: SeedClient,
    course_id: str,
    module_id: str,
    lesson: LessonSeed,
    content_dir: Path,
) -> None:
    pdf_path = content_dir / lesson.pdf_file
    if not pdf_path.exists():
        raise FileNotFoundError(f"Missing PDF file: {pdf_path}")

    with pdf_path.open("rb") as file_handle:
        files = {"file": (pdf_path.name, file_handle, "application/pdf")}
        form = {
            "title": lesson.title,
            "type": "text",
            "duration_minutes": str(lesson.duration_minutes),
            "order": str(lesson.order),
            "is_preview": "false",
        }
        response = client.session.post(
            f"{client.base_url}/courses/{course_id}/content/modules/{module_id}/lessons/with-file",
            data=form,
            files=files,
            timeout=120,
        )

    data = _decode_response(response)

    for module_data in data.get("modules", []):
        if module_data.get("module_id") != module_id:
            continue
        for lesson_data in module_data.get("lessons", []):
            if lesson_data.get("order") == lesson.order:
                lesson_id = lesson_data.get("lesson_id")
                if lesson_id:
                    log_success(f"  Lesson created: {lesson.title} (ID: {lesson_id})")
                    return

    raise RuntimeError(
        f"Could not verify lesson creation for order={lesson.order}: {data}"
    )


def get_module_lesson_ids(client: SeedClient, course_id: str) -> dict[str, list[str]]:
    data = client.get_json(f"/courses/{course_id}/content")
    mapping: dict[str, list[str]] = {}
    for module in data.get("modules", []):
        module_id = module.get("module_id")
        if not module_id:
            continue
        lesson_ids = [
            lesson.get("lesson_id")
            for lesson in module.get("lessons", [])
            if lesson.get("lesson_id")
        ]
        mapping[module_id] = lesson_ids
    return mapping


def generate_quiz(
    client: SeedClient, course_id: str, module_id: str, lesson_ids: list[str]
) -> None:
    payload = {
        "source_lesson_ids": lesson_ids,
        "num_questions": 5,
        "passing_score": 70,
        "max_attempts": 3,
        "time_limit_minutes": 30,
    }
    data = client.post_json(
        f"/courses/{course_id}/modules/{module_id}/quiz/generate", payload
    )
    quiz_id = data.get("id")
    if not quiz_id:
        raise RuntimeError(f"Quiz generation failed for module {module_id}: {data}")
    log_success(f"  Quiz generated for module {module_id} (ID: {quiz_id})")


def generate_summary(
    client: SeedClient, course_id: str, module_id: str, lesson_ids: list[str]
) -> None:
    payload = {
        "source_lesson_ids": lesson_ids,
        "include_glossary": True,
        "include_key_points": True,
        "include_learning_objectives": True,
    }
    data = client.post_json(
        f"/courses/{course_id}/modules/{module_id}/summary/generate",
        payload,
    )
    summary_id = data.get("id")
    if not summary_id:
        raise RuntimeError(f"Summary generation failed for module {module_id}: {data}")
    log_success(f"  Summary generated for module {module_id} (ID: {summary_id})")


def publish_module_artifacts(
    client: SeedClient, course_id: str, module_id: str
) -> None:
    quiz_data = client.patch_json(
        f"/courses/{course_id}/modules/{module_id}/quiz/publish",
        {"is_published": True},
    )
    if not quiz_data.get("is_published"):
        raise RuntimeError(f"Quiz publish failed for module {module_id}: {quiz_data}")

    summary_data = client.patch_json(
        f"/courses/{course_id}/modules/{module_id}/summary/publish",
        {"is_published": True},
    )
    if not summary_data.get("is_published"):
        raise RuntimeError(
            f"Summary publish failed for module {module_id}: {summary_data}"
        )

    log_success(f"  Quiz and summary published for module {module_id}")


def publish_course(client: SeedClient, course_id: str, timeout_seconds: int) -> str:
    data = client.patch_json(f"/courses/{course_id}/status", {"status": "published"})
    status = data.get("status", "")
    if status == "published":
        return status

    if status != "publish_requested":
        raise RuntimeError(f"Unexpected publish status: {data}")

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        time.sleep(2)
        check = client.get_json(f"/courses/{course_id}")
        current = check.get("status", "")
        if current == "published":
            return current

    raise TimeoutError("Timed out waiting for course publish workflow.")


def summarize_content(
    client: SeedClient, course_id: str
) -> tuple[int, int, dict[str, Any]]:
    data = client.get_json(f"/courses/{course_id}/content")
    modules = data.get("modules", [])
    total_modules = len(modules)
    total_lessons = sum(len(module.get("lessons", [])) for module in modules)
    return total_modules, total_lessons, data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed Python course data with PDF-only lessons"
    )
    parser.add_argument(
        "--base-url", default="http://localhost:8000", help="API base URL"
    )
    parser.add_argument("--email", default="teacher@test.com", help="Teacher email")
    parser.add_argument("--password", default="TestPass123", help="Teacher password")
    parser.add_argument(
        "--content-dir",
        default=str(Path(__file__).resolve().parent / "content"),
        help="Directory containing lesson PDFs",
    )
    parser.add_argument(
        "--slug-prefix",
        default="python-mastery",
        help="Slug prefix (timestamp is appended)",
    )
    parser.add_argument(
        "--skip-course-publish",
        action="store_true",
        help="Create content/quizzes/summaries but skip course status publish",
    )
    parser.add_argument(
        "--publish-timeout-seconds",
        type=int,
        default=60,
        help="How long to wait for async course publish completion",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    content_dir = Path(args.content_dir).resolve()

    try:
        log_step("Logging in as teacher...")
        access_token = login(args.base_url, args.email, args.password)
        log_success("Logged in successfully.")

        client = SeedClient(args.base_url, access_token)

        log_step("Creating Python course...")
        course_id = create_course(client, args.slug_prefix)
        log_success(f"Course created with ID: {course_id}")

        log_step("Initializing course content...")
        init_course_content(client, course_id)
        log_success("Course content initialized.")

        log_step("Creating modules...")
        module_ids: dict[int, str] = {}
        for module in MODULES:
            module_id = create_module(client, course_id, module)
            module_ids[module.order] = module_id
            log_success(f"  {module.title} created (ID: {module_id})")

        log_step("Creating PDF lessons (no audio/video)...")
        for module in MODULES:
            module_id = module_ids[module.order]
            log_info(f"  Populating {module.title}...")
            for lesson in module.lessons:
                create_pdf_lesson(client, course_id, module_id, lesson, content_dir)

        log_step("Collecting lesson IDs per module...")
        lesson_ids_by_module = get_module_lesson_ids(client, course_id)

        log_step("Generating quizzes and summaries...")
        for module in MODULES:
            module_id = module_ids[module.order]
            lesson_ids = lesson_ids_by_module.get(module_id, [])
            if not lesson_ids:
                raise RuntimeError(f"No lesson IDs found for module {module_id}")
            generate_quiz(client, course_id, module_id, lesson_ids)
            generate_summary(client, course_id, module_id, lesson_ids)

        log_step("Publishing quizzes and summaries...")
        for module in MODULES:
            module_id = module_ids[module.order]
            publish_module_artifacts(client, course_id, module_id)

        course_status = "draft"
        if not args.skip_course_publish:
            log_step("Publishing the course...")
            course_status = publish_course(
                client, course_id, args.publish_timeout_seconds
            )
            log_success(f"Course publish workflow completed (status: {course_status})")
        else:
            log_info("Skipping course publish as requested.")

        log_step("Final verification...")
        total_modules, total_lessons, content_data = summarize_content(
            client, course_id
        )

        print("\n============================================")
        print(f"{Colors.GREEN}Course Seeding Complete!{Colors.NC}")
        print("============================================")
        print(f"Course ID:       {Colors.YELLOW}{course_id}{Colors.NC}")
        print(f"Status:          {Colors.YELLOW}{course_status}{Colors.NC}")
        print(f"Total Modules:   {Colors.YELLOW}{total_modules}{Colors.NC}")
        print(f"Total Lessons:   {Colors.YELLOW}{total_lessons}{Colors.NC}")
        print("\nCourse Structure:")

        for module in sorted(
            content_data.get("modules", []), key=lambda m: m.get("order", 0)
        ):
            print(f"  Module {module.get('order')}: {module.get('title')}")
            for lesson in sorted(
                module.get("lessons", []), key=lambda l: l.get("order", 0)
            ):
                print(
                    f"    Lesson {lesson.get('order')}: {lesson.get('title')} [{lesson.get('type')}]"
                )
            print("    Quiz: Generated & Published")
            print("    Summary: Generated & Published")

        print("============================================")
        return 0

    except Exception as exc:  # pylint: disable=broad-except
        log_error(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
