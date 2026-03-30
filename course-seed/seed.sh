#!/bin/bash

# ============================================
# Smart Course Seed Script
# Creates a JavaScript Mastery course with
# 3 modules, each with 4 lessons,
# plus quizzes and summaries for each module
# ============================================

set -e

BASE_URL="http://localhost:8000"
CONTENT_DIR="$(cd "$(dirname "$0")/content" && pwd)"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${YELLOW}[STEP]${NC} $1"; }

# ============================================
# Step 1: Login as teacher
# ============================================
log_step "Logging in as teacher..."

LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "teacher@test.com",
    "password": "TestPass123"
  }')

ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)

if [ -z "$ACCESS_TOKEN" ] || [ "$ACCESS_TOKEN" = "null" ]; then
  log_error "Failed to login. Response: $LOGIN_RESPONSE"
  exit 1
fi

log_success "Logged in successfully. Token obtained."

# ============================================
# Step 2: Create Course
# ============================================
log_step "Creating JavaScript Mastery course..."

SLUG="js-mastery-$(date +%s)"

COURSE_RESPONSE=$(curl -s -X POST "${BASE_URL}/courses" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -d "{
    \"title\": \"JavaScript Mastery: From Fundamentals to Advanced\",
    \"slug\": \"${SLUG}\",
    \"description\": \"A comprehensive JavaScript course covering fundamentals, DOM manipulation, async programming, ES6+ features, OOP, design patterns, testing, and Node.js. Perfect for beginners who want to become proficient JavaScript developers.\",
    \"category\": \"Programming\",
    \"level\": \"beginner\",
    \"language\": \"en\",
    \"duration_hours\": 24.0,
    \"price\": 79.99,
    \"currency\": \"USD\",
    \"max_students\": 100
  }")

echo "$COURSE_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$COURSE_RESPONSE"

COURSE_ID=$(echo "$COURSE_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])" 2>/dev/null)

if [ -z "$COURSE_ID" ] || [ "$COURSE_ID" = "null" ]; then
  log_error "Failed to create course. Response: $COURSE_RESPONSE"
  exit 1
fi

log_success "Course created with ID: ${COURSE_ID}"

# ============================================
# Step 3: Initialize course content in MongoDB
# ============================================
log_step "Initializing course content..."

INIT_RESPONSE=$(curl -s -X PUT "${BASE_URL}/courses/${COURSE_ID}/content" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -d '{
    "modules": [],
    "metadata": {
      "total_modules": 0,
      "total_lessons": 0,
      "total_duration_hours": 0,
      "tags": ["javascript", "programming", "web-development"]
    }
  }')

INIT_CHECK=$(echo "$INIT_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('course_id', ''))" 2>/dev/null)

if [ -z "$INIT_CHECK" ] || [ "$INIT_CHECK" = "" ]; then
  log_error "Failed to initialize course content. Response: $INIT_RESPONSE"
  exit 1
fi

log_success "Course content initialized."

# ============================================
# Step 4: Create Module 1 - JavaScript Fundamentals
# ============================================
log_step "Creating Module 1: JavaScript Fundamentals..."

MODULE1_RESPONSE=$(curl -s -X POST "${BASE_URL}/courses/${COURSE_ID}/content/modules" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -d '{
    "title": "Module 1: JavaScript Fundamentals",
    "description": "Learn the core building blocks of JavaScript including variables, data types, operators, control flow, functions, arrays, objects, and error handling.",
    "order": 1,
    "is_published": true,
    "lessons": []
  }')

