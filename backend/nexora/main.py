"""Çalıştır: NEXORA_API_KEY=gizli uvicorn nexora.main:app --host 0.0.0.0 --port 8000"""
import os
from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel
from .core import Paper, CFG

app = FastAPI(title="NEXORA 2.0")
paper = Paper(os.getenv("NEXORA_DB", "nexora_paper.db"))
KEY = os.getenv("NEXORA_API_KEY", "")

def auth(x_api_key: str = Header(default="")):
    if not KEY or x_api_key != KEY:
        raise HTTPException(401, "yetkisiz")

class Signal(BaseModel):
    event_id: str; wallet: str; token: str; side: str
    price: float; liquidity_usd: float; signal_age_s: float = 0

@app.get("/durum", dependencies=[Depends(auth)])
def durum(): return dict(mod="PAPER", gercek_islem="KAPALI", acil_durdurma=paper.killed(), ayarlar=CFG)

@app.get("/portfoy", dependencies=[Depends(auth)])
def portfoy(): return paper.portfolio()

@app.get("/islemler", dependencies=[Depends(auth)])
def islemler(): return paper.trades()

@app.post("/sinyal", dependencies=[Depends(auth)])
def sinyal(s: Signal):
    return paper.handle_signal(s.event_id, s.wallet, s.token, s.side, s.price, s.liquidity_usd, s.signal_age_s)

@app.post("/acil-durdur", dependencies=[Depends(auth)])
def durdur(): paper.set_kill(True); return dict(acil_durdurma=True)

@app.post("/devam", dependencies=[Depends(auth)])
def devam(): paper.set_kill(False); return dict(acil_durdurma=False)
