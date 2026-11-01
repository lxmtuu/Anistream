#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# check_cron.sh — cron GitHub Actions có THẬT SỰ chạy không?
#
# Vì sao có script này: bảng Actions trông như đã bật, `state=active`, nhưng ngày
# 2026-11-01 kiểm tra thật thì `event=schedule` có **0 run** dù cron
# `*/30 * * * *` phải bắn ít nhất 1 lần trong 25 phút. Tức là "xanh mà không có
# việc thật" — dữ liệu đứng yên mà không ai biết.
#
# Dùng:  bash scripts/check_cron.sh                 # repo hiện tại, cửa sổ 3 giờ
#        bash scripts/check_cron.sh owner/repo 6
#
# Exit code: 0 = có run theo lịch · 1 = KHÔNG có run nào (cron chết) · 2 = lỗi công cụ
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO="${1:-}"
HOURS="${2:-3}"

if ! command -v gh >/dev/null 2>&1; then
  echo "❌ chưa có gh CLI → cài: https://cli.github.com" >&2
  exit 2
fi
if [ -z "$REPO" ]; then
  REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null) || {
    echo "❌ không xác định được repo (chạy trong thư mục repo, hoặc truyền owner/repo)" >&2
    exit 2
  }
fi

# Mốc ISO, chịu được cả GNU date lẫn BSD/macOS date
SINCE=$(date -u -d "-${HOURS} hours" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
        || date -u -v-"${HOURS}"H +%Y-%m-%dT%H:%M:%SZ)

echo "▶ Kiểm cron của $REPO · cửa sổ ${HOURS} giờ (từ $SINCE)"
echo

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

if ! gh api "repos/$REPO/actions/runs?event=schedule&per_page=100" >"$TMP" 2>/dev/null; then
  echo "❌ không đọc được API Actions (thiếu quyền?). Chạy: gh auth status" >&2
  exit 2
fi

# Phân tích JSON: in 2 dòng cho shell đọc + chi tiết ra stderr
read -r COUNT LAST <<EOF
$(python3 -c '
import json, sys

path, since = sys.argv[1], sys.argv[2]
runs = json.load(open(path)).get("workflow_runs", [])
recent = [r for r in runs if (r.get("created_at") or "") > since]

print(len(recent), runs[0]["created_at"] if runs else "(chua-tung-co)")

for r in recent[:5]:
    print("  - %s  %s  %s" % (r.get("created_at"), r.get("name"), r.get("conclusion")),
          file=sys.stderr)
' "$TMP" "$SINCE")
EOF

echo "  run theo lịch trong ${HOURS}h : ${COUNT:-?}"
echo "  run theo lịch gần nhất     : ${LAST:-?}"

if [ "${COUNT:-0}" -ge 1 ]; then
  echo
  echo "✅ Cron ĐANG chạy."
  exit 0
fi

cat <<'TXT'

❌ KHÔNG có run nào do lịch (event=schedule) → dữ liệu sẽ KHÔNG tự cập nhật.
   Workflow `state=active` KHÔNG có nghĩa là cron sẽ chạy.

   Cách xử (chọn 1):
   A. Chờ thêm 1–2 giờ rồi chạy lại script này. Cron của repo mới tạo có thể trễ;
      nếu vẫn 0 run thì đừng tin cron nữa.
   B. Dùng cron ngoài (chắc ăn): tạo job ở https://cron-job.org gọi
        POST https://api.github.com/repos/<owner>/<repo>/actions/workflows/ingest.yml/dispatches
        Header: Authorization: Bearer <fine-grained token có quyền Actions: write>
        Body  : {"ref":"main"}
   C. Kiểm tra cuối cùng: Actions → ingest → "Enable workflow", và xác nhận repo
      không bị tắt Actions vì hết hạn mức.

   Bằng chứng cần lưu: nếu đã hẹn giờ mà DB vẫn không đổi, đó là cron chết —
   đừng ghi "đã bật cron" trong báo cáo.
TXT
exit 1
