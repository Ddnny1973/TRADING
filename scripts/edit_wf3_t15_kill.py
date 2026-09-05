#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
edit_wf3_t15_kill.py - T15: agrega /pausar y /reanudar a WF3 (kill-switch).

- Respaldo local de workflow3-telegram-monitor.json en n8n-workflows/backups/
- Añade 2 ramas al Router: "pausar" (/pausar) y "reanudar" (/reanudar)
- Añade los nodos nuevos (2 HTTP + 3 Code => Pausar Notify / Reanudar Notify)
- Actualiza Format: Help con [KILL-SWITCH] /pausar /reanudar
- Recalcula posiciones en X de los nodos nuevos
- Reordena el array "nodes" para que Send Telegram Reply al final

El JSON resultante se escribe en el repo (source of truth). CI/CD lo sube a prod.
"""
import json
import os
import shutil
import time

BASE = os.path.join(os.path.dirname(__file__), "..", "n8n-workflows")
PATH = os.path.join(BASE, "workflow3-telegram-monitor.json")
BACKUP = os.path.join(BASE, f"backup-workflow3-kill-{time.strftime('%Y%m%d-%H%M%S')}.json")

# ---------- helpers ----------
_UUID = 0


def nid():
    global _UUID
    _UUID += 1
    return f"kill-{_UUID:08d}"


def new_node(name, ntype, version, params, x, y, xoff, type_nid=None, creds=None, wid=None):
    node = {
        "parameters": params,
        "id": type_nid or nid(),
        "name": name,
        "type": ntype,
        "typeVersion": version,
        "position": [x + xoff, y],
    }
    if wid:
        node["webhookId"] = wid
    if creds:
        node["credentials"] = creds
    return node


def main():
    if not os.path.exists(PATH):
        raise SystemExit(f"No existe {PATH}")
    with open(PATH, "r", encoding="utf-8") as f:
        wf = json.load(f)

    os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
    with open(BACKUP, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"Respaldo: {BACKUP}")

    nodes = wf["nodes"]
    conns = wf["connections"]
    by_name = {n["name"]: n for n in nodes}

    # ---- 1. Router: anade las reglas /pausar y /reanudar ----
    router = by_name["Router"]
    rules = router["parameters"]["rules"]["values"]

    rules.append({
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
            "conditions": [{
                "id": "cmd-pausar",
                "leftValue": "={{ $json.command }}",
                "rightValue": "/pausar",
                "operator": {"type": "string", "operation": "equals"},
            }],
            "combinator": "and",
        },
        "renameOutput": True,
        "outputKey": "pausar",
    })
    rules.append({
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
            "conditions": [{
                "id": "cmd-reanudar",
                "leftValue": "={{ $json.command }}",
                "rightValue": "/reanudar",
                "operator": {"type": "string", "operation": "equals"},
            }],
            "combinator": "and",
        },
        "renameOutput": True,
        "outputKey": "reanudar",
    })

    # ---- 2. Nodos nuevos ----
    # /pausar: POST /kill-switch engage -> cierra todos los grids
    http_pausar = new_node(
        name="Kill: Pausar (engage)",
        ntype="n8n-nodes-base.httpRequest", version=4.2,
        x=-560, y=1040, xoff=0,
        params={
            "url": "={{ $env.BACKEND_URL }}/api/v1/kill-switch",
            "method": "POST",
            "sendBody": True,
            "bodyParameters": {
                "parameters": [
                    {"name": "action", "value": "engage"},
                    {"name": "reason", "value": "MANUAL_TELEGRAM"},
                ]
            },
            "options": {"response": {"response": {"fullResponse": False, "neverError": True}}},
        },
    )
    code_pausar = new_node(
        name="Format: Pausar",
        ntype="n8n-nodes-base.code", version=2,
        x=-340, y=1040, xoff=0,
        params={
            "jsCode": (
                "const chatId = $('Parse Command').first().json.chatId;\n"
                "const ks = $json;\n"
                "const closed = (ks.closed_grids || []).length;\n"
                "let text = '🛑 KILL-SWITCH ENGAGED. ';\n"
                "if (ks.active) {\n"
                "  text += `Trading pausado, se cerraron ${closed} grid(s). `;\n"
                "  text += `Motivo: ${ks.reason || 'MANUAL'}.`;\n"
                "} else {\n"
                "  text += `El kill-switch NO se activo (respuesta inesperada: ${JSON.stringify(ks)}).`;\n"
                "}\n"
                "return [{ json: { chatId, text } }];"
            ),
        },
    )
    http_reanudar = new_node(
        name="Kill: Reanudar (disarm)",
        ntype="n8n-nodes-base.httpRequest", version=4.2,
        x=-560, y=1120, xoff=0,
        params={
            "url": "={{ $env.BACKEND_URL }}/api/v1/kill-switch",
            "method": "POST",
            "sendBody": True,
            "bodyParameters": {
                "parameters": [
                    {"name": "action", "value": "disarm"},
                ]
            },
            "options": {"response": {"response": {"fullResponse": False, "neverError": True}}},
        },
    )
    code_reanudar = new_node(
        name="Format: Reanudar",
        ntype="n8n-nodes-base.code", version=2,
        x=-340, y=1120, xoff=0,
        params={
            "jsCode": (
                "const chatId = $('Parse Command').first().json.chatId;\n"
                "const ks = $json;\n"
                "let text = '🟢 KILL-SWITCH DISARMED. ';\n"
                "if (!ks.active) {\n"
                "  text += 'Trading reanudado. Puedes volver a crear grids.';\n"
                "} else {\n"
                "  text += `Sigue activo: ${ks.reason || 'desconocido'}.`;\n"
                "}\n"
                "return [{ json: { chatId, text } }];"
            ),
        },
    )

    new_nodes = [http_pausar, code_pausar, http_reanudar, code_reanudar]
    for nn in new_nodes:
        nodes.append(nn)
        by_name[nn["name"]] = nn

    # ---- 4. Conexiones ----
    router_conn = []
    for n in nodes:
        if n["name"] == "Router":
            router_conn = conns["Router"]["main"]
            break

    # Los outputs del switch siguen el orden de las reglas, y el BONO "extra"
    # (fallback de /help) es el ULTIMO forward. Con 10 reglas -> 11 outputs
    # (indices 0-9 = reglas, indice 10 = extra). Las 8 primeras reglas ya
    # estaban; las dos nuevas (/pausar, /reanudar) entran en los indices 8 y 9
    # y el extra (/help) queda al final (indice 10).
    # Construimos la lista ordenada explícitamente para no depender del orden
    # del array previo.
    help_forward = [x for x in router_conn if x[0]["node"] == "Format: Help"]
    base = [x for x in router_conn if x[0]["node"] != "Format: Help"]
    # base conserva el orden de las 8 reglas existentes (0-7)
    new_router_conn = base + [
        [{"node": "Kill: Pausar (engage)", "type": "main", "index": 0}],
        [{"node": "Kill: Reanudar (disarm)", "type": "main", "index": 0}],
    ]
    if help_forward:
        new_router_conn.append(help_forward[0])
    conns["Router"]["main"] = new_router_conn

    conns["Kill: Pausar (engage)"] = {"main": [[{"node": "Format: Pausar", "type": "main", "index": 0}]]}
    conns["Format: Pausar"] = {"main": [[{"node": "Send Telegram Reply", "type": "main", "index": 0}]]}
    conns["Kill: Reanudar (disarm)"] = {"main": [[{"node": "Format: Reanudar", "type": "main", "index": 0}]]}
    conns["Format: Reanudar"] = {"main": [[{"node": "Send Telegram Reply", "type": "main", "index": 0}]]}

    # ---- 5. Help ----
    help_node = by_name["Format: Help"]
    help_code = help_node["parameters"]["jsCode"]
    help_code = help_code.replace(
        "  '/trigger-wf2 — Igual que /monitorear',",
        "  '/trigger-wf2 — Igual que /monitorear',\n"
        "  '',\n"
        "  '[KILL-SWITCH]',\n"
        "  '/pausar — Cerrar todos los grids y pausar (kill-switch)',\n"
        "  '/reanudar — Reanudar trading (disarm kill-switch)',",
    )
    help_node["parameters"]["jsCode"] = help_code

    # ---- 6. Send Telegram Reply al final ----
    reply = by_name["Send Telegram Reply"]
    nodes.remove(reply)
    nodes.append(reply)

    wf["nodes"] = nodes
    wf["connections"] = conns

    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"WF3 actualizado: {PATH}")


if __name__ == "__main__":
    main()
