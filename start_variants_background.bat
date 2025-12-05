@echo off
cd /d "c:\inetpub\wwwroot\Tasarim"
py -m uvicorn variants_api:app --host 0.0.0.0 --port 5055
