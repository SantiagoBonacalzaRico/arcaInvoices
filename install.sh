#!/usr/bin/env bash
# Quick-start installer for Factura SiRADIG
# Requires: Python 3.11+, Node 18+, Tesseract with Spanish language pack

set -e

echo "=== Factura SiRADIG — Instalación ==="

# --- Backend ---
echo ""
echo "1. Configurando backend Python..."
cd backend
python3.11 -m venv venv || python3 -m venv venv
venv/bin/pip install --quiet --upgrade pip
venv/bin/pip install --quiet -r requirements.txt
mkdir -p data/invoices data/certs

if [ ! -f ../.env ]; then
  cp ../.env.example ../.env
  echo "   ✅ Archivo .env creado desde .env.example — editalo con tus datos."
else
  echo "   ℹ️  Archivo .env ya existe."
fi
cd ..

# --- Frontend ---
echo ""
echo "2. Construyendo frontend Vue/PWA..."
cd frontend
npm install --silent
npm run build
cd ..

echo ""
echo "=== Instalación completa ==="
echo ""
echo "Para iniciar el servidor:"
echo "  cd backend && venv/bin/uvicorn app.main:app --reload"
echo ""
echo "La API estará disponible en: http://localhost:8000"
echo "La UI (PWA) estará disponible en: http://localhost:8000"
echo ""
echo "⚠️  Antes de usar la sincronización con ARCA:"
echo "  1. Editá .env y configurá los valores de AFIP_SIRADIG_*"
echo "     (ver ManualSiRADIG.pdf v1.19 en https://www.afip.gob.ar/572web/documentos/ManualSiRADIG.pdf)"
echo "  2. En la UI, ir a Configuración → Integración AFIP/ARCA"
echo "     y seguir el asistente de certificado digital."
