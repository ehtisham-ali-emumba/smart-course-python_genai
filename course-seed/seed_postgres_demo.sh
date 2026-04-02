#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PSQL_SC="docker compose exec -T postgres psql -U smartcourse -d smartcourse"
PSQL_AN="docker compose exec -T postgres psql -U smartcourse -d analytics_db"

log() {
  printf "[seed-postgres] %s\n" "$1"
}

log "Seeding smartcourse relational tables..."
$PSQL_SC <<'SQL'
WITH pairs AS (
  SELECT
    sp.id AS student_id,
    c.id AS course_id,
    c.price,
    ROW_NUMBER() OVER (ORDER BY sp.id, c.created_at DESC, c.id) AS seq
  FROM student_profiles sp
  CROSS JOIN (
    SELECT id, price, created_at
    FROM courses
    ORDER BY created_at DESC, id
    LIMIT 10
  ) c
),
seeded AS (
  SELECT
    (
      substr(md5('enrollment:' || student_id::text || ':' || course_id::text), 1, 8) || '-' ||
      substr(md5('enrollment:' || student_id::text || ':' || course_id::text), 9, 4) || '-' ||
      substr(md5('enrollment:' || student_id::text || ':' || course_id::text), 13, 4) || '-' ||
      substr(md5('enrollment:' || student_id::text || ':' || course_id::text), 17, 4) || '-' ||
      substr(md5('enrollment:' || student_id::text || ':' || course_id::text), 21, 12)
    )::uuid AS id,
    student_id,
    course_id,
    CASE
      WHEN seq % 5 = 0 THEN 'completed'
      WHEN seq % 7 = 0 THEN 'dropped'
      ELSE 'active'
    END AS status,
    now() - ((seq * 2) || ' days')::interval AS enrolled_at,
    now() - ((seq * 2 - 1) || ' days')::interval AS started_at,
    CASE WHEN seq % 5 = 0 THEN now() - ((seq / 2) || ' days')::interval END AS completed_at,
    CASE WHEN seq % 7 = 0 THEN now() - ((seq / 2) || ' days')::interval END AS dropped_at,
    now() - ((seq % 3) || ' hours')::interval AS last_accessed_at,
    'paid'::text AS payment_status,
    price AS payment_amount,
    CASE WHEN seq % 2 = 0 THEN 'web' ELSE 'mentor_demo' END AS enrollment_source
  FROM pairs
)
INSERT INTO enrollments (
  id,
  student_id,
  course_id,
  status,
  enrolled_at,
  started_at,
  completed_at,
  dropped_at,
  last_accessed_at,
  payment_status,
  payment_amount,
  enrollment_source
)
SELECT
  id,
  student_id,
  course_id,
  status,
  enrolled_at,
  started_at,
  completed_at,
  dropped_at,
  last_accessed_at,
  payment_status,
  payment_amount,
  enrollment_source
FROM seeded
ON CONFLICT (student_id, course_id)
DO UPDATE SET
  status = EXCLUDED.status,
  started_at = EXCLUDED.started_at,
  completed_at = EXCLUDED.completed_at,
  dropped_at = EXCLUDED.dropped_at,
  last_accessed_at = EXCLUDED.last_accessed_at,
  payment_status = EXCLUDED.payment_status,
  payment_amount = EXCLUDED.payment_amount,
  enrollment_source = EXCLUDED.enrollment_source,
  updated_at = now();

