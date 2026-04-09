@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\02.1 - Script build App Client"
python -u build_release.py --plain-extension 1>"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\02.1 - Script build App Client\build_app_live.log" 2>&1
> "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\02.1 - Script build App Client\build_app_exitcode.txt" echo %ERRORLEVEL%