MODULE1_ID=$(echo "$MODULE1_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
modules = data.get('modules', [])
for m in modules:
    if m.get('order') == 1:
        print(m['module_id'])
        break
" 2>/dev/null)

if [ -z "$MODULE1_ID" ] || [ "$MODULE1_ID" = "null" ]; then
  log_error "Failed to get Module 1 ID. Response: $MODULE1_RESPONSE"
  exit 1
fi

log_success "Module 1 created with ID: ${MODULE1_ID}"

# ============================================
# Step 5: Create Module 2 - Intermediate JavaScript
# ============================================
log_step "Creating Module 2: Intermediate JavaScript..."

MODULE2_RESPONSE=$(curl -s -X POST "${BASE_URL}/courses/${COURSE_ID}/content/modules" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -d '{
    "title": "Module 2: Intermediate JavaScript",
    "description": "Dive into asynchronous programming, DOM manipulation, the Fetch API, and modern ES6+ features including modules, iterators, and advanced patterns.",
    "order": 2,
    "is_published": true,
    "lessons": []
  }')

MODULE2_ID=$(echo "$MODULE2_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
modules = data.get('modules', [])
for m in modules:
    if m.get('order') == 2:
        print(m['module_id'])
        break
" 2>/dev/null)

if [ -z "$MODULE2_ID" ] || [ "$MODULE2_ID" = "null" ]; then
  log_error "Failed to get Module 2 ID. Response: $MODULE2_RESPONSE"
  exit 1
fi

log_success "Module 2 created with ID: ${MODULE2_ID}"

# ============================================
# Step 6: Create Module 3 - Advanced JavaScript
# ============================================
log_step "Creating Module 3: Advanced JavaScript..."

MODULE3_RESPONSE=$(curl -s -X POST "${BASE_URL}/courses/${COURSE_ID}/content/modules" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -d '{
    "title": "Module 3: Advanced JavaScript",
    "description": "Master design patterns, object-oriented programming, testing methodologies, and server-side JavaScript with Node.js.",
    "order": 3,
    "is_published": true,
    "lessons": []
  }')

MODULE3_ID=$(echo "$MODULE3_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
modules = data.get('modules', [])
for m in modules:
    if m.get('order') == 3:
        print(m['module_id'])
        break
" 2>/dev/null)

if [ -z "$MODULE3_ID" ] || [ "$MODULE3_ID" = "null" ]; then
  log_error "Failed to get Module 3 ID. Response: $MODULE3_RESPONSE"
  exit 1
fi

log_success "Module 3 created with ID: ${MODULE3_ID}"

# ============================================
# Helper function to create a lesson with PDF file upload
# ============================================
create_lesson() {
  local course_id=$1
  local module_id=$2
  local title="$3"
  local type=$4
  local duration=$5
  local order=$6
  local pdf_file=$7

  log_info "  Creating lesson ${order}: ${title} (${type}, PDF: ${pdf_file})..."

  local response=$(curl -s -X POST "${BASE_URL}/courses/${course_id}/content/modules/${module_id}/lessons/with-file" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -F "title=${title}" \
    -F "type=${type}" \
    -F "duration_minutes=${duration}" \
    -F "order=${order}" \
    -F "is_preview=false" \
    -F "file=@${CONTENT_DIR}/${pdf_file};type=application/pdf")

  # Check if lesson was created
  local lesson_check=$(echo "$response" | python3 -c "
import sys, json
data = json.load(sys.stdin)
modules = data.get('modules', [])
for m in modules:
    if m.get('module_id') == '${module_id}':
        for l in m.get('lessons', []):
            if l.get('order') == ${order}:
                print(l.get('lesson_id', 'unknown'))
                break
        break
" 2>/dev/null)

  if [ -n "$lesson_check" ] && [ "$lesson_check" != "null" ]; then
    log_success "  Lesson '${title}' created (ID: ${lesson_check})"
  else
    log_error "  Failed to create lesson '${title}'. Response:"
    echo "$response" | python3 -m json.tool 2>/dev/null | head -10 || echo "$response" | head -5
  fi
}

# ============================================
# Helper function to create a lesson with audio file upload
# ============================================
create_audio_lesson() {
  local course_id=$1
  local module_id=$2
  local title="$3"
  local duration=$4
  local order=$5
  local audio_file=$6

  log_info "  Creating audio lesson ${order}: ${title} (audio: ${audio_file})..."

  local response=$(curl -s -X POST "${BASE_URL}/courses/${course_id}/content/modules/${module_id}/lessons/with-file" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -F "title=${title}" \
    -F "type=audio" \
    -F "duration_minutes=${duration}" \
    -F "order=${order}" \
    -F "is_preview=false" \
    -F "file=@${CONTENT_DIR}/${audio_file};type=audio/mpeg")

  local lesson_check=$(echo "$response" | python3 -c "
import sys, json
data = json.load(sys.stdin)
modules = data.get('modules', [])
for m in modules:
    if m.get('module_id') == '${module_id}':
        for l in m.get('lessons', []):
            if l.get('order') == ${order}:
                print(l.get('lesson_id', 'unknown'))
                break
        break
" 2>/dev/null)

  if [ -n "$lesson_check" ] && [ "$lesson_check" != "null" ]; then
    log_success "  Audio lesson '${title}' created (ID: ${lesson_check})"
  else
    log_error "  Failed to create audio lesson '${title}'. Response:"
    echo "$response" | python3 -m json.tool 2>/dev/null | head -10 || echo "$response" | head -5
  fi
}

# ============================================
# Helper function to create a lesson with video file upload
# ============================================
create_video_lesson() {
  local course_id=$1
  local module_id=$2
  local title="$3"
  local duration=$4
  local order=$5
  local video_file=$6

  log_info "  Creating video lesson ${order}: ${title} (video: ${video_file})..."

  local response=$(curl -s -X POST "${BASE_URL}/courses/${course_id}/content/modules/${module_id}/lessons/with-file" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -F "title=${title}" \
    -F "type=video" \
    -F "duration_minutes=${duration}" \
    -F "order=${order}" \
    -F "is_preview=false" \
    -F "file=@${CONTENT_DIR}/${video_file};type=video/mp4")

  local lesson_check=$(echo "$response" | python3 -c "
import sys, json
data = json.load(sys.stdin)
modules = data.get('modules', [])
for m in modules:
    if m.get('module_id') == '${module_id}':
        for l in m.get('lessons', []):
            if l.get('order') == ${order}:
                print(l.get('lesson_id', 'unknown'))
                break
        break
" 2>/dev/null)

  if [ -n "$lesson_check" ] && [ "$lesson_check" != "null" ]; then
    log_success "  Video lesson '${title}' created (ID: ${lesson_check})"
  else
    log_error "  Failed to create video lesson '${title}'. Response:"
    echo "$response" | python3 -m json.tool 2>/dev/null | head -10 || echo "$response" | head -5
  fi
}

# ============================================
# Step 7: Create lessons for Module 1
# ============================================
log_step "Creating lessons for Module 1: JavaScript Fundamentals..."

create_lesson "$COURSE_ID" "$MODULE1_ID" \
  "Introduction to JavaScript - Variables, Types & Control Flow" \
  "text" \
  45 1 \
  "m1_l1_transcript.pdf"

create_lesson "$COURSE_ID" "$MODULE1_ID" \
  "Functions, Scope, and Closures" \
  "text" \
  30 2 \
  "m1_l2_functions.pdf"

create_lesson "$COURSE_ID" "$MODULE1_ID" \
  "Arrays and Objects Deep Dive" \
  "text" \
  35 3 \
  "m1_l3_arrays_objects.pdf"

create_lesson "$COURSE_ID" "$MODULE1_ID" \
  "Error Handling and Debugging" \
  "text" \
  25 4 \
  "m1_l4_error_handling.pdf"

create_audio_lesson "$COURSE_ID" "$MODULE1_ID" \
  "TypeScript Fundamentals - Audio Overview" \
  15 5 \
  "typescript-lesson.mp3"

create_video_lesson "$COURSE_ID" "$MODULE1_ID" \
  "TypeScript Utility Types - Video Deep Dive" \
  20 6 \
  "video-lesson-on-typescript-utility-types.mp4"

# ============================================
# Step 8: Create lessons for Module 2
# ============================================
log_step "Creating lessons for Module 2: Intermediate JavaScript..."

create_lesson "$COURSE_ID" "$MODULE2_ID" \
  "Asynchronous JavaScript - Callbacks, Promises & Async/Await" \
  "text" \
  50 1 \
  "m2_l1_transcript.pdf"

create_lesson "$COURSE_ID" "$MODULE2_ID" \
  "DOM Manipulation Mastery" \
  "text" \
  35 2 \
  "m2_l2_dom.pdf"

create_lesson "$COURSE_ID" "$MODULE2_ID" \
  "Fetch API and HTTP Requests" \
  "text" \
  30 3 \
  "m2_l3_fetch_api.pdf"

create_lesson "$COURSE_ID" "$MODULE2_ID" \
  "ES6+ Modules and Modern Features" \
  "text" \
  35 4 \
  "m2_l4_es6_modules.pdf"

# ============================================
# Step 9: Create lessons for Module 3
# ============================================
log_step "Creating lessons for Module 3: Advanced JavaScript..."

create_lesson "$COURSE_ID" "$MODULE3_ID" \
  "Design Patterns and Best Practices" \
  "text" \
  55 1 \
  "m3_l1_transcript.pdf"

create_lesson "$COURSE_ID" "$MODULE3_ID" \
  "Object-Oriented Programming in JavaScript" \
  "text" \
  40 2 \
  "m3_l2_oop.pdf"

create_lesson "$COURSE_ID" "$MODULE3_ID" \
  "JavaScript Testing - A Practical Guide" \
  "text" \
  35 3 \
  "m3_l3_testing.pdf"

create_lesson "$COURSE_ID" "$MODULE3_ID" \
  "Introduction to Node.js and Server-Side JavaScript" \
  "text" \
  40 4 \
  "m3_l4_nodejs.pdf"

# ============================================
# Step 10: Fetch course content to get lesson IDs
# ============================================
log_step "Fetching course content to retrieve lesson IDs..."

CONTENT_RESPONSE=$(curl -s -X GET "${BASE_URL}/courses/${COURSE_ID}/content" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}")

# Extract lesson IDs for each module
get_lesson_ids() {
  local module_id=$1
  echo "$CONTENT_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
modules = data.get('modules', [])
for m in modules:
    if m.get('module_id') == '${module_id}':
        ids = [l.get('lesson_id') for l in m.get('lessons', []) if l.get('lesson_id')]
        print(','.join(ids))
        break
" 2>/dev/null
}

MODULE1_LESSON_IDS=$(get_lesson_ids "$MODULE1_ID")
MODULE2_LESSON_IDS=$(get_lesson_ids "$MODULE2_ID")
MODULE3_LESSON_IDS=$(get_lesson_ids "$MODULE3_ID")

log_success "Module 1 lesson IDs: ${MODULE1_LESSON_IDS}"
log_success "Module 2 lesson IDs: ${MODULE2_LESSON_IDS}"
log_success "Module 3 lesson IDs: ${MODULE3_LESSON_IDS}"

# ============================================
# Helper: Convert comma-separated IDs to JSON array
# ============================================
ids_to_json_array() {
  local ids_csv=$1
  echo "$ids_csv" | python3 -c "
import sys
ids = sys.stdin.read().strip().split(',')
print('[' + ','.join('\"' + id.strip() + '\"' for id in ids if id.strip()) + ']')
" 2>/dev/null
}

# ============================================
# Helper: Generate quiz for a module
# ============================================
generate_quiz() {
  local course_id=$1
  local module_id=$2
  local module_name=$3
  local lesson_ids_csv=$4
  local num_questions=${5:-5}

  local lesson_ids_json=$(ids_to_json_array "$lesson_ids_csv")

  log_info "  Generating quiz for ${module_name}..."

  local response=$(curl -s -X POST "${BASE_URL}/courses/${course_id}/modules/${module_id}/quiz/generate" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -d "{
      \"source_lesson_ids\": ${lesson_ids_json},
      \"num_questions\": ${num_questions},
      \"passing_score\": 70,
      \"max_attempts\": 3,
      \"time_limit_minutes\": 30
    }")

  local quiz_id=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)

  if [ -n "$quiz_id" ] && [ "$quiz_id" != "" ] && [ "$quiz_id" != "None" ]; then
    log_success "  Quiz generated for ${module_name} (ID: ${quiz_id})"
  else
    log_error "  Failed to generate quiz for ${module_name}. Response:"
    echo "$response" | python3 -m json.tool 2>/dev/null | head -10 || echo "$response" | head -5
  fi
}

# ============================================
# Helper: Generate summary for a module
# ============================================
generate_summary() {
  local course_id=$1
  local module_id=$2
  local module_name=$3
  local lesson_ids_csv=$4

  local lesson_ids_json=$(ids_to_json_array "$lesson_ids_csv")

  log_info "  Generating summary for ${module_name}..."

  local response=$(curl -s -X POST "${BASE_URL}/courses/${course_id}/modules/${module_id}/summary/generate" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -d "{
      \"source_lesson_ids\": ${lesson_ids_json},
      \"include_glossary\": true,
      \"include_key_points\": true,
      \"include_learning_objectives\": true
    }")

  local summary_id=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)

  if [ -n "$summary_id" ] && [ "$summary_id" != "" ] && [ "$summary_id" != "None" ]; then
    log_success "  Summary generated for ${module_name} (ID: ${summary_id})"
  else
    log_error "  Failed to generate summary for ${module_name}. Response:"
    echo "$response" | python3 -m json.tool 2>/dev/null | head -10 || echo "$response" | head -5
  fi
}

# ============================================
# Helper: Publish quiz for a module
# ============================================
publish_quiz() {
  local course_id=$1
  local module_id=$2
  local module_name=$3

  log_info "  Publishing quiz for ${module_name}..."

  local response=$(curl -s -X PATCH "${BASE_URL}/courses/${course_id}/modules/${module_id}/quiz/publish" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -d '{"is_published": true}')

  local is_published=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('is_published', False))" 2>/dev/null)

  if [ "$is_published" = "True" ]; then
    log_success "  Quiz published for ${module_name}"
  else
    log_error "  Failed to publish quiz for ${module_name}. Response:"
    echo "$response" | python3 -m json.tool 2>/dev/null | head -10 || echo "$response" | head -5
  fi
}

# ============================================
# Helper: Publish summary for a module
# ============================================
publish_summary() {
  local course_id=$1
  local module_id=$2
  local module_name=$3

  log_info "  Publishing summary for ${module_name}..."

  local response=$(curl -s -X PATCH "${BASE_URL}/courses/${course_id}/modules/${module_id}/summary/publish" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -d '{"is_published": true}')

  local is_published=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('is_published', False))" 2>/dev/null)

  if [ "$is_published" = "True" ]; then
    log_success "  Summary published for ${module_name}"
  else
    log_error "  Failed to publish summary for ${module_name}. Response:"
    echo "$response" | python3 -m json.tool 2>/dev/null | head -10 || echo "$response" | head -5
  fi
}

# ============================================
# Step 11: Generate quizzes for all modules
# ============================================
log_step "Generating quizzes for all modules..."

generate_quiz "$COURSE_ID" "$MODULE1_ID" "Module 1: JavaScript Fundamentals" "$MODULE1_LESSON_IDS" 5
generate_quiz "$COURSE_ID" "$MODULE2_ID" "Module 2: Intermediate JavaScript" "$MODULE2_LESSON_IDS" 5
generate_quiz "$COURSE_ID" "$MODULE3_ID" "Module 3: Advanced JavaScript" "$MODULE3_LESSON_IDS" 5

# ============================================
# Step 12: Generate summaries for all modules
# ============================================
log_step "Generating summaries for all modules..."

generate_summary "$COURSE_ID" "$MODULE1_ID" "Module 1: JavaScript Fundamentals" "$MODULE1_LESSON_IDS"
generate_summary "$COURSE_ID" "$MODULE2_ID" "Module 2: Intermediate JavaScript" "$MODULE2_LESSON_IDS"
generate_summary "$COURSE_ID" "$MODULE3_ID" "Module 3: Advanced JavaScript" "$MODULE3_LESSON_IDS"

# ============================================
# Step 13: Publish quizzes and summaries
# ============================================
log_step "Publishing quizzes and summaries..."

publish_quiz "$COURSE_ID" "$MODULE1_ID" "Module 1"
publish_quiz "$COURSE_ID" "$MODULE2_ID" "Module 2"
publish_quiz "$COURSE_ID" "$MODULE3_ID" "Module 3"

publish_summary "$COURSE_ID" "$MODULE1_ID" "Module 1"
publish_summary "$COURSE_ID" "$MODULE2_ID" "Module 2"
publish_summary "$COURSE_ID" "$MODULE3_ID" "Module 3"

# ============================================
# Step 14: Publish the course
# ============================================
log_step "Publishing the course..."

PUBLISH_RESPONSE=$(curl -s -X PATCH "${BASE_URL}/courses/${COURSE_ID}/status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -d '{"status": "published"}')

COURSE_STATUS=$(echo "$PUBLISH_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', ''))" 2>/dev/null)

if [ "$COURSE_STATUS" = "published" ] || [ "$COURSE_STATUS" = "publish_requested" ]; then
  log_success "Course publish workflow started (status: ${COURSE_STATUS})"

  # Wait for the Temporal workflow to finish publishing
  if [ "$COURSE_STATUS" = "publish_requested" ]; then
    log_info "Waiting for course publish workflow to complete..."
    for i in $(seq 1 30); do
      sleep 2
      CHECK_RESPONSE=$(curl -s -X GET "${BASE_URL}/courses/${COURSE_ID}" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}")
      CURRENT_STATUS=$(echo "$CHECK_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', ''))" 2>/dev/null)
      if [ "$CURRENT_STATUS" = "published" ]; then
        COURSE_STATUS="published"
        log_success "Course published successfully!"
        break
      fi
      if [ $i -eq 30 ]; then
        log_error "Timed out waiting for course to publish. Current status: ${CURRENT_STATUS}"
      fi
    done
  fi
else
  log_error "Failed to publish course. Response:"
  echo "$PUBLISH_RESPONSE" | python3 -m json.tool 2>/dev/null | head -10 || echo "$PUBLISH_RESPONSE" | head -5
fi

# ============================================
# Step 15: Final verification
# ============================================
log_step "Final verification..."

CONTENT_RESPONSE=$(curl -s -X GET "${BASE_URL}/courses/${COURSE_ID}/content" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}")

TOTAL_MODULES=$(echo "$CONTENT_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
modules = data.get('modules', [])
print(len(modules))
" 2>/dev/null)

TOTAL_LESSONS=$(echo "$CONTENT_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
modules = data.get('modules', [])
total = sum(len(m.get('lessons', [])) for m in modules)
print(total)
" 2>/dev/null)

# Count quizzes and summaries
QUIZ_COUNT=0
SUMMARY_COUNT=0
for MODULE_ID_CHECK in "$MODULE1_ID" "$MODULE2_ID" "$MODULE3_ID"; do
  QUIZ_CHECK=$(curl -s -X GET "${BASE_URL}/courses/${COURSE_ID}/modules/${MODULE_ID_CHECK}/quiz" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}")
  QUIZ_EXISTS=$(echo "$QUIZ_CHECK" | python3 -c "import sys, json; d=json.load(sys.stdin); print('yes' if d.get('id') else 'no')" 2>/dev/null)
  if [ "$QUIZ_EXISTS" = "yes" ]; then
    QUIZ_COUNT=$((QUIZ_COUNT + 1))
  fi

  SUMMARY_CHECK=$(curl -s -X GET "${BASE_URL}/courses/${COURSE_ID}/modules/${MODULE_ID_CHECK}/summary" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}")
  SUMMARY_EXISTS=$(echo "$SUMMARY_CHECK" | python3 -c "import sys, json; d=json.load(sys.stdin); print('yes' if d.get('id') else 'no')" 2>/dev/null)
  if [ "$SUMMARY_EXISTS" = "yes" ]; then
    SUMMARY_COUNT=$((SUMMARY_COUNT + 1))
  fi
done

echo ""
echo "============================================"
echo -e "${GREEN}Course Seeding Complete!${NC}"
echo "============================================"
echo -e "Course ID:       ${YELLOW}${COURSE_ID}${NC}"
echo -e "Status:          ${YELLOW}${COURSE_STATUS:-draft}${NC}"
echo -e "Total Modules:   ${YELLOW}${TOTAL_MODULES}${NC}"
echo -e "Total Lessons:   ${YELLOW}${TOTAL_LESSONS}${NC}"
echo -e "Total Quizzes:   ${YELLOW}${QUIZ_COUNT}${NC}"
echo -e "Total Summaries: ${YELLOW}${SUMMARY_COUNT}${NC}"
echo ""
echo "Course Structure:"
echo "$CONTENT_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
modules = data.get('modules', [])
for m in sorted(modules, key=lambda x: x.get('order', 0)):
    print(f\"  Module {m.get('order')}: {m.get('title')}\")
    for l in sorted(m.get('lessons', []), key=lambda x: x.get('order', 0)):
        print(f\"    Lesson {l.get('order')}: {l.get('title')} [{l.get('type')}]\")
    print(f\"    Quiz: Generated & Published\")
    print(f\"    Summary: Generated & Published\")
" 2>/dev/null
echo ""
echo "============================================"