WITH progress_seed AS (
  SELECT
    e.id AS enrollment_id,
    e.status,
    gs AS item_idx,
    CASE
      WHEN gs <= 4 THEN 'lesson'
      WHEN gs = 5 THEN 'quiz'
      ELSE 'assignment'
    END AS item_type,
    CASE
      WHEN gs <= 4 THEN 'lesson-' || gs::text
      WHEN gs = 5 THEN 'quiz-1'
      ELSE 'assignment-1'
    END AS item_id
  FROM enrollments e
  CROSS JOIN generate_series(1, 6) gs
),
materialized AS (
  SELECT
    (
      substr(md5('progress:' || enrollment_id::text || ':' || item_type || ':' || item_id), 1, 8) || '-' ||
      substr(md5('progress:' || enrollment_id::text || ':' || item_type || ':' || item_id), 9, 4) || '-' ||
      substr(md5('progress:' || enrollment_id::text || ':' || item_type || ':' || item_id), 13, 4) || '-' ||
      substr(md5('progress:' || enrollment_id::text || ':' || item_type || ':' || item_id), 17, 4) || '-' ||
      substr(md5('progress:' || enrollment_id::text || ':' || item_type || ':' || item_id), 21, 12)
    )::uuid AS id,
    enrollment_id,
    item_type,
    item_id,
    CASE
      WHEN status = 'completed' THEN 100.00
      WHEN status = 'dropped' THEN LEAST(85.00, (item_idx * 16)::numeric)
      ELSE LEAST(95.00, (30 + item_idx * 11)::numeric)
    END::numeric(5,2) AS progress_percentage,
    CASE WHEN status = 'completed' THEN now() - ((7 - item_idx) || ' days')::interval END AS completed_at
  FROM progress_seed
)
INSERT INTO progress (id, enrollment_id, item_type, item_id, progress_percentage, completed_at)
SELECT id, enrollment_id, item_type, item_id, progress_percentage, completed_at
FROM materialized
ON CONFLICT (enrollment_id, item_type, item_id)
DO UPDATE SET
  progress_percentage = EXCLUDED.progress_percentage,
  completed_at = EXCLUDED.completed_at,
  updated_at = now();

WITH quiz_seed AS (
  SELECT
    e.id AS enrollment_id,
    CASE WHEN e.status = 'completed' THEN 88.00 ELSE 74.00 END::numeric(5,2) AS score,
    e.status
  FROM enrollments e
  WHERE e.status IN ('active', 'completed')
),
materialized AS (
  SELECT
    (
      substr(md5('quiz:' || enrollment_id::text || ':module-1:1'), 1, 8) || '-' ||
      substr(md5('quiz:' || enrollment_id::text || ':module-1:1'), 9, 4) || '-' ||
      substr(md5('quiz:' || enrollment_id::text || ':module-1:1'), 13, 4) || '-' ||
      substr(md5('quiz:' || enrollment_id::text || ':module-1:1'), 17, 4) || '-' ||
      substr(md5('quiz:' || enrollment_id::text || ':module-1:1'), 21, 12)
    )::uuid AS id,
    enrollment_id,
    'module-1'::text AS module_id,
    1 AS attempt_number,
    'submitted'::text AS status,
    score,
    (score >= 70)::boolean AS passed,
    CASE WHEN status = 'completed' THEN 1400 ELSE 1750 END AS time_spent_seconds,
    1 AS quiz_version,
    now() - interval '1 day' AS submitted_at,
    now() - interval '23 hours' AS graded_at
  FROM quiz_seed
)
INSERT INTO quiz_attempts (
  id,
  enrollment_id,
  module_id,
  attempt_number,
  status,
  score,
  passed,
  time_spent_seconds,
  quiz_version,
  submitted_at,
  graded_at
)
SELECT
  id,
  enrollment_id,
  module_id,
  attempt_number,
  status,
  score,
  passed,
  time_spent_seconds,
  quiz_version,
  submitted_at,
  graded_at
FROM materialized
ON CONFLICT (enrollment_id, module_id, attempt_number)
DO UPDATE SET
  status = EXCLUDED.status,
  score = EXCLUDED.score,
  passed = EXCLUDED.passed,
  time_spent_seconds = EXCLUDED.time_spent_seconds,
  quiz_version = EXCLUDED.quiz_version,
  submitted_at = EXCLUDED.submitted_at,
  graded_at = EXCLUDED.graded_at,
  updated_at = now();

WITH answer_seed AS (
  SELECT
    qa.id AS quiz_attempt_id,
    gs AS q_idx,
    qa.score,
    qa.passed
  FROM quiz_attempts qa
  CROSS JOIN generate_series(1, 5) gs
),
materialized AS (
  SELECT
    (
      substr(md5('answer:' || quiz_attempt_id::text || ':q' || q_idx::text), 1, 8) || '-' ||
      substr(md5('answer:' || quiz_attempt_id::text || ':q' || q_idx::text), 9, 4) || '-' ||
      substr(md5('answer:' || quiz_attempt_id::text || ':q' || q_idx::text), 13, 4) || '-' ||
      substr(md5('answer:' || quiz_attempt_id::text || ':q' || q_idx::text), 17, 4) || '-' ||
      substr(md5('answer:' || quiz_attempt_id::text || ':q' || q_idx::text), 21, 12)
    )::uuid AS id,
    quiz_attempt_id,
    'q-' || q_idx::text AS question_id,
    'mcq'::text AS question_type,
    jsonb_build_object(
      'choice', chr(64 + ((q_idx % 4) + 1)),
      'notes', 'demo seed answer'
    ) AS user_response,
    CASE
      WHEN passed THEN q_idx <= 4
      ELSE q_idx <= 2
    END AS is_correct,
    35 + (q_idx * 7) AS time_spent_seconds
  FROM answer_seed
)
INSERT INTO user_answers (
  id,
  quiz_attempt_id,
  question_id,
  question_type,
  user_response,
  is_correct,
  time_spent_seconds
)
SELECT
  id,
  quiz_attempt_id,
  question_id,
  question_type,
  user_response,
  is_correct,
  time_spent_seconds
