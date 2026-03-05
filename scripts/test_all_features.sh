#!/bin/bash
# SkillSight 全功能测试脚本
# 测试所有 API 端点和核心功能

set -e

API_BASE="${API_BASE:-http://localhost:8001}"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
SKIP=0

test_endpoint() {
    local method=$1
    local endpoint=$2
    local data=$3
    local expected_code=${4:-200}
    local desc=$5
    
    echo -n "Testing: $desc... "
    
    if [ "$method" == "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" "$API_BASE$endpoint")
    else
        response=$(curl -s -w "\n%{http_code}" -X "$method" \
            -H "Content-Type: application/json" \
            -d "$data" \
            "$API_BASE$endpoint")
    fi
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [[ "$http_code" =~ ^$expected_code ]]; then
        echo -e "${GREEN}✓ PASS${NC} ($http_code)"
        ((PASS++))
        return 0
    else
        echo -e "${RED}✗ FAIL${NC} (expected $expected_code, got $http_code)"
        echo "  Response: $body"
        ((FAIL++))
        return 1
    fi
}

upload_file() {
    local file=$1
    local desc=$2
    
    echo -n "Testing: $desc... "
    
    response=$(curl -s -w "\n%{http_code}" -X POST \
        -F "file=@$file" \
        "$API_BASE/documents/upload?user_id=test_user&consent=true")
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [[ "$http_code" == "200" ]]; then
        echo -e "${GREEN}✓ PASS${NC}"
        DOC_ID=$(echo "$body" | grep -o '"doc_id":"[^"]*"' | cut -d'"' -f4)
        ((PASS++))
        return 0
    else
        echo -e "${RED}✗ FAIL${NC} ($http_code)"
        ((FAIL++))
        return 1
    fi
}

echo "=============================================="
echo "  SkillSight Full Feature Test Suite"
echo "  API Base: $API_BASE"
echo "=============================================="
echo ""

# ============================================
# 1. Health & Status
# ============================================
echo "📡 1. Health & Status Endpoints"
echo "----------------------------------------------"

test_endpoint "GET" "/health" "" "200" "Health check"
test_endpoint "GET" "/stats" "" "200" "Database stats"
test_endpoint "GET" "/api/overview" "" "200" "API overview"

echo ""

# ============================================
# 2. Skills Management
# ============================================
echo "🎯 2. Skills Management"
echo "----------------------------------------------"

test_endpoint "GET" "/skills?limit=10" "" "200" "List skills"
test_endpoint "GET" "/skills/search?q=python" "" "200" "Search skills"

echo ""

# ============================================
# 3. Roles Management
# ============================================
echo "👔 3. Roles Management"
echo "----------------------------------------------"

test_endpoint "GET" "/roles?limit=10" "" "200" "List roles"

echo ""

# ============================================
# 4. Document Management
# ============================================
echo "📄 4. Document Management"
echo "----------------------------------------------"

test_endpoint "GET" "/documents?limit=10" "" "200" "List documents"

# Create test file
echo "This is a test document for SkillSight testing. It demonstrates various skills including Python programming and data analysis." > /tmp/test_doc.txt

upload_file "/tmp/test_doc.txt" "Upload TXT document"

if [ -n "$DOC_ID" ]; then
    test_endpoint "GET" "/documents/$DOC_ID" "" "200" "Get document by ID"
    test_endpoint "GET" "/documents/$DOC_ID/chunks" "" "200" "Get document chunks"
fi

rm -f /tmp/test_doc.txt

echo ""

# ============================================
# 5. Search Endpoints
# ============================================
echo "🔍 5. Search Endpoints"
echo "----------------------------------------------"

test_endpoint "POST" "/search/evidence_vector" \
    '{"query_text": "python programming", "k": 5}' \
    "200" "Vector search"

test_endpoint "POST" "/search/evidence_keyword" \
    '{"query_text": "data analysis", "k": 5}' \
    "200" "Keyword search"

echo ""

# ============================================
# 6. AI Assessment
# ============================================
echo "🤖 6. AI Assessment"
echo "----------------------------------------------"

# These may fail if Ollama is not running
test_endpoint "POST" "/ai/demonstration" \
    '{"skill_id": "HKU.SKILL.PYTHON.v1", "k": 3}' \
    "200|404|503" "Demonstration assessment"

test_endpoint "POST" "/ai/proficiency" \
    '{"skill_id": "HKU.SKILL.PYTHON.v1", "k": 3}' \
    "200|404|503" "Proficiency assessment"

echo ""

# ============================================
# 7. Role Readiness
# ============================================
echo "🎯 7. Role Readiness"
echo "----------------------------------------------"

test_endpoint "POST" "/assess/role_readiness" \
    '{"role_id": "HKU.ROLE.DATA_ANALYST.v1"}' \
    "200|404" "Role readiness assessment"

echo ""

