#!/usr/bin/env python3
"""Generate Python-course PDFs for seeding.

Creates 12 lesson PDFs in the content directory that match the lesson
structure used by seed_python_course.py.
"""

from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

try:
    from fpdf import FPDF
except ImportError:
    raise SystemExit("Missing dependency: fpdf. Install with: pip install fpdf")

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    plt = None


CONTENT_DIR = Path(__file__).resolve().parent / "content"


LESSONS = [
    {
        "filename": "py_m1_l1_basics.pdf",
        "title": "Python Basics: Variables, Data Types, and Control Flow",
        "section": "Module 1: Python Fundamentals",
        "duration": 45,
        "topics": [
            "Variables, naming, and dynamic typing",
            "Core data types: str, int, float, bool, list, dict, tuple, set",
            "Conditionals and loops for program flow",
            "Practical coding patterns for clean beginner code",
        ],
    },
    {
        "filename": "py_m1_l2_functions.pdf",
        "title": "Python Functions, Scope, and Lambda Expressions",
        "section": "Module 1: Python Fundamentals",
        "duration": 30,
        "topics": [
            "Function definitions, parameters, and return values",
            "Local vs global scope and LEGB lookup",
            "Lambda expressions and functional helpers",
            "Writing reusable logic with clear APIs",
        ],
    },
    {
        "filename": "py_m1_l3_collections.pdf",
        "title": "Working with Lists, Tuples, Dictionaries, and Sets",
        "section": "Module 1: Python Fundamentals",
        "duration": 35,
        "topics": [
            "Choosing the right collection for each task",
            "Mutability, hashing, and membership performance",
            "Comprehensions for concise transformations",
            "Common anti-patterns and readability trade-offs",
        ],
    },
    {
        "filename": "py_m1_l4_debugging.pdf",
        "title": "Error Handling and Debugging in Python",
        "section": "Module 1: Python Fundamentals",
        "duration": 25,
        "topics": [
            "try/except/else/finally patterns",
            "Raising custom exceptions responsibly",
            "Stack traces and root-cause debugging",
            "Using logging over print in real projects",
        ],
    },
    {
        "filename": "py_m2_l1_async.pdf",
        "title": "Asynchronous Concepts and Concurrency in Python",
        "section": "Module 2: Intermediate Python",
        "duration": 50,
        "topics": [
            "Threads vs processes vs asyncio",
            "Coroutines, await, and event loops",
            "I/O-bound vs CPU-bound workload strategy",
            "Concurrency pitfalls and mitigation",
        ],
    },
    {
        "filename": "py_m2_l2_file_io.pdf",
        "title": "File Handling and Data Processing",
        "section": "Module 2: Intermediate Python",
        "duration": 35,
        "topics": [
            "Pathlib and safe file operations",
            "CSV/JSON parsing and serialization",
            "Streaming large files efficiently",
            "Validation and defensive parsing",
        ],
    },
    {
        "filename": "py_m2_l3_http.pdf",
        "title": "HTTP APIs in Python with requests",
        "section": "Module 2: Intermediate Python",
        "duration": 30,
        "topics": [
            "GET/POST workflows with requests",
            "Headers, auth, query params, and timeouts",
            "Retry and backoff strategies",
            "Robust error handling for network calls",
        ],
    },
    {
        "filename": "py_m2_l4_packages.pdf",
        "title": "Modules, Packages, and Virtual Environments",
        "section": "Module 2: Intermediate Python",
        "duration": 35,
        "topics": [
            "Organizing code into modules and packages",
            "Imports and dependency boundaries",
            "Virtual environments and reproducibility",
            "Project structure for scalable codebases",
        ],
    },
    {
        "filename": "py_m3_l1_patterns.pdf",
        "title": "Design Patterns and Best Practices in Python",
        "section": "Module 3: Advanced Python",
        "duration": 55,
        "topics": [
            "Factory, strategy, adapter, and repository patterns",
            "Separation of concerns in service design",
            "Balancing abstraction and simplicity",
            "Refactoring toward maintainability",
        ],
    },
    {
        "filename": "py_m3_l2_oop.pdf",
        "title": "Object-Oriented Programming in Python",
        "section": "Module 3: Advanced Python",
        "duration": 40,
        "topics": [
            "Classes, inheritance, composition",
            "Dunder methods and data model basics",
            "Dataclasses and typed models",
            "When to prefer OOP vs functional approaches",
        ],
    },
    {
        "filename": "py_m3_l3_testing.pdf",
        "title": "Testing Python Applications: pytest and unittest",
        "section": "Module 3: Advanced Python",
        "duration": 35,
        "topics": [
            "Unit, integration, and contract testing",
            "pytest fixtures and parametrization",
            "Mocking external systems",
            "Coverage quality and CI gating",
        ],
    },
    {
        "filename": "py_m3_l4_services.pdf",
        "title": "Building and Deploying Python Backend Services",
        "section": "Module 3: Advanced Python",
        "duration": 40,
        "topics": [
            "FastAPI service design essentials",
            "Configuration and environment management",
            "Containerization and observability basics",
            "Deployment safety and rollback planning",
        ],
    },
]


