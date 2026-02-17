# Script tao GitHub Releases cho moi tag
# Cach dung: .\create_releases.ps1 -Token "ghp_YOUR_PERSONAL_ACCESS_TOKEN"
# Tao token tai: https://github.com/settings/tokens/new (chon scope "repo")

param(
    [Parameter(Mandatory=$true)]
    [string]$Token
)

$owner = "levanlinh"
$repo = "veo-pro-max"
$headers = @{
    "Authorization" = "Bearer $Token"
    "Accept" = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
}

$releases = @(
    @{ tag = "v1.0.0"; title = "v1.0.0 — Initial Commit"; body = "Initial commit: VEO Pro Max - Documentation + Client + Research" },
    @{ tag = "v1.0.1"; title = "v1.0.1 — Session Validation & Browser Debug"; body = "fix: session validation using __NEXT_DATA__, add browser debug features, inline credits fetch during login" },
    @{ tag = "v1.0.2"; title = "v1.0.2 — reCAPTCHA & CSS Fixes"; body = "fix: RecaptchaBrowserSession clicks Create with Flow, forward profiles_controller to Engine, remove invalid CSS cursor" },
    @{ tag = "v1.0.3"; title = "v1.0.3 — Thread Safety & Upscale MediaId"; body = "fix: thread-safe Qt updates, upscale mediaId, queue expand/collapse, filename quality" },
    @{ tag = "v1.1.0"; title = "v1.1.0 — Full Client Application"; body = "feat: implement initial VEO Pro Max client application with core logic, UI, and session/cache management" },
    @{ tag = "v1.1.1"; title = "v1.1.1 — License Roles Alignment"; body = "fix: align license roles to docs (3 roles: TRIAL/PREMIUM/TESTER)" },
    @{ tag = "v1.1.2"; title = "v1.1.2 — Queue Cancel Fix"; body = "fix: queue delete now cancels RUNNING/WAITING_POLL tasks" },
    @{ tag = "v1.1.3"; title = "v1.1.3 — Concurrency Warning Fix"; body = "fix: concurrency warning - accurate calc + dont-remind-again checkbox" },
    @{ tag = "v1.1.4"; title = "v1.1.4 — Submit Prompts Fix"; body = "fix: UnboundLocalError in submit_prompts + toast gating" },
    @{ tag = "v1.2.0"; title = "v1.2.0 — Notifications, Settings & UI"; body = "feat: notification sounds, image slot widget, settings, queue UI, and misc improvements" },
    @{ tag = "v1.3.0"; title = "v1.3.0 — Extension Bridge, reCAPTCHA Fix & Multi-Pipeline"; body = "feat: extension bridge (WebSocket), reCAPTCHA fix (chrome.scripting.executeScript), CDP HTTP extension installer (pure Python, no Node.js), splash screen, drag-drop widgets, I2V/R2V/I2I/F2V pipelines, x-client-data header extraction, persistent Chrome management" }
)

$created = 0
$failed = 0

foreach ($r in $releases) {
    Write-Host "Creating release: $($r.title)..." -NoNewline
    
    $body = @{
        tag_name = $r.tag
        name = $r.title
        body = $r.body
        draft = $false
        prerelease = $false
    } | ConvertTo-Json -Compress
    
    try {
        $response = Invoke-RestMethod `
            -Uri "https://api.github.com/repos/$owner/$repo/releases" `
            -Method Post `
            -Headers $headers `
            -Body $body `
            -ContentType "application/json"
        
        Write-Host " OK (id=$($response.id))" -ForegroundColor Green
        $created++
    }
    catch {
        Write-Host " FAILED: $($_.Exception.Message)" -ForegroundColor Red
        $failed++
    }
}

Write-Host ""
Write-Host "Done! Created: $created, Failed: $failed" -ForegroundColor Cyan
