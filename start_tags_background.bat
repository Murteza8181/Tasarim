@echo off
cd /d "c:\inetpub\wwwroot\Tasarim"
py -m uvicorn tags_api:app --host 127.0.0.1 --port 8001 --reload
