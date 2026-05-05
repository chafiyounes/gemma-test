#!/usr/bin/env bash
# Run a few real /chat queries through the FastAPI stack with RAG and time them.
set -uo pipefail
PROJ="/workspace/gemma-test"
cd "$PROJ"

USER_PW=$(awk -F= '/^USER_SITE_PASSWORD=/{print $2; exit}' "$PROJ/.env")

curl -sS -c /tmp/cj.txt -X POST http://localhost:8000/auth/login \
     -H "content-type: application/json" --data "{\"password\":\"$USER_PW\"}" >/dev/null

CATS=$(curl -sS --max-time 5 http://localhost:8000/categories | \
    python3 -c "import sys,json; print(','.join(c['name'] for c in json.load(sys.stdin).get('categories', [])))")
FIRST_CAT=$(echo "$CATS" | cut -d, -f1)

run_query () {
    local cat="$1"
    local q="$2"
    echo
    echo "════════════════════════════════════════════════════════════════════"
    echo "  category=$cat"
    echo "  Q: $q"
    echo "════════════════════════════════════════════════════════════════════"
    cat > /tmp/chat.json <<EOF
{"user_id":"smoke","session_id":"$(date +%s)","message":"$q","conversation_history":[],"category":"$cat"}
EOF
    T0=$(date +%s.%N)
    R=$(curl -sS --max-time 120 -b /tmp/cj.txt -X POST http://localhost:8000/chat \
         -H "content-type: application/json" --data @/tmp/chat.json)
    T1=$(date +%s.%N)
    elapsed=$(python3 -c "print(f'{$T1 - $T0:.2f}')")
    echo "$R" | python3 -c "
import json, sys
r = json.load(sys.stdin)
print('A:', r.get('response', '<no response>'))
print(f'(elapsed={$elapsed}s, model={r.get(\"model\")})')
"
}

# Targeted queries based on the actual SOP docs we have on disk:
#   - 'Demande de remboursement - colis endommagé'
#   - 'Gestion des Coordonnées (ramassage)' / (retour)
#   - 'Gestion des colis endommagé' / 'colis supprimé'
#   - 'Informations destination'
#   - 'Plateforme Sendit (Assistance)'
#   - '16 Ville de ramassage (information)'
run_query "$FIRST_CAT" "Quelle est la procédure exacte pour qu'un client demande un remboursement pour un colis endommagé ?"
run_query "$FIRST_CAT" "Comment dois-je gérer une demande de modification des coordonnées de ramassage ?"
run_query "$FIRST_CAT" "Quelles sont les villes où SENDIT fait du ramassage ?"
# A free-form question with no category -> RAG off, model should respond freely.
run_query ""           "En 2 phrases simples : qu'est-ce qu'un grand modèle de langage ?"
