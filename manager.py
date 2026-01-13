import os, json, time, sys, subprocess, requests, uvicorn, asyncio, uuid, socket
from pathlib import Path
from typing import List, Dict, Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

try:
    from src.config import CLIENT_ID, CLIENT_SECRET, ANTI_CLIENT_ID, ANTI_CLIENT_SECRET
except ImportError:
    CLIENT_ID = CLIENT_SECRET = ANTI_CLIENT_ID = ANTI_CLIENT_SECRET = "YOUR_CONFIG"

# --- 1. 全局配置与补丁 ---
import oauthlib.oauth2.rfc6749.parameters
oauthlib.oauth2.rfc6749.parameters.validate_token_parameters = lambda params: None

MANAGEMENT_PORT = 3000
CONFIG_FILE = "servers_config.json"
REDIRECT_URI = f"http://localhost:{MANAGEMENT_PORT}/api/auth/callback"

# 类型配置映射表
TYPE_CONFIG = {
    "cli": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "base_url": "https://cloudcode-pa.googleapis.com",
        "ua": "GeminiCLI/0.1.5",
        "dir": Path("tokens/cli"),
        "scopes": ["https://www.googleapis.com/auth/cloud-platform", "openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"]
    },
    "antigravity": {
        "client_id": ANTI_CLIENT_ID,
        "client_secret": ANTI_CLIENT_SECRET,
        "base_url": "https://daily-cloudcode-pa.sandbox.googleapis.com",
        # "base_url": "https://cloudcode-pa.googleapis.com",
        "ua": "antigravity/1.11.9 windows/amd64",
        "dir": Path("tokens/antigravity"),
        "scopes": [
            'https://www.googleapis.com/auth/cloud-platform',
            "openid",
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile',
            'https://www.googleapis.com/auth/cclog',
            'https://www.googleapis.com/auth/experimentsandconfigs'
        ]
    }
}

for cfg in TYPE_CONFIG.values(): cfg["dir"].mkdir(parents=True, exist_ok=True)

# --- 2. 数据模型与状态 ---
class ServerConfig(BaseModel):
    id: Optional[str] = None
    name: str
    type: str = "cli"
    token_file: str
    project_id: str
    project_ids: List[dict] = []
    port: int
    password: str
    is_pro: bool = False
    status: str = "stopped"
    quota_info: Optional[dict] = None

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
running_processes: Dict[str, subprocess.Popen] = {}

# --- 3. 工具函数 ---

def load_config() -> List[dict]:
    if not os.path.exists(CONFIG_FILE): return []
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return []

def save_config(configs: List[dict]):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(configs, f, indent=2)

def get_google_session(filename: str, t_type: str):
    """统一获取已授权的 Session 和 Credentials"""
    conf = TYPE_CONFIG.get(t_type, TYPE_CONFIG["cli"])
    path = conf["dir"] / filename
    if not path.exists(): raise FileNotFoundError("Token file missing")

    with open(path, 'r') as f: token_data = json.load(f)
    creds = Credentials.from_authorized_user_info(token_data, conf["scopes"])
    
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
        with open(path, 'w') as f: f.write(creds.to_json())
    
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {creds.token}", "User-Agent": conf["ua"], "Content-Type": "application/json"})
    return s, creds

def check_pro_status(session, base_url, t_type):
    """检测账号是否为 Pro (Standard Tier)"""
    try:
        res = session.post(f"{base_url}/v1internal:loadCodeAssist", json={}, timeout=8).json()
        if t_type == "antigravity":
            has_paid = res.get("paidTier", {}).get("id") == "g1-pro-tier"
            is_standard = res.get("currentTier", {}).get("id") == "standard-tier"
            return has_paid or is_standard
        else:
            is_pro = res.get("currentTier", {}).get("id") == "standard-tier"
            if not is_pro: # 检查默认允许列表
                is_pro = any(t.get("id") == "standard-tier" and t.get("isDefault") for t in res.get("allowedTiers", []))
            return is_pro and not res.get("ineligibleTiers")
    except:
        return t_type == "antigravity" # Anti 默认给 Pro 保证可用性

