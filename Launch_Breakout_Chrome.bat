@echo off
rem Launch Google Chrome with CDP remote debugging and dedicated user profile for Breakout Prop Firm
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\Google\Chrome_Breakout" "https://trade.breakoutprop.com"
