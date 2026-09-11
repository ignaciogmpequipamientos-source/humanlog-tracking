from datetime import datetime, timedelta
from pathlib import Path
import glob
import json
import os
import time

import gspread
import pandas as pd
from gspread.utils import rowcol_to_a1
from gspread_formatting import (
    CellFormat,
    Color,
    TextFormat,
    format_cell_range,
    set_column_width,
    set_frozen,
)
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


DOWNLOAD_DIR = Path.cwd() / "downloads"
DEFAULT_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1qE4-tQ6BfCPkkHmAUQZSy9pwAkBa4w3BlNPsVdCixTw/edit?usp=sharing"
)
SHEET_URL = os.getenv("SHEET_URL") or DEFAULT_SHEET_URL
OUTPUT_COLUMNS = [
    "pedido",
    "destinatario",
    "provincia destino",
    "guia",
    "fecha carga",
]
HEADER = [
    "PEDIDO",
    "NOMBRE DESTINATARIO",
    "PROVINCIA DESTINO",
    "GUIA",
    "FECHA CARGA",
]
HISTORICAL_COLUMN_MAP = {
    "pedido": "pedido",
    "nombre destinatario": "destinatario",
    "destinatario": "destinatario",
    "provincia destino": "provincia destino",
    "guia": "guia",
    "numero de guia": "guia",
    "fecha carga": "fecha carga",
}


def required_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Falta configurar el secret o variable de entorno {name}.")
    return value


def date_range(days=7):
    today = datetime.today()
    since = today - timedelta(days=days)
    return since.strftime("%d/%m/%Y"), today.strftime("%d/%m/%Y")


def build_driver():
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    prefs = {
        "download.default_directory": str(DOWNLOAD_DIR),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
    }
    options.add_experimental_option("prefs", prefs)

    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )


def clear_previous_downloads():
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    for path in DOWNLOAD_DIR.glob("*.csv"):
        path.unlink()
    for path in DOWNLOAD_DIR.glob("*.crdownload"):
        path.unlink()


def wait_for_csv(timeout_seconds=60):
    deadline = time.time() + timeout_seconds
    last_size = None
    stable_since = None

    while time.time() < deadline:
        csv_files = glob.glob(str(DOWNLOAD_DIR / "*.csv"))
        partial_files = glob.glob(str(DOWNLOAD_DIR / "*.crdownload"))

        if csv_files and not partial_files:
            latest = Path(max(csv_files, key=os.path.getctime))
            current_size = latest.stat().st_size

            if current_size == last_size:
                stable_since = stable_since or time.time()
                if time.time() - stable_since >= 2:
                    return latest
            else:
                last_size = current_size
                stable_since = None

        time.sleep(1)

    raise RuntimeError("No se encontro un CSV descargado nuevo dentro del tiempo esperado.")


def download_csv():
    fecha_desde, fecha_hasta = date_range()
    humanlog_user = required_env("HUMANLOG_USER")
    humanlog_pass = required_env("HUMANLOG_PASS")

    clear_previous_downloads()
    driver = build_driver()
    wait = WebDriverWait(driver, 30)

    try:
        driver.get("https://human-log.com/BPlogin.php")
        wait.until(EC.presence_of_element_located((By.NAME, "usu"))).send_keys(humanlog_user)
        driver.find_element(By.NAME, "pass").send_keys(humanlog_pass)
        driver.find_element(By.ID, "registrar").click()

        driver.get("https://human-log.com/BPcon.php")

        campo_desde = wait.until(EC.presence_of_element_located((By.NAME, "fechadesde")))
        campo_desde.clear()
        campo_desde.send_keys(fecha_desde)

        campo_hasta = driver.find_element(By.NAME, "fechahasta")
        campo_hasta.clear()
        campo_hasta.send_keys(fecha_hasta)

        wait.until(
            EC.element_to_be_clickable((By.XPATH, "//input[@value='Actualiza Consulta']"))
        ).click()

        wait.until(EC.element_to_be_clickable((By.ID, "btnGeneraExcel"))).click()
        csv_path = wait_for_csv()
        print(f"CSV descargado: {csv_path}")
        return csv_path
    finally:
        driver.quit()


