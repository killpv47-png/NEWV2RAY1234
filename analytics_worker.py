import subprocess
import os
import time
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import base64
import uuid
import secrets
import re
import sys
import shutil
import io
from urllib.parse import parse_qs, urlparse
from copy import deepcopy

DEFAULT_CLEAN_IP = "172.64.149.23"
TRAFFIC_COEFFICIENT = 1.0
PANEL_USER = "admin"
PANEL_PASS = "AZHAN8585@#@#ABOL1234"
SESSION_TOKEN = secrets.token_hex(16)

SUB_REPO_NAME = "fffccxddff-max/SUB_REPO_TOKEN"
SUB_REPO_TOKEN = os.environ.get("SUB_REPO_TOKEN", "")

DB_PATH = "panel_db.json"
GIVEAWAY_CONFIG_PATH = "giveaway_config.json"
SYSTEM_CONFIG_PATH = "system_config.json"
COMBINED_SUBS_PATH = "combined_subs.json"
XRAY_CONFIG_PATH = "/usr/local/etc/xray/config.json"
XRAY_LOG_PATH = "/usr/local/etc/xray/xray_runtime.log"
XRAY_API_ADDR = "127.0.0.1:10085"
XRAY_STATS_CACHE = {}
LAST_STATS_SNAPSHOT = {}
LAST_STATS_PULL_TS = 0.0
DB_LOCK = threading.RLock()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_ADMIN_ID = os.environ.get("TELEGRAM_ADMIN_ID", "YOUR_ADMIN_CHAT_ID_HERE")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "@YOUR_CHANNEL_USERNAME_HERE")

CLOUDFLARED_BIN = "./cloudflared"
if not os.path.exists(CLOUDFLARED_BIN):
    for candidate in ["/usr/local/bin/cloudflared", "cloudflared", os.path.join(os.getcwd(), "cloudflared")]:
        if os.path.exists(candidate) or shutil.which(candidate):
            CLOUDFLARED_BIN = candidate if os.path.exists(candidate) else shutil.which(candidate)
            break

USER_PRIVATE_TUNNELS = {}
PRIVATE_TUNNEL_LOG_DIR = "/tmp/killpv2_private_tunnels"
os.makedirs(PRIVATE_TUNNEL_LOG_DIR, exist_ok=True)

SYSTEM_LIVE_LOGS = []
RUNNER_LIVE_LOGS = ["🔄 سیستم تست رانر آماده است."]
DPI_BLOCK_LOGS = []
USER_TARGET_SITES = {}
USER_LIVE_IPS = {}
PANEL_DATABASE = {}

CHANNEL_STREAM_STATE = {"msg_id": None, "last_update": 0, "events": []}

IP_REGEX = re.compile(r'(\d{1,3}(?:\.\d{1,3}){3}):\d+')
DOMAIN_REGEX = re.compile(r'(?:tcp|udp|tls|http):([a-zA-Z0-9.-]+\.[a-zA-Z]{2,12})|->\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,12})', re.IGNORECASE)
REAL_TRAFFIC_REGEX = re.compile(r'(?:uplink[:\s]+(\d+)[^\d]+downlink[:\s]+(\d+))|(?:size[:\s]+(\d+))|(?:uploaded[:\s]+(\d+))', re.IGNORECASE)
DPI_RESET_REGEX = re.compile(r'(connection reset|reset by peer|broken pipe|EOF|closed prematurely|handshake failed|tls.*failed|i/o timeout|context deadline)', re.IGNORECASE)

if os.path.exists('active_edge_host.txt'):
    with open('active_edge_host.txt', 'r') as f:
        tunnel_host = f.read().strip()
else:
    tunnel_host = "127.0.0.1"

if os.path.exists('active_runner_host.txt'):
    with open('active_runner_host.txt', 'r') as f:
        runner_host = f.read().strip()
else:
    runner_host = tunnel_host


def panel_default_record():
    return {
        "uuid": str(uuid.uuid4()),
        "total_limit_bytes": 0,
        "used_bytes": 0,
        "clean_ip": DEFAULT_CLEAN_IP,
        "custom_host": "",
        "status": "OFFLINE",
        "last_active_time": 0,
        "down_speed": 0,
        "up_speed": 0,
        "created_at": int(time.time()),
        "expire_seconds": 31536000,
        "active": True,
        "coefficient": 1.0,
        "real_traffic": False,
        "max_ips": 2,
        "is_proxy_type": False,
        "use_runner_balancer": False,
        "optimization": False,
        "private_tunnel_enabled": False,
        "private_tunnel_host": ""
    }


def normalize_panel_record(name, raw):
    item = panel_default_record()
    if isinstance(raw, dict):
        item.update(raw)
    item["uuid"] = str(item.get("uuid") or uuid.uuid4())
    item["clean_ip"] = item.get("clean_ip") or DEFAULT_CLEAN_IP
    item["custom_host"] = str(item.get("custom_host") or "").strip()
    item["private_tunnel_host"] = str(item.get("private_tunnel_host") or "").strip()
    item["status"] = item.get("status") or "OFFLINE"
    item["created_at"] = int(item.get("created_at") or time.time())
    item["expire_seconds"] = int(item.get("expire_seconds") or 2592000)
    item["total_limit_bytes"] = int(float(item.get("total_limit_bytes") or 0))
    item["used_bytes"] = int(float(item.get("used_bytes") or 0))
    item["down_speed"] = int(float(item.get("down_speed") or 0))
    item["up_speed"] = int(float(item.get("up_speed") or 0))
    item["coefficient"] = float(item.get("coefficient") or 1.0)
    item["max_ips"] = max(1, int(item.get("max_ips") or 2))
    for k in ["active", "real_traffic", "is_proxy_type", "use_runner_balancer", "optimization", "private_tunnel_enabled"]:
        item[k] = bool(item.get(k, False))
    if name.startswith("primeconfigfree_") and "tg_user_id" in raw:
        item["tg_user_id"] = raw.get("tg_user_id")
    return item


def default_panel_database():
    return {"Main_kill_pv2_8086": panel_default_record()}


def sanitize_database(data):
    if not isinstance(data, dict) or not data:
        return default_panel_database()
    fixed = {}
    for name, raw in data.items():
        if not isinstance(name, str) or not name.strip():
            continue
        fixed[name.strip()] = normalize_panel_record(name.strip(), raw or {})
    return fixed or default_panel_database()


def load_json_file(path, default):
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return deepcopy(default)


def write_json_file(path, data):
    tmp_path = f"{path}.tmp"
    with open(tmp_path, 'w') as f:
        json.dump(data, f, indent=4)
    os.replace(tmp_path, path)


def load_system_config():
    defaults = {
        "panel_user": PANEL_USER,
        "panel_pass": PANEL_PASS,
        "default_clean_ip": DEFAULT_CLEAN_IP,
        "traffic_coefficient": TRAFFIC_COEFFICIENT,
        "sub_repo_name": SUB_REPO_NAME,
        "sub_repo_token": SUB_REPO_TOKEN,
        "telegram_bot_token": TELEGRAM_BOT_TOKEN,
        "telegram_admin_id": TELEGRAM_ADMIN_ID,
        "telegram_channel_id": TELEGRAM_CHANNEL_ID,
    }
    data = load_json_file(SYSTEM_CONFIG_PATH, defaults)
    for k, v in data.items():
        if v not in [None, ""]:
            defaults[k] = v
    return defaults


def save_system_config(cfg):
    try:
        write_json_file(SYSTEM_CONFIG_PATH, cfg)
        git_commit_files([SYSTEM_CONFIG_PATH], "⚙️ Update system_config.json [Skip CI]")
    except Exception as e:
        print(f"⚠️ Failed saving system_config: {e}", flush=True)


SYSTEM_CONFIG = load_system_config()
PANEL_USER = SYSTEM_CONFIG["panel_user"]
PANEL_PASS = SYSTEM_CONFIG["panel_pass"]
DEFAULT_CLEAN_IP = SYSTEM_CONFIG["default_clean_ip"]
TRAFFIC_COEFFICIENT = float(SYSTEM_CONFIG["traffic_coefficient"])
SUB_REPO_NAME = SYSTEM_CONFIG["sub_repo_name"]
SUB_REPO_TOKEN = SYSTEM_CONFIG["sub_repo_token"]
TELEGRAM_BOT_TOKEN = SYSTEM_CONFIG["telegram_bot_token"]
TELEGRAM_ADMIN_ID = SYSTEM_CONFIG["telegram_admin_id"]
TELEGRAM_CHANNEL_ID = SYSTEM_CONFIG["telegram_channel_id"]


def load_combined_subs():
    data = load_json_file(COMBINED_SUBS_PATH, {})
    return data if isinstance(data, dict) else {}


def save_combined_subs(data):
    try:
        write_json_file(COMBINED_SUBS_PATH, data)
        git_commit_files([COMBINED_SUBS_PATH], "🔗 Update combined_subs [Skip CI]")
    except Exception as e:
        print(f"⚠️ save_combined_subs failed: {e}", flush=True)


def restore_database_from_xray_backup():
    if not os.path.exists(XRAY_CONFIG_PATH):
        return None
    try:
        with open(XRAY_CONFIG_PATH, 'r') as f:
            xcfg = json.load(f)
        backup_string = xcfg.get("_killpv2_db_backup", "")
        if not backup_string:
            return None
        decoded = base64.b64decode(backup_string.encode('utf-8')).decode('utf-8')
        raw = json.loads(decoded)
        restored = sanitize_database(raw)
        print("♻️ PANEL DB restored from xray embedded backup", flush=True)
        return restored
    except Exception as e:
        print(f"⚠️ restore_database_from_xray_backup failed: {e}", flush=True)
        return None


def load_database():
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, 'r') as f:
                return sanitize_database(json.load(f))
        except Exception:
            pass
    restored = restore_database_from_xray_backup()
    if restored:
        try:
            write_json_file(DB_PATH, restored)
        except Exception:
            pass
        return restored
    return default_panel_database()


PANEL_DATABASE = load_database()


def save_database():
    with DB_LOCK:
        write_json_file(DB_PATH, PANEL_DATABASE)


def load_giveaway_config():
    default = {
        "max_claims": 0, "volume_value": 0.0, "volume_unit": "GB",
        "volume_gb": 0.0, "claimed_count": 0, "claimed_users": [],
        "status": "inactive", "channel_msg_id": None
    }
    data = load_json_file(GIVEAWAY_CONFIG_PATH, default)
    return data if isinstance(data, dict) else deepcopy(default)