def _add_header(pdf: FPDF, section: str, title: str, duration: int) -> None:
    pdf.set_font("Helvetica", "B", 18)
    pdf.multi_cell(0, 10, title)
    pdf.ln(1)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 8, f"{section} | Estimated Duration: {duration} minutes", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)


def _add_body(pdf: FPDF, title: str, topics: list[str]) -> None:
    intro = (
        f"This lesson develops practical understanding for: {title}. "
        "The notes are optimized for course seeding and AI quiz/summary generation."
    )
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, textwrap.fill(intro, width=100))
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Key Topics", ln=True)
    pdf.set_font("Helvetica", "", 11)
    for topic in topics:
        pdf.multi_cell(0, 6, f"- {topic}")

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Hands-on Focus", ln=True)
    pdf.set_font("Helvetica", "", 11)
    practice = (
        "Students should implement small exercises per topic, then combine concepts "
        "into one mini project to reinforce retention and confidence."
    )
    pdf.multi_cell(0, 6, textwrap.fill(practice, width=100))


def _create_runtime_plot_image(tmp_dir: Path) -> Path:
    if plt is None:
        raise RuntimeError("matplotlib is not installed")

    labels = ["FastAPI", "Flask", "Django", "Node.js", "Go"]
    rps = [820, 640, 560, 760, 940]
    colors = ["#009688", "#3F51B5", "#607D8B", "#4CAF50", "#FF9800"]

    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    bars = ax.bar(labels, rps, color=colors)
    for bar, val in zip(bars, rps):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            val + 10,
            str(val),
            ha="center",
            fontsize=9,
        )
    ax.set_title("API Throughput Comparison (Req/s)", fontsize=12, fontweight="bold")
    ax.set_ylabel("Requests per second")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_ylim(0, 1020)

    out_path = tmp_dir / "python_runtime_plot.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


def _add_plot_page_if_needed(pdf: FPDF, out_path: Path) -> None:
    if out_path.name != "py_m3_l4_services.pdf":
        return

    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "Service Runtime Snapshot", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(
        0,
        6,
        (
            "This visual compares representative throughput across backend runtimes. "
            "It is included for chart-based content testing in seeded lessons."
        ),
    )
    pdf.ln(2)

    if plt is None:
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, "Plot omitted: install matplotlib to embed chart images.")
        return

    with tempfile.TemporaryDirectory() as td:
        chart_path = _create_runtime_plot_image(Path(td))
        pdf.image(str(chart_path), x=15, w=180)


def generate_pdf(
    out_path: Path, title: str, section: str, duration: int, topics: list[str]
) -> None:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    _add_header(pdf, section, title, duration)
    _add_body(pdf, title, topics)
    _add_plot_page_if_needed(pdf, out_path)

    pdf.output(str(out_path))


def main() -> int:
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating Python course PDFs...")

    for lesson in LESSONS:
        out_file = CONTENT_DIR / lesson["filename"]
        generate_pdf(
            out_path=out_file,
            title=lesson["title"],
            section=lesson["section"],
            duration=lesson["duration"],
            topics=lesson["topics"],
        )
        print(f"  Created {out_file.name}")

    print("Done. Generated 12 Python course PDFs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
