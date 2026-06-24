"""
audit.py — Verificação e exportação da trilha de auditoria (Fase 4) · Tortuga

A trilha vive na tabela append-only `audit_chain` (events_store): cada evento
detectado vira um registro encadeado por hash SHA-256 (cada hash inclui o hash
anterior). Adulterar/remover qualquer registro QUEBRA a cadeia — é tamper-evident.

Aqui ficam: verificação de integridade, assinatura HMAC do "hash-cabeça"
(com segredo em TORTUGA_AUDIT_SECRET) e exportação CSV/HTML assinada, filtrável
por operador / estação(câmera) / turno / área (rastreabilidade, LGPD-aware).
"""
from __future__ import annotations
import csv, hashlib, hmac, html, io, json, os
from datetime import datetime

_FILT_KEYS = ("worker_id", "station_id", "turno", "area")


def recompute_hash(prev: str, ts: str, payload: str) -> str:
    return hashlib.sha256((prev + "|" + ts + "|" + payload).encode("utf-8")).hexdigest()


def verify(rows: list[dict]) -> dict:
    """Recalcula a cadeia e confirma que nada foi alterado."""
    prev = "GENESIS"; broken = None
    for r in rows:
        h = recompute_hash(prev, r["ts"], r["payload"])
        if r["prev_hash"] != prev or r["hash"] != h:
            broken = r["seq"]; break
        prev = r["hash"]
    return {"ok": broken is None, "count": len(rows),
            "head": rows[-1]["hash"] if rows else "GENESIS",
            "broken_at": broken}


def head(rows: list[dict]) -> str:
    return rows[-1]["hash"] if rows else "GENESIS"


def sign(head_hash: str, secret: str | None = None) -> str:
    secret = secret or os.environ.get("TORTUGA_AUDIT_SECRET") or "tortuga-dev-key"
    return hmac.new(secret.encode("utf-8"), head_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def flatten(rows: list[dict], filt: dict | None = None) -> list[dict]:
    out = []
    for r in rows:
        p = json.loads(r["payload"])
        if filt and any(filt.get(k) and p.get(k) != filt[k] for k in _FILT_KEYS):
            continue
        out.append({"seq": r["seq"], "audit_ts": r["ts"], **p, "hash": r["hash"]})
    return out


_COLS = ["seq", "audit_ts", "event_ts", "worker_id", "station_id", "area",
         "turno", "type", "epi", "severity", "hash"]


def export_csv(rows: list[dict], filt: dict | None = None, secret: str | None = None) -> str:
    data = flatten(rows, filt); v = verify(rows); h = head(rows)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=_COLS, extrasaction="ignore"); w.writeheader()
    for d in data:
        w.writerow(d)
    buf.write("\n")
    buf.write("# registros,%d\n" % len(data))
    buf.write("# cadeia_integra,%s\n" % v["ok"])
    buf.write("# hash_cabeca,%s\n" % h)
    buf.write("# assinatura_hmac_sha256,%s\n" % sign(h, secret))
    buf.write("# gerado_em,%s\n" % datetime.now().isoformat(timespec="seconds"))
    return buf.getvalue()


def export_html(rows: list[dict], filt: dict | None = None, secret: str | None = None) -> str:
    data = flatten(rows, filt); v = verify(rows); h = head(rows)
    seal_ok = "ÍNTEGRA" if v["ok"] else "VIOLADA (seq %s)" % v["broken_at"]
    seal_color = "#1E8E3E" if v["ok"] else "#C81E14"
    fcap = " · ".join("%s=%s" % (k, filt[k]) for k in _FILT_KEYS if filt and filt.get(k)) or "todos"
    trs = "\n".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td class='m'>%s…</td></tr>" % (
            d["seq"], html.escape(str(d.get("event_ts", "")[:19])), html.escape(str(d.get("worker_id", ""))),
            html.escape(str(d.get("station_id", "") or "")), html.escape(str(d.get("area", "") or "")),
            html.escape(str(d.get("type", ""))), html.escape(str(d.get("severity", ""))),
            html.escape(str(d.get("hash", ""))[:12]))
        for d in data)
    return """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">
<title>Tortuga · Relatório de auditoria</title><style>
body{font-family:-apple-system,'Segoe UI',Arial,sans-serif;color:#1D1D1F;margin:32px;font-size:13px}
h1{color:#0071E3;font-size:22px;margin:0 0 2px}.sub{color:#6E6E73;margin-bottom:18px}
.seal{border:1px solid #D2D2D7;border-radius:10px;padding:14px 18px;margin:0 0 20px;background:#F5F5F7}
.seal b{font-size:15px;color:%s}.seal code{font-family:ui-monospace,Consolas,monospace;font-size:11px;word-break:break-all}
table{width:100%%;border-collapse:collapse;font-size:12px}th,td{text-align:left;padding:7px 8px;border-bottom:1px solid #EDEDF0}
th{color:#6E6E73;font-size:10px;text-transform:uppercase;letter-spacing:.04em}td.m{font-family:ui-monospace,Consolas,monospace}
@media print{body{margin:0}}
</style></head><body>
<h1>Tortuga · Relatório de auditoria</h1>
<div class="sub">Projeto Tortuga · SSMA · gerado em %s · filtro: %s</div>
<div class="seal">
  <div>Integridade da cadeia: <b>%s</b> &nbsp;·&nbsp; registros: %d</div>
  <div style="margin-top:8px">Hash-cabeça: <code>%s</code></div>
  <div style="margin-top:4px">Assinatura HMAC-SHA256: <code>%s</code></div>
</div>
<table><thead><tr><th>#</th><th>Evento (ts)</th><th>Operador</th><th>Estação</th><th>Área</th><th>Tipo</th><th>Severidade</th><th>Hash</th></tr></thead>
<tbody>%s</tbody></table>
<p style="color:#999;margin-top:18px;font-size:11px">Imprima como PDF para arquivar. A assinatura confirma o hash-cabeça com o segredo do gestor (TORTUGA_AUDIT_SECRET).</p>
</body></html>""" % (
        seal_color, datetime.now().isoformat(timespec="seconds"), html.escape(fcap),
        seal_ok, len(data), h, sign(h, secret), trs)