def read_shipments(csv_path):
    df = pd.read_csv(csv_path, sep=";", encoding="latin1", dtype=str).fillna("")

    required_columns = [
        "Pedido",
        "Destinatario",
        "Provincia Destino",
        "Numero de Guia",
    ]
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise RuntimeError(f"El CSV no tiene las columnas esperadas: {missing}")

    df = df[required_columns].rename(
        columns={
            "Pedido": "pedido",
            "Destinatario": "destinatario",
            "Provincia Destino": "provincia destino",
            "Numero de Guia": "guia",
        }
    )
    df["fecha carga"] = datetime.now().strftime("%Y-%m-%d")
    return normalize_shipments(df)


def normalize_shipments(df):
    df = df.copy()
    df.columns = [str(column).lower().strip() for column in df.columns]
    df = df.rename(columns=HISTORICAL_COLUMN_MAP)
    df = df.reindex(columns=OUTPUT_COLUMNS, fill_value="")
    df = df.fillna("").astype(str)

    for column in OUTPUT_COLUMNS:
        df[column] = df[column].str.strip()

    df["pedido"] = df["pedido"].str.replace("'", "", regex=False)

    df = df[
        (df["pedido"] != "")
        & (df["pedido"] != "0")
        & (df["pedido"].str.lower() != "nan")
        & (df["guia"] != "")
        & (df["guia"].str.lower() != "nan")
    ]
    df = df.replace("nan", "")
    df.drop_duplicates(subset=["pedido", "guia"], keep="first", inplace=True)
    return df


def get_google_credentials(scope):
    if os.getenv("GOOGLE_CREDS"):
        google_creds = json.loads(os.environ["GOOGLE_CREDS"])
        return ServiceAccountCredentials.from_json_keyfile_dict(google_creds, scope)

    creds_path = Path("credenciales.json")
    if not creds_path.exists():
        raise RuntimeError(
            "Falta GOOGLE_CREDS o el archivo local credenciales.json para autenticar Google Sheets."
        )
    return ServiceAccountCredentials.from_json_keyfile_name(str(creds_path), scope)


def open_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    client = gspread.authorize(get_google_credentials(scope))
    return client.open_by_url(SHEET_URL).sheet1


def read_historical(sheet):
    records = sheet.get_all_records()
    if not records:
        print("No hay historico previo.")
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    historical = normalize_shipments(pd.DataFrame(records))
    print(f"Historico encontrado: {len(historical)} registros")
    return historical


def build_final_data(new_shipments, historical):
    df = pd.concat([historical, new_shipments], ignore_index=True)
    df = normalize_shipments(df)
    print(f"Registros finales: {len(df)}")
    return df


def format_sheet(sheet):
    fmt = CellFormat(
        backgroundColor=Color(0.35, 0.20, 0.60),
        textFormat=TextFormat(
            foregroundColor=Color(1, 1, 1),
            bold=True,
            fontSize=12,
        ),
        horizontalAlignment="CENTER",
    )

    format_cell_range(sheet, "A1:E1", fmt)
    set_frozen(sheet, rows=1)
    set_column_width(sheet, "A", 120)
    set_column_width(sheet, "B", 320)
    set_column_width(sheet, "C", 180)
    set_column_width(sheet, "D", 220)
    set_column_width(sheet, "E", 140)


def update_sheet(sheet, df):
    values = [HEADER] + df.reindex(columns=OUTPUT_COLUMNS).values.tolist()
    old_rows = max(sheet.row_count, 1)
    old_cols = max(sheet.col_count, len(HEADER))

    sheet.update(values=values, range_name="A1")

    new_rows = len(values)
    if old_rows > new_rows:
        sheet.batch_clear([f"A{new_rows + 1}:{rowcol_to_a1(old_rows, len(HEADER))}"])
    if old_cols > len(HEADER):
        sheet.batch_clear([f"{rowcol_to_a1(1, len(HEADER) + 1)}:{rowcol_to_a1(old_rows, old_cols)}"])

    format_sheet(sheet)


def main():
    csv_path = download_csv()
    new_shipments = read_shipments(csv_path)
    print(new_shipments.head())

    sheet = open_sheet()
    historical = read_historical(sheet)
    final_data = build_final_data(new_shipments, historical)
    update_sheet(sheet, final_data)

    print("Google Sheets actualizado.")
    print("Proceso finalizado.")


if __name__ == "__main__":
    main()
