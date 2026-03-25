"""
Generate PDFs with charts, graphs, and images for testing.
Replaces select PDFs in the content/ folder.
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont
import os
import io
import tempfile

CONTENT_DIR = os.path.join(os.path.dirname(__file__), "content")
TEMP_DIR = tempfile.mkdtemp()


def save_fig(fig, name):
    path = os.path.join(TEMP_DIR, name)
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return path


def create_diagram_image(name, width=600, height=300, draw_fn=None):
    img = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(img)
    if draw_fn:
        draw_fn(draw, width, height)
    path = os.path.join(TEMP_DIR, name)
    img.save(path)
    return path


# ============================================================
# PDF 1: m1_l2_functions.pdf - Functions, Scope, and Closures
# ============================================================
def gen_functions_pdf():
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    # --- Page 1: Title + Intro ---
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 15, "Functions, Scope, and Closures", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, (
        "Functions are one of the fundamental building blocks in JavaScript. A function is a reusable "
        "block of code designed to perform a particular task. In this lesson, we explore function declarations, "
        "expressions, arrow functions, scope rules, and closures."
    ))
    pdf.ln(5)

    # Chart 1: Function types usage in modern JS projects
    fig, ax = plt.subplots(figsize=(6, 3.5))
    types = ['Arrow\nFunctions', 'Function\nDeclarations', 'Function\nExpressions', 'IIFE', 'Generator\nFunctions']
    usage = [62, 25, 8, 3, 2]
    colors = ['#4CAF50', '#2196F3', '#FF9800', '#9C27B0', '#F44336']
    bars = ax.bar(types, usage, color=colors, edgecolor='white', linewidth=1.2)
    for bar, val in zip(bars, usage):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, f'{val}%', ha='center', fontsize=9, fontweight='bold')
    ax.set_ylabel('Usage (%)', fontsize=10)
    ax.set_title('Function Type Usage in Modern JavaScript Projects', fontsize=12, fontweight='bold')
    ax.set_ylim(0, 75)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    chart1 = save_fig(fig, "func_types_bar.png")

    pdf.image(chart1, x=15, w=180)
    pdf.ln(5)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "1. Function Declarations vs Expressions", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, (
        "A function declaration defines a named function using the 'function' keyword. It is hoisted to the top "
        "of its scope, meaning it can be called before it appears in the code. A function expression assigns an "
        "anonymous (or named) function to a variable. Unlike declarations, expressions are not hoisted.\n\n"
        "Example:\n"
        "  // Declaration\n"
        "  function greet(name) { return `Hello, ${name}!`; }\n\n"
        "  // Expression\n"
        "  const greet = function(name) { return `Hello, ${name}!`; };\n\n"
        "  // Arrow Function (ES6+)\n"
        "  const greet = (name) => `Hello, ${name}!`;"
    ))
    pdf.ln(3)

    # --- Page 2: Scope ---
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "2. Understanding Scope", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, (
        "Scope determines the accessibility of variables. JavaScript has three types of scope:\n"
        "- Global Scope: Variables declared outside any function or block\n"
        "- Function Scope: Variables declared inside a function (var)\n"
        "- Block Scope: Variables declared inside a block with let/const\n\n"
        "The scope chain allows inner functions to access variables from outer scopes, "
        "but not the other way around."
    ))
    pdf.ln(3)

    # Diagram: Scope chain visualization
    def draw_scope(draw, w, h):
        # Global scope box
        draw.rounded_rectangle([20, 10, w-20, h-10], radius=15, outline='#1565C0', width=3)
        draw.text((30, 15), "Global Scope", fill='#1565C0')
        draw.text((30, 35), "var globalVar = 'I am global';", fill='#333')
        # Function scope box
        draw.rounded_rectangle([50, 60, w-50, h-30], radius=12, outline='#2E7D32', width=3)
        draw.text((60, 65), "Function Scope (outer)", fill='#2E7D32')
        draw.text((60, 85), "var outerVar = 'I am outer';", fill='#333')
        # Block scope box
        draw.rounded_rectangle([80, 115, w-80, h-50], radius=10, outline='#E65100', width=3)
        draw.text((90, 120), "Block Scope (inner)", fill='#E65100')
        draw.text((90, 140), "let innerVar = 'I am block-scoped';", fill='#333')
        # Arrows
        draw.text((w-180, 165), "Can access: innerVar, outerVar, globalVar", fill='#555')

    scope_img = create_diagram_image("scope_chain.png", 600, 220, draw_scope)
    pdf.image(scope_img, x=15, w=180)
    pdf.ln(5)

    # Chart 2: Pie chart - var vs let vs const usage
    fig, ax = plt.subplots(figsize=(5, 4))
    labels = ['const', 'let', 'var']
    sizes = [58, 35, 7]
    colors_pie = ['#4CAF50', '#2196F3', '#FF5722']
    explode = (0.05, 0.02, 0.1)
    wedges, texts, autotexts = ax.pie(sizes, explode=explode, labels=labels, colors=colors_pie,
                                       autopct='%1.0f%%', startangle=90, textprops={'fontsize': 11})
    for t in autotexts:
        t.set_fontweight('bold')
    ax.set_title('Variable Declaration Usage in ES6+ Codebases', fontsize=12, fontweight='bold')
    chart2 = save_fig(fig, "var_let_const_pie.png")
    pdf.image(chart2, x=30, w=150)
    pdf.ln(3)

    # --- Page 3: Closures ---
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "3. Closures", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, (
        "A closure is a function that retains access to its outer (enclosing) function's variables even after "
        "the outer function has returned. Closures are created every time a function is created.\n\n"
        "Example:\n"
        "  function createCounter() {\n"
        "    let count = 0;\n"
        "    return {\n"
        "      increment: () => ++count,\n"
        "      getCount: () => count\n"
        "    };\n"
        "  }\n"
        "  const counter = createCounter();\n"
        "  counter.increment(); // 1\n"
        "  counter.increment(); // 2\n"
        "  counter.getCount();  // 2\n\n"
        "Closures are widely used for data privacy, factory functions, memoization, "
        "and maintaining state in functional programming patterns."
    ))
    pdf.ln(5)

    # Chart 3: Line chart - closure memory retention over time
    fig, ax = plt.subplots(figsize=(6, 3.5))
    calls = np.arange(0, 11)
    mem_with_closure = 2 + 0.5 * calls + 0.05 * calls**2
    mem_without = np.full_like(calls, 2.0, dtype=float)
    ax.plot(calls, mem_with_closure, 'o-', color='#E53935', linewidth=2, label='With Closures (retaining state)')
    ax.plot(calls, mem_without, 's--', color='#43A047', linewidth=2, label='Without Closures (no state)')
    ax.fill_between(calls, mem_without, mem_with_closure, alpha=0.1, color='red')
    ax.set_xlabel('Number of Function Calls', fontsize=10)
    ax.set_ylabel('Memory Usage (MB)', fontsize=10)
    ax.set_title('Memory Footprint: Closures vs Regular Functions', fontsize=12, fontweight='bold')
    ax.legend(fontsize=9)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    chart3 = save_fig(fig, "closure_memory.png")
    pdf.image(chart3, x=15, w=180)

    pdf.output(os.path.join(CONTENT_DIR, "m1_l2_functions.pdf"))
    print("  Created m1_l2_functions.pdf")


# ============================================================
# PDF 2: m1_l3_arrays_objects.pdf - Arrays and Objects Deep Dive
# ============================================================
def gen_arrays_objects_pdf():
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    # --- Page 1 ---
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 15, "Arrays and Objects Deep Dive", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, (
        "Arrays and objects are the two most important data structures in JavaScript. Arrays store ordered "
        "collections of values, while objects store key-value pairs. Understanding their methods and performance "
        "characteristics is essential for writing efficient JavaScript code."
    ))
    pdf.ln(5)

    # Chart: Array method performance comparison
    fig, ax = plt.subplots(figsize=(7, 4))
    methods = ['push', 'pop', 'shift', 'unshift', 'splice\n(middle)', 'indexOf', 'includes', 'forEach', 'map', 'filter', 'reduce']
    # Time complexity visualization (relative ops/sec in thousands)
    perf = [950, 980, 120, 110, 85, 200, 210, 450, 420, 400, 380]
    colors = ['#4CAF50' if p > 500 else '#FF9800' if p > 200 else '#F44336' for p in perf]
    bars = ax.barh(methods, perf, color=colors, edgecolor='white', height=0.7)
    for bar, val in zip(bars, perf):
        ax.text(val + 10, bar.get_y() + bar.get_height()/2, f'{val}K ops/s', va='center', fontsize=8)
    ax.set_xlabel('Operations per Second (thousands)', fontsize=10)
    ax.set_title('JavaScript Array Method Performance Benchmark', fontsize=12, fontweight='bold')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    legend_elements = [
        mpatches.Patch(color='#4CAF50', label='O(1) - Fast'),
        mpatches.Patch(color='#FF9800', label='O(n) - Medium'),
        mpatches.Patch(color='#F44336', label='O(n) - Slow'),
    ]
    ax.legend(handles=legend_elements, loc='lower right', fontsize=9)
    chart1 = save_fig(fig, "array_perf.png")
    pdf.image(chart1, x=10, w=190)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "1. Array Fundamentals", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, (
        "Arrays in JavaScript are dynamic, meaning they can grow or shrink. Key methods include:\n"
        "- Mutating: push(), pop(), shift(), unshift(), splice(), sort(), reverse()\n"
        "- Non-mutating: map(), filter(), reduce(), slice(), concat(), find(), every(), some()\n\n"
        "Example:\n"
        "  const nums = [1, 2, 3, 4, 5];\n"
        "  const doubled = nums.map(n => n * 2);     // [2, 4, 6, 8, 10]\n"
        "  const evens = nums.filter(n => n % 2 === 0); // [2, 4]\n"
        "  const sum = nums.reduce((a, b) => a + b, 0); // 15"
    ))

    # --- Page 2 ---
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "2. Objects and Prototypes", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, (
        "Objects are collections of key-value pairs. They can be created using object literals, "
        "constructors, or Object.create(). Every object has a prototype chain.\n\n"
        "Example:\n"
        "  const user = {\n"
        "    name: 'Alice',\n"
        "    age: 30,\n"
        "    greet() { return `Hi, I'm ${this.name}`; }\n"
        "  };\n\n"
        "Useful static methods: Object.keys(), Object.values(), Object.entries(), "
        "Object.assign(), Object.freeze(), Object.defineProperty()."
    ))
    pdf.ln(5)

    # Chart: Object operations comparison
    fig, ax = plt.subplots(figsize=(6, 4))
    categories = ['Property\nAccess', 'Property\nSet', 'delete', 'Object.keys()', 'for...in', 'JSON.stringify()']
    obj_10 = [98, 95, 80, 90, 85, 70]
    obj_1000 = [97, 93, 75, 60, 45, 25]
    obj_100000 = [96, 91, 70, 20, 12, 5]
    x = np.arange(len(categories))
    w = 0.25
    ax.bar(x - w, obj_10, w, label='10 properties', color='#4CAF50')
    ax.bar(x, obj_1000, w, label='1,000 properties', color='#2196F3')
    ax.bar(x + w, obj_100000, w, label='100,000 properties', color='#F44336')
    ax.set_ylabel('Relative Speed Score', fontsize=10)
    ax.set_title('Object Operation Speed by Object Size', fontsize=12, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=8)
    ax.legend(fontsize=9)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    chart2 = save_fig(fig, "obj_operations.png")
    pdf.image(chart2, x=15, w=180)
    pdf.ln(5)

    # Diagram: Array vs Object decision flowchart
    def draw_decision(draw, w, h):
        # Title
        draw.text((w//2 - 100, 5), "When to Use Array vs Object?", fill='#1565C0')
        # Start
        draw.rounded_rectangle([w//2-60, 30, w//2+60, 60], radius=8, outline='#333', width=2)
        draw.text((w//2-40, 38), "Is data ordered?", fill='#333')
        # Yes -> Array
        draw.line([(w//2-30, 60), (w//4, 90)], fill='#4CAF50', width=2)
        draw.text((w//4-50, 70), "Yes", fill='#4CAF50')
        draw.rounded_rectangle([w//4-60, 90, w//4+60, 120], radius=8, fill='#E8F5E9', outline='#4CAF50', width=2)
        draw.text((w//4-35, 98), "Use Array []", fill='#2E7D32')
        # No -> more questions
        draw.line([(w//2+30, 60), (3*w//4, 90)], fill='#F44336', width=2)
        draw.text((3*w//4-30, 70), "No", fill='#F44336')
        draw.rounded_rectangle([3*w//4-80, 90, 3*w//4+80, 120], radius=8, outline='#333', width=2)
        draw.text((3*w//4-65, 98), "Need named keys?", fill='#333')
        # Yes -> Object
        draw.line([(3*w//4-40, 120), (3*w//4-60, 150)], fill='#4CAF50', width=2)
        draw.text((3*w//4-110, 133), "Yes", fill='#4CAF50')
        draw.rounded_rectangle([3*w//4-120, 150, 3*w//4-10, 180], radius=8, fill='#E3F2FD', outline='#2196F3', width=2)
        draw.text((3*w//4-105, 158), "Use Object {}", fill='#1565C0')
        # No -> Map
        draw.line([(3*w//4+40, 120), (3*w//4+60, 150)], fill='#F44336', width=2)
        draw.text((3*w//4+45, 133), "No", fill='#F44336')
        draw.rounded_rectangle([3*w//4+10, 150, 3*w//4+130, 180], radius=8, fill='#FFF3E0', outline='#FF9800', width=2)
        draw.text((3*w//4+20, 158), "Use Map/Set", fill='#E65100')

    decision_img = create_diagram_image("array_vs_obj.png", 600, 200, draw_decision)
    pdf.image(decision_img, x=15, w=180)

    # --- Page 3: Destructuring ---
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "3. Destructuring and Spread Operator", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, (
        "ES6 introduced destructuring assignment, which makes it easy to extract values from arrays "
        "and objects into distinct variables.\n\n"
        "Array Destructuring:\n"
        "  const [first, second, ...rest] = [1, 2, 3, 4, 5];\n"
        "  // first = 1, second = 2, rest = [3, 4, 5]\n\n"
        "Object Destructuring:\n"
        "  const { name, age, ...other } = { name: 'Alice', age: 30, city: 'NYC' };\n\n"
        "Spread Operator:\n"
        "  const merged = [...arr1, ...arr2];\n"
        "  const clone = { ...original, newProp: 'value' };"
    ))
    pdf.ln(5)

    # Chart: Feature adoption timeline
    fig, ax = plt.subplots(figsize=(6, 3.5))
    years = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]
    destructuring = [5, 15, 35, 55, 70, 80, 88, 92, 95, 97]
    spread = [3, 10, 28, 48, 65, 78, 85, 90, 93, 96]
    optional_chain = [0, 0, 0, 0, 2, 15, 40, 60, 75, 85]
    ax.plot(years, destructuring, 'o-', color='#4CAF50', linewidth=2, label='Destructuring')
    ax.plot(years, spread, 's-', color='#2196F3', linewidth=2, label='Spread Operator')
    ax.plot(years, optional_chain, '^-', color='#FF9800', linewidth=2, label='Optional Chaining')
    ax.set_xlabel('Year', fontsize=10)
    ax.set_ylabel('Adoption Rate (%)', fontsize=10)
    ax.set_title('ES6+ Feature Adoption in JavaScript Projects', fontsize=12, fontweight='bold')
    ax.legend(fontsize=9)
    ax.set_ylim(0, 105)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='y', alpha=0.3)
    chart3 = save_fig(fig, "es6_adoption.png")
    pdf.image(chart3, x=15, w=180)

    pdf.output(os.path.join(CONTENT_DIR, "m1_l3_arrays_objects.pdf"))
    print("  Created m1_l3_arrays_objects.pdf")


# ============================================================
# PDF 3: m2_l3_fetch_api.pdf - Fetch API and HTTP Requests
# ============================================================
def gen_fetch_api_pdf():
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    # --- Page 1 ---
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 15, "Fetch API and HTTP Requests", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, (
        "The Fetch API provides a modern interface for making HTTP requests in JavaScript. "
        "It returns Promises, making it easier to work with asynchronous code compared to "
        "the older XMLHttpRequest API."
    ))
    pdf.ln(3)

    # Diagram: HTTP Request/Response flow
    def draw_http_flow(draw, w, h):
        # Client
        draw.rounded_rectangle([20, 50, 140, 110], radius=10, fill='#E3F2FD', outline='#1565C0', width=2)
        draw.text((45, 60), "Browser", fill='#1565C0')
        draw.text((35, 82), "fetch('/api/data')", fill='#333')
        # Server
        draw.rounded_rectangle([w-160, 50, w-20, 110], radius=10, fill='#E8F5E9', outline='#2E7D32', width=2)
        draw.text((w-130, 60), "Server", fill='#2E7D32')
        draw.text((w-155, 82), "Process & Respond", fill='#333')
        # Request arrow
        draw.line([(140, 65), (w-160, 65)], fill='#1565C0', width=3)
        draw.polygon([(w-165, 60), (w-160, 65), (w-165, 70)], fill='#1565C0')
        draw.text((w//2-60, 45), "HTTP Request (GET/POST)", fill='#1565C0')
        # Response arrow
        draw.line([(w-160, 95), (140, 95)], fill='#2E7D32', width=3)
        draw.polygon([(145, 90), (140, 95), (145, 100)], fill='#2E7D32')
        draw.text((w//2-55, 100), "JSON Response (200 OK)", fill='#2E7D32')
        # Status codes
        draw.text((20, 135), "Common Status Codes:", fill='#333')
        draw.text((20, 155), "200 OK | 201 Created | 400 Bad Request | 401 Unauthorized | 404 Not Found | 500 Server Error", fill='#555')

    http_img = create_diagram_image("http_flow.png", 650, 180, draw_http_flow)
    pdf.image(http_img, x=10, w=190)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "1. Basic Fetch Usage", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, (
        "The simplest use of fetch() takes a URL and returns a Promise:\n\n"
        "  // GET request\n"
        "  const response = await fetch('https://api.example.com/users');\n"
        "  const data = await response.json();\n\n"
        "  // POST request\n"
        "  const response = await fetch('https://api.example.com/users', {\n"
        "    method: 'POST',\n"
        "    headers: { 'Content-Type': 'application/json' },\n"
        "    body: JSON.stringify({ name: 'Alice', email: 'alice@example.com' })\n"
        "  });"
    ))

    # --- Page 2 ---
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "2. API Response Times by Method", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, (
        "Different HTTP methods have different performance profiles depending on the payload size "
        "and server processing requirements. The chart below shows typical API response times."
    ))
    pdf.ln(3)

    # Chart: Response times by HTTP method
    fig, ax = plt.subplots(figsize=(7, 4))
    methods_http = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']
    small_payload = [45, 65, 60, 55, 50]
    medium_payload = [50, 120, 110, 85, 55]
    large_payload = [80, 250, 230, 150, 60]
    x = np.arange(len(methods_http))
    w = 0.25
    ax.bar(x - w, small_payload, w, label='Small (<1KB)', color='#4CAF50')
    ax.bar(x, medium_payload, w, label='Medium (1-100KB)', color='#FF9800')
    ax.bar(x + w, large_payload, w, label='Large (>100KB)', color='#F44336')
    ax.set_ylabel('Response Time (ms)', fontsize=10)
    ax.set_title('Average API Response Time by HTTP Method & Payload Size', fontsize=12, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(methods_http)
    ax.legend()
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    chart1 = save_fig(fig, "api_response_times.png")
    pdf.image(chart1, x=10, w=190)
    pdf.ln(5)

    # Chart: Error rate distribution
    fig, ax = plt.subplots(figsize=(5, 4))
    error_labels = ['2xx Success', '3xx Redirect', '4xx Client Error', '5xx Server Error']
    error_sizes = [85, 5, 8, 2]
    error_colors = ['#4CAF50', '#2196F3', '#FF9800', '#F44336']
    wedges, texts, autotexts = ax.pie(error_sizes, labels=error_labels, colors=error_colors,
                                       autopct='%1.0f%%', startangle=90, textprops={'fontsize': 9})
    for t in autotexts:
        t.set_fontweight('bold')
    ax.set_title('HTTP Response Status Code Distribution\n(Typical Production API)', fontsize=11, fontweight='bold')
    chart2 = save_fig(fig, "status_dist.png")
    pdf.image(chart2, x=30, w=150)

    # --- Page 3: Error handling ---
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "3. Error Handling and Best Practices", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, (
        "The Fetch API does NOT reject on HTTP error statuses (404, 500). You must check response.ok:\n\n"
        "  async function fetchData(url) {\n"
        "    try {\n"
        "      const response = await fetch(url);\n"
        "      if (!response.ok) {\n"
        "        throw new Error(`HTTP error! status: ${response.status}`);\n"
        "      }\n"
        "      return await response.json();\n"
        "    } catch (error) {\n"
        "      console.error('Fetch failed:', error);\n"
        "      throw error;\n"
        "    }\n"
        "  }\n\n"
        "Best Practices:\n"
        "- Always handle network errors with try/catch\n"
        "- Check response.ok before parsing the body\n"
        "- Use AbortController for request timeouts\n"
        "- Set appropriate Content-Type headers\n"
        "- Use async/await over .then() chains for readability"
    ))
    pdf.ln(5)

    # Chart: Fetch vs XMLHttpRequest vs Axios popularity
    fig, ax = plt.subplots(figsize=(6, 3.5))
    years = [2018, 2019, 2020, 2021, 2022, 2023, 2024]
    fetch_pop = [25, 35, 48, 58, 67, 75, 82]
    axios_pop = [50, 52, 48, 42, 35, 28, 22]
    xhr_pop = [20, 10, 4, 2, 1, 0.5, 0.3]
    ax.stackplot(years, fetch_pop, axios_pop, xhr_pop,
                 labels=['Fetch API', 'Axios', 'XMLHttpRequest'],
                 colors=['#4CAF50', '#2196F3', '#FF9800'], alpha=0.8)
    ax.set_xlabel('Year', fontsize=10)
    ax.set_ylabel('Usage Share (%)', fontsize=10)
    ax.set_title('HTTP Client Library Usage Trends', fontsize=12, fontweight='bold')
    ax.legend(loc='center right', fontsize=9)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    chart3 = save_fig(fig, "http_client_trends.png")
    pdf.image(chart3, x=15, w=180)

    pdf.output(os.path.join(CONTENT_DIR, "m2_l3_fetch_api.pdf"))
    print("  Created m2_l3_fetch_api.pdf")


# ============================================================
# PDF 4: m3_l3_testing.pdf - JavaScript Testing
# ============================================================
def gen_testing_pdf():
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    # --- Page 1 ---
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 15, "JavaScript Testing - A Practical Guide", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, (
        "Testing is a critical part of software development. It helps catch bugs early, "
        "ensures code correctness, and provides confidence when refactoring. This lesson covers "
        "unit testing, integration testing, and end-to-end testing in JavaScript."
    ))
    pdf.ln(3)

    # Chart: Testing Pyramid
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    # E2E (top - small)
    triangle_e2e = plt.Polygon([[5, 9.5], [3.5, 7], [6.5, 7]], color='#F44336', alpha=0.8)
    ax.add_patch(triangle_e2e)
    ax.text(5, 7.8, 'E2E Tests', ha='center', va='center', fontsize=11, fontweight='bold', color='white')
    ax.text(5, 7.3, '~10%', ha='center', va='center', fontsize=9, color='white')
    # Integration (middle)
    trap_int = plt.Polygon([[3.5, 7], [6.5, 7], [7.5, 4], [2.5, 4]], color='#FF9800', alpha=0.8)
    ax.add_patch(trap_int)
    ax.text(5, 5.5, 'Integration Tests', ha='center', va='center', fontsize=12, fontweight='bold', color='white')
    ax.text(5, 4.8, '~20%', ha='center', va='center', fontsize=9, color='white')
    # Unit (bottom - large)
    trap_unit = plt.Polygon([[2.5, 4], [7.5, 4], [8.5, 1], [1.5, 1]], color='#4CAF50', alpha=0.8)
    ax.add_patch(trap_unit)
    ax.text(5, 2.5, 'Unit Tests', ha='center', va='center', fontsize=14, fontweight='bold', color='white')
    ax.text(5, 1.8, '~70%', ha='center', va='center', fontsize=10, color='white')
    # Labels on sides
    ax.annotate('Slower\nMore expensive\nHigher confidence', xy=(7.5, 8), fontsize=8, color='#666', ha='left')
    ax.annotate('Faster\nCheaper\nMore isolated', xy=(1.5, 1.5), fontsize=8, color='#666', ha='right')
    ax.arrow(8.5, 2, 0, 6, head_width=0.2, head_length=0.2, fc='#999', ec='#999')
    ax.set_title('The Testing Pyramid', fontsize=14, fontweight='bold', pad=10)
    ax.axis('off')
    chart1 = save_fig(fig, "testing_pyramid.png")
    pdf.image(chart1, x=25, w=160)

    # --- Page 2 ---
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "1. Unit Testing with Jest", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, (
        "Jest is the most popular JavaScript testing framework. It provides a test runner, "
        "assertion library, and mocking capabilities out of the box.\n\n"
        "Example:\n"
        "  // math.js\n"
        "  function add(a, b) { return a + b; }\n"
        "  function multiply(a, b) { return a * b; }\n\n"
        "  // math.test.js\n"
        "  describe('Math functions', () => {\n"
        "    test('adds 1 + 2 to equal 3', () => {\n"
        "      expect(add(1, 2)).toBe(3);\n"
        "    });\n"
        "    test('multiplies 3 * 4 to equal 12', () => {\n"
        "      expect(multiply(3, 4)).toBe(12);\n"
        "    });\n"
        "  });"
    ))
    pdf.ln(3)

    # Chart: Test framework popularity
    fig, ax = plt.subplots(figsize=(6, 3.5))
    frameworks = ['Jest', 'Vitest', 'Mocha', 'Cypress\n(E2E)', 'Playwright\n(E2E)', 'Jasmine']
    popularity = [72, 28, 15, 35, 30, 8]
    colors = ['#4CAF50', '#8BC34A', '#FF9800', '#2196F3', '#9C27B0', '#F44336']
    bars = ax.bar(frameworks, popularity, color=colors, edgecolor='white', linewidth=1.5)
    for bar, val in zip(bars, popularity):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, f'{val}%', ha='center', fontsize=9, fontweight='bold')
    ax.set_ylabel('Usage Among JS Developers (%)', fontsize=10)
    ax.set_title('JavaScript Testing Framework Popularity (2024)', fontsize=12, fontweight='bold')
    ax.set_ylim(0, 85)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    chart2 = save_fig(fig, "test_frameworks.png")
    pdf.image(chart2, x=15, w=180)

    # --- Page 3: Coverage ---
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "2. Code Coverage and Best Practices", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, (
        "Code coverage measures how much of your code is executed during tests. "
        "While 100% coverage doesn't guarantee bug-free code, it's a useful metric. "
        "Most teams aim for 70-90% coverage.\n\n"
        "Coverage Types:\n"
        "- Statement Coverage: % of statements executed\n"
        "- Branch Coverage: % of if/else branches taken\n"
        "- Function Coverage: % of functions called\n"
        "- Line Coverage: % of lines executed"
    ))
    pdf.ln(3)

    # Chart: Coverage metrics radar chart
    fig, ax = plt.subplots(figsize=(5, 5), subplot_kw=dict(polar=True))
    categories = ['Statement', 'Branch', 'Function', 'Line']
    N = len(categories)
    project_a = [92, 78, 88, 90]
    project_b = [75, 55, 70, 72]
    angles = [n / float(N) * 2 * np.pi for n in range(N)]
    angles += angles[:1]
    project_a += project_a[:1]
    project_b += project_b[:1]
    ax.plot(angles, project_a, 'o-', linewidth=2, color='#4CAF50', label='Well-tested Project')
    ax.fill(angles, project_a, alpha=0.15, color='#4CAF50')
    ax.plot(angles, project_b, 's-', linewidth=2, color='#F44336', label='Under-tested Project')
    ax.fill(angles, project_b, alpha=0.15, color='#F44336')
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=10)
    ax.set_ylim(0, 100)
    ax.set_title('Code Coverage Comparison', fontsize=12, fontweight='bold', pad=20)
    ax.legend(loc='lower right', bbox_to_anchor=(1.3, 0), fontsize=9)
    chart3 = save_fig(fig, "coverage_radar.png")
    pdf.image(chart3, x=25, w=160)
    pdf.ln(3)

    # Chart: Bug discovery rate by test type
    fig, ax = plt.subplots(figsize=(6, 3))
    test_types = ['Unit Tests', 'Integration Tests', 'E2E Tests', 'Manual QA', 'Production\nMonitoring']
    bugs_found = [35, 25, 15, 18, 7]
    cost_per_bug = [1, 5, 15, 25, 100]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.5))
    ax1.bar(test_types, bugs_found, color=['#4CAF50', '#8BC34A', '#FF9800', '#2196F3', '#F44336'])
    ax1.set_ylabel('Bugs Found (%)')
    ax1.set_title('Bug Discovery by Test Type', fontweight='bold', fontsize=11)
    ax1.tick_params(axis='x', labelsize=8)
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax2.bar(test_types, cost_per_bug, color=['#4CAF50', '#8BC34A', '#FF9800', '#2196F3', '#F44336'])
    ax2.set_ylabel('Relative Cost to Fix')
    ax2.set_title('Cost of Bug Fix by Stage', fontweight='bold', fontsize=11)
    ax2.tick_params(axis='x', labelsize=8)
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)
    plt.tight_layout()
    chart4 = save_fig(fig, "bug_cost.png")
    pdf.image(chart4, x=5, w=200)

    pdf.output(os.path.join(CONTENT_DIR, "m3_l3_testing.pdf"))
    print("  Created m3_l3_testing.pdf")


# ============================================================
# PDF 5: m3_l4_nodejs.pdf - Node.js (add some charts to this one too)
# ============================================================
def gen_nodejs_pdf():
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.add_page()
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 15, "Introduction to Node.js", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, (
        "Node.js is a JavaScript runtime built on Chrome's V8 engine that allows you to run "
        "JavaScript on the server side. It uses an event-driven, non-blocking I/O model that "
        "makes it lightweight and efficient for building scalable network applications."
    ))
    pdf.ln(3)

    # Diagram: Event Loop
    def draw_event_loop(draw, w, h):
        cx, cy = w // 2, h // 2
        r = 80
        draw.text((cx - 30, 10), "Node.js Event Loop", fill='#1565C0')
        # Draw circle
        draw.ellipse([cx-r, cy-r+10, cx+r, cy+r+10], outline='#1565C0', width=3)
        # Phases
        phases = [
            ("Timers", -60), ("Pending\nCallbacks", 0), ("Idle/Prepare", 60),
            ("Poll", 120), ("Check", 180), ("Close\nCallbacks", 240)
        ]
        import math
        for label, angle_deg in phases:
            angle = math.radians(angle_deg - 90)
            px = cx + int((r + 40) * math.cos(angle))
            py = cy + 10 + int((r + 30) * math.sin(angle))
            draw.text((px - 25, py - 5), label, fill='#333')
            # dot on circle
            dx = cx + int(r * math.cos(angle))
            dy = cy + 10 + int(r * math.sin(angle))
            draw.ellipse([dx-5, dy-5, dx+5, dy+5], fill='#4CAF50')
        draw.text((cx - 25, cy + 5), "Event\nLoop", fill='#1565C0')

    event_loop_img = create_diagram_image("event_loop.png", 500, 280, draw_event_loop)
    pdf.image(event_loop_img, x=25, w=160)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "1. Why Node.js?", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, (
        "Node.js has become one of the most popular server-side platforms:\n"
        "- Non-blocking I/O for handling concurrent connections\n"
        "- Same language (JavaScript) on both client and server\n"
        "- Massive npm ecosystem with 2M+ packages\n"
        "- Great for real-time applications (chat, streaming)\n"
        "- Microservice architecture friendly"
    ))

    # --- Page 2 ---
    pdf.add_page()

    # Chart: Node.js vs other runtimes performance
    fig, ax = plt.subplots(figsize=(7, 4))
    scenarios = ['JSON\nSerialization', 'File I/O', 'HTTP\nRequests', 'WebSocket\nConnections', 'Database\nQueries']
    nodejs = [85, 70, 90, 95, 75]
    python = [40, 55, 45, 50, 60]
    go_lang = [95, 90, 92, 88, 85]
    x = np.arange(len(scenarios))
    w = 0.25
    ax.bar(x - w, nodejs, w, label='Node.js', color='#4CAF50')
    ax.bar(x, python, w, label='Python (Flask)', color='#2196F3')
    ax.bar(x + w, go_lang, w, label='Go', color='#FF9800')
    ax.set_ylabel('Relative Performance Score', fontsize=10)
    ax.set_title('Runtime Performance Comparison (Higher is Better)', fontsize=12, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios, fontsize=9)
    ax.legend()
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    chart1 = save_fig(fig, "runtime_perf.png")
    pdf.image(chart1, x=10, w=190)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "2. Core Modules", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, (
        "Node.js comes with several built-in modules:\n\n"
        "  const fs = require('fs');       // File system operations\n"
        "  const path = require('path');   // Path manipulation\n"
        "  const http = require('http');   // HTTP server/client\n"
        "  const crypto = require('crypto'); // Cryptographic functions\n"
        "  const os = require('os');       // Operating system info\n\n"
        "Creating a simple HTTP server:\n"
        "  const http = require('http');\n"
        "  const server = http.createServer((req, res) => {\n"
        "    res.writeHead(200, { 'Content-Type': 'text/plain' });\n"
        "    res.end('Hello World!');\n"
        "  });\n"
        "  server.listen(3000);"
    ))

    # --- Page 3 ---
    pdf.add_page()

    # Chart: npm downloads over time
    fig, ax = plt.subplots(figsize=(6, 3.5))
    years = [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]
    downloads_b = [5, 10, 18, 30, 45, 65, 80, 100, 130]  # billions per week
    ax.plot(years, downloads_b, 'o-', color='#CB3837', linewidth=2.5, markersize=8)
    ax.fill_between(years, downloads_b, alpha=0.15, color='#CB3837')
    ax.set_xlabel('Year', fontsize=10)
    ax.set_ylabel('Weekly Downloads (Billions)', fontsize=10)
    ax.set_title('npm Weekly Download Growth', fontsize=12, fontweight='bold')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='y', alpha=0.3)
    chart2 = save_fig(fig, "npm_growth.png")
    pdf.image(chart2, x=15, w=180)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "3. Node.js Use Cases", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, (
        "Node.js excels in several areas:\n"
        "- REST APIs and GraphQL servers\n"
        "- Real-time applications (Socket.io)\n"
        "- Microservices architecture\n"
        "- Server-side rendering (Next.js, Nuxt.js)\n"
        "- CLI tools and build tools\n"
        "- IoT applications"
    ))
    pdf.ln(3)

    # Chart: Industry adoption
    fig, ax = plt.subplots(figsize=(6, 3.5))
    industries = ['Tech/SaaS', 'E-commerce', 'Finance', 'Healthcare', 'Media', 'Gaming', 'Education']
    adoption = [88, 72, 55, 42, 65, 58, 48]
    colors = plt.cm.viridis(np.linspace(0.2, 0.9, len(industries)))
    bars = ax.barh(industries, adoption, color=colors, edgecolor='white')
    for bar, val in zip(bars, adoption):
        ax.text(val + 1, bar.get_y() + bar.get_height()/2, f'{val}%', va='center', fontsize=9)
    ax.set_xlabel('Adoption Rate (%)', fontsize=10)
    ax.set_title('Node.js Adoption by Industry (2024)', fontsize=12, fontweight='bold')
    ax.set_xlim(0, 100)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    chart3 = save_fig(fig, "nodejs_adoption.png")
    pdf.image(chart3, x=15, w=180)

    pdf.output(os.path.join(CONTENT_DIR, "m3_l4_nodejs.pdf"))
    print("  Created m3_l4_nodejs.pdf")


if __name__ == "__main__":
    print("Generating PDFs with charts, graphs, and images...")
    gen_functions_pdf()
    gen_arrays_objects_pdf()
    gen_fetch_api_pdf()
    gen_testing_pdf()
    gen_nodejs_pdf()
    print("\nDone! Generated 5 PDFs with visual content.")
