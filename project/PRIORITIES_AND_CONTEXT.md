# Priorités produit — prompt, contexte, admin

La sécurité (mots de passe forts, secrets rotatifs) est **volontairement secondaire** pour l’instant ; on se concentre sur la **qualité des réponses** et la **transparence du RAG**.

## Objectif immédiat

1. **Compréhension du contexte** : le modèle doit exploiter les SOPs injectés (section DOCUMENTS DE RÉFÉRENCE) même quand la question est formulée en darija / anglais / mélange.
2. **Pas de « vide » silencieux** : si aucun document n’est injecté, l’API et l’admin doivent l’indiquer clairement (métadonnées `rag` + catégorie résolue).

## Comportement RAG (résumé)

- Si le client **n’envoie pas** `category`, l’API utilise **`RAG_DEFAULT_CATEGORY`** (`procedures` par défaut dans `app_config/settings.py`) lorsque ce dossier existe sous `data/documents/`, sinon la **première catégorie** (ordre alphabétique).
- Chaque réponse persistante en base inclut `metadata.rag` : `context_chars`, `documents_in_prompt`, `context_preview`, `note` éventuelle.
- L’**admin** (`/admin`) affiche ce bloc pour chaque interaction.

## Vérifier si la réponse est *vraiment* absente du corpus

Le dépôt Git peut ne **pas** contenir vos `.docx` / `.txt` (données sur le pod uniquement). Pour trancher **absence réelle** vs **modèle qui refuse** :

1. Sur la machine où vivent les fichiers (`data/documents/…` ou `data/documents_txt/…`), exécuter :
   ```bash
   cd /workspace/gemma-test   # ou le chemin local
   python scripts/rag_audit.py "Vendor bghay ybdel numéro ... livraison" procedures
   ```
2. Le script affiche, **par fichier**, des compteurs sur des thèmes (téléphone, livraison, modification, etc.), l’ordre BM25 et un extrait du texte injecté.  
   - Si **tous les compteurs sont 0** : le thème est probablement **absent** des textes — la phrase « absent des documents » peut être fondée.  
   - Si des compteurs sont **> 0** : le contenu est là — regarder la **prévisualisation RAG** dans l’admin et la troncature (`RAG_INJECT_MAX_CHARS`).

## Console admin

- URL : **`http://<hôte>:8000/admin`** (même origine que l’API ; cookies de session admin).
- Assets statiques : montés sous **`/admin-static/`** (CSS/JS).
- Problèmes historiques corrigés côté API : forme **`feedback`** imbriquée (likes/dislikes), **filtre** `feedback_reason`, **total** de résultats, **conversations** par `session_id` en SQL (ordre chronologique), fil des **tours uniques** dans le panneau Conversation.

## Accès pod RunPod

| Élément | Valeur typique |
|--------|----------------|
| Hôte SSH | `ssh.runpod.io` |
| Utilisateur | Voir `project/DEPLOYMENT.md` (identifiant pod) |
| Clé | `~/.ssh/id_ed25519` (Windows : `C:\Users\<vous>\.ssh\id_ed25519`) |

**Important :** le bastion RunPod exige souvent un **PTY**. Pour une commande non interactive, utiliser `python scripts/pod_cmd.py "commande"` ou `python scripts/deploy_runner.py`.

Chemins usuels sur le pod :

```bash
cd /workspace/gemma-test
bash start_all.sh gemma4    # tmux : vllm + api
curl -sS http://localhost:8002/v1/models   # inference prête si JSON
curl -sS http://localhost:8000/health
```

## Fichiers clés

| Fichier | Rôle |
|---------|------|
| `core/llm.py` | Prompt système, construction du bloc DOCUMENTS, `LLMGenerateResult` + `rag` |
| `core/documents.py` | Chargement `data/documents/`, BM25, ordre des docs par requête |
| `api/main.py` | `_resolve_rag_category`, `/chat`, routes `/admin/*` |
| `core/persistence.py` | SQLite, forme des interactions pour l’admin |
| `admin_site/` | Interface statique admin |

Pour le déploiement détaillé : [`DEPLOYMENT.md`](DEPLOYMENT.md). Pour l’architecture RAG : [`ARCHITECTURE.md`](ARCHITECTURE.md).