def save_giveaway_config(config_data):
    write_json_file(GIVEAWAY_CONFIG_PATH, config_data)


def git_commit_files(files, message):
    try:
        files = [f for f in files if f]
        if not files:
            return
        subprocess.run("git config --local user.email 'action@github.com' || true", shell=True)
        subprocess.run("git config --local user.name 'GitHub Action' || true", shell=True)
        subprocess.run("git add " + " ".join(files) + " || true", shell=True)
        subprocess.run(f"git commit -m {json.dumps(message)} || true", shell=True)
        subprocess.run("git push || true", shell=True)
    except Exception as e:
        print(f"⚠️ git commit failed: {e}", flush=True)


def format_bytes_display(b):
    if b >= 1024**3: return f"{b / (1024**3):.2f} GB"
    if b >= 1024**2: return f"{b / (1024**2):.2f} MB"
    if b >= 1024: return f"{b / 1024:.2f} KB"
    return f"{b} B"


def get_server_resources():
    cpu_pct, ram_pct = 0.0, 0.0
    try:
        if sys.platform.startswith('linux'):
            with open('/proc/meminfo', 'r') as f:
                m = f.read()
            t = re.search(r'MemTotal:\s+(\d+)', m)
            a = re.search(r'MemAvailable:\s+(\d+)', m)
            if t and a:
                total = int(t.group(1))
                avail = int(a.group(1))
                ram_pct = ((total - avail) / total) * 100
            with open('/proc/stat', 'r') as f:
                l1 = f.readline().split()
            time.sleep(0.05)
            with open('/proc/stat', 'r') as f:
                l2 = f.readline().split()
            id1 = int(l1[4]) + int(l1[5])
            tot1 = sum(int(x) for x in l1[1:8])
            id2 = int(l2[4]) + int(l2[5])
            tot2 = sum(int(x) for x in l2[1:8])
            if tot2 - tot1 > 0:
                cpu_pct = (1 - (id2 - id1) / (tot2 - tot1)) * 100
    except Exception:
        pass
    if cpu_pct == 0.0: cpu_pct = secrets.randbelow(12) + 4
    if ram_pct == 0.0: ram_pct = secrets.randbelow(15) + 30
    return round(cpu_pct, 1), round(ram_pct, 1)


def generate_qr_png_bytes(text_data):
    try:
        import qrcode
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
        qr.add_data(text_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"⚠️ QR generation failed: {e}", flush=True)
        return None


def push_channel_event(event_text):
    try:
        CHANNEL_STREAM_STATE["events"].append(f"`{time.strftime('%H:%M:%S')}` — {event_text}")
        if len(CHANNEL_STREAM_STATE["events"]) > 15:
            CHANNEL_STREAM_STATE["events"] = CHANNEL_STREAM_STATE["events"][-15:]
    except Exception:
        pass


def is_xray_core_running():
    if not sys.platform.startswith('linux'):
        return True
    try:
        out = subprocess.check_output("pgrep xray || pidof xray", shell=True)
        return len(out.strip()) > 0
    except Exception:
        return False


def kill_private_tunnel_for_user(username):
    try:
        if username in USER_PRIVATE_TUNNELS:
            try:
                USER_PRIVATE_TUNNELS[username]["process"].kill()
            except Exception:
                pass
            USER_PRIVATE_TUNNELS.pop(username, None)
    except Exception:
        pass


def spawn_private_tunnel_for_user(username):
    try:
        kill_private_tunnel_for_user(username)
        if not CLOUDFLARED_BIN or (not os.path.exists(CLOUDFLARED_BIN) and not shutil.which(CLOUDFLARED_BIN)):
            print(f"⚠️ cloudflared binary not found for {username}", flush=True)
            return None
        log_path = os.path.join(PRIVATE_TUNNEL_LOG_DIR, f"{username}_{int(time.time())}.log")
        cmd = f"{CLOUDFLARED_BIN} tunnel --url http://127.0.0.1:8080 --no-autoupdate"
        log_f = open(log_path, 'w')
        proc = subprocess.Popen(cmd, shell=True, stdout=log_f, stderr=subprocess.STDOUT)
        host = None
        for _ in range(35):
            time.sleep(1)
            try:
                with open(log_path, 'r') as lf:
                    content = lf.read()
                match = re.search(r'https://([a-zA-Z0-9.-]+\.trycloudflare\.com)', content)
                if match:
                    host = match.group(1)
                    break
            except Exception:
                pass
        if host:
            USER_PRIVATE_TUNNELS[username] = {"process": proc, "host": host, "log_file": log_path, "started_at": int(time.time())}
            push_channel_event(f"🆕 تونل اختصاصی ساخته شد برای {username}: {host}")
            return host
        try:
            proc.kill()
        except Exception:
            pass
        return None
    except Exception as e:
        print(f"⚠️ spawn_private_tunnel_for_user failed for {username}: {e}", flush=True)
        return None


def get_user_effective_host(u_name, u_data):
    if u_data.get("private_tunnel_enabled", False):
        priv_host = str(u_data.get("private_tunnel_host", "")).strip()
        if priv_host:
            return priv_host
    if u_data.get("use_runner_balancer", False):
        return runner_host
    return str(u_data.get("custom_host", "")).strip() or runner_host

def bootstrap_private_tunnels_on_startup():
    needs_save = False
    for u_name, u_data in list(PANEL_DATABASE.items()):
        if u_data.get("private_tunnel_enabled", False) and u_data.get("active", True):
            PANEL_DATABASE[u_name]["private_tunnel_host"] = ""
            needs_save = True
    if needs_save:
        save_database()
    for u_name, u_data in list(PANEL_DATABASE.items()):
        if u_data.get("private_tunnel_enabled", False) and u_data.get("active", True):
            print(f"🔄 Bootstrapping private tunnel for {u_name}...", flush=True)
            new_host = spawn_private_tunnel_for_user(u_name)
            PANEL_DATABASE[u_name]["private_tunnel_host"] = new_host or ""
            save_database()


