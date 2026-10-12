import sqlite3
import json
import uuid
from datetime import datetime

DB_PATH = r"C:\Users\thikpad\.n8n\database.sqlite"

workflow_id = "socBrdcast99Nevn"
workflow_name = "Nevon Autonomous Social Broadcaster & Watchdog"

nodes = [
    {
        "parameters": {
            "rule": {
                "interval": [
                    {
                        "field": "cronExpression",
                        "expression": "0,5,10,15,30,45 10-18 * * *"
                    }
                ]
            }
        },
        "id": "e1f1a1b1-1111-4000-8000-000000000001",
        "name": "Social Hours Watchdog (10 AM - 6 PM PKT)",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [240, 300]
    },
    {
        "parameters": {
            "command": "python C:\\Users\\thikpad\\Desktop\\Kaam\\slack-ai-bot\\social_harvester.py --slot=auto"
        },
        "id": "e1f1a1b1-2222-4000-8000-000000000002",
        "name": "Scan Profiles & Broadcast New Posts",
        "type": "n8n-nodes-base.executeCommand",
        "typeVersion": 1,
        "position": [480, 300]
    },
    {
        "parameters": {
            "httpMethod": "POST",
            "path": "social-broadcast",
            "responseMode": "onReceived",
            "options": {}
        },
        "id": "e1f1a1b1-3333-4000-8000-000000000003",
        "name": "Instant Social Webhook Trigger",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [240, 500]
    },
    {
        "parameters": {
            "command": "python C:\\Users\\thikpad\\Desktop\\Kaam\\slack-ai-bot\\social_harvester.py --broadcast {{$json.body.urls ? $json.body.urls.join(' ') : $json.body.url}}"
        },
        "id": "e1f1a1b1-4444-4000-8000-000000000004",
        "name": "Broadcast Webhook Posts to Slack",
        "type": "n8n-nodes-base.executeCommand",
        "typeVersion": 1,
        "position": [480, 500]
    }
]

connections = {
    "Social Hours Watchdog (10 AM - 6 PM PKT)": {
        "main": [
            [
                {
                    "node": "Scan Profiles & Broadcast New Posts",
                    "type": "main",
                    "index": 0
                }
            ]
        ]
    },
    "Instant Social Webhook Trigger": {
        "main": [
            [
                {
                    "node": "Broadcast Webhook Posts to Slack",
                    "type": "main",
                    "index": 0
                }
            ]
        ]
    }
}

settings = {
    "executionOrder": "v1",
    "saveManualExecutions": True,
    "saveDataErrorExecution": "all",
    "saveDataSuccessExecution": "all"
}

def inject():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    
    # Check if workflow exists
    cur.execute("SELECT id FROM workflow_entity WHERE id = ?", (workflow_id,))
    existing = cur.fetchone()
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    version_id = str(uuid.uuid4())
    if existing:
        cur.execute("""
            UPDATE workflow_entity
            SET name = ?, nodes = ?, connections = ?, settings = ?, active = 1, updatedAt = ?
            WHERE id = ?
        """, (workflow_name, json.dumps(nodes), json.dumps(connections), json.dumps(settings), now_str, workflow_id))
        print("Updated existing workflow:", workflow_id)
    else:
        cur.execute("""
            INSERT INTO workflow_entity (id, name, active, nodes, connections, settings, versionId, createdAt, updatedAt)
            VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?)
        """, (workflow_id, workflow_name, json.dumps(nodes), json.dumps(connections), json.dumps(settings), version_id, now_str, now_str))
        print("Inserted new workflow:", workflow_id)
        
    con.commit()
    con.close()

if __name__ == "__main__":
    inject()
