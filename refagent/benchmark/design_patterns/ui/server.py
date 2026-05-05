import http.server
import json
import os
import urllib.parse

PORT = 8000
UI_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.abspath(os.path.join(UI_DIR, "../../../../data/design_patterns/aggregated_candidates.json"))
REVIEWED_FILE = os.path.abspath(os.path.join(UI_DIR, "../../../../data/design_patterns/reviewed_ids.json"))

REPO_MAPPING = {
    "AxonFramework": "https://github.com/AxonFramework/AxonFramework",
    "ant": "https://github.com/apache/ant",
    "camunda": "https://github.com/camunda/camunda",
    "cayenne": "https://github.com/apache/cayenne",
    "cucumber-jvm": "https://github.com/cucumber/cucumber-jvm",
    "flink": "https://github.com/apache/flink",
    "hbase": "https://github.com/apache/hbase",
    "jackrabbit": "https://github.com/apache/jackrabbit",
    "kafka": "https://github.com/apache/kafka"
}

class ValidationHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/candidates":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            
            reviewed_ids = set()
            if os.path.exists(REVIEWED_FILE):
                with open(REVIEWED_FILE, "r") as f:
                    reviewed_ids = set(json.load(f))

            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, "r") as f:
                    data = json.load(f)
                # Add mapping and construct URLs
                for item in data:
                    repo_path = item.get("repo_path")
                    base_url = REPO_MAPPING.get(repo_path.split('/')[-1], "")
                    if base_url:
                        base_url = base_url.replace(".git", "").replace("www.github.com", "github.com")
                        item["birth_commit_url"] = f"{base_url}/commit/{item['birth_commit_sha']}"
                    else:
                        item["birth_commit_url"] = "#"
                    
                    item["reviewed"] = item["id"] in reviewed_ids
                
                self.wfile.write(json.dumps(data).encode())
            else:
                self.wfile.write(json.dumps([]).encode())
        else:
            return super().do_GET()

    def do_POST(self):
        if self.path == "/api/update":
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            updates = json.loads(post_data)
            
            # updates expect: { "id": "...", "human_validation": bool, "reviewed": bool }
            
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, "r") as f:
                    data = json.load(f)
                
                # Update records based on ID
                update_map = {u["id"]: u["human_validation"] for u in updates}
                reviewed_in_batch = [u["id"] for u in updates if u.get("reviewed")]

                for item in data:
                    if item["id"] in update_map:
                        item["human_validation"] = update_map[item["id"]]
                
                with open(DATA_FILE, "w") as f:
                    json.dump(data, f, indent=2)
                
                # Update reviewed_ids.json
                reviewed_ids = []
                if os.path.exists(REVIEWED_FILE):
                    with open(REVIEWED_FILE, "r") as f:
                        reviewed_ids = json.load(f)
                
                new_reviewed = list(set(reviewed_ids + reviewed_in_batch))
                with open(REVIEWED_FILE, "w") as f:
                    json.dump(new_reviewed, f, indent=2)

                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == "__main__":
    print(f"Starting server at http://localhost:{PORT}")
    http.server.HTTPServer(("", PORT), ValidationHandler).serve_forever()
