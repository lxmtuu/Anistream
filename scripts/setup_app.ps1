# ─────────────────────────────────────────────────────────────────────────────
# setup_app.ps1 — chuẩn bị project Flutter trên Windows, KHÔNG ghi đè code.
#
# Cách làm: sinh project Flutter tạm rồi chỉ copy các thư mục platform
# (android\, ios\, windows\...) vào app\. lib\main.dart và pubspec.yaml giữ nguyên.
#
# Dùng:  powershell -ExecutionPolicy Bypass -File scripts\setup_app.ps1
# ─────────────────────────────────────────────────────────────────────────────
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$root = (Get-Location).Path
$app  = Join-Path $root "app"

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

$tmp = Join-Path $env:TEMP ("anistream_gen_" + [guid]::NewGuid().ToString("N").Substring(0,8))

try {
  Write-Host "Sinh project Flutter tam..." -ForegroundColor Cyan
  flutter create --org com.anistream --project-name anistream `
    --platforms=android,ios,web,windows,macos,linux $tmp | Out-Null

  Write-Host "Copy platform folders vao app\ (khong dung toi lib\)..." -ForegroundColor Cyan
  foreach ($d in @("android","ios","windows","macos","linux","web")) {
    $src = Join-Path $tmp $d
    if (Test-Path $src) {
      $dst = Join-Path $app $d
      if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
      Copy-Item $src $dst -Recurse
      Write-Host "   + $d\"
    }
  }
  $meta = Join-Path $tmp ".metadata"
  if (Test-Path $meta) { Copy-Item $meta (Join-Path $app ".metadata") -Force }

  Write-Host "flutter pub get..." -ForegroundColor Cyan
  Push-Location $app
  flutter pub get
  Pop-Location

  Write-Host ""
  Write-Host "XONG. Chay thu (chon 1):" -ForegroundColor Green
  Write-Host "  cd app; flutter run -d chrome        # nhanh nhat"
  Write-Host "  cd app; flutter run -d windows       # desktop (can Visual Studio C++)"
  Write-Host "  cd app; flutter devices              # xem thiet bi co san"
} finally {
  if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue }
}
