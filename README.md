# NEXORA 2.0 (iskelet — N1/N8/N9/N14'ün ilk sürümü)
Mod: yalnızca PAPER. Gerçek işlem kodu yoktur.

## Backend
    cd backend && pip install -r requirements.txt
    NEXORA_API_KEY=gizli-bir-anahtar uvicorn nexora.main:app --host 0.0.0.0 --port 8000
    python -m unittest discover -s tests

Test sinyali:
    curl -X POST localhost:8000/sinyal -H "X-API-Key: gizli-bir-anahtar" -H "Content-Type: application/json" \
     -d '{"event_id":"e1","wallet":"W","token":"BONK","side":"buy","price":1.0,"liquidity_usd":1000000}'

## APK
GitHub'a yükle → Actions → "APK Derle" → Artifacts → nexora-apk.