FROM materialized
ON CONFLICT (id)
DO UPDATE SET
  user_response = EXCLUDED.user_response,
  is_correct = EXCLUDED.is_correct,
  time_spent_seconds = EXCLUDED.time_spent_seconds,
  updated_at = now();

WITH completed_enrollments AS (
  SELECT e.id AS enrollment_id, e.completed_at
  FROM enrollments e
  WHERE e.status = 'completed'
),
materialized AS (
  SELECT
    (
      substr(md5('cert:' || enrollment_id::text), 1, 8) || '-' ||
      substr(md5('cert:' || enrollment_id::text), 9, 4) || '-' ||
      substr(md5('cert:' || enrollment_id::text), 13, 4) || '-' ||
      substr(md5('cert:' || enrollment_id::text), 17, 4) || '-' ||
      substr(md5('cert:' || enrollment_id::text), 21, 12)
    )::uuid AS id,
    enrollment_id,
    'CERT-' || upper(substr(md5('cert:' || enrollment_id::text), 1, 10)) AS certificate_number,
    COALESCE(completed_at::date, current_date) AS issue_date,
    'https://certs.smartcourse.local/' || lower(substr(md5('cert:' || enrollment_id::text), 1, 16)) AS certificate_url,
    upper(substr(md5('verify:' || enrollment_id::text), 1, 12)) AS verification_code
  FROM completed_enrollments
)
INSERT INTO certificates (
  id,
  enrollment_id,
  certificate_number,
  issue_date,
  certificate_url,
  verification_code,
  grade,
  score_percentage,
  is_revoked
)
SELECT
  m.id,
  m.enrollment_id,
  m.certificate_number,
  m.issue_date,
  m.certificate_url,
  m.verification_code,
  'A'::text,
  COALESCE((SELECT qa.score FROM quiz_attempts qa WHERE qa.enrollment_id = m.enrollment_id LIMIT 1), 91.00),
  false
FROM materialized m
ON CONFLICT (enrollment_id)
DO UPDATE SET
  issue_date = EXCLUDED.issue_date,
  certificate_url = EXCLUDED.certificate_url,
  grade = EXCLUDED.grade,
  score_percentage = EXCLUDED.score_percentage,
  is_revoked = false;

UPDATE student_profiles sp
SET
  total_enrollments = COALESCE(stats.total_enrollments, 0),
  total_completed = COALESCE(stats.total_completed, 0),
  updated_at = now()
FROM (
  SELECT
    e.student_id,
    COUNT(*)::int AS total_enrollments,
    SUM(CASE WHEN e.status = 'completed' THEN 1 ELSE 0 END)::int AS total_completed
  FROM enrollments e
  GROUP BY e.student_id
) stats
WHERE stats.student_id = sp.id;

UPDATE instructor_profiles ip
SET
  total_students = COALESCE(stats.total_students, 0),
  total_courses = COALESCE(stats.total_courses, 0),
  average_rating = COALESCE(stats.average_rating, 4.6),
  updated_at = now()
FROM (
  SELECT
    c.instructor_id,
    COUNT(DISTINCT c.id)::int AS total_courses,
    COUNT(DISTINCT e.student_id)::int AS total_students,
    4.6::float AS average_rating
  FROM courses c
  LEFT JOIN enrollments e ON e.course_id = c.id
  GROUP BY c.instructor_id
) stats
WHERE stats.instructor_id = ip.id;
SQL

log "Smartcourse relational seeding complete."
log "Seeding analytics_db metrics and trends..."

