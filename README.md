# arcaInvoices

Escaneá tus facturas, organizalas y exportalas para cargarlas en [SiRADIG (ARCA/AFIP)](https://www.afip.gob.ar/572web/) sin perder ninguna deducción del Impuesto a las Ganancias.

## ¿Qué hace?

| Funcionalidad | Descripción |
|---|---|
| **Escaneo OCR** | Sacá una foto de una factura y la app extrae automáticamente CUIT, fecha, número de comprobante e importe |
| **Base de datos local** | Todas las facturas se guardan en SQLite — sin cloud, sin suscripciones |
| **Razón Social automática** | Ingresá el CUIT una vez y la app busca la razón social en AFIP |
| **Exportación CSV** | Descargá un archivo listo para abrir en Excel o Google Sheets y cargar manualmente en SiRADIG |
| **Recordatorios** | Configurá el día del mes para sincronizar y la app te avisa por email y/o SMS si te quedan pocas facturas por cargar |
| **PWA** | Funciona desde el celular como una app nativa (instalable en iOS y Android) |

> **Nota sobre la integración con SiRADIG:** ARCA/AFIP no expone una API pública para que empleados carguen deducciones programáticamente. La carga en SiRADIG debe hacerse manualmente desde [afip.gob.ar](https://www.afip.gob.ar/572web/). Esta app te ayuda a tener todos los datos organizados y listos para esa carga.

---

## Requisitos

- **Python 3.11+**
- **Node.js 18+**
- **Tesseract OCR** con el paquete de español

### Instalar dependencias del sistema

**macOS (Homebrew):**
```bash
brew install python@3.11 node tesseract tesseract-lang
```

**Ubuntu/Debian:**
```bash
sudo apt-get install python3.11 nodejs tesseract-ocr tesseract-ocr-spa
```

---

## Instalación rápida

```bash
git clone https://github.com/SantiagoBonacalzaRico/arcaInvoices.git
cd arcaInvoices
chmod +x install.sh && ./install.sh
```

El script crea el entorno virtual de Python, instala dependencias y compila el frontend.

---

## Instalación manual paso a paso

### 1. Clonar el repositorio

```bash
git clone https://github.com/SantiagoBonacalzaRico/arcaInvoices.git
cd arcaInvoices
```

### 2. Configurar el entorno

```bash
cp .env.example .env
```

Editá `.env` con tus datos (ver sección [Configuración](#configuración)).

### 3. Backend

```bash
cd backend
python3.11 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
mkdir -p data/invoices data/certs
```

### 4. Frontend

```bash
cd ../frontend
npm install
npm run build
```

### 5. Iniciar el servidor

```bash
cd ../backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Abrí **http://localhost:8000** en tu navegador.

---

## Instalación con Docker

```bash
cp .env.example .env
# Editá .env con tus datos
docker-compose up --build
```

---

## Configuración

Editá el archivo `.env` en la raíz del proyecto:

```env
# Directorio donde se guardan las fotos de facturas
INVOICE_DIR=data/invoices

# Clave secreta (generá una con: openssl rand -hex 32)
SECRET_KEY=tu-clave-secreta-aqui
```

El resto de la configuración (día de sincronización, notificaciones, AFIP) se hace directamente desde la UI en **Configuración**.

---

## Uso

### Escanear una factura

1. Andá a **Escanear** en el menú.
2. Tocá **Seleccionar imagen** o usá la cámara del celular.
3. La app procesa la imagen con OCR y extrae los datos automáticamente.
4. Revisá y corregí cualquier campo que no haya sido detectado correctamente.
5. Elegí la **categoría de deducción** (Gastos Médicos, Educación, etc.).
6. Guardá la factura.

> Si la app no reconoce algún campo (por ejemplo el número de comprobante), te va a pedir que lo ingreses manualmente. Ese dato queda guardado y la próxima vez que escanees una factura del mismo emisor lo va a completar automáticamente.

### Ver y editar facturas

En **Facturas** podés:
- Filtrar por estado (pendiente / sincronizado / error)
- Editar cualquier campo de una factura
- Eliminar facturas

### Exportar para SiRADIG

En **Exportar** encontrás:
- Un resumen agrupado por **CUIT y razón social**
- Cada factura con: número de comprobante, fecha, importe en formato `201000.00` y categoría
- Un botón **Descargar CSV** para abrir el archivo en Excel o Google Sheets y transcribir los datos en SiRADIG

Si la razón social de un CUIT no se detectó automáticamente, podés editarla haciendo clic sobre el nombre.

### Cargar en SiRADIG

1. Ingresá a [SiRADIG – Trabajador](https://auth.afip.gob.ar/contribuyente_/loginClave.xhtml) con tu CUIT y Clave Fiscal.
2. Usá el CSV exportado como referencia para cargar cada factura.

---

## Notificaciones automáticas

Configurá en **Configuración → Sincronización**:

| Campo | Descripción |
|---|---|
| Día del mes | Día objetivo para tener todas las facturas cargadas en SiRADIG |
| Notificar X días antes | Cuántos días antes querés recibir el aviso |
| Mínimo de facturas | Si tenés menos que este número, la app te manda la notificación |

### Email (Gmail)

1. En tu cuenta de Google, activá la verificación en dos pasos.
2. Generá una **contraseña de aplicación** en [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
3. En la app: SMTP host `smtp.gmail.com`, puerto `587`, usuario = tu email, contraseña = la contraseña de aplicación.

### SMS (Twilio, opcional)

1. Creá una cuenta en [twilio.com](https://www.twilio.com) y obtené un número de teléfono.
2. Agregá al `.env`:
```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxx
TWILIO_FROM_NUMBER=+1xxxxxxxxxx
```

---

## Búsqueda automática de Razón Social

La app puede buscar la razón social de un CUIT automáticamente usando dos fuentes:

### Opción A — Cuitalizer (recomendado, sin certificado AFIP)

1. Registrate gratis en [cuitalizer.com.ar](https://cuitalizer.com.ar).
2. Copiá tu API Key.
3. Pegala en **Configuración → Búsqueda de Razón Social**.

El plan gratuito incluye 10 consultas por mes. Como los resultados se cachean localmente, es más que suficiente para uso personal.

### Opción B — ws_sr_padron_a13 (oficial AFIP)

Si ya configuraste el certificado digital de AFIP (ver sección siguiente), la app usa automáticamente el servicio oficial de padrón de ARCA.

---

## Integración AFIP (opcional)

Esta sección es necesaria únicamente si querés usar el servicio de padrón oficial de ARCA (`ws_sr_padron_a13`) para la búsqueda de razón social. **No es necesaria para ninguna otra función de la app.**

Seguí el asistente paso a paso en **Configuración → Integración AFIP/ARCA**:

1. Ingresá a [auth.afip.gob.ar](https://auth.afip.gob.ar/contribuyente_/loginClave.xhtml) con tu CUIT y Clave Fiscal (nivel 2 o superior).
2. Ir a **Administrador de Relaciones de Clave Fiscal → Adherir Servicio → ARCA → WebServices → ws_sr_padron_a13**.
3. En la app, ingresá tu CUIT y hacé clic en **Generar par de claves (CSR)**.
4. Descargá el archivo `request.csr`.
5. En el portal de AFIP, ir a **Administrador de Certificados Digitales → Nueva solicitud**, subí el `.csr` y descargá el `cert.crt`.
6. En la app, pegá el contenido del `cert.crt` y hacé clic en **Subir certificado**.
7. Hacé clic en **Verificar conexión WSAA** para confirmar que todo funciona.

---

## Instalar como app en el celular (PWA)

### iPhone (Safari)
1. Abrí `http://tu-servidor:8000` en Safari.
2. Tocá el botón compartir → **Agregar a pantalla de inicio**.

### Android (Chrome)
1. Abrí `http://tu-servidor:8000` en Chrome.
2. Tocá el menú → **Instalar aplicación**.

---

## Estructura del proyecto

```
arcaInvoices/
├── backend/
│   ├── app/
│   │   ├── afip/          # WSAA auth, padrón lookup, SiRADIG stub
│   │   ├── ocr/           # Tesseract pipeline + patrones regex
│   │   ├── routers/       # FastAPI endpoints (invoices, sync, settings, export)
│   │   ├── models.py      # SQLAlchemy models
│   │   ├── scheduler.py   # APScheduler (sync mensual + notificaciones)
│   │   └── notifications.py
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   └── src/
│       └── views/         # Dashboard, Capture, Invoices, Export, Settings
├── docker-compose.yml
├── install.sh
└── .env.example
```

---

## Licencia

MIT