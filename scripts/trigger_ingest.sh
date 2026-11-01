#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# trigger_ingest.sh — KÍCH HOẠT workflow `ingest` qua GitHub API.
#
# Vì sao cần: cron của GitHub Actions trên repo này đã đo được 0 lần chạy trong
# 10 giờ (`bash scripts/check_cron.sh` → exit 1). Không có gì chạy thì mọi job
# (lịch phát, video Muse, TMDB, mùa mới) đều đứng im. Script này để một dịch vụ
# cron BÊN NGOÀI (cron-job.org, hoặc pg_cron trong Supabase) gọi vào.
#
# Dùng:
#   export GH_TOKEN=github_pat_xxx          # PAT chỉ cần quyền Actions: write
#   bash scripts/trigger_ingest.sh lxmtuu/Anistream all
#   bash scripts/trigger_ingest.sh lxmtuu/Anistream tmdb --refresh
#
# Exit: 0 = đã kích hoạt · 1 = GitHub từ chối/không gọi được · 2 = thiếu tham số
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO="${1:-}"
CMD="${2:-all}"
shift $(( $# > 2 ? 2 : $# ))
# cờ thêm (--refresh, --limit-tmdb …) nối vào input "extra" của workflow
EXTRA="$*"
WORKFLOW="${WORKFLOW:-ingest.yml}"
REF="${REF:-main}"

if [ -z "$REPO" ]; then
  echo "Dùng: GH_TOKEN=... bash scripts/trigger_ingest.sh <owner/repo> [command] [cờ…]" >&2
  exit 2
fi
if [ -z "${GH_TOKEN:-}" ]; then
  # `gh auth token` nếu máy đã đăng nhập gh → không cần export tay
  GH_TOKEN="$(gh auth token 2>/dev/null || true)"
fi
if [ -z "${GH_TOKEN:-}" ]; then
  echo "✗ Thiếu GH_TOKEN (PAT có quyền Actions: write trên $REPO)" >&2
  echo "  → github.com/settings/tokens → Fine-grained → Repository access: $REPO"
  echo "    → Permissions → Actions: Read and write" >&2
  exit 2
fi

API="https://api.github.com/repos/$REPO/actions/workflows/$WORKFLOW/dispatches"
# Dựng JSON bằng python để không phải lo escape chuỗi trong bash
BODY=$(python3 -c '
import json, os, sys
cmd, extra = sys.argv[1], " ".join(sys.argv[2:]).strip()
inputs = {"command": cmd}
if extra:
    inputs["extra"] = extra
print(json.dumps({"ref": os.environ.get("REF", "main"), "inputs": inputs}))
' "$CMD" $EXTRA)

RESP=$(curl -sS -o /tmp/trigger.out -w '%{http_code}' -X POST "$API" \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -H "Content-Type: application/json" \
  -d "$BODY" 2>/dev/null)

case "$RESP" in
  204) echo "✅ đã kích hoạt $WORKFLOW (command=$CMD${EXTRA:+, $EXTRA}) trên $REPO@$REF" ;;
  401|403) echo "❌ GitHub từ chối ($RESP): token thiếu quyền Actions:write hoặc đã hết hạn"
           head -c 300 /tmp/trigger.out; echo; exit 1 ;;
  404) echo "❌ 404: sai owner/repo, sai tên workflow ($WORKFLOW), hoặc nhánh '$REF' không tồn tại"
       head -c 300 /tmp/trigger.out; echo; exit 1 ;;
  422) echo "❌ 422: input không hợp lệ (command=$CMD). Workflow chỉ nhận: schedule|catalog|youtube|tmdb|seasons|all"
       head -c 300 /tmp/trigger.out; echo; exit 1 ;;
  000) echo "❌ không kết nối được tới api.github.com (mạng/bị chặn)"; exit 1 ;;
  *)   echo "❌ HTTP $RESP"; head -c 300 /tmp/trigger.out; echo; exit 1 ;;
esac

# In trạng thái run vừa tạo (best-effort, không làm hỏng exit code)
sleep 4
curl -sS "https://api.github.com/repos/$REPO/actions/workflows/$WORKFLOW/runs?per_page=1" \
  -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json" 2>/dev/null \
  | python3 -c '
import json, sys
try:
    r = (json.load(sys.stdin).get("workflow_runs") or [{}])[0]
    print(f"   run #{r.get(\"run_number\")} · {r.get(\"status\")} · {r.get(\"html_url\")}")
except Exception:
    pass'
exit 0
