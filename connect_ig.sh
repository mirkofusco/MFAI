#!/usr/bin/env bash
set -euo pipefail

APP_ID='2838563556329480' # MF_AI
BASE='https://mid-ranna-soluzionidigitaliroma-f8d1ef2a.koyeb.app'
ADMIN_USER='admin'
ADMIN_PASSWORD='Asia2020$flavia'   # è già nota; resta tra apici!

# jq è comodo ma non obbligatorio
if command -v jq >/dev/null 2>&1; then
  USE_JQ=1
else
  USE_JQ=0
  echo "Suggerimento: installa jq (brew install jq) per output più pulito. Procedo senza."
fi

# 1) Prendi i segreti in input (App Secret nascosto)
read -rsp "App Secret per APP_ID ${APP_ID}: " APP_SECRET; echo
read -rp  "Incolla SHORT_TOKEN (User Access Token dello Graph Explorer): " SHORT_TOKEN

# 2) Verifica che lo SHORT_TOKEN appartenga alla tua app
APP_ACCESS_TOKEN="${APP_ID}|${APP_SECRET}"
DEBUG_JSON="$(curl -s -G \
  -d "input_token=${SHORT_TOKEN}" \
  -d "access_token=${APP_ACCESS_TOKEN}" \
  'https://graph.facebook.com/debug_token')"

if [[ "${DEBUG_JSON}" != *"\"app_id\":\"${APP_ID}\""* && "${DEBUG_JSON}" != *"\"app_id\":${APP_ID}"* ]]; then
  echo "❌ Il token NON appartiene all'app ${APP_ID}. Rigenera lo SHORT_TOKEN scegliendo la tua app nel Graph Explorer."
  echo "Debug: ${DEBUG_JSON}"
  exit 1
fi
echo "✅ Token appartiene all'app ${APP_ID}"

# 3) Scambia lo SHORT_TOKEN in LONG_TOKEN (60gg)
LL_JSON="$(curl -s -G \
  --data-urlencode "grant_type=fb_exchange_token" \
  --data-urlencode "client_id=${APP_ID}" \
  --data-urlencode "client_secret=${APP_SECRET}" \
  --data-urlencode "fb_exchange_token=${SHORT_TOKEN}" \
  'https://graph.facebook.com/v19.0/oauth/access_token')"

if [[ "${LL_JSON}" == *"error"* ]]; then
  echo "❌ Errore nello scambio long-lived:"
  echo "${LL_JSON}"
  exit 1
fi

if [[ ${USE_JQ} -eq 1 ]]; then
  LONG_TOKEN="$(printf '%s' "${LL_JSON}" | jq -r '.access_token')"
  EXPIRES_IN="$(printf '%s' "${LL_JSON}" | jq -r '.expires_in')"
else
  LONG_TOKEN="$(printf '%s' "${LL_JSON}" | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')"
  EXPIRES_IN="$(printf '%s' "${LL_JSON}" | sed -n 's/.*"expires_in":\([0-9]*\).*/\1/p')"
fi
if [[ -z "${LONG_TOKEN}" ]]; then
  echo "❌ Non sono riuscito ad estrarre il LONG_TOKEN. Risposta:"
  echo "${LL_JSON}"
  exit 1
fi
echo "✅ Ottenuto LONG_TOKEN (scade in ~${EXPIRES_IN}s)"

# 4) Prendi le pagine che gestisci e scegli la PAGE_ID
ACCTS_JSON="$(curl -s -G -d "access_token=${LONG_TOKEN}" \
  'https://graph.facebook.com/v19.0/me/accounts?limit=25')"

if [[ ${USE_JQ} -eq 1 ]]; then
  echo "📃 Pagine trovate:"
  printf '%s' "${ACCTS_JSON}" | jq -r '.data[] | "\(.id)  \(.name)"'
  PAGE_ID="$(printf '%s' "${ACCTS_JSON}" | jq -r '.data[0].id')"
else
  # fallback grezzo
  echo "📃 Pagine (raw): ${ACCTS_JSON}"
  PAGE_ID="$(printf '%s' "${ACCTS_JSON}" | sed -n 's/.*"id":"\([0-9]\+\)".*/\1/p' | head -n1)"
fi
read -rp "Usare questa PAGE_ID? [${PAGE_ID}] (invio per confermare, oppure scrivi un'altra PAGE_ID): " PAGE_ID_INPUT
PAGE_ID="${PAGE_ID_INPUT:-$PAGE_ID}"
if [[ -z "${PAGE_ID}" ]]; then
  echo "❌ Nessuna PAGE_ID selezionata."
  exit 1
fi
echo "✅ PAGE_ID=${PAGE_ID}"

# 5) Ottieni IG_USER_ID dalla pagina
IG_JSON="$(curl -s -G \
  -d "fields=connected_instagram_account" \
  -d "access_token=${LONG_TOKEN}" \
  "https://graph.facebook.com/v19.0/${PAGE_ID}")"

if [[ ${USE_JQ} -eq 1 ]]; then
  IG_USER_ID="$(printf '%s' "${IG_JSON}" | jq -r '.connected_instagram_account.id // empty')"
else
  IG_USER_ID="$(printf '%s' "${IG_JSON}" | sed -n 's/.*"connected_instagram_account":{"id":"\([0-9]\+\)".*/\1/p')"
fi

if [[ -z "${IG_USER_ID}" ]]; then
  echo "❌ Nessun IG collegato a PAGE_ID=${PAGE_ID}. Collega l'account IG alla pagina FB e riprova."
  echo "Risposta: ${IG_JSON}"
  exit 1
fi
echo "✅ IG_USER_ID=${IG_USER_ID}"

# 6) Salva il token nel backend (UI2 /tokens/refresh)
RESP="$(curl -s -i -u "${ADMIN_USER}:${ADMIN_PASSWORD}" -X POST \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode "ig_user_id=${IG_USER_ID}" \
  --data-urlencode "token=${LONG_TOKEN}" \
  --data-urlencode "expires_in_days=60" \
  "${BASE}/ui2/tokens/refresh")"

echo "${RESP}"

if echo "${RESP}" | grep -q " 303 "; then
  echo "✅ Token salvato. Vai su ${BASE}/ui2 (vedrai: Token aggiornato)."
else
  echo "⚠️ Controlla la risposta sopra. Se 401, verifica X-API-KEY lato backend; se 500, guarda i log Koyeb."
fi