def fetch_account_data_sync(filename, project_id, t_type="cli"):
    """聚合获取用户信息、额度、Pro状态"""
    try:
        conf = TYPE_CONFIG[t_type]
        s, creds = get_google_session(filename, t_type)
        user = s.get("https://www.googleapis.com/oauth2/v2/userinfo", timeout=8).json()
        
        quotas = []
        if t_type == "antigravity":
            q_res = s.post(f"{conf['base_url']}/v1internal:fetchAvailableModels", json={"project": project_id}, timeout=8).json()
            for mid, mdata in q_res.get('models', {}).items():
                if 'quotaInfo' in mdata:
                    quotas.append({**mdata['quotaInfo'], "modelId": mid, "is_antigravity": True})
        else:
            q_res = s.post(f"{conf['base_url']}/v1internal:retrieveUserQuota", json={"project": project_id}, timeout=8).json()
            quotas = q_res.get("buckets", [])

        return {
            "status": "success", "filename": filename, "user": user, "quotas": quotas, 
            "is_pro": check_pro_status(s, conf['base_url'], t_type), "type": t_type
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "filename": filename}

# --- 4. API 路由 ---

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/api/tokens")
async def list_tokens(type: str = "cli"):
    target_dir = TYPE_CONFIG[type]["dir"]
    return [f for f in os.listdir(target_dir) if f.endswith('.json')]

@app.get("/api/tokens/{filename}/projects")
async def get_google_projects(filename: str, type: str = "cli"):
    try:
        s, creds = get_google_session(filename, type)
        results = []
        conf = TYPE_CONFIG[type]
        
        # 1. 获取内测项目
        try:
            tier_res = s.post(f"{conf['base_url']}/v1internal:loadCodeAssist", json={}, timeout=5).json()
            p_id = tier_res.get("cloudaicompanionProject")
            if p_id:
                pid = p_id.get("id") if isinstance(p_id, dict) else p_id
                results.append({"id": pid, "type": "internal"}) 
        except: pass

        # 2. 获取 CRM 项目列表
        try:
            service = build('cloudresourcemanager', 'v1', credentials=creds)
            res = service.projects().list().execute()
            for p in res.get('projects', []):
                if p.get('lifecycleState') == 'ACTIVE' and not any(r['id'] == p['projectId'] for r in results):
                    results.append({"id": p['projectId'], "type": "cloud"})
        except: pass

        # 3. Antigravity 随机生成
        if not results and type == "antigravity":
            rid = f"test-project-{uuid.uuid4().hex[:8]}"
            results.append({"id": rid, "type": "generated"})

        return results
    except Exception as e:
        return JSONResponse(500, {"message": str(e)})

@app.get("/api/servers")
async def get_servers():
    configs = load_config()
    for cfg in configs:
        sid = cfg['id']
        is_alive = sid in running_processes and running_processes[sid].poll() is None
        cfg['status'] = "running" if is_alive else "stopped"
        if not is_alive and sid in running_processes: del running_processes[sid]
    return configs

@app.post("/api/servers")
@app.put("/api/servers/{server_id}")
async def save_server(config: ServerConfig, server_id: str = None):
    configs = load_config()
    data = config.dict()
    
    # 自动校验 Pro 状态
    res = fetch_account_data_sync(data['token_file'], data['project_id'], data['type'])
    data['is_pro'] = res.get("is_pro", False)
    
    # 项目 ID 去重与补全
    existing_ids = [p['id'] for p in data.get('project_ids', [])]
    if data['project_id'] not in existing_ids:
        data['project_ids'].append({"id": data['project_id'], "type": "custom"})

    if server_id: # Update
        for i, cfg in enumerate(configs):
            if cfg['id'] == server_id:
                data['id'] = server_id
                configs[i] = data
                break
    else: # Create
        data['id'] = str(int(time.time() * 1000))
        configs.append(data)
    
    save_config(configs)
    return {"status": "success"}

