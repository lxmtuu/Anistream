# ─────────────────────────────────────────────────────────────────────────────
# setup_app.ps1 — chuẩn bị project Flutter trên Windows, KHÔNG ghi đè code.
#
# Nguyên tắc: CHỈ sinh thư mục platform nào còn THIẾU. Repo đã có sẵn
# android\ ios\ windows\ macos\ linux\ web\ (đã chỉnh tay: quyền INTERNET,
# POST_NOTIFICATIONS, tên app…). Ghi đè sẽ làm mất các chỉnh sửa đó và làm bản
# release mất mạng → script này không bao giờ copy đè.
#
# Dùng:  powershell -ExecutionPolicy Bypass -File scripts\setup_app.ps1
# ─────────────────────────────────────────────────────────────────────────────
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$root = (Get-Location).Path
$app  = Join-Path $root "app"
$platforms = @("android","ios","web","windows","macos","linux")

if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
  Write-Host "CHUA CO FLUTTER tren PATH." -ForegroundColor Red
  Write-Host "Cai tai: https://docs.flutter.dev/get-started/install"
  Write-Host "Sau khi cai, DONG terminal va mo lai roi chay lai lenh nay."
  exit 1
}

flutter --version | Select-Object -First 1

if (-not (Test-Path (Join-Path $app "pubspec.yaml"))) {
  Write-Host "Khong thay app\pubspec.yaml - ban dang chay script trong thu muc sai?" -ForegroundColor Red
  exit 1
}

$missing = @($platforms | Where-Object { -not (Test-Path (Join-Path $app $_)) })

if ($missing.Count -eq 0) {
  Write-Host "Da co du thu muc platform - bo qua buoc sinh, khong dung file nao." -ForegroundColor Cyan
} else {
  Write-Host ("Thieu: " + ($missing -join ", ") + " -> sinh phan con thieu...") -ForegroundColor Cyan
  $tmp = Join-Path $env:TEMP ("anistream_gen_" + [guid]::NewGuid().ToString("N").Substring(0,8))
  try {
    flutter create --org com.anistream --project-name anistream `
      --platforms=android,ios,web,windows,macos,linux $tmp | Out-Null

    foreach ($d in $missing) {
      $src = Join-Path $tmp $d
      if (Test-Path $src) {
        Copy-Item $src (Join-Path $app $d) -Recurse
        Write-Host "   + $d\"
      }
    }
    $meta = Join-Path $tmp ".metadata"
    if ((Test-Path $meta) -and -not (Test-Path (Join-Path $app ".metadata"))) {
      Copy-Item $meta (Join-Path $app ".metadata")
    }
  } finally {
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue }
  }
}

Write-Host "flutter pub get..." -ForegroundColor Cyan
Push-Location $app
flutter pub get
Pop-Location

Write-Host ""
Write-Host "XONG. Chay thu (chon 1):" -ForegroundColor Green
Write-Host "  cd app; flutter run -d chrome        # nhanh nhat"
Write-Host "  cd app; flutter run -d windows       # desktop (can Visual Studio C++)"
Write-Host "  cd app; flutter devices              # xem thiet bi co san"
Write-Host ""
Write-Host "Bat thong bao 'tap moi vua ra' (tuy chon):" -ForegroundColor DarkGray
Write-Host "  dart pub global activate flutterfire_cli; flutterfire configure" -ForegroundColor DarkGray