log "Refreshing course_metrics from smartcourse aggregates..."
while IFS=$'\t' read -r course_id title category instructor_id published_at; do
  [[ -z "$course_id" ]] && continue

  metrics=$($PSQL_SC -At -F $'\t' -c "
    SELECT
      (SELECT COUNT(*)::int FROM enrollments e WHERE e.course_id = '$course_id'),
      (SELECT COUNT(*)::int FROM enrollments e WHERE e.course_id = '$course_id' AND e.status = 'active'),
      (SELECT COUNT(*)::int FROM enrollments e WHERE e.course_id = '$course_id' AND e.status = 'completed'),
      (SELECT COUNT(*)::int FROM enrollments e WHERE e.course_id = '$course_id' AND e.status = 'dropped'),
      (SELECT COALESCE(ROUND(AVG(p.progress_percentage)::numeric, 2), 0) FROM progress p JOIN enrollments e ON e.id = p.enrollment_id WHERE e.course_id = '$course_id'),
      (SELECT COALESCE(ROUND(AVG(EXTRACT(EPOCH FROM (e.completed_at - e.enrolled_at)) / 3600)::numeric, 2), 0) FROM enrollments e WHERE e.course_id = '$course_id' AND e.completed_at IS NOT NULL),
      (SELECT COALESCE(ROUND(AVG(qa.score)::numeric, 2), 0) FROM quiz_attempts qa JOIN enrollments e ON e.id = qa.enrollment_id WHERE e.course_id = '$course_id' AND qa.score IS NOT NULL),
      (SELECT COUNT(*)::int FROM quiz_attempts qa JOIN enrollments e ON e.id = qa.enrollment_id WHERE e.course_id = '$course_id'),
      (SELECT COALESCE(MAX(e.enrolled_at), now()) FROM enrollments e WHERE e.course_id = '$course_id');
  ")

  IFS=$'\t' read -r total active completed dropped avg_progress avg_time avg_quiz total_attempts last_enrollment <<< "$metrics"

  ai_questions=$(( total_attempts * 3 + completed * 2 + active ))
  completion_rate="0.00"
  if [[ "$total" -gt 0 ]]; then
    completion_rate=$(awk "BEGIN { printf \"%.2f\", ($completed*100)/$total }")
  fi

  esc_title=${title//\'/\'\'}
  esc_category=${category//\'/\'\'}

  $PSQL_AN -c "
    INSERT INTO course_metrics (
      id,
      course_id,
      instructor_id,
      title,
      category,
      total_enrollments,
      active_enrollments,
      completed_enrollments,
      dropped_enrollments,
      completion_rate,
      avg_progress_percentage,
      avg_time_to_complete_hours,
      avg_quiz_score,
      total_quiz_attempts,
      ai_questions_asked,
      published_at,
      last_enrollment_at
    )
    VALUES (
      (
        substr(md5('course-metrics:' || '$course_id'), 1, 8) || '-' ||
        substr(md5('course-metrics:' || '$course_id'), 9, 4) || '-' ||
        substr(md5('course-metrics:' || '$course_id'), 13, 4) || '-' ||
        substr(md5('course-metrics:' || '$course_id'), 17, 4) || '-' ||
        substr(md5('course-metrics:' || '$course_id'), 21, 12)
      )::uuid,
      '$course_id'::uuid,
      '$instructor_id'::uuid,
      '$esc_title',
      '$esc_category',
      $total,
      $active,
      $completed,
      $dropped,
      $completion_rate,
      $avg_progress,
      NULLIF('$avg_time', '0.00')::numeric,
      NULLIF('$avg_quiz', '0.00')::numeric,
      $total_attempts,
      $ai_questions,
      $( [[ -n "$published_at" ]] && printf "'%s'::timestamptz" "$published_at" || printf "NULL" ),
      '$last_enrollment'::timestamptz
    )
    ON CONFLICT (course_id)
    DO UPDATE SET
      instructor_id = EXCLUDED.instructor_id,
      title = EXCLUDED.title,
      category = EXCLUDED.category,
      total_enrollments = EXCLUDED.total_enrollments,
      active_enrollments = EXCLUDED.active_enrollments,
      completed_enrollments = EXCLUDED.completed_enrollments,
      dropped_enrollments = EXCLUDED.dropped_enrollments,
      completion_rate = EXCLUDED.completion_rate,
      avg_progress_percentage = EXCLUDED.avg_progress_percentage,
      avg_time_to_complete_hours = EXCLUDED.avg_time_to_complete_hours,
      avg_quiz_score = EXCLUDED.avg_quiz_score,
      total_quiz_attempts = EXCLUDED.total_quiz_attempts,
      ai_questions_asked = EXCLUDED.ai_questions_asked,
      published_at = EXCLUDED.published_at,
      last_enrollment_at = EXCLUDED.last_enrollment_at,
      updated_at = now();
  " >/dev/null </dev/null

done < <($PSQL_SC -At -F $'\t' -c "
  SELECT
    c.id::text,
    c.title,
    COALESCE(c.category, 'General') AS category,
    c.instructor_id::text,
    COALESCE(to_char(c.published_at, 'YYYY-MM-DD HH24:MI:SSOF'), '') AS published_at
  FROM courses c
  ORDER BY c.created_at DESC;
")

log "Refreshing student_metrics from smartcourse student_profiles..."
while IFS=$'\t' read -r student_id; do
  [[ -z "$student_id" ]] && continue

  stats=$($PSQL_SC -At -F $'\t' -c "
    SELECT
      (SELECT COUNT(*)::int FROM enrollments e WHERE e.student_id = '$student_id'),
      (SELECT COUNT(*)::int FROM enrollments e WHERE e.student_id = '$student_id' AND e.status = 'active'),
      (SELECT COUNT(*)::int FROM enrollments e WHERE e.student_id = '$student_id' AND e.status = 'completed'),
      (SELECT COUNT(*)::int FROM enrollments e WHERE e.student_id = '$student_id' AND e.status = 'dropped'),
      (SELECT COALESCE(ROUND(AVG(p.progress_percentage)::numeric, 2), 0) FROM progress p JOIN enrollments e ON e.id = p.enrollment_id WHERE e.student_id = '$student_id'),
      (SELECT COALESCE(ROUND(AVG(qa.score)::numeric, 2), 0) FROM quiz_attempts qa JOIN enrollments e ON e.id = qa.enrollment_id WHERE e.student_id = '$student_id' AND qa.score IS NOT NULL),
      (SELECT COUNT(*)::int FROM certificates c JOIN enrollments e ON e.id = c.enrollment_id WHERE e.student_id = '$student_id'),
      (SELECT COALESCE(MAX(COALESCE(e.last_accessed_at, e.completed_at, e.started_at, e.enrolled_at)), now()) FROM enrollments e WHERE e.student_id = '$student_id');
  ")

  IFS=$'\t' read -r total active completed dropped avg_progress avg_quiz total_certs last_active <<< "$stats"

  $PSQL_AN -c "
    INSERT INTO student_metrics (
      id,
      student_id,
      total_enrollments,
      active_enrollments,
      completed_courses,
      dropped_courses,
      avg_progress,
      avg_quiz_score,
      total_certificates,
      last_active_at
    )
    VALUES (
      (
        substr(md5('student-metrics:' || '$student_id'), 1, 8) || '-' ||
        substr(md5('student-metrics:' || '$student_id'), 9, 4) || '-' ||
        substr(md5('student-metrics:' || '$student_id'), 13, 4) || '-' ||
        substr(md5('student-metrics:' || '$student_id'), 17, 4) || '-' ||
        substr(md5('student-metrics:' || '$student_id'), 21, 12)
      )::uuid,
      '$student_id'::uuid,
      $total,
      $active,
      $completed,
      $dropped,
      $avg_progress,
      NULLIF('$avg_quiz', '0.00')::numeric,
      $total_certs,
      '$last_active'::timestamptz
    )
    ON CONFLICT (student_id)
    DO UPDATE SET
      total_enrollments = EXCLUDED.total_enrollments,
      active_enrollments = EXCLUDED.active_enrollments,
      completed_courses = EXCLUDED.completed_courses,
      dropped_courses = EXCLUDED.dropped_courses,
      avg_progress = EXCLUDED.avg_progress,
      avg_quiz_score = EXCLUDED.avg_quiz_score,
      total_certificates = EXCLUDED.total_certificates,
      last_active_at = EXCLUDED.last_active_at,
      updated_at = now();
  " >/dev/null </dev/null

done < <($PSQL_SC -At -F $'\t' -c "SELECT id::text FROM student_profiles ORDER BY created_at;")

log "Refreshing instructor_metrics from smartcourse instructor_profiles..."
while IFS=$'\t' read -r instructor_id; do
  [[ -z "$instructor_id" ]] && continue

  stats=$($PSQL_SC -At -F $'\t' -c "
    SELECT
      (SELECT COUNT(*)::int FROM courses c WHERE c.instructor_id = '$instructor_id'),
      (SELECT COUNT(*)::int FROM courses c WHERE c.instructor_id = '$instructor_id' AND c.published_at IS NOT NULL),
      (SELECT COUNT(DISTINCT e.student_id)::int FROM enrollments e JOIN courses c ON c.id = e.course_id WHERE c.instructor_id = '$instructor_id'),
      (SELECT COUNT(*)::int FROM enrollments e JOIN courses c ON c.id = e.course_id WHERE c.instructor_id = '$instructor_id'),
      (SELECT COUNT(*)::int FROM enrollments e JOIN courses c ON c.id = e.course_id WHERE c.instructor_id = '$instructor_id' AND e.status = 'completed'),
      (SELECT COALESCE(ROUND(AVG(qa.score)::numeric, 2), 0) FROM quiz_attempts qa JOIN enrollments e ON e.id = qa.enrollment_id JOIN courses c ON c.id = e.course_id WHERE c.instructor_id = '$instructor_id' AND qa.score IS NOT NULL);
  ")

  IFS=$'\t' read -r total_courses published_courses total_students total_enrollments total_completions avg_quiz <<< "$stats"

  avg_completion="0.00"
  if [[ "$total_enrollments" -gt 0 ]]; then
    avg_completion=$(awk "BEGIN { printf \"%.2f\", ($total_completions*100)/$total_enrollments }")
  fi

  $PSQL_AN -c "
    INSERT INTO instructor_metrics (
      id,
      instructor_id,
      total_courses,
      published_courses,
      total_students,
      total_enrollments,
      total_completions,
      avg_completion_rate,
      avg_quiz_score
    )
    VALUES (
      (
        substr(md5('instructor-metrics:' || '$instructor_id'), 1, 8) || '-' ||
        substr(md5('instructor-metrics:' || '$instructor_id'), 9, 4) || '-' ||
        substr(md5('instructor-metrics:' || '$instructor_id'), 13, 4) || '-' ||
        substr(md5('instructor-metrics:' || '$instructor_id'), 17, 4) || '-' ||
        substr(md5('instructor-metrics:' || '$instructor_id'), 21, 12)
      )::uuid,
      '$instructor_id'::uuid,
      $total_courses,
      $published_courses,
      $total_students,
      $total_enrollments,
      $total_completions,
      $avg_completion,
      NULLIF('$avg_quiz', '0.00')::numeric
    )
    ON CONFLICT (instructor_id)
    DO UPDATE SET
      total_courses = EXCLUDED.total_courses,
      published_courses = EXCLUDED.published_courses,
      total_students = EXCLUDED.total_students,
      total_enrollments = EXCLUDED.total_enrollments,
      total_completions = EXCLUDED.total_completions,
      avg_completion_rate = EXCLUDED.avg_completion_rate,
      avg_quiz_score = EXCLUDED.avg_quiz_score,
      updated_at = now();
  " >/dev/null </dev/null

done < <($PSQL_SC -At -F $'\t' -c "SELECT id::text FROM instructor_profiles ORDER BY created_at;")

log "Rebuilding enrollment_daily and ai_usage_daily trends..."
$PSQL_AN -c "TRUNCATE TABLE enrollment_daily, ai_usage_daily;" >/dev/null

while IFS=$'\t' read -r day course_id new_enrollments new_completions new_drops; do
  [[ -z "$day" ]] && continue

  if [[ "$course_id" == "__platform__" ]]; then
    course_sql="NULL"
    key="platform"
  else
    course_sql="'$course_id'::uuid"
    key="$course_id"
  fi

  $PSQL_AN -c "
    INSERT INTO enrollment_daily (
      id,
      date,
      course_id,
      new_enrollments,
      new_completions,
      new_drops
    )
    VALUES (
      (
        substr(md5('enroll-daily:' || '$day' || ':' || '$key'), 1, 8) || '-' ||
        substr(md5('enroll-daily:' || '$day' || ':' || '$key'), 9, 4) || '-' ||
        substr(md5('enroll-daily:' || '$day' || ':' || '$key'), 13, 4) || '-' ||
        substr(md5('enroll-daily:' || '$day' || ':' || '$key'), 17, 4) || '-' ||
        substr(md5('enroll-daily:' || '$day' || ':' || '$key'), 21, 12)
      )::uuid,
      '$day'::date,
      $course_sql,
      $new_enrollments,
      $new_completions,
      $new_drops
    )
    ON CONFLICT (date, course_id)
    DO UPDATE SET
      new_enrollments = EXCLUDED.new_enrollments,
      new_completions = EXCLUDED.new_completions,
      new_drops = EXCLUDED.new_drops;
  " >/dev/null </dev/null
done < <($PSQL_SC -At -F $'\t' -c "
  WITH days AS (
    SELECT generate_series((current_date - interval '29 days')::date, current_date, interval '1 day')::date AS day
  ),
  course_pool AS (
    SELECT id
    FROM courses
    ORDER BY created_at DESC, id
    LIMIT 6
  ),
  platform_daily AS (
    SELECT
      d.day,
      NULL::uuid AS course_id,
      COALESCE((SELECT COUNT(*) FROM enrollments e WHERE e.enrolled_at::date = d.day), 0) AS new_enrollments,
      COALESCE((SELECT COUNT(*) FROM enrollments e WHERE e.completed_at::date = d.day), 0) AS new_completions,
      COALESCE((SELECT COUNT(*) FROM enrollments e WHERE e.dropped_at::date = d.day), 0) AS new_drops
    FROM days d
  ),
  per_course_daily AS (
    SELECT
      d.day,
      cp.id AS course_id,
      COALESCE((SELECT COUNT(*) FROM enrollments e WHERE e.course_id = cp.id AND e.enrolled_at::date = d.day), 0) AS new_enrollments,
      COALESCE((SELECT COUNT(*) FROM enrollments e WHERE e.course_id = cp.id AND e.completed_at::date = d.day), 0) AS new_completions,
      COALESCE((SELECT COUNT(*) FROM enrollments e WHERE e.course_id = cp.id AND e.dropped_at::date = d.day), 0) AS new_drops
    FROM days d
    CROSS JOIN course_pool cp
  )
  SELECT day::text, '__platform__'::text, new_enrollments, new_completions, new_drops
  FROM platform_daily
  UNION ALL
  SELECT day::text, course_id::text, new_enrollments, new_completions, new_drops
  FROM per_course_daily
  WHERE (new_enrollments + new_completions + new_drops) > 0
  ORDER BY 1, 2;
")

$PSQL_AN -c "
  INSERT INTO ai_usage_daily (
    id,
    date,
    course_id,
    tutor_questions,
    instructor_requests,
    total_questions
  )
  SELECT
    (
      substr(md5('ai-daily:' || ed.date::text || ':' || COALESCE(ed.course_id::text, 'platform')), 1, 8) || '-' ||
      substr(md5('ai-daily:' || ed.date::text || ':' || COALESCE(ed.course_id::text, 'platform')), 9, 4) || '-' ||
      substr(md5('ai-daily:' || ed.date::text || ':' || COALESCE(ed.course_id::text, 'platform')), 13, 4) || '-' ||
      substr(md5('ai-daily:' || ed.date::text || ':' || COALESCE(ed.course_id::text, 'platform')), 17, 4) || '-' ||
      substr(md5('ai-daily:' || ed.date::text || ':' || COALESCE(ed.course_id::text, 'platform')), 21, 12)
    )::uuid,
    ed.date,
    ed.course_id,
    CASE
      WHEN ed.course_id IS NULL THEN GREATEST(8, ed.new_enrollments * 4 + ed.new_completions)
      ELSE GREATEST(1, ed.new_enrollments * 3 + ed.new_completions)
    END AS tutor_questions,
    CASE
      WHEN ed.course_id IS NULL THEN GREATEST(3, ed.new_drops + ed.new_completions)
      ELSE GREATEST(0, ed.new_completions)
    END AS instructor_requests,
    CASE
      WHEN ed.course_id IS NULL THEN
        GREATEST(11, ed.new_enrollments * 4 + ed.new_completions + ed.new_drops + 2)
      ELSE
        GREATEST(1, ed.new_enrollments * 3 + ed.new_completions + ed.new_drops)
    END AS total_questions
  FROM enrollment_daily ed
  ON CONFLICT (date, course_id)
  DO UPDATE SET
    tutor_questions = EXCLUDED.tutor_questions,
    instructor_requests = EXCLUDED.instructor_requests,
    total_questions = EXCLUDED.total_questions;
" >/dev/null

log "Done. smartcourse + analytics_db are now demo-seeded."