@app.delete("/api/servers/{server_id}")
async def delete_server(server_id: str):
    if server_id in running_processes:
        running_processes[server_id].terminate()
        del running_processes[server_id]
    save_config([c for c in load_config() if c['id'] != server_id])
    return {"status": "success"}

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0
        
@app.post("/api/servers/{server_id}/start")
async def start_server(server_id: str):
    configs = load_config()
    srv = next((c for c in configs if c['id'] == server_id), None)
    if not srv: return JSONResponse(404, {"message": "Not found"})

    # 端口检测
    if any(p.poll() is None and next((c['port'] for c in configs if c['id'] == sid), 0) == srv['port'] for sid, p in running_processes.items()):
        return JSONResponse(400, {"message": f"端口 {srv['port']} 已被占用"})
        
    if is_port_in_use(srv['port']):
        return JSONResponse(400, {"message": f"端口 {srv['port']} 被系统占用，请稍后再试"})

    env = {**os.environ, 
           "GOOGLE_APPLICATION_CREDENTIALS": str(TYPE_CONFIG[srv['type']]['dir'] / srv['token_file']),
           "GOOGLE_CLOUD_PROJECT": srv['project_id'], "PORT": str(srv['port']),
           "GEMINI_AUTH_PASSWORD": srv['password'], "PROXY_TYPE": srv['type']}
    
    running_processes[server_id] = subprocess.Popen([sys.executable, "run_proxy.py"], env=env)
    return {"status": "started"}

@app.post("/api/servers/{server_id}/stop")
async def stop_server(server_id: str):
    if server_id in running_processes:
        proc = running_processes[server_id]
        try:
            proc.terminate()
            try:
                proc.wait(timeout=3) 
            except subprocess.TimeoutExpired:
                print(f"强制结束进程 {server_id}")
                proc.kill()
                proc.wait()
        except Exception as e:
            print(f"Error stopping: {e}")
        finally:
            if server_id in running_processes:
                del running_processes[server_id]
    return {"status": "stopped"}

@app.get("/api/servers/{server_id}/quota")
async def get_server_quota(server_id: str):
    configs = load_config()
    srv = next((c for c in configs if c['id'] == server_id), None)
    res = await asyncio.get_running_loop().run_in_executor(None, fetch_account_data_sync, srv['token_file'], srv['project_id'], srv['type'])
    if res.get("status") == "success":
        srv['is_pro'] = res.get("is_pro", False)
        save_config(configs)
    return {**res, "config_name": srv['name']}

@app.get("/api/auth/url")
async def get_auth_url(type: str = "cli"):
    conf = TYPE_CONFIG[type]
    flow = Flow.from_client_config(
        {"web": {"client_id": conf['client_id'], "client_secret": conf['client_secret'], 
                "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}}, 
        scopes=conf['scopes']
    )
    flow.redirect_uri = REDIRECT_URI
    url, _ = flow.authorization_url(access_type='offline', prompt='consent', state=type)
    return {"url": url}

@app.get("/api/auth/callback")
async def auth_callback(code: str, state: str = "cli"):
    conf = TYPE_CONFIG.get(state, TYPE_CONFIG["cli"])
    flow = Flow.from_client_config(
        {"web": {"client_id": conf['client_id'], "client_secret": conf['client_secret'], 
                "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}}, 
        scopes=conf['scopes']
    )
    flow.redirect_uri = REDIRECT_URI
    flow.fetch_token(code=code)
    
    creds = flow.credentials
    user_info = build('oauth2', 'v2', credentials=creds).userinfo().get().execute()
    email = user_info.get("email")
    
    token_data = json.loads(creds.to_json())
    token_data.update({"client_id": conf['client_id'], "client_secret": conf['client_secret']})
    
    with open(conf['dir'] / f"{email}.json", 'w') as f: json.dump(token_data, f, indent=2)
    return templates.TemplateResponse("auth_success.html", {"request": {}, "email": f"[{state.upper()}] {email}"})

if __name__ == "__main__":

    uvicorn.run(app, host="0.0.0.0", port=MANAGEMENT_PORT)
