import os, json, time, sys, subprocess, requests, uvicorn, asyncio
from typing import List, Dict, Optional
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from src.config import CLIENT_ID, CLIENT_SECRET

MANAGEMENT_PORT = 3000
TOKENS_DIR = os.path.join(os.getcwd(), "tokens")
CONFIG_FILE = "servers_config.json"
REDIRECT_URI = f"http://localhost:{MANAGEMENT_PORT}/api/auth/callback"
SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid"
]

app = FastAPI()
templates = Jinja2Templates(directory="templates")
running_processes: Dict[int, subprocess.Popen] = {}

class ServerConfig(BaseModel):
    id: Optional[str] = None
    name: str
    token_file: str
    project_id: str
    project_ids: List[dict] = []
    port: int
    password: str
    is_pro: bool = False
    status: str = "stopped"

def load_config():
    if not os.path.exists(CONFIG_FILE): return []
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return []

def save_config(configs):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(configs, f, indent=2)

def fetch_account_data_sync(filename, project_id):
    file_path = os.path.join(TOKENS_DIR, filename)
    try:
        with open(file_path, 'r') as f: token_data = json.load(f)
        for k, v in {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "token_uri": "https://oauth2.googleapis.com/token"}.items():
            if k not in token_data: token_data[k] = v
        creds = Credentials.from_authorized_user_info(token_data, SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            token_data.update(json.loads(creds.to_json()))
            with open(file_path, 'w') as f: json.dump(token_data, f, indent=2)

        headers = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json", "User-Agent": "GeminiCLI/v0.1.5"}
        with requests.Session() as s:
            s.headers.update(headers)
            user_resp = s.get("https://www.googleapis.com/oauth2/v2/userinfo", timeout=8)
            quota_resp = s.post("https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuota", json={"project": project_id}, timeout=8)
            tier_resp = s.post("https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist", json={}, timeout=8)
            
            # --- 核心判断逻辑修改 ---
            tier_data = tier_resp.json()
            # 1. 优先从 currentTier 获取状态
            current_tier_id = tier_data.get("currentTier", {}).get("id")
            # 2. 如果没有 currentTier，则查找 allowedTiers 里的默认项 (Pro账号特征)
            if not current_tier_id:
                for tier in tier_data.get("allowedTiers", []):
                    if tier.get("isDefault"):
                        current_tier_id = tier.get("id")
                        break
            
            is_pro = (current_tier_id == "standard-tier")
            # --- 修改结束 ---

        return {"status": "success", "filename": filename, "user": user_resp.json(), "quotas": quota_resp.json().get("buckets", []), "is_pro": is_pro}
    except Exception as e:
        return {"status": "error", "filename": filename, "message": str(e)}

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/api/tokens")
async def list_tokens():
    if not os.path.exists(TOKENS_DIR): os.makedirs(TOKENS_DIR)
    return [f for f in os.listdir(TOKENS_DIR) if f.endswith('.json')]

@app.get("/api/tokens/{filename}/projects")
async def get_google_projects(filename: str):
    file_path = os.path.join(TOKENS_DIR, filename)
    try:
        with open(file_path, 'r') as f: token_data = json.load(f)
        creds = Credentials.from_authorized_user_info(token_data, SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
        
        headers = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}
        # 获取内测ID
        preview_id = None
        try:
            tier_res = requests.post("https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist", json={}, headers=headers, timeout=8).json()
            preview_id = tier_res.get("cloudaicompanionProject")
        except: pass

        # 获取CRM项目列表
        projects = []
        try:
            service = build('cloudresourcemanager', 'v1', credentials=creds)
            res = service.projects().list().execute()
            projects = [p['projectId'] for p in res.get('projects', []) if p.get('lifecycleState') == 'ACTIVE']
        except: pass

        results = []
        if preview_id:
            results.append({"id": preview_id, "name": f"{preview_id} (内测预览项目ID)"})
        for pid in sorted(projects):
            if pid != preview_id: results.append({"id": pid, "name": pid})
        return results
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.get("/api/servers")
async def get_servers():
    configs = load_config()
    for cfg in configs:
        p = cfg['port']
        cfg['status'] = "running" if p in running_processes and running_processes[p].poll() is None else "stopped"
    return configs

@app.post("/api/servers")
async def add_server(config: ServerConfig):
    configs = load_config()
    config.id = str(int(time.time() * 1000))
    # 强制检测 Pro 状态
    res = fetch_account_data_sync(config.token_file, config.project_id)
    data = config.dict()
    data['is_pro'] = res.get("is_pro", False) if res.get("status") == "success" else False
    
    # 项目 ID 去重逻辑
    existing_pids = [p['id'] if isinstance(p, dict) else p for p in data.get('project_ids', [])]
    if data['project_id'] not in existing_pids:
        data['project_ids'].append({"id": data['project_id'], "name": data['project_id']})
        
    configs.append(data)
    save_config(configs)
    return {"status": "success"}

@app.put("/api/servers/{server_id}")
async def update_server(server_id: str, config: ServerConfig):
    configs = load_config()
    for i, cfg in enumerate(configs):
        if cfg['id'] == server_id:
            data = config.dict()
            data['id'] = server_id
            
            # 检查凭证文件是否发生变化
            if cfg.get('token_file') != data['token_file']:
                # 凭证变了，重新检测 Pro
                res = fetch_account_data_sync(data['token_file'], data['project_id'])
                data['is_pro'] = res.get("is_pro", False) if res.get("status") == "success" else False
            else:
                # 凭证没变，沿用之前的 Pro 标志
                data['is_pro'] = cfg.get('is_pro', False)

            # 项目 ID 去重逻辑
            existing_pids = [p['id'] if isinstance(p, dict) else p for p in data.get('project_ids', [])]
            if data['project_id'] not in existing_pids:
                data['project_ids'].append({"id": data['project_id'], "name": data['project_id']})
                
            configs[i] = data
            save_config(configs)
            return {"status": "success"}
    return JSONResponse(404, {"message": "Not found"})

@app.delete("/api/servers/{server_id}")
async def delete_server(server_id: str):
    configs = load_config()
    target = next((c for c in configs if c['id'] == server_id), None)
    if target and target['port'] in running_processes:
        proc = running_processes[target['port']]
        proc.terminate()
        del running_processes[target['port']]
    save_config([c for c in configs if c['id'] != server_id])
    return {"status": "success"}

@app.post("/api/servers/{server_id}/start")
async def start_server(server_id: str):
    configs = load_config()
    t = next((c for c in configs if c['id'] == server_id), None)
    if not t: return JSONResponse(404, {"message": "Not found"})
    env = os.environ.copy()
    env.update({"GOOGLE_APPLICATION_CREDENTIALS": os.path.join(TOKENS_DIR, t['token_file']), "GOOGLE_CLOUD_PROJECT": t['project_id'], "PORT": str(t['port']), "GEMINI_AUTH_PASSWORD": t['password']})
    proc = subprocess.Popen([sys.executable, "run_proxy.py"], env=env)
    running_processes[t['port']] = proc
    return {"status": "started"}

@app.post("/api/servers/{server_id}/stop")
async def stop_server(server_id: str):
    configs = load_config()
    t = next((c for c in configs if c['id'] == server_id), None)
    if t and t['port'] in running_processes:
        running_processes[t['port']].terminate()
        del running_processes[t['port']]
    return {"status": "stopped"}

@app.get("/api/servers/{server_id}/quota")
async def get_server_quota(server_id: str):
    configs = load_config()
    t = next((c for c in configs if c['id'] == server_id), None)
    res = await asyncio.get_running_loop().run_in_executor(None, fetch_account_data_sync, t['token_file'], t['project_id'])
    if res.get("status") == "success":
        t['is_pro'] = res.get("is_pro", False)
        save_config(configs)
    res['config_name'] = t['name']
    return res

@app.get("/api/auth/url")
async def get_auth_url():
    flow = Flow.from_client_config({"web": {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}}, scopes=SCOPES)
    flow.redirect_uri = REDIRECT_URI
    url, _ = flow.authorization_url(access_type='offline', prompt='consent')
    return {"url": url}

@app.get("/api/auth/callback")
async def auth_callback(code: str):
    flow = Flow.from_client_config({"web": {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}}, scopes=SCOPES)
    flow.redirect_uri = REDIRECT_URI
    flow.fetch_token(code=code)
    creds = flow.credentials
    user_info = build('oauth2', 'v2', credentials=creds).userinfo().get().execute()
    email = user_info.get("email")
    token_data = json.loads(creds.to_json())
    token_data.update({"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET})
    with open(os.path.join(TOKENS_DIR, f"{email}.json"), 'w') as f: json.dump(token_data, f, indent=2)
    return templates.TemplateResponse("auth_success.html", {"request": {}, "email": email})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=MANAGEMENT_PORT)