def build_user_subscription_payload(username, v, now=None, include_info=True):
    now = now or int(time.time())
    if not v.get("active", True):
        return "// ACCOUNT EXPIRED OR DISABLED\n"
    if v.get("is_proxy_type", False):
        return f"socks5://{username}:{v.get('uuid','')}@{tunnel_host}:8089#{username}_Socks5_Proxy\n"
    c_ip = v.get("clean_ip", DEFAULT_CLEAN_IP)
    t_host = get_user_effective_host(username, v)
    total_bytes = v.get("total_limit_bytes", 0)
    rem_bytes = max(0, total_bytes - v.get("used_bytes", 0)) if total_bytes > 0 else 0
    passed_seconds = now - v.get("created_at", now)
    total_seconds = v.get("expire_seconds", 2592000)
    rem_seconds = max(0, total_seconds - passed_seconds)
    rem_d = int(rem_seconds // 86400)
    rem_h = int((rem_seconds % 86400) // 3600)
    suffix = "_⚡Opt" if v.get("optimization", False) else "_Clean"
    if v.get("private_tunnel_enabled", False):
        suffix += "_🔒Priv"
    clean_link = f"vless://{v.get('uuid', '')}@{c_ip}:443?path=%2Fkillpv2&security=tls&encryption=none&insecure=0&type=ws&allowInsecure=0&host={t_host}&sni={t_host}#{username}{suffix}"
    regular_link = f"vless://{v.get('uuid', '')}@{t_host}:443?path=%2Fkillpv2&security=tls&encryption=none&insecure=0&type=ws&allowInsecure=0#{username}_Direct"
    if not include_info:
        return f"{clean_link}\n{regular_link}\n"
    info_used = f"vless://{v.get('uuid', '')}@{c_ip}:443?path=%2Fkillpv2&security=tls&encryption=none&insecure=0&type=ws&allowInsecure=0&host={t_host}&sni={t_host}#📊_Used:_{format_bytes_display(v.get('used_bytes', 0))}"
    info_rem = f"vless://{v.get('uuid', '')}@{c_ip}:443?path=%2Fkillpv2&security=tls&encryption=none&insecure=0&type=ws&allowInsecure=0&host={t_host}&sni={t_host}#💾_Left:_{format_bytes_display(rem_bytes) if total_bytes > 0 else 'Unlimited'}"
    info_time = f"vless://{v.get('uuid', '')}@{c_ip}:443?path=%2Fkillpv2&security=tls&encryption=none&insecure=0&type=ws&allowInsecure=0&host={t_host}&sni={t_host}#⏳_Days:_{rem_d}_Hours:_{rem_h}"
    return f"{clean_link}\n{regular_link}\n{info_used}\n{info_rem}\n{info_time}\n"


def push_subs_to_github():
    try:
        now = int(time.time())
        temp_dir = "/tmp/sub_secure_push_8086"
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        for k, v in PANEL_DATABASE.items():
            payload_str = build_user_subscription_payload(k, v, now=now, include_info=True)
            payload = base64.b64encode(payload_str.encode('utf-8')).decode('utf-8')
            with open(os.path.join(temp_dir, k), 'w') as sf:
                sf.write(payload)
        combined_subs = load_combined_subs()
        for combo_name, usernames in combined_subs.items():
            combined_payload_lines = []
            for un in usernames:
                if un in PANEL_DATABASE and PANEL_DATABASE[un].get("active", True):
                    combined_payload_lines.append(build_user_subscription_payload(un, PANEL_DATABASE[un], now=now, include_info=False).strip())
            encoded = base64.b64encode(("\n".join([x for x in combined_payload_lines if x]) + "\n").encode('utf-8')).decode('utf-8')
            with open(os.path.join(temp_dir, f"combo_{combo_name}"), 'w') as sf:
                sf.write(encoded)
        if SUB_REPO_NAME and SUB_REPO_TOKEN and "نام_کاربری" not in SUB_REPO_NAME:
            try:
                git_dir = "/tmp/git_push_8086"
                if os.path.exists(git_dir):
                    shutil.rmtree(git_dir)
                os.makedirs(git_dir, exist_ok=True)
                for item in os.listdir(temp_dir):
                    shutil.copy(os.path.join(temp_dir, item), os.path.join(git_dir, item))
                cwd = os.getcwd()
                os.chdir(git_dir)
                subprocess.run("git init || true", shell=True)
                subprocess.run("git config --local user.email 'action@github.com' || true", shell=True)
                subprocess.run("git config --local user.name 'GitHub Action' || true", shell=True)
                subprocess.run("git checkout -b main || true", shell=True)
                subprocess.run("git add . || true", shell=True)
                subprocess.run("git commit -m '🔗 Update Subscriptions [Skip CI]' || true", shell=True)
                remote_url = f"https://{SUB_REPO_TOKEN}@github.com/{SUB_REPO_NAME}.git"
                subprocess.run(f"git push \"{remote_url}\" main --force || true", shell=True)
                os.chdir(cwd)
                shutil.rmtree(git_dir)
            except Exception as e:
                print(f"⚠️ push_subs_to_github remote push failed: {e}", flush=True)
        shutil.rmtree(temp_dir)
        git_commit_files([DB_PATH, GIVEAWAY_CONFIG_PATH, SYSTEM_CONFIG_PATH, COMBINED_SUBS_PATH], "💾 Sync DB Securely [Skip CI]")
    except Exception as e:
        print(f"⚠️ push_subs_to_github failed: {e}", flush=True)


def check_expiration_and_limits():
    now = int(time.time())
    changed = False
    for u_name, u_data in list(PANEL_DATABASE.items()):
        total_limit = u_data.get("total_limit_bytes", 0)
        if total_limit > 0 and u_data.get("used_bytes", 0) >= total_limit:
            if u_data.get("active", True) or u_data.get("status") != "EXPIRED":
                PANEL_DATABASE[u_name]["active"] = False
                PANEL_DATABASE[u_name]["status"] = "EXPIRED"
                changed = True
            continue
        created_time = u_data.get("created_at", now)
        expire_seconds = u_data.get("expire_seconds", 2592000)
        if now - created_time > expire_seconds:
            if u_data.get("active", True) or u_data.get("status") != "EXPIRED":
                PANEL_DATABASE[u_name]["active"] = False
                PANEL_DATABASE[u_name]["status"] = "EXPIRED"
                changed = True
            continue
        live_ips_count = len(USER_LIVE_IPS.get(u_name, {}))
        max_allowed_ips = int(u_data.get("max_ips", 2))
        if live_ips_count > max_allowed_ips:
            if u_data.get("active", True):
                PANEL_DATABASE[u_name]["active"] = False
                PANEL_DATABASE[u_name]["status"] = "IP_LIMIT_EXCEEDED"
                changed = True
        else:
            if u_data.get("status") == "IP_LIMIT_EXCEEDED" and not u_data.get("active", True):
                PANEL_DATABASE[u_name]["active"] = True
                PANEL_DATABASE[u_name]["status"] = "OFFLINE"
                changed = True
    if changed:
        save_database()
        sync_xray_core()
        push_subs_to_github()


def sync_xray_core():
    vless_clients = [{"id": u_data.get("uuid", ""), "email": u_name, "level": 0} for u_name, u_data in PANEL_DATABASE.items() if u_data.get("active", True) and not u_data.get("is_proxy_type", False)]
    proxy_users = [{"user": u_name, "pass": u_data.get("uuid", "")} for u_name, u_data in PANEL_DATABASE.items() if u_data.get("active", True) and u_data.get("is_proxy_type", False)]
    any_optimized = any(u_data.get("optimization", False) for u_data in PANEL_DATABASE.values() if u_data.get("active", True))
    sockopt_config = {
        "tcpKeepAliveInterval": 20,
        "tcpKeepAliveIdle": 60,
        "tcpNoDelay": True,
        "domainStrategy": "UseIP" if any_optimized else "AsIs"
    }
    if any_optimized:
        sockopt_config.update({"tcpFastOpen": True, "tcpcongestion": "bbr", "tcpMptcp": True, "mark": 0})
    db_backup_string = base64.b64encode(json.dumps(PANEL_DATABASE).encode('utf-8')).decode('utf-8')
    xray_json_config = {
        "_killpv2_db_backup": db_backup_string,
        "log": {"loglevel": "info", "access": XRAY_LOG_PATH, "error": XRAY_LOG_PATH},
        "stats": {},
        "api": {"tag": "api", "listen": XRAY_API_ADDR, "services": ["StatsService"]},
        "policy": {
            "levels": {"0": {"handshake": 4, "connIdle": 600, "uplinkOnly": 5, "downlinkOnly": 10, "bufferSize": 4, "statsUserUplink": True, "statsUserDownlink": True}},
            "system": {"statsInboundUplink": True, "statsInboundDownlink": True, "statsOutboundUplink": True, "statsOutboundDownlink": True}
        },
        "routing": {"rules": [{"inboundTag": ["api"], "outboundTag": "api"}]},
        "inbounds": [
            {"port": 8085, "protocol": "vless", "tag": "killpv2-vless", "settings": {"clients": vless_clients, "decryption": "none"}, "streamSettings": {"network": "ws", "wsSettings": {"path": "/killpv2", "headers": {}}, "sockopt": sockopt_config}, "sniffing": {"enabled": True, "destOverride": ["http", "tls"], "routeOnly": False}},
            {"port": 8089, "protocol": "socks", "tag": "killpv2-socks", "settings": {"auth": "password" if proxy_users else "noauth", "accounts": proxy_users, "udp": True}, "streamSettings": {"sockopt": sockopt_config}, "sniffing": {"enabled": True, "destOverride": ["http", "tls"]}}
        ],
        "outbounds": [{"protocol": "freedom", "tag": "direct_out", "settings": {"domainStrategy": "UseIP" if any_optimized else "AsIs"}, "streamSettings": {"sockopt": sockopt_config}}]
    }
    with open(XRAY_CONFIG_PATH, 'w') as f:
        json.dump(xray_json_config, f, indent=4)
    subprocess.run("sudo fuser -k 8085/tcp || true", shell=True)
    subprocess.run("sudo fuser -k 8089/tcp || true", shell=True)
    subprocess.run("sudo fuser -k 10085/tcp || true", shell=True)
    subprocess.run(f"sudo touch {XRAY_LOG_PATH} && sudo chmod 777 {XRAY_LOG_PATH}", shell=True)
    subprocess.run(f"sudo nohup /usr/local/bin/xray -config {XRAY_CONFIG_PATH} > /dev/null 2>&1 &", shell=True)
    push_channel_event("🔄 هسته Xray ریلود شد")


def query_xray_stats_raw():
    candidates = [
        f"/usr/local/bin/xray api statsquery --server={XRAY_API_ADDR}",
        f"/usr/local/bin/xray api statsquery --server={XRAY_API_ADDR} -pattern 'user>>>'",
        f"xray api statsquery --server={XRAY_API_ADDR}",
        f"xray api statsquery --server={XRAY_API_ADDR} -pattern 'user>>>'",
    ]
    for cmd in candidates:
        try:
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=8)
            output = (res.stdout or "") + "\n" + (res.stderr or "")
            if "user>>>" in output:
                return output
        except Exception:
            pass
    return ""


def parse_stats_query_output(raw_text):
    stats = {}
    if not raw_text:
        return stats
    patterns = [
        re.compile(r'name\s*:\s*"(user>>>[^\"]+>>>traffic>>>(?:uplink|downlink))"[^\n\r]*value\s*:\s*(\d+)', re.IGNORECASE),
        re.compile(r'"name"\s*:\s*"(user>>>[^\"]+>>>traffic>>>(?:uplink|downlink))"\s*,\s*"value"\s*:\s*(\d+)', re.IGNORECASE),
        re.compile(r'(user>>>[^\s]+>>>traffic>>>(?:uplink|downlink))\s*[:=]\s*(\d+)', re.IGNORECASE),
    ]
    for pat in patterns:
        for name, value in pat.findall(raw_text):
            stats[name.strip()] = int(value)
    if not stats:
        current_name = None
        for line in raw_text.splitlines():
            m_name = re.search(r'name\s*:\s*"(user>>>[^\"]+>>>traffic>>>(?:uplink|downlink))"', line, re.IGNORECASE)
            if m_name:
                current_name = m_name.group(1).strip()
                continue
            m_val = re.search(r'value\s*:\s*(\d+)', line, re.IGNORECASE)
            if current_name and m_val:
                stats[current_name] = int(m_val.group(1))
                current_name = None
    return stats


def refresh_user_usage_from_xray_stats(force=False):
    global XRAY_STATS_CACHE, LAST_STATS_SNAPSHOT, LAST_STATS_PULL_TS
    now = time.time()
    if not force and now - LAST_STATS_PULL_TS < 2:
        return bool(XRAY_STATS_CACHE)
    raw_output = query_xray_stats_raw()
    parsed = parse_stats_query_output(raw_output)
    LAST_STATS_PULL_TS = now
    if not parsed:
        return False
    XRAY_STATS_CACHE = parsed
    for username, u_data in PANEL_DATABASE.items():
        if not u_data.get("real_traffic", False):
            continue
        up_name = f"user>>>{username}>>>traffic>>>uplink"
        down_name = f"user>>>{username}>>>traffic>>>downlink"
        uplink = int(parsed.get(up_name, 0))
        downlink = int(parsed.get(down_name, 0))
        total = uplink + downlink
        prev_total = int(LAST_STATS_SNAPSHOT.get(username, 0))
        delta = max(0, total - prev_total)
        LAST_STATS_SNAPSHOT[username] = total
        PANEL_DATABASE[username]["used_bytes"] = total
        PANEL_DATABASE[username]["up_speed"] = int(uplink if delta == 0 else max(0, delta // 2))
        PANEL_DATABASE[username]["down_speed"] = int(downlink if delta == 0 else max(0, delta // 2))
    return True


def periodic_stats_refresher():
    while True:
        try:
            changed = refresh_user_usage_from_xray_stats(force=True)
            if changed:
                save_database()
        except Exception as e:
            print(f"⚠️ periodic_stats_refresher: {e}", flush=True)
        time.sleep(4)

class SanaeiMobileXuiServer(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def is_authenticated(self):
        cookies = self.headers.get('Cookie', '')
        return f"session={SESSION_TOKEN}" in cookies

    def redirect_home(self, suffix="/"):
        self.send_response(303)
        self.send_header('Location', suffix)
        self.end_headers()

    def do_POST(self):
        global PANEL_USER, PANEL_PASS, DEFAULT_CLEAN_IP, TRAFFIC_COEFFICIENT, SUB_REPO_NAME, SUB_REPO_TOKEN
        global TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_ID, TELEGRAM_CHANNEL_ID

        if self.path == "/api/terminal":
            if not self.is_authenticated():
                self.send_response(403); self.end_headers(); return
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            params = parse_qs(post_data)
            cmd = params.get('command', [''])[0].strip()
            output = ""
            if cmd:
                try:
                    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=12)
                    output = res.stdout if res.stdout else res.stderr
                    if not output.strip():
                        output = "✔ دستور با موفقیت اجرا شد (بدون خروجی سیستم)."
                except subprocess.TimeoutExpired:
                    output = "❌ خطا: زمان اجرای دستور به پایان رسید (محدودیت ۱۲ ثانیه)."
                except Exception as e:
                    output = f"💥 خطای سیستمی در اجرا: {str(e)}"
            else:
                output = "⚠️ خط فرمان خالی است داداش!"
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({"output": output}).encode('utf-8'))
            return

        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        params = parse_qs(post_data)
        action = params.get('action', [''])[0]

        if self.path == "/login":
            username = params.get('username', [''])[0].strip()
            password = params.get('password', [''])[0].strip()
            if username == PANEL_USER and password == PANEL_PASS:
                self.send_response(303)
                self.send_header('Set-Cookie', f'session={SESSION_TOKEN}; Path=/; HttpOnly')
                self.send_header('Location', '/')
                self.end_headers()
            else:
                self.redirect_home('/?error=true')
            return

        if not self.is_authenticated():
            self.redirect_home('/')
            return

        if action == 'save_system_settings':
            new_user = params.get('panel_user', [PANEL_USER])[0].strip() or PANEL_USER
            new_pass = params.get('panel_pass', [PANEL_PASS])[0].strip() or PANEL_PASS
            new_clean_ip = params.get('default_clean_ip', [DEFAULT_CLEAN_IP])[0].strip() or DEFAULT_CLEAN_IP
            try:
                new_coef = float(params.get('traffic_coefficient', [str(TRAFFIC_COEFFICIENT)])[0])
            except Exception:
                new_coef = TRAFFIC_COEFFICIENT
            new_repo_name = params.get('sub_repo_name', [SUB_REPO_NAME])[0].strip() or SUB_REPO_NAME
            new_repo_token = params.get('sub_repo_token', [SUB_REPO_TOKEN])[0].strip() or SUB_REPO_TOKEN
            PANEL_USER, PANEL_PASS = new_user, new_pass
            DEFAULT_CLEAN_IP, TRAFFIC_COEFFICIENT = new_clean_ip, new_coef
            SUB_REPO_NAME, SUB_REPO_TOKEN = new_repo_name, new_repo_token
            SYSTEM_CONFIG.update({
                "panel_user": PANEL_USER,
                "panel_pass": PANEL_PASS,
                "default_clean_ip": DEFAULT_CLEAN_IP,
                "traffic_coefficient": TRAFFIC_COEFFICIENT,
                "sub_repo_name": SUB_REPO_NAME,
                "sub_repo_token": SUB_REPO_TOKEN,
            })
            save_system_config(SYSTEM_CONFIG)
            push_subs_to_github()
            push_channel_event("⚙️ تنظیمات عمومی سیستم بروزرسانی شد")
            self.redirect_home('/?saved=settings')
            return

        if action == 'save_telegram_settings':
            new_token = params.get('telegram_bot_token', [TELEGRAM_BOT_TOKEN])[0].strip()
            new_admin = params.get('telegram_admin_id', [TELEGRAM_ADMIN_ID])[0].strip()
            new_channel = params.get('telegram_channel_id', [TELEGRAM_CHANNEL_ID])[0].strip()
            if new_token: TELEGRAM_BOT_TOKEN = new_token
            if new_admin: TELEGRAM_ADMIN_ID = new_admin
            if new_channel: TELEGRAM_CHANNEL_ID = new_channel
            SYSTEM_CONFIG["telegram_bot_token"] = TELEGRAM_BOT_TOKEN
            SYSTEM_CONFIG["telegram_admin_id"] = TELEGRAM_ADMIN_ID
            SYSTEM_CONFIG["telegram_channel_id"] = TELEGRAM_CHANNEL_ID
            save_system_config(SYSTEM_CONFIG)
            push_channel_event("🤖 تنظیمات ربات تلگرام بروزرسانی شد")
            self.redirect_home('/?saved=telegram')
            return

        if action == 'build_combined_sub':
            combo_name = params.get('combo_name', [''])[0].strip() or f"combo_{int(time.time())}"
            combo_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', combo_name)
            selected_users = params.get('selected_users', [])
            if selected_users:
                combined = load_combined_subs()
                combined[combo_name] = selected_users
                save_combined_subs(combined)
                push_subs_to_github()
                push_channel_event(f"🔗 ساب ترکیبی ساخته شد: {combo_name} با {len(selected_users)} کانفیگ")
            self.redirect_home('/?combo_built=1&combo_name=' + combo_name)
            return

        if action == 'delete_combined_sub':
            combo_name = params.get('combo_name', [''])[0].strip()
            combined = load_combined_subs()
            if combo_name in combined:
                del combined[combo_name]
                save_combined_subs(combined)
                push_subs_to_github()
                push_channel_event(f"🗑️ ساب ترکیبی حذف شد: {combo_name}")
            self.redirect_home('/?combo_deleted=1')
            return

        if action == 'toggle_all_runner_balancer':
            any_disabled = any(not v.get("use_runner_balancer", False) for v in PANEL_DATABASE.values())
            target_state = True if any_disabled else False
            for u_name in PANEL_DATABASE:
                PANEL_DATABASE[u_name]["use_runner_balancer"] = target_state
            save_database(); sync_xray_core(); push_subs_to_github()
            push_channel_event(f"⚖️ سوئیچ رانر برای همه: {'فعال' if target_state else 'غیرفعال'}")
            self.redirect_home('/'); return

        if action == 'toggle_all_optimization':
            any_disabled = any(not v.get("optimization", False) for v in PANEL_DATABASE.values())
            target_state = True if any_disabled else False
            for u_name in PANEL_DATABASE:
                PANEL_DATABASE[u_name]["optimization"] = target_state
            save_database(); sync_xray_core(); push_subs_to_github()
            push_channel_event(f"⚡ OPT برای همه: {'فعال' if target_state else 'غیرفعال'}")
            self.redirect_home('/'); return

        if action == 'create':
            username = params.get('username', [''])[0].strip()
            is_unlimited = params.get('unlimited_volume', [''])[0] == 'true'
            volume_val = float(params.get('volume_value', [0])[0] or 0)
            volume_unit = params.get('volume_unit', ['GB'])[0]
            expire_days = int(params.get('expire_days', [0])[0] or 0)
            expire_hours = int(params.get('expire_hours', [0])[0] or 0)
            total_seconds = (expire_days * 86400) + (expire_hours * 3600)
            if total_seconds == 0:
                total_seconds = 2592000
            if username:
                multiplier = 1024 * 1024 * 1024 if volume_unit == 'GB' else 1024 * 1024
                final_bytes = 0 if is_unlimited else int(volume_val * multiplier)
                private_tunnel_enabled = params.get('private_tunnel_enabled', [''])[0] == 'true'
                PANEL_DATABASE[username] = normalize_panel_record(username, {
                    "uuid": str(uuid.uuid4()),
                    "total_limit_bytes": final_bytes,
                    "used_bytes": 0,
                    "clean_ip": params.get('clean_ip', [DEFAULT_CLEAN_IP])[0].strip() or DEFAULT_CLEAN_IP,
                    "custom_host": params.get('custom_host', [''])[0].strip(),
                    "status": "OFFLINE",
                    "last_active_time": 0,
                    "down_speed": 0,
                    "up_speed": 0,
                    "created_at": int(time.time()),
                    "expire_seconds": total_seconds,
                    "active": True,
                    "coefficient": float(params.get('coefficient', [1.0])[0] or 1.0),
                    "real_traffic": params.get('real_traffic', [''])[0] == 'true',
                    "max_ips": int(params.get('max_ips', [2])[0] or 2),
                    "is_proxy_type": params.get('is_proxy_type', [''])[0] == 'true',
                    "use_runner_balancer": params.get('use_runner_balancer', [''])[0] == 'true',
                    "optimization": params.get('optimization', [''])[0] == 'true',
                    "private_tunnel_enabled": private_tunnel_enabled,
                    "private_tunnel_host": ""
                })
                save_database(); sync_xray_core()
                if private_tunnel_enabled:
                    PANEL_DATABASE[username]["private_tunnel_host"] = spawn_private_tunnel_for_user(username) or ""
                    save_database()
                push_subs_to_github(); push_channel_event(f"➕ کلاینت جدید: {username}")

        elif action == 'edit':
            username = params.get('username', [''])[0].strip()
            if username in PANEL_DATABASE:
                is_unlimited = params.get('unlimited_volume', [''])[0] == 'true'
                volume_val = float(params.get('volume_value', [0])[0] or 0)
                used_val = float(params.get('used_value', [0])[0] or 0)
                clean_ip = params.get('clean_ip', [DEFAULT_CLEAN_IP])[0].strip() or DEFAULT_CLEAN_IP
                custom_host = params.get('custom_host', [''])[0].strip()
                coef_val = float(params.get('coefficient', [1.0])[0] or 1.0)
                is_real_traffic = params.get('real_traffic', [''])[0] == 'true'
                max_ips_val = int(params.get('max_ips', [2])[0] or 2)
                use_runner_balancer = params.get('use_runner_balancer', [''])[0] == 'true'
                optimization = params.get('optimization', [''])[0] == 'true'
                private_tunnel_enabled = params.get('private_tunnel_enabled', [''])[0] == 'true'
                final_bytes = 0 if is_unlimited else int(volume_val * 1024 * 1024 * 1024)
                final_used_bytes = int(used_val * 1024 * 1024 * 1024)
                was_private = PANEL_DATABASE[username].get("private_tunnel_enabled", False)
                PANEL_DATABASE[username].update({
                    "total_limit_bytes": final_bytes,
                    "used_bytes": final_used_bytes,
                    "clean_ip": clean_ip,
                    "custom_host": custom_host,
                    "coefficient": coef_val,
                    "real_traffic": is_real_traffic,
                    "max_ips": max_ips_val,
                    "use_runner_balancer": use_runner_balancer,
                    "optimization": optimization,
                    "private_tunnel_enabled": private_tunnel_enabled,
                })
                if PANEL_DATABASE[username].get("status") in ["EXPIRED", "IP_LIMIT_EXCEEDED"]:
                    PANEL_DATABASE[username]["active"] = True
                    PANEL_DATABASE[username]["status"] = "OFFLINE"
                if private_tunnel_enabled and (not was_private or not PANEL_DATABASE[username].get("private_tunnel_host")):
                    PANEL_DATABASE[username]["private_tunnel_host"] = spawn_private_tunnel_for_user(username) or ""
                elif not private_tunnel_enabled and was_private:
                    kill_private_tunnel_for_user(username)
                    PANEL_DATABASE[username]["private_tunnel_host"] = ""
                save_database(); sync_xray_core(); push_subs_to_github(); push_channel_event(f"✏️ کلاینت ویرایش شد: {username}")

        elif action == 'delete':
            username = params.get('username', [''])[0].strip()
            if username in PANEL_DATABASE:
                kill_private_tunnel_for_user(username)
                del PANEL_DATABASE[username]
                USER_LIVE_IPS.pop(username, None)
                USER_TARGET_SITES.pop(username, None)
                LAST_STATS_SNAPSHOT.pop(username, None)
                save_database(); sync_xray_core(); push_subs_to_github(); push_channel_event(f"🗑️ کلاینت حذف شد: {username}")

        elif action == 'toggle':
            username = params.get('username', [''])[0].strip()
            if username in PANEL_DATABASE:
                PANEL_DATABASE[username]["active"] = not PANEL_DATABASE[username].get("active", True)
                if not PANEL_DATABASE[username]["active"]:
                    PANEL_DATABASE[username]["status"] = "OFFLINE"
                save_database(); sync_xray_core(); push_subs_to_github()
                push_channel_event(f"⚙️ {username} → {'فعال' if PANEL_DATABASE[username]['active'] else 'غیرفعال'}")

        self.redirect_home('/')

    def do_GET(self):
        url_path = self.path.strip("/")
        if "?" in url_path:
            url_path = url_path.split("?")[0]

        if url_path == "api/test_runner":
            if not self.is_authenticated():
                self.send_response(403); self.end_headers(); return
            global RUNNER_LIVE_LOGS, runner_host
            RUNNER_LIVE_LOGS.append(f"⏱️ شروع تلاش اتصال: {time.strftime('%H:%M:%S')}")
            success = False
            try:
                if os.path.exists('active_runner_host.txt'):
                    with open('active_runner_host.txt', 'r') as f:
                        host = f.read().strip()
                    RUNNER_LIVE_LOGS.append(f"🔍 رانر هاست از فایل: {host}")
                else:
                    RUNNER_LIVE_LOGS.append("⚠️ فایل active_runner_host.txt یافت نشد.")
                    host = tunnel_host
                    with open('active_runner_host.txt', 'w') as f:
                        f.write(host)
                RUNNER_LIVE_LOGS.append("🌐 ارسال درخواست آزمایشی...")
                res_code = subprocess.run(f"curl -s -o /dev/null -w '%{{http_code}}' -k --connect-timeout 4 https://{host}/killpv2", shell=True, capture_output=True, text=True)
                code = res_code.stdout.strip()
                if code in ["200", "301", "302", "404", "403", "400"]:
                    RUNNER_LIVE_LOGS.append(f"🟢 تانل رانر زنده! کد: {code}")
                    runner_host = host
                    success = True
                else:
                    RUNNER_LIVE_LOGS.append(f"❌ رانر پاسخ مناسب نداد. کد: {code if code else 'Timeout'}")
            except Exception as e:
                RUNNER_LIVE_LOGS.append(f"💥 خطای سیستمی: {str(e)}")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({"success": success, "logs": RUNNER_LIVE_LOGS[-20:]}).encode('utf-8'))
            return

        if url_path == "api/stats":
            if not self.is_authenticated():
                self.send_response(403); self.end_headers(); return
            refresh_user_usage_from_xray_stats(force=False)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            response_data = []
            total_sys_bytes = sum(v.get("used_bytes", 0) for v in PANEL_DATABASE.values())
            now = int(time.time())
            runner_agg_ds = 0; runner_agg_us = 0; total_online = 0
            for k, v in PANEL_DATABASE.items():
                is_online = (len(USER_LIVE_IPS.get(k, {})) > 0 or v.get("status") == "ONLINE") and v.get("active", True)
                if is_online:
                    total_online += 1
                    if v.get("use_runner_balancer", False):
                        runner_agg_ds += v.get("down_speed", 0); runner_agg_us += v.get("up_speed", 0)
                total = v.get("total_limit_bytes", 0); used = v.get("used_bytes", 0); rem = max(0, total - used) if total > 0 else 0
                pct = min(100, (used / total * 100)) if total > 0 else 0
                passed_seconds = now - v.get("created_at", now)
                total_seconds = v.get("expire_seconds", 2592000)
                rem_seconds = max(0, total_seconds - passed_seconds)
                rem_d = int(rem_seconds // 86400); rem_h = int((rem_seconds % 86400) // 3600)
                vless_config_str = build_user_subscription_payload(k, v, now=now, include_info=False).splitlines()[0] if build_user_subscription_payload(k, v, now=now, include_info=False).splitlines() else ""
                live_ips_count = len(USER_LIVE_IPS.get(k, {})); status_label = "🔴 آفلاین"
                if v.get("status") == "IP_LIMIT_EXCEEDED": status_label = f"🚨 سقف IP ({live_ips_count}/{v.get('max_ips', 2)})"
                elif live_ips_count > 0 and v.get("active", True): status_label = f"🟢 {live_ips_count} متصل"
                elif v.get("status") == "ONLINE" and v.get("active", True): status_label = "🟢 متصل"
                elif v.get("status") == "OFFLINE": status_label = "🔴 آفلاین"
                if not v.get("active", True) and v.get("status") != "IP_LIMIT_EXCEEDED": status_label = "⏳ تمام شده" if v.get("status") == "EXPIRED" else "⚫ غیرفعال"
                ds = v.get("down_speed", 0) / 1024; us = v.get("up_speed", 0) / 1024
                ds_str = f"{ds/1024:.1f} MB/s" if ds >= 1024 else f"{ds:.1f} KB/s"
                us_str = f"{us/1024:.1f} MB/s" if us >= 1024 else f"{us:.1f} KB/s"
                response_data.append({"username": k, "status": status_label, "used": format_bytes_display(used), "total": format_bytes_display(total) if total > 0 else "نامحدود", "remaining": format_bytes_display(rem) if total > 0 else "نامحدود", "rem_days": f"{rem_d} روز و {rem_h} ساعت", "progress": pct, "down_speed": ds_str, "up_speed": us_str, "down_speed_raw": v.get("down_speed", 0), "up_speed_raw": v.get("up_speed", 0), "config_raw": vless_config_str, "destinations": USER_TARGET_SITES.get(k, [])[-12:], "total_raw": total, "used_raw": used, "clean_ip": v.get("clean_ip", DEFAULT_CLEAN_IP), "custom_host": v.get("custom_host", ""), "coefficient": v.get("coefficient", 1.0), "real_traffic": v.get("real_traffic", False), "max_ips": v.get("max_ips", 2), "is_proxy_type": v.get("is_proxy_type", False), "use_runner_balancer": v.get("use_runner_balancer", False), "optimization": v.get("optimization", False), "private_tunnel_enabled": v.get("private_tunnel_enabled", False), "private_tunnel_host": v.get("private_tunnel_host", "")})
            srv_cpu, srv_ram = get_server_resources()
            r_ds = runner_agg_ds / 1024; r_us = runner_agg_us / 1024
            runner_speed_display = (f"⬇️{r_ds/1024:.1f}M" if r_ds >= 1024 else f"⬇️{r_ds:.0f}K") + " | " + (f"⬆️{r_us/1024:.1f}M" if r_us >= 1024 else f"⬆️{r_us:.0f}K")
            final_payload = {"total_online": total_online, "users": response_data, "sys_logs": SYSTEM_LIVE_LOGS[-30:], "runner_logs": RUNNER_LIVE_LOGS[-20:], "dpi_logs": DPI_BLOCK_LOGS[-40:], "server_cpu": srv_cpu, "server_ram": srv_ram, "total_sys_used": format_bytes_display(total_sys_bytes), "xray_live": is_xray_core_running(), "is_using_runner": os.path.exists('active_runner_host.txt'), "runner_host": runner_host, "runner_speed": runner_speed_display, "combined_subs": load_combined_subs()}
            self.wfile.write(json.dumps(final_payload).encode('utf-8')); return

        if url_path.startswith("combo/"):
            combo_name = url_path.replace("combo/", "", 1)
            combined = load_combined_subs()
            if combo_name in combined:
                lines = []
                for un in combined[combo_name]:
                    if un in PANEL_DATABASE and PANEL_DATABASE[un].get("active", True):
                        lines.append(build_user_subscription_payload(un, PANEL_DATABASE[un], include_info=False).strip())
                encoded_payload = base64.b64encode(("\n".join(lines) + "\n").encode('utf-8')).decode('utf-8')
                self.send_response(200); self.send_header('Content-Type', 'text/plain; charset=utf-8'); self.end_headers(); self.wfile.write(encoded_payload.encode('utf-8')); return
            self.send_response(404); self.end_headers(); return

        if url_path.startswith("sub/"):
            target_user = url_path.replace("sub/", "", 1)
            if target_user in PANEL_DATABASE and PANEL_DATABASE[target_user].get("active", True):
                payload = build_user_subscription_payload(target_user, PANEL_DATABASE[target_user], include_info=False)
                encoded_payload = base64.b64encode(payload.encode('utf-8')).decode('utf-8')
                self.send_response(200); self.send_header('Content-Type', 'text/plain; charset=utf-8'); self.end_headers(); self.wfile.write(encoded_payload.encode('utf-8')); return
            self.send_response(404); self.end_headers(); return

        if not self.is_authenticated():
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            err_msg = '❌ رمز عبور اشتباه است داداش!' if "error=true" in self.path else ''
            with open(os.path.join(os.path.dirname(__file__), 'login_template.html'), 'r', encoding='utf-8') as f:
                html = f.read().replace('__ERROR_MESSAGE__', err_msg)
            self.wfile.write(html.encode('utf-8'))
            return

        if url_path == "" or url_path == "index.html":
            clients_html_str = ""
            tg_html_str = ""
            for user_name, user_data in PANEL_DATABASE.items():
                is_active = user_data.get("active", True)
                u_status = user_data.get("status", "OFFLINE")
                total = user_data.get("total_limit_bytes", 0)
                used = user_data.get("used_bytes", 0)
                rem = max(0, total - used) if total > 0 else 0
                live_ips_count = len(USER_LIVE_IPS.get(user_name, {}))
                badge_class = "bg-slate-800/80 text-slate-400 border border-slate-700/50"
                status_text = "🔴 آفلاین"
                if user_data.get("is_proxy_type", False):
                    status_text = "🔌 SOCKS5"
                    badge_class = "bg-amber-500/15 text-amber-300 border border-amber-500/30"
                if u_status == "IP_LIMIT_EXCEEDED":
                    badge_class = "bg-orange-500/15 text-orange-300 border border-orange-500/30"
                    status_text = "🚨 سقف IP"
                elif not is_active:
                    badge_class = "bg-rose-500/15 text-rose-400 border border-rose-500/30"
                    status_text = "⏳ پایان" if u_status == "EXPIRED" else "⚫ غیرفعال"
                elif (u_status == "ONLINE" or live_ips_count > 0) and not user_data.get("is_proxy_type", False):
                    badge_class = "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                    status_text = f"🟢 {live_ips_count} متصل" if live_ips_count > 0 else "🟢 متصل"
                priv_badge = ""
                if user_data.get("private_tunnel_enabled", False):
                    priv_host_short = user_data.get("private_tunnel_host", "")[:28]
                    priv_badge = f'<div class="col-span-2 text-[9px] text-violet-400 truncate mt-0.5">🔒 {priv_host_short or "در حال ساخت..."}</div>'
                row_markup = f"""
<div id=\"u_{user_name}\" onclick=\"filterUserSniper('{user_name}')\" class=\"card-user relative bg-gradient-to-br from-slate-900 to-slate-950 p-3 rounded-2xl border border-slate-800/60 hover:border-indigo-500/40 transition-all cursor-pointer overflow-hidden\">
<div class=\"relative\"><div class=\"flex justify-between items-center mb-2\"><span class=\"font-bold text-sm text-white user-name-label\">{user_name}</span><span class=\"badge text-[10px] px-2 py-0.5 rounded-lg font-bold {badge_class}\">{status_text}</span></div>
<div class=\"grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-slate-500 border-t border-slate-800/60 pt-2 mb-2.5\"><div>مصرف: <span class=\"text-slate-200 font-semibold u-used\">{format_bytes_display(used)}</span></div><div>باقی: <span class=\"text-slate-200 font-semibold u-rem\">{'نامحدود' if total == 0 else format_bytes_display(rem)}</span></div><div class=\"col-span-2 text-[10px]\">زمان: <span class=\"text-indigo-300 font-medium u-days\">...</span></div><div class=\"text-emerald-400/80 text-[10px]\">⬇ <span class=\"u-dspeed\">0 KB/s</span></div><div class=\"text-sky-400/80 text-[10px]\">⬆ <span class=\"u-uspeed\">0 KB/s</span></div>{priv_badge}</div>
<div class=\"w-full bg-slate-950 rounded-full h-1 mb-3 overflow-hidden\"><div class=\"p-bar-fill bg-gradient-to-r from-indigo-500 to-purple-500 h-1 rounded-full transition-all duration-700\" style=\"width:0%\"></div></div>
<div class=\"flex flex-wrap gap-1\" onclick=\"event.stopPropagation();\"><button onclick=\"copyFixedSubscription('{user_name}')\" class=\"text-[10px] bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 px-2 py-1 rounded-xl font-bold flex-1 hover:bg-indigo-500/20 transition-colors cursor-pointer\">🔗 ساب</button><button onclick=\"copyConfig('{user_name}')\" class=\"text-[10px] bg-purple-500/10 text-purple-400 border border-purple-500/20 px-2 py-1 rounded-xl font-bold flex-1 hover:bg-purple-500/20 transition-colors cursor-pointer\">📋 کانفیگ</button><button onclick=\"openQrModal('{user_name}')\" class=\"text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-1 rounded-xl font-bold hover:bg-emerald-500/20 transition-colors cursor-pointer\">📱 QR</button><button onclick=\"openEditModalFromRow('{user_name}')\" class=\"text-[10px] bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 px-1.5 py-1 rounded-xl font-bold hover:bg-cyan-500/20 transition-colors cursor-pointer\">✏️</button><form action=\"/\" method=\"POST\" class=\"inline\"><input type=\"hidden\" name=\"action\" value=\"toggle\"><input type=\"hidden\" name=\"username\" value=\"{user_name}\"><button type=\"submit\" class=\"text-[10px] bg-amber-500/10 text-amber-400 border border-amber-500/20 px-1.5 py-1 rounded-xl font-bold hover:bg-amber-500/20 transition-colors cursor-pointer\">⚙️</button></form><form action=\"/\" method=\"POST\" class=\"inline\"><input type=\"hidden\" name=\"action\" value=\"delete\"><input type=\"hidden\" name=\"username\" value=\"{user_name}\"><button type=\"submit\" onclick=\"return confirm('حذف {user_name}؟')\" class=\"text-[10px] bg-rose-500/10 text-rose-400 border border-rose-500/20 px-1.5 py-1 rounded-xl font-bold hover:bg-rose-500/20 transition-colors cursor-pointer\">🗑️</button></form></div></div></div>"""
                if user_name.startswith("primeconfigfree_"):
                    tg_html_str += row_markup
                else:
                    clients_html_str += row_markup
            combo_user_list_html = ""
            for user_name, user_data in PANEL_DATABASE.items():
                if user_data.get("active", True) and not user_data.get("is_proxy_type", False):
                    combo_user_list_html += f'<label class="flex items-center justify-between bg-slate-950/70 border border-slate-800/60 rounded-xl px-3 py-2.5 cursor-pointer hover:border-purple-500/40 transition-colors"><span class="text-xs text-slate-200 font-semibold">{user_name}</span><input type="checkbox" name="selected_users" value="{user_name}" class="w-4 h-4 accent-purple-500"></label>'
            combined_subs = load_combined_subs()
            existing_combos_html = ""
            for combo_name, users_list in combined_subs.items():
                users_str = ", ".join(users_list[:5])
                if len(users_list) > 5:
                    users_str += f"... (+{len(users_list)-5})"
                existing_combos_html += f'<div class="bg-slate-950/60 border border-slate-800/60 rounded-2xl p-3 space-y-2"><div class="flex justify-between items-center"><span class="text-xs font-bold text-purple-400">🔗 {combo_name}</span><form action="/" method="POST" class="inline"><input type="hidden" name="action" value="delete_combined_sub"><input type="hidden" name="combo_name" value="{combo_name}"><button type="submit" onclick="return confirm(\'حذف ساب ترکیبی {combo_name}؟\')" class="text-[10px] bg-rose-500/10 text-rose-400 border border-rose-500/20 px-2 py-1 rounded-lg font-bold cursor-pointer">🗑️</button></form></div><div class="text-[10px] text-slate-500">شامل: {users_str}</div><button onclick="copyComboSubLink(\'{combo_name}\')" class="w-full bg-purple-500/10 text-purple-400 border border-purple-500/20 px-2 py-1.5 rounded-xl font-bold text-[10px] cursor-pointer hover:bg-purple-500/20 transition-colors">📋 کپی لینک ساب ترکیبی</button></div>'
            saved_msg = ""
            if "saved=settings" in self.path:
                saved_msg = '<div class="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-bold p-3 rounded-2xl text-center animate-pulse">✅ تنظیمات عمومی ذخیره شد!</div>'
            elif "saved=telegram" in self.path:
                saved_msg = '<div class="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-bold p-3 rounded-2xl text-center animate-pulse">✅ تنظیمات ربات ذخیره شد!</div>'
            elif "combo_built=1" in self.path:
                saved_msg = '<div class="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-bold p-3 rounded-2xl text-center animate-pulse">✅ ساب ترکیبی ساخته شد!</div>'
            elif "combo_deleted=1" in self.path:
                saved_msg = '<div class="bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs font-bold p-3 rounded-2xl text-center">🗑️ ساب ترکیبی حذف شد.</div>'
            masked_token = (TELEGRAM_BOT_TOKEN[:8] + "..." + TELEGRAM_BOT_TOKEN[-6:]) if TELEGRAM_BOT_TOKEN and len(TELEGRAM_BOT_TOKEN) > 16 and "YOUR_" not in TELEGRAM_BOT_TOKEN else TELEGRAM_BOT_TOKEN
            masked_repo_token = (SUB_REPO_TOKEN[:6] + "..." + SUB_REPO_TOKEN[-4:]) if SUB_REPO_TOKEN and len(SUB_REPO_TOKEN) > 12 else ("(تنظیم نشده)" if not SUB_REPO_TOKEN else SUB_REPO_TOKEN)
            with open(os.path.join(os.path.dirname(__file__), 'panel_template.html'), 'r', encoding='utf-8') as f:
                html_content = f.read()
            replacements = {
                '__SAVED_MSG__': saved_msg,
                '__CLIENTS_HTML__': clients_html_str,
                '__TG_HTML__': tg_html_str,
                '__COMBO_USER_LIST_HTML__': combo_user_list_html or '<div class="text-xs text-slate-600 italic text-center py-4">هیچ کانفیگ فعالی وجود ندارد.</div>',
                '__EXISTING_COMBOS_HTML__': existing_combos_html or '<div class="text-xs text-slate-600 italic text-center py-4 bg-slate-900/40 rounded-2xl">هنوز ساب ترکیبی ساخته نشده.</div>',
                '__PANEL_USER__': PANEL_USER,
                '__PANEL_PASS__': PANEL_PASS,
                '__DEFAULT_CLEAN_IP__': DEFAULT_CLEAN_IP,
                '__TRAFFIC_COEFFICIENT__': str(TRAFFIC_COEFFICIENT),
                '__SUB_REPO_NAME__': SUB_REPO_NAME,
                '__MASKED_REPO_TOKEN__': masked_repo_token,
                '__TELEGRAM_BOT_TOKEN__': TELEGRAM_BOT_TOKEN,
                '__TELEGRAM_ADMIN_ID__': str(TELEGRAM_ADMIN_ID),
                '__TELEGRAM_CHANNEL_ID__': str(TELEGRAM_CHANNEL_ID),
                '__MASKED_TOKEN__': str(masked_token),
            }
            for key, val in replacements.items():
                html_content = html_content.replace(key, str(val))
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html_content.encode('utf-8'))
            return

        self.send_response(404)
        self.end_headers()

def xray_live_log_sniffer():
    global SYSTEM_LIVE_LOGS, USER_LIVE_IPS, DPI_BLOCK_LOGS
    while not os.path.exists(XRAY_LOG_PATH):
        time.sleep(1)
    log_file = open(XRAY_LOG_PATH, "r")
    log_file.seek(0, os.SEEK_END)
    while True:
        line = log_file.readline()
        if not line:
            time.sleep(0.05)
            continue
        clean_line = line.strip()
        if not clean_line:
            continue
        SYSTEM_LIVE_LOGS.append(clean_line)
        if len(SYSTEM_LIVE_LOGS) > 100:
            SYSTEM_LIVE_LOGS.pop(0)
        if DPI_RESET_REGEX.search(clean_line):
            dpi_entry = f"[{time.strftime('%H:%M:%S')}] {clean_line}"
            DPI_BLOCK_LOGS.append(dpi_entry)
            if len(DPI_BLOCK_LOGS) > 200:
                DPI_BLOCK_LOGS.pop(0)
        for user_name in list(PANEL_DATABASE.keys()):
            user_uuid = PANEL_DATABASE[user_name].get("uuid", "")
            if user_name not in clean_line and (not user_uuid or user_uuid not in clean_line):
                continue
            if not (PANEL_DATABASE[user_name].get("active", True) or PANEL_DATABASE[user_name].get("status") == "IP_LIMIT_EXCEEDED"):
                continue
            PANEL_DATABASE[user_name]["last_active_time"] = time.time()
            if PANEL_DATABASE[user_name].get("status") != "IP_LIMIT_EXCEEDED":
                PANEL_DATABASE[user_name]["status"] = "ONLINE"
            ip_match = IP_REGEX.search(clean_line)
            if ip_match:
                client_ip = ip_match.group(1)
                USER_LIVE_IPS.setdefault(user_name, {})[client_ip] = time.time()
            domain_match = DOMAIN_REGEX.search(clean_line)
            if domain_match:
                dst = domain_match.group(1) or domain_match.group(2)
                if dst and not dst.startswith("127.") and "cloudflare" not in dst:
                    USER_TARGET_SITES.setdefault(user_name, [])
                    if dst not in USER_TARGET_SITES[user_name]:
                        USER_TARGET_SITES[user_name].append(dst)
            if not PANEL_DATABASE[user_name].get("active", True):
                continue
            if PANEL_DATABASE[user_name].get("real_traffic", False):
                continue
            u_coef = PANEL_DATABASE[user_name].get("coefficient", TRAFFIC_COEFFICIENT)
            traffic_match = REAL_TRAFFIC_REGEX.search(clean_line)
            if traffic_match:
                uplink = int(traffic_match.group(1) or 0)
                downlink = int(traffic_match.group(2) or 0)
                size_val = int(traffic_match.group(3) or 0)
                uploaded_val = int(traffic_match.group(4) or 0)
                base_bytes = (uplink + downlink) or size_val or uploaded_val
                if base_bytes > 0:
                    PANEL_DATABASE[user_name]["used_bytes"] += int(base_bytes * u_coef)
                    PANEL_DATABASE[user_name]["down_speed"] = int(base_bytes * 1.5 * u_coef)
                    PANEL_DATABASE[user_name]["up_speed"] = int(base_bytes * 0.2 * u_coef)
                else:
                    fake_bytes = secrets.randbelow(3000) + 500
                    PANEL_DATABASE[user_name]["used_bytes"] += int(fake_bytes * u_coef)
                    PANEL_DATABASE[user_name]["down_speed"] = secrets.randbelow(800000) + 200000
                    PANEL_DATABASE[user_name]["up_speed"] = secrets.randbelow(20000) + 30000
            else:
                fake_bytes = secrets.randbelow(3000) + 500
                PANEL_DATABASE[user_name]["used_bytes"] += int(fake_bytes * u_coef)
                PANEL_DATABASE[user_name]["down_speed"] = secrets.randbelow(800000) + 200000
                PANEL_DATABASE[user_name]["up_speed"] = secrets.randbelow(20000) + 30000
            save_database()


def speed_and_ip_cleaner():
    while True:
        time.sleep(4)
        now = time.time()
        for u_name in list(USER_LIVE_IPS.keys()):
            for ip_addr, last_seen in list(USER_LIVE_IPS[u_name].items()):
                if now - last_seen > 10:
                    del USER_LIVE_IPS[u_name][ip_addr]
        p_changed = False
        for u_name, u_data in list(PANEL_DATABASE.items()):
            if now - u_data.get("last_active_time", 0) > 8:
                if u_data.get("down_speed", 0) > 0 or u_data.get("up_speed", 0) > 0:
                    PANEL_DATABASE[u_name]["down_speed"] = 0
                    PANEL_DATABASE[u_name]["up_speed"] = 0
                    p_changed = True
            if now - u_data.get("last_active_time", 0) > 130:
                if u_data.get("status") not in ["OFFLINE", "EXPIRED", "IP_LIMIT_EXCEEDED"]:
                    PANEL_DATABASE[u_name]["status"] = "OFFLINE"
                    p_changed = True
        if p_changed:
            save_database()


def periodic_state_flusher():
    while True:
        time.sleep(60)
        try:
            save_database()
            push_subs_to_github()
        except Exception as e:
            print(f"⚠️ periodic_state_flusher: {e}", flush=True)


def channel_live_stream_worker(bot_instance):
    try:
        init_text = f"📡 *استریم زنده مدیریت سیستم kill_pv2*\n\n🟢 سرویس راه‌اندازی شد\n⏱️ شروع: `{time.strftime('%Y-%m-%d %H:%M:%S')}`\n\n_در حال انتظار رویدادها..._"
        try:
            sent = bot_instance.send_message(TELEGRAM_CHANNEL_ID, init_text, parse_mode="Markdown")
            CHANNEL_STREAM_STATE["msg_id"] = sent.message_id
            try: bot_instance.pin_chat_message(TELEGRAM_CHANNEL_ID, sent.message_id, disable_notification=True)
            except Exception: pass
            push_channel_event("📡 استریم زنده در کانال ایجاد شد")
        except Exception as e:
            print(f"⚠️ Channel stream init failed: {e}", flush=True)
            return
        last_rendered_events = []
        while True:
            time.sleep(8)
            try:
                if not CHANNEL_STREAM_STATE.get("msg_id"):
                    continue
                current_events = list(CHANNEL_STREAM_STATE["events"][-12:])
                if current_events == last_rendered_events:
                    continue
                cpu_v, ram_v = get_server_resources()
                total_users = len(PANEL_DATABASE)
                active_users = sum(1 for v in PANEL_DATABASE.values() if v.get("active", True))
                online_users = sum(1 for k, v in PANEL_DATABASE.items() if len(USER_LIVE_IPS.get(k, {})) > 0 and v.get("active", True))
                events_block = "\n".join(current_events) if current_events else "_رویدادی ثبت نشده_"
                stream_text = f"📡 *استریم زنده kill_pv2*\n\n⏱️ `{time.strftime('%H:%M:%S')}`\n👥 `{online_users}` آنلاین | `{active_users}` فعال | `{total_users}` کل\n🖥️ CPU `{cpu_v}%` | RAM `{ram_v}%`\n🛡️ Xray: {'🟢 فعال' if is_xray_core_running() else '🔴 متوقف'}\n\n📋 *رویدادهای اخیر:*\n{events_block}"
                try:
                    bot_instance.edit_message_text(stream_text, TELEGRAM_CHANNEL_ID, CHANNEL_STREAM_STATE["msg_id"], parse_mode="Markdown")
                    last_rendered_events = current_events
                except Exception:
                    pass
            except Exception:
                pass
    except Exception as e:
        print(f"⚠️ Channel stream error: {e}", flush=True)


def init_telegram_bot_service():
    if not TELEGRAM_BOT_TOKEN or "YOUR_BOT_TOKEN" in TELEGRAM_BOT_TOKEN:
        print("⚠️ Telegram Bot Token missing. Bot bypassed.", flush=True)
        return
    try:
        import telebot
        from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
        bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
        threading.Thread(target=channel_live_stream_worker, args=(bot,), daemon=True).start()

        @bot.message_handler(commands=['start'])
        def handle_start_command(message):
            chat_id_str = str(message.chat.id)
            if chat_id_str == str(TELEGRAM_ADMIN_ID) and 'claim' not in message.text:
                g_config = load_giveaway_config()
                total_free_cnt = sum(1 for k in PANEL_DATABASE.keys() if k.startswith("primeconfigfree_"))
                admin_text = f"👑 *سلام داداش!*\n\n📊 *وضعیت چالش:*\n👥 `{g_config['claimed_count']}` از `{g_config['max_claims']}`\n💾 `{g_config.get('volume_value', 0)} {g_config.get('volume_unit', 'GB')}`\n⚙️ `{g_config.get('status', 'inactive')}`\n\n🛠️ کانفیگ‌های رایگان: `{total_free_cnt}`"
                markup = ReplyKeyboardMarkup(resize_keyboard=True)
                markup.row(KeyboardButton("🚀 ایجاد چالش جدید"), KeyboardButton("📊 آمار چالش"))
                markup.row(KeyboardButton("🛠️ مدیریت وضعیت چالش"))
                markup.row(KeyboardButton("🔒 ساخت تونل اختصاصی برای کاربر"))
                bot.send_message(message.chat.id, admin_text, parse_mode="Markdown", reply_markup=markup)
                return
            if 'claim' in message.text:
                g_config = load_giveaway_config()
                if g_config.get("status", "inactive") != "active" or g_config["max_claims"] == 0:
                    bot.send_message(message.chat.id, "❌ چالشی فعال نیست!"); return
                if chat_id_str in g_config["claimed_users"]:
                    bot.send_message(message.chat.id, "⚠️ قبلاً دریافت کردی!"); return
                if g_config["claimed_count"] >= g_config["max_claims"]:
                    bot.send_message(message.chat.id, "🏁 ظرفیت تموم شد."); return
                i = 1
                while f"primeconfigfree_{i}" in PANEL_DATABASE: i += 1
                new_username = f"primeconfigfree_{i}"
                final_bytes = int(g_config["volume_gb"] * 1024 * 1024 * 1024)
                PANEL_DATABASE[new_username] = normalize_panel_record(new_username, {"uuid": str(uuid.uuid4()), "total_limit_bytes": final_bytes, "used_bytes": 0, "clean_ip": DEFAULT_CLEAN_IP, "custom_host": "", "status": "OFFLINE", "last_active_time": 0, "down_speed": 0, "up_speed": 0, "created_at": int(time.time()), "expire_seconds": 2592000, "active": True, "coefficient": 1.0, "real_traffic": False, "max_ips": 2, "is_proxy_type": False, "use_runner_balancer": False, "optimization": True, "private_tunnel_enabled": False, "private_tunnel_host": "", "tg_user_id": chat_id_str})
                g_config["claimed_count"] += 1; g_config["claimed_users"].append(chat_id_str)
                if g_config["claimed_count"] >= g_config["max_claims"]:
                    g_config["status"] = "finished"
                save_database(); save_giveaway_config(g_config); sync_xray_core(); push_subs_to_github(); push_channel_event(f"🎁 کلیم شد: {new_username}")
                t_host = runner_host
                vless_link = f"vless://{PANEL_DATABASE[new_username]['uuid']}@{DEFAULT_CLEAN_IP}:443?path=%2Fkillpv2&security=tls&encryption=none&insecure=0&type=ws&allowInsecure=0&host={t_host}&sni={t_host}#{new_username}_⚡Opt"
                sub_link = f"https://raw.githubusercontent.com/{SUB_REPO_NAME}/main/{new_username}"
                vol_display = f"{g_config.get('volume_value', 0)} {g_config.get('volume_unit', 'GB')}"
                success_text = f"🎉 *تبریک!*\n\n👤 `{new_username}`\n💾 `{vol_display}`\n\n📋 *کانفیگ:*\n`{vless_link}`\n\n🔗 *ساب:*\n`{sub_link}`"
                user_kb = ReplyKeyboardMarkup(resize_keyboard=True)
                user_kb.row(KeyboardButton("📊 مشاهده کانفیگ‌ها و حجم من"), KeyboardButton("ℹ️ راهنما"))
                bot.send_message(message.chat.id, success_text, parse_mode="Markdown", reply_markup=user_kb)
                try:
                    qr_buf = generate_qr_png_bytes(vless_link)
                    if qr_buf: bot.send_photo(message.chat.id, qr_buf, caption=f"📱 QR `{new_username}`", parse_mode="Markdown")
                except Exception: pass
            else:
                user_kb = ReplyKeyboardMarkup(resize_keyboard=True)
                user_kb.row(KeyboardButton("📊 مشاهده کانفیگ‌ها و حجم من"), KeyboardButton("ℹ️ راهنما"))
                bot.send_message(message.chat.id, "👋 سلام! برای دریافت کانفیگ از لینک چالش استفاده کن.", reply_markup=user_kb)

        @bot.message_handler(func=lambda msg: msg.text == "📊 مشاهده کانفیگ‌ها و حجم من")
        def handle_user_stats(message):
            chat_id_str = str(message.chat.id)
            configs_found = [(k, v) for k, v in PANEL_DATABASE.items() if str(v.get("tg_user_id", "")) == chat_id_str]
            if not configs_found:
                bot.send_message(message.chat.id, "⚠️ کانفیگی برای شما یافت نشد."); return
            now = int(time.time())
            resp = "📊 *کانفیگ‌های شما:*\n\n"
            for u_name, u_data in configs_found:
                total_l = u_data.get("total_limit_bytes", 0); used = u_data.get("used_bytes", 0); rem = max(0, total_l - used) if total_l > 0 else 0
                passed_s = now - u_data.get("created_at", now); rem_s = max(0, u_data.get("expire_seconds", 2592000) - passed_s); rem_d = int(rem_s // 86400); rem_h = int((rem_s % 86400) // 3600)
                t_host = get_user_effective_host(u_name, u_data); suffix = "_⚡Opt" if u_data.get("optimization", False) else ""
                vless_link = f"vless://{u_data.get('uuid', '')}@{DEFAULT_CLEAN_IP}:443?path=%2Fkillpv2&security=tls&encryption=none&insecure=0&type=ws&allowInsecure=0&host={t_host}&sni={t_host}#{u_name}{suffix}"
                sub_link = f"https://raw.githubusercontent.com/{SUB_REPO_NAME}/main/{u_name}"
                resp += f"{'🟢' if u_data.get('active', True) else '🔴'} `{u_name}`\n💾 کل: `{format_bytes_display(total_l) if total_l > 0 else 'نامحدود'}`\n📊 مصرف: `{format_bytes_display(used)}`\n💾 باقی: `{format_bytes_display(rem) if total_l > 0 else 'نامحدود'}`\n⏳ `{rem_d} روز و {rem_h} ساعت`\n\n📋 `{vless_link}`\n🔗 `{sub_link}`\n─────────────\n"
            bot.send_message(message.chat.id, resp, parse_mode="Markdown")

        @bot.message_handler(func=lambda msg: msg.text == "ℹ️ راهنما")
        def handle_help(message):
            bot.send_message(message.chat.id, "ℹ️ *راهنما:*\n▪️ اندروید: `v2rayNG` / `NekoBox`\n▪️ آیفون: `v2box` / `FoXray`\n▪️ ویندوز: `v2rayN`", parse_mode="Markdown")

        @bot.message_handler(func=lambda msg: str(msg.chat.id) == str(TELEGRAM_ADMIN_ID) and msg.text == "🔒 ساخت تونل اختصاصی برای کاربر")
        def handle_admin_build_tunnel(message):
            active_users = [k for k, v in PANEL_DATABASE.items() if v.get("active", True) and not v.get("is_proxy_type", False)]
            if not active_users:
                bot.send_message(message.chat.id, "❌ هیچ کاربر فعالی وجود ندارد."); return
            markup = InlineKeyboardMarkup(row_width=2)
            buttons = [InlineKeyboardButton(u, callback_data=f"build_tunnel_{u}") for u in active_users[:20]]
            markup.add(*buttons)
            bot.send_message(message.chat.id, "👤 *برای کدام کاربر تونل اختصاصی بسازم؟*\n\n⚠️ اگه کاربر قبلاً تونل اختصاصی داشته، تونل جدید جایگزین میشه.", parse_mode="Markdown", reply_markup=markup)

        @bot.callback_query_handler(func=lambda call: True)
        def handle_callbacks(call):
            if str(call.message.chat.id) != str(TELEGRAM_ADMIN_ID):
                return
            if call.data.startswith("build_tunnel_"):
                target_user = call.data.replace("build_tunnel_", "", 1)
                if target_user not in PANEL_DATABASE:
                    bot.answer_callback_query(call.id, "❌ کاربر یافت نشد!"); return
                bot.answer_callback_query(call.id, "🔄 در حال ساخت تونل...")
                bot.edit_message_text(f"🔄 در حال ساخت تونل اختصاصی برای `{target_user}`...\nلطفاً صبر کن (~۳۵ ثانیه)", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
                def do_build():
                    try:
                        PANEL_DATABASE[target_user]["private_tunnel_enabled"] = True
                        new_host = spawn_private_tunnel_for_user(target_user)
                        if new_host:
                            PANEL_DATABASE[target_user]["private_tunnel_host"] = new_host
                            save_database(); sync_xray_core(); push_subs_to_github(); push_channel_event(f"🔒 تونل اختصاصی از ربات ساخته شد: {target_user} → {new_host}")
                            result_msg = f"✅ *تونل اختصاصی ساخته شد!*\n\n👤 کاربر: `{target_user}`\n🌐 هاست: `{new_host}`\n\nساب لینک آپدیت شد و از این تونل استفاده میکنه."
                        else:
                            result_msg = f"❌ ساخت تونل برای `{target_user}` ناموفق بود.\nممکنه cloudflared در دسترس نباشه."
                        bot.edit_message_text(result_msg, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
                    except Exception as e:
                        try: bot.edit_message_text(f"❌ خطا: {str(e)}", call.message.chat.id, call.message.message_id)
                        except Exception: pass
                threading.Thread(target=do_build, daemon=True).start(); return
        threading.Thread(target=lambda: bot.infinity_polling(timeout=20, long_polling_timeout=10), daemon=True).start()
        print("🤖 TELEGRAM BOT RUNNING", flush=True)
    except Exception as e:
        print(f"⚠️ Telegram Bot failed: {str(e)}", flush=True)


def main():
    print("\n==============================================================", flush=True)
    print("🛡️ KILL_PV2 PANEL INITIALIZED ON PORT 8086", flush=True)
    print(f"🔗 GATEWAY HOST: https://{tunnel_host}", flush=True)
    print(f"🚀 RUNNER HOST:  https://{runner_host}", flush=True)
    print("==============================================================\n", flush=True)

    sync_xray_core()
    bootstrap_private_tunnels_on_startup()
    push_subs_to_github()
    init_telegram_bot_service()

    threading.Thread(target=lambda: ThreadingHTTPServer(('127.0.0.1', 8086), SanaeiMobileXuiServer).serve_forever(), daemon=True).start()
    threading.Thread(target=xray_live_log_sniffer, daemon=True).start()
    threading.Thread(target=speed_and_ip_cleaner, daemon=True).start()
    threading.Thread(target=periodic_stats_refresher, daemon=True).start()
    threading.Thread(target=periodic_state_flusher, daemon=True).start()

    push_channel_event("🚀 سرویس kill_pv2 بالا اومد")

    total_duration = 19800
    elapsed = 0
    last_github_update_time = time.time()
    while elapsed < total_duration:
        time.sleep(5)
        elapsed += 5
        check_expiration_and_limits()
        if time.time() - last_github_update_time >= 60:
            push_subs_to_github()
            last_github_update_time = time.time()


if __name__ == "__main__":
    main()
