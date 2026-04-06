@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

set "SCRIPT_DIR=D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\02.1 - Script build App Client"
set "PYTHONUNBUFFERED=1"
set "PYTHONIOENCODING=utf-8"
set "BUILD_LOG=%SCRIPT_DIR%\build_app_live.log"
set "BUILD_EXIT=%SCRIPT_DIR%\build_app_exitcode.txt"
set "BUILD_RUNNER=%SCRIPT_DIR%\build_app_runner.cmd"
set "MONITOR_INTERVAL=15"

echo ===================================================
echo VEO Pro Max - Build Script (v2.3.11)
echo ===================================================
echo.

cd /d "%SCRIPT_DIR%"

echo [INFO] This BAT is a wrapper.
echo [INFO] GitHub upload is handled INSIDE build_release.py:
echo        - VEO_Pro_Max_v2.3.11.zip
echo        - VEO_Extension_v2.3.11.zip
echo        - VEO_Pro_Max_Setup_v2.3.11.exe
echo        - push version.json to public repo
echo [INFO] First full build may take a long time on Windows if Nuitka needs
echo        to auto-download MinGW64 because no native C compiler is installed.
echo.

where gh >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] gh CLI not found.
    echo         Install GitHub CLI or add it to PATH before running publish flow.
    pause
    exit /b 1
)

if "%GH_TOKEN%"=="" if "%GITHUB_TOKEN%"=="" (
    gh auth status >nul 2>nul
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] GitHub auth not detected.
        echo         Run: gh auth login
        echo         or set GH_TOKEN before running this BAT.
        pause
        exit /b 1
    )
) else (
    echo [INFO] GitHub token detected in environment.
)

echo [1/2] Running Preflight...
python -u build_release.py --archive-assets --preflight --plain-extension
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Preflight failed. See console output for details.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [INFO] Preflight completed.
echo [INFO] Full build can appear idle while compiling or downloading build tools.
choice /C YN /N /M "Continue with Full Build + GitHub Publish? [Y/N]: "
if ERRORLEVEL 2 (
    echo.
    echo [INFO] Stopped after preflight by user choice.
    pause
    exit /b 0
)

echo.
echo [2/2] Running Full Build + Package + GitHub Publish...
if exist "%BUILD_LOG%" del /f /q "%BUILD_LOG%" >nul 2>nul
if exist "%BUILD_EXIT%" del /f /q "%BUILD_EXIT%" >nul 2>nul
if exist "%BUILD_RUNNER%" del /f /q "%BUILD_RUNNER%" >nul 2>nul

echo [INFO] Live build log: "%BUILD_LOG%"
echo [INFO] Monitoring compiler/linker heartbeat every %MONITOR_INTERVAL%s...
(
    echo @echo off
    echo setlocal EnableExtensions EnableDelayedExpansion
    echo cd /d "%SCRIPT_DIR%"
    echo python -u build_release.py --plain-extension 1^>"%BUILD_LOG%" 2^>^&1
    echo ^> "%BUILD_EXIT%" echo %%ERRORLEVEL%%
) > "%BUILD_RUNNER%"
start "VEOBuild" /b cmd /c "\"%BUILD_RUNNER%\""

:monitor_loop
if exist "%BUILD_EXIT%" goto build_done

echo.
echo -------------------- [%DATE% %TIME%] Build heartbeat --------------------
powershell -NoProfile -Command ^
  "$procs = Get-Process link,cl,python -ErrorAction SilentlyContinue | Sort-Object ProcessName;" ^
  "if ($procs) {" ^
  "  $procs | Select-Object ProcessName,Id,@{n='CPU_s';e={[math]::Round($_.CPU,1)}},@{n='WS_MB';e={[math]::Round($_.WS/1MB,1)}},StartTime | Format-Table -AutoSize" ^
  "} else {" ^
  "  Write-Host 'No python/cl/link process detected yet.';" ^
  "}" ^
  "if (Test-Path '%BUILD_LOG%') {" ^
  "  $f = Get-Item '%BUILD_LOG%';" ^
  "  Write-Host ('Log: ' + $f.FullName);" ^
  "  Write-Host ('Size: ' + [math]::Round($f.Length / 1KB, 1) + ' KB | LastWrite: ' + $f.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'));" ^
  "  Write-Host 'Last log lines:';" ^
  "  Get-Content -Path '%BUILD_LOG%' -Tail 5" ^
  "} else {" ^
  "  Write-Host 'Log file not created yet.';" ^
  "}"
timeout /t %MONITOR_INTERVAL% /nobreak >nul
goto monitor_loop

:build_done
set /p BUILD_RC=<"%BUILD_EXIT%"
if exist "%BUILD_RUNNER%" del /f /q "%BUILD_RUNNER%" >nul 2>nul
echo.
echo -------------------- Final log tail --------------------
if exist "%BUILD_LOG%" (
    powershell -NoProfile -Command "Get-Content -Path '%BUILD_LOG%' -Tail 20"
)

if not "%BUILD_RC%"=="0" (
    echo.
    echo [ERROR] Build failed with exit code %BUILD_RC%.
    echo         Full log: "%BUILD_LOG%"
    pause
    exit /b %BUILD_RC%
)

echo.
echo ===================================================
echo Build + GitHub publish completed successfully!
echo ===================================================
pause
