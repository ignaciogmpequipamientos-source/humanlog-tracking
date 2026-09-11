from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import json
import os

import gspread
from oauth2client.service_account import ServiceAccountCredentials


DEFAULT_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1qE4-tQ6BfCPkkHmAUQZSy9pwAkBa4w3BlNPsVdCixTw/edit?usp=sharing"
)
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


def json_response(handler, status, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def normalize(value):
    return str(value or "").replace("'", "").strip()


def open_sheet():
    google_creds = os.getenv("GOOGLE_CREDS")
    if not google_creds:
        raise RuntimeError("Falta configurar GOOGLE_CREDS en Vercel.")

    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        json.loads(google_creds),
        SCOPE,
    )
    client = gspread.authorize(creds)
    return client.open_by_url(os.getenv("SHEET_URL") or DEFAULT_SHEET_URL).sheet1


def find_order(pedido):
    sheet = open_sheet()
    records = sheet.get_all_records()
    wanted = normalize(pedido)

    for record in records:
        current = normalize(record.get("PEDIDO"))
        if current == wanted:
            return {
                "found": True,
                "pedido": current,
                "guia": normalize(record.get("GUIA")),
                "destinatario": normalize(record.get("NOMBRE DESTINATARIO")),
                "provincia": normalize(record.get("PROVINCIA DESTINO")),
                "fechaCarga": normalize(record.get("FECHA CARGA")),
            }

    return {"found": False, "pedido": wanted}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        pedido = normalize(query.get("pedido", [""])[0])

        if not pedido:
            json_response(self, 400, {"error": "Ingresa un numero de pedido."})
            return

        try:
            json_response(self, 200, find_order(pedido))
        except Exception as exc:
            print(f"Error buscando pedido: {exc}")
            json_response(
                self,
                500,
                {"error": "No se pudo consultar la guia en este momento."},
            )
