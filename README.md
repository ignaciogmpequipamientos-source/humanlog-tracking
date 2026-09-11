# humanlog-tracking

Automatiza la descarga de envios desde Human Log y actualiza una Google Sheet con pedidos, destinatarios, provincia, guia y fecha de carga.

El historico conserva solamente registros con fecha de carga de los ultimos 20 dias. En cada corrida se agregan envios nuevos, se eliminan duplicados por pedido + guia y se descartan filas mas antiguas.

## Ejecucion local

1. Instalar dependencias:

```powershell
py -m pip install -r requirements.txt
```

2. Configurar variables de entorno:

```powershell
$env:HUMANLOG_USER = "usuario"
$env:HUMANLOG_PASS = "password"
$env:GOOGLE_CREDS = Get-Content -Raw .\credenciales.json
```

Tambien se puede usar `credenciales.json` local si no se define `GOOGLE_CREDS`.

3. Ejecutar:

```powershell
py humanlog.py
```

## GitHub Actions

Configurar estos secrets en el repositorio:

- `HUMANLOG_USER`
- `HUMANLOG_PASS`
- `GOOGLE_CREDS`

Opcionalmente se puede configurar la variable `SHEET_URL` si se quiere cambiar la planilla destino sin editar el codigo.

Opcionalmente se puede configurar la variable `RETENTION_DAYS` si se quiere cambiar la retencion por defecto de 20 dias.
