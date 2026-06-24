#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: "Mock Interview & Referral App (ReferME). 3-sided marketplace (students, professionals, employers) with credits/leaderboards/payouts. Backend refactor in progress: extracting endpoints from server.py into routers/. Phase A done (referrals, leaderboard). Phase B (interviews) had a crash because _can_use_free helper was moved into routers/interviews.py and still referenced by server.py (referral apply path) → circular import."

backend:
  - task: "Phase B refactor: extract interview endpoints to routers/interviews.py + restore _can_use_free helper in server.py"
    implemented: true
    working: true
    file: "/app/backend/server.py, /app/backend/routers/interviews.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: false
          agent: "main"
          comment: "Previous refactor moved _can_use_free to interviews.py and removed it from server.py, causing 'cannot import name _can_use_free from partially initialized module server' and full backend crash."
        - working: "NA"
          agent: "main"
          comment: "Re-defined _can_use_free(u, kind) in server.py just above _credit_user. interviews.py still imports it from server (works once defined at module-level before routers are included). Backend now boots cleanly."
        - working: true
          agent: "testing"
          comment: "Iter30 regression: 22/22 new tests pass. /api/interviews/{slots,book,my-bookings,joined,complete} all behaviour-neutral vs pre-refactor. /api/jobs/apply path that calls _can_use_free now works (used_free=true for free-pool users, -49 credits otherwise). Phase A endpoints (referrals + leaderboard) still 200. Pre-existing iter13 phone-gate fixture failures are unrelated to this refactor."

  - task: "Mark as Hired modal — replace base64 textarea with Image/PDF picker"
    implemented: true
    working: true
    file: "/app/frontend/app/professional/my-jobs/[id].tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: false
          agent: "main"
          comment: "User reported the 'Mark as Hired' modal still asked for a raw base64 paste — terrible UX. Required a proper file attachment chooser supporting Image (camera roll) AND PDF."
        - working: "NA"
          agent: "main"
          comment: "Replaced base64 multi-line Input with two file-picker buttons (Image + PDF/File) using expo-image-picker + expo-document-picker — same pattern already used in slots.tsx. Selected file is converted to a data URL and POSTed as proof_base64. Backend unchanged. Lint clean."
        - working: true
          agent: "testing"
          comment: "Iter33 frontend verification PASS 8/8: raw base64 textarea is gone; testIDs pick-hire-image + pick-hire-pdf render with 'Image' / 'PDF / File' labels; evidence note Input preserved; doHire alert + null proof_base64 path works; cancel/close reset state; slots.tsx regression intact. Flagged one defensive-symmetry nit (open handler didn't reset proofPreview/proofKind) which main agent then fixed."
        - working: true
          agent: "main"
          comment: "Applied the defensive-symmetry fix: 'Mark Hired' button onPress now also resets proofPreview + proofKind, so modal opens 100% clean every time."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 33
  run_ui: false

test_plan:
  current_focus:
    - "Mark as Hired modal — replace base64 textarea with Image/PDF picker"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: "Iter33: 'Mark as Hired' modal now offers Image + PDF picker buttons (no more raw base64 paste). Reused existing expo-image-picker / expo-document-picker pattern from slots.tsx. Need a quick FRONTEND test pass: (a) login as a professional who has at least one applicant in 'Referred' status on a posted job, (b) click 'Mark Hired' on that applicant → modal opens with title 'Mark as Hired' and shows two buttons 'Image' and 'PDF / File' (not a paste-base64 textarea), (c) verify both buttons render with their icons, (d) Submit is blocked if neither note nor proof attached (alert 'Evidence required'), (e) verify Cancel/X close resets state. NOTE: actually picking a file inside Playwright is hard — focus on UI rendering + behaviour, not the actual file-system attach. Also verify NO regression on the existing interview-completion proof picker on /app/professional/slots.tsx (same file-picker code reused)."
    implemented: true
    working: true
    file: "/app/backend/server.py, /app/backend/.env, /app/backend/requirements.txt"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: false
          agent: "main"
          comment: "Previous SendGrid API key returned 401 Unauthorized on every send, so all OTP/booking emails were silently mock-logged."
        - working: "NA"
          agent: "main"
          comment: "Migrated to Resend. Added resend==2.32.2. Rewrote send_html_email() to try Resend first via asyncio.to_thread, fallback to SendGrid then mock. MOCK_OTP_MODE now also considers RESEND_API_KEY. Live smoke test returned a Resend email id."
        - working: false
          agent: "testing"
          comment: "Iter31: 8/9 pass. CRITICAL booking bug — /api/interviews/book fires two emails back-to-back (student + pro), Resend free tier 2 req/sec → second hits 429 → SendGrid fallback also 401 → pro never gets booking email + ICS invite."
        - working: "NA"
          agent: "main"
          comment: "Added global async throttle inside send_html_email: _resend_lock + RESEND_MIN_GAP_SECS (default 0.55s) ensures every Resend send respects 2 req/sec — auto-applies to ALL callers, not just the booking endpoint. Local asyncio.gather of two sends now both succeed (~700ms apart, both got Resend IDs)."
        - working: true
          agent: "testing"
          comment: "Iter32: 9/9 iter31 tests now pass + new iter32 DB-status test passes. Booking flow emits two consecutive 'Resend OK' logs ~800ms apart, zero 429s, zero SendGrid fallback. Booking doc persists student_email_status='sent' AND pro_email_status='sent'. P0 closed."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 32
  run_ui: false

test_plan:
  current_focus: []
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: "Iter32: Resend migration is fully live + throttle bug fixed. All booking + auth flows green via Resend. SendGrid kept only as silent fallback. Awaiting user direction on next item (Phase C refactor / Razorpay live / AI Resume Review / MSG91 keys)."