# ============================================
# 8. Action Recommendations
# ============================================
echo "💡 8. Action Recommendations"
echo "----------------------------------------------"

test_endpoint "GET" "/actions/templates" "" "200" "List action templates"

test_endpoint "POST" "/actions/recommend" \
    '{"gap_types": ["missing_proof"]}' \
    "200" "Get action recommendations"

echo ""

# ============================================
# 9. Interactive Assessments
# ============================================
echo "📝 9. Interactive Assessments"
echo "----------------------------------------------"

# Communication
COMM_RESPONSE=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d '{"user_id": "test_user", "duration_seconds": 60}' \
    "$API_BASE/interactive/communication/start")

COMM_SESSION=$(echo "$COMM_RESPONSE" | grep -o '"session_id":"[^"]*"' | cut -d'"' -f4 2>/dev/null || echo "")

if [ -n "$COMM_SESSION" ]; then
    echo -e "Communication session started: ${GREEN}✓ PASS${NC}"
    ((PASS++))
    
    test_endpoint "POST" "/interactive/communication/submit" \
        "{\"session_id\": \"$COMM_SESSION\", \"transcript\": \"This is my response about the topic.\", \"audio_duration_seconds\": 30}" \
        "200" "Submit communication response"
else
    echo -e "Communication session: ${YELLOW}○ SKIP${NC} (endpoint may not be available)"
    ((SKIP++))
fi

# Programming
PROG_RESPONSE=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d '{"user_id": "test_user", "difficulty": "easy"}' \
    "$API_BASE/interactive/programming/start")

PROG_SESSION=$(echo "$PROG_RESPONSE" | grep -o '"session_id":"[^"]*"' | cut -d'"' -f4 2>/dev/null || echo "")

if [ -n "$PROG_SESSION" ]; then
    echo -e "Programming session started: ${GREEN}✓ PASS${NC}"
    ((PASS++))
    
    test_endpoint "POST" "/interactive/programming/submit" \
        "{\"session_id\": \"$PROG_SESSION\", \"code\": \"def solution(nums, target):\\n    return []\", \"language\": \"python\"}" \
        "200" "Submit programming solution"
else
    echo -e "Programming session: ${YELLOW}○ SKIP${NC} (endpoint may not be available)"
    ((SKIP++))
fi

# Writing
WRITE_RESPONSE=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d '{"user_id": "test_user", "time_limit_minutes": 30}' \
    "$API_BASE/interactive/writing/start")

WRITE_SESSION=$(echo "$WRITE_RESPONSE" | grep -o '"session_id":"[^"]*"' | cut -d'"' -f4 2>/dev/null || echo "")
WRITE_TOKEN=$(echo "$WRITE_RESPONSE" | grep -o '"anti_copy_token":"[^"]*"' | cut -d'"' -f4 2>/dev/null || echo "")

if [ -n "$WRITE_SESSION" ] && [ -n "$WRITE_TOKEN" ]; then
    echo -e "Writing session started: ${GREEN}✓ PASS${NC}"
    ((PASS++))
    
    test_endpoint "POST" "/interactive/writing/submit" \
        "{\"session_id\": \"$WRITE_SESSION\", \"content\": \"This is my essay about the topic. I believe that effective communication is essential for success in any field. In my experience, clear and concise writing has helped me achieve my academic goals.\", \"anti_copy_token\": \"$WRITE_TOKEN\", \"keystroke_data\": {\"chars_per_minute\": 200, \"paste_count\": 0}}" \
        "200" "Submit writing assessment"
else
    echo -e "Writing session: ${YELLOW}○ SKIP${NC} (endpoint may not be available)"
    ((SKIP++))
fi

echo ""

# ============================================
# 10. Consent Management
# ============================================
echo "🔒 10. Consent Management"
echo "----------------------------------------------"

test_endpoint "POST" "/consent/grant" \
    '{"doc_id": "test-doc-id", "user_id": "test_user"}' \
    "200|400" "Grant consent"

echo ""

# ============================================
# 11. Job Queue
# ============================================
echo "⚙️ 11. Job Queue"
echo "----------------------------------------------"

test_endpoint "GET" "/jobs?limit=10" "" "200" "List jobs"
test_endpoint "GET" "/jobs/queue/status" "" "200" "Queue status"

echo ""

# ============================================
# Summary
# ============================================
echo "=============================================="
echo "  Test Summary"
echo "=============================================="
echo -e "  ${GREEN}Passed: $PASS${NC}"
echo -e "  ${RED}Failed: $FAIL${NC}"
echo -e "  ${YELLOW}Skipped: $SKIP${NC}"
echo ""

TOTAL=$((PASS + FAIL))
if [ $TOTAL -gt 0 ]; then
    PCT=$((PASS * 100 / TOTAL))
    echo "  Coverage: $PCT%"
fi

echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed. Please check the output above.${NC}"
    exit 1
fi
