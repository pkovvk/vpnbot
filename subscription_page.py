"""
Сервер страницы подписки.
- VPN клиенты (по User-Agent) → проксирует конфиг с 3x-ui
- Браузеры → красивый wizard с инструкцией по подключению
"""

import asyncio
import re
from aiohttp import web, ClientSession
from config import settings

# User-Agent паттерны VPN клиентов
VPN_CLIENT_PATTERNS = [
    r"clash", r"hiddify", r"v2ray", r"xray", r"sing-box",
    r"shadowrocket", r"quantumult", r"surge", r"stash",
    r"nekoray", r"matsuri", r"neko", r"happ",
]

def is_vpn_client(user_agent: str) -> bool:
    ua = user_agent.lower()
    return any(re.search(p, ua) for p in VPN_CLIENT_PATTERNS)


async def proxy_subscription(sub_id: str, request: web.Request) -> web.Response:
    """Проксируем запрос к subscription серверу 3x-ui."""
    sub_url = f"https://leftvpn.online:2096/leftsubb/{sub_id}"
    headers = dict(request.headers)
    headers.pop("Host", None)

    try:
        async with ClientSession() as session:
            async with session.get(sub_url, headers=headers, ssl=False) as resp:
                content = await resp.read()
                response_headers = {}
                for key in ["Content-Type", "Profile-Title", "Profile-Update-Interval",
                            "Announce", "Profile-Web-Page-Url", "Routing-Enable"]:
                    if key in resp.headers:
                        response_headers[key] = resp.headers[key]
                return web.Response(body=content, status=resp.status, headers=response_headers)
    except Exception as e:
        return web.Response(text="Error", status=500)


def render_page(sub_id: str) -> str:
    sub_url = f"https://leftvpn.online:2096/leftsubb/{sub_id}"
    happ_ios = "https://apps.apple.com/app/happ-proxy-utility/id6504287215"
    happ_android = "https://play.google.com/store/apps/details?id=com.happ.vpn"
    happ_windows = "https://github.com/happvpn/happ/releases/latest"
    happ_mac = "https://apps.apple.com/app/happ-proxy-utility/id6504287215"

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Left VPN — Подключение</title>
<link href="https://fonts.googleapis.com/css2?family=Onest:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --white: #ffffff;
    --off-white: #f7f7f5;
    --light: #efefed;
    --border: #e2e2de;
    --text: #1a1a18;
    --muted: #8a8a82;
    --accent: #2563eb;
    --accent-light: #eff4ff;
    --accent-hover: #1d4ed8;
    --success: #16a34a;
    --success-light: #f0fdf4;
    --radius: 16px;
    --radius-sm: 10px;
  }}

  html, body {{
    height: 100%;
    font-family: 'Onest', sans-serif;
    background: var(--off-white);
    color: var(--text);
    -webkit-font-smoothing: antialiased;
  }}

  .page {{
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 24px 16px 48px;
  }}

  /* Header */
  .header {{
    width: 100%;
    max-width: 480px;
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 32px;
  }}
  .logo {{
    width: 36px; height: 36px;
    background: var(--text);
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
  }}
  .logo svg {{ width: 20px; height: 20px; fill: white; }}
  .brand {{ font-size: 17px; font-weight: 600; letter-spacing: -0.3px; }}

  /* Card */
  .card {{
    width: 100%;
    max-width: 480px;
    background: var(--white);
    border: 1px solid var(--border);
    border-radius: 24px;
    overflow: hidden;
    box-shadow: 0 2px 16px rgba(0,0,0,0.06);
  }}

  /* Progress */
  .progress-bar {{
    height: 3px;
    background: var(--light);
    position: relative;
    overflow: hidden;
  }}
  .progress-fill {{
    height: 100%;
    background: var(--accent);
    border-radius: 2px;
    transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  }}

  /* Steps */
  .step {{ display: none; padding: 32px 28px; }}
  .step.active {{ display: block; animation: fadeIn 0.3s ease; }}

  @keyframes fadeIn {{
    from {{ opacity: 0; transform: translateY(8px); }}
    to {{ opacity: 1; transform: translateY(0); }}
  }}

  .step-label {{
    font-size: 12px;
    font-weight: 500;
    color: var(--muted);
    letter-spacing: 0.5px;
    text-transform: uppercase;
    margin-bottom: 8px;
  }}

  h2 {{
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -0.5px;
    line-height: 1.3;
    margin-bottom: 8px;
  }}

  .subtitle {{
    font-size: 15px;
    color: var(--muted);
    line-height: 1.5;
    margin-bottom: 24px;
  }}

  /* Device grid */
  .device-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-bottom: 8px;
  }}

  .device-btn {{
    background: var(--off-white);
    border: 1.5px solid var(--border);
    border-radius: var(--radius);
    padding: 18px 14px;
    cursor: pointer;
    transition: all 0.18s ease;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    font-family: inherit;
  }}
  .device-btn:hover {{
    border-color: var(--accent);
    background: var(--accent-light);
    transform: translateY(-1px);
  }}
  .device-btn .icon {{ font-size: 28px; line-height: 1; }}
  .device-btn .label {{ font-size: 14px; font-weight: 600; color: var(--text); }}
  .device-btn .sublabel {{ font-size: 12px; color: var(--muted); }}

  /* Download block */
  .download-block {{
    background: var(--off-white);
    border: 1.5px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 20px;
    text-decoration: none;
    color: inherit;
    transition: all 0.18s ease;
  }}
  .download-block:hover {{
    border-color: var(--accent);
    background: var(--accent-light);
    transform: translateY(-1px);
  }}
  .app-icon {{
    width: 56px; height: 56px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 26px;
    flex-shrink: 0;
  }}
  .app-info {{ flex: 1; }}
  .app-name {{ font-size: 16px; font-weight: 600; margin-bottom: 2px; }}
  .app-desc {{ font-size: 13px; color: var(--muted); }}
  .download-arrow {{ font-size: 18px; color: var(--muted); }}

  /* Steps list */
  .steps-list {{
    display: flex;
    flex-direction: column;
    gap: 14px;
    margin-bottom: 24px;
  }}
  .step-item {{
    display: flex;
    gap: 14px;
    align-items: flex-start;
  }}
  .step-num {{
    width: 28px; height: 28px;
    background: var(--accent);
    color: white;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 13px;
    font-weight: 700;
    flex-shrink: 0;
    margin-top: 1px;
  }}
  .step-text {{ font-size: 15px; line-height: 1.5; padding-top: 3px; }}
  .step-text b {{ font-weight: 600; }}

  /* Connect button */
  .connect-btn {{
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    width: 100%;
    padding: 16px;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: var(--radius);
    font-family: inherit;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
    text-decoration: none;
    transition: all 0.18s ease;
    margin-bottom: 12px;
  }}
  .connect-btn:hover {{ background: var(--accent-hover); transform: translateY(-1px); }}
  .connect-btn:active {{ transform: translateY(0); }}

  /* Success */
  .success-icon {{
    width: 64px; height: 64px;
    background: var(--success-light);
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 30px;
    margin: 0 auto 20px;
  }}
  .success-card {{
    background: var(--success-light);
    border: 1.5px solid #bbf7d0;
    border-radius: var(--radius);
    padding: 16px;
    margin-bottom: 20px;
    font-size: 14px;
    color: #15803d;
    line-height: 1.5;
    text-align: center;
  }}

  /* Navigation */
  .nav {{
    display: flex;
    gap: 10px;
    padding: 20px 28px 28px;
    border-top: 1px solid var(--border);
  }}

  .btn-back {{
    flex: 0 0 auto;
    padding: 14px 20px;
    background: transparent;
    border: 1.5px solid var(--border);
    border-radius: var(--radius-sm);
    font-family: inherit;
    font-size: 15px;
    font-weight: 500;
    color: var(--muted);
    cursor: pointer;
    transition: all 0.18s ease;
  }}
  .btn-back:hover {{ border-color: var(--text); color: var(--text); }}

  .btn-next {{
    flex: 1;
    padding: 14px;
    background: var(--text);
    border: none;
    border-radius: var(--radius-sm);
    font-family: inherit;
    font-size: 15px;
    font-weight: 600;
    color: white;
    cursor: pointer;
    transition: all 0.18s ease;
  }}
  .btn-next:hover {{ background: #333330; transform: translateY(-1px); }}
  .btn-next:disabled {{ background: var(--light); color: var(--muted); cursor: not-allowed; transform: none; }}

  .hint {{
    font-size: 13px;
    color: var(--muted);
    text-align: center;
    line-height: 1.5;
  }}
  .hint a {{ color: var(--accent); text-decoration: none; }}
</style>
</head>
<body>
<div class="page">
  <div class="header">
    <div class="logo">
      <svg viewBox="0 0 24 24"><path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4z"/></svg>
    </div>
    <span class="brand">Left VPN</span>
  </div>

  <div class="card">
    <div class="progress-bar">
      <div class="progress-fill" id="progress" style="width: 25%"></div>
    </div>

    <!-- Шаг 1: Выбор устройства -->
    <div class="step active" id="step-1">
      <div class="step-label">Шаг 1 из 4</div>
      <h2>Какое у вас устройство?</h2>
      <p class="subtitle">Выберите, чтобы получить инструкцию именно для вашего устройства</p>
      <div class="device-grid">
        <button class="device-btn" onclick="selectDevice('ios')">
          <span class="icon">📱</span>
          <span class="label">iPhone</span>
          <span class="sublabel">iOS</span>
        </button>
        <button class="device-btn" onclick="selectDevice('android')">
          <span class="icon">🤖</span>
          <span class="label">Android</span>
          <span class="sublabel">Смартфон</span>
        </button>
        <button class="device-btn" onclick="selectDevice('windows')">
          <span class="icon">💻</span>
          <span class="label">Windows</span>
          <span class="sublabel">ПК / Ноутбук</span>
        </button>
        <button class="device-btn" onclick="selectDevice('mac')">
          <span class="icon">🍎</span>
          <span class="label">Mac</span>
          <span class="sublabel">macOS</span>
        </button>
      </div>
    </div>

    <!-- Шаг 2: Скачать приложение -->
    <div class="step" id="step-2">
      <div class="step-label">Шаг 2 из 4</div>
      <h2>Скачайте приложение</h2>
      <p class="subtitle">Happ — простое и надёжное приложение для подключения к VPN</p>
      <a class="download-block" id="download-link" href="#" target="_blank">
        <div class="app-icon">🛡️</div>
        <div class="app-info">
          <div class="app-name">Happ</div>
          <div class="app-desc" id="download-desc">Нажмите для скачивания</div>
        </div>
        <span class="download-arrow">↗</span>
      </a>
      <p class="hint">Установите приложение и вернитесь сюда для следующего шага</p>
    </div>

    <!-- Шаг 3: Добавить подписку -->
    <div class="step" id="step-3">
      <div class="step-label">Шаг 3 из 4</div>
      <h2>Добавьте подписку</h2>
      <p class="subtitle">Нажмите кнопку ниже — приложение откроется и подписка добавится автоматически</p>
      <div class="steps-list">
        <div class="step-item">
          <div class="step-num">1</div>
          <div class="step-text">Убедитесь что приложение <b>Happ установлено</b></div>
        </div>
        <div class="step-item">
          <div class="step-num">2</div>
          <div class="step-text">Нажмите кнопку <b>«Добавить подписку»</b> ниже</div>
        </div>
        <div class="step-item">
          <div class="step-num">3</div>
          <div class="step-text">Подтвердите добавление в приложении</div>
        </div>
      </div>
      <a class="connect-btn" id="add-sub-btn" href="#">
        ✚ Добавить подписку в Happ
      </a>
      <p class="hint">Не открывается автоматически? <a href="#" id="manual-link" onclick="showManual()">Добавить вручную</a></p>
    </div>

    <!-- Шаг 4: Готово -->
    <div class="step" id="step-4">
      <div class="success-icon">✅</div>
      <h2 style="text-align:center">Всё готово!</h2>
      <p class="subtitle" style="text-align:center">VPN успешно настроен. Теперь вы можете подключиться.</p>
      <div class="success-card">
        🎉 Подписка добавлена в Happ.<br>
        Откройте приложение и нажмите кнопку подключения.
      </div>
      <div class="steps-list">
        <div class="step-item">
          <div class="step-num">1</div>
          <div class="step-text">Откройте приложение <b>Happ</b></div>
        </div>
        <div class="step-item">
          <div class="step-num">2</div>
          <div class="step-text">Нажмите большую кнопку <b>подключения</b></div>
        </div>
        <div class="step-item">
          <div class="step-num">3</div>
          <div class="step-text">Готово — вы защищены 🛡️</div>
        </div>
      </div>
    </div>

    <div class="nav" id="nav">
      <button class="btn-back" id="btn-back" onclick="prevStep()" style="display:none">← Назад</button>
      <button class="btn-next" id="btn-next" onclick="nextStep()" disabled>Далее →</button>
    </div>
  </div>
</div>

<script>
const SUB_URL = "{sub_url}";
const HAPP_LINKS = {{
  ios: "{happ_ios}",
  android: "{happ_android}",
  windows: "{happ_windows}",
  mac: "{happ_mac}",
}};
const STORE_LABELS = {{
  ios: "Скачать в App Store",
  android: "Скачать в Google Play",
  windows: "Скачать для Windows",
  mac: "Скачать для Mac",
}};

let currentStep = 1;
let selectedDevice = null;
const totalSteps = 4;

function updateProgress() {{
  document.getElementById('progress').style.width = (currentStep / totalSteps * 100) + '%';
}}

function showStep(n) {{
  document.querySelectorAll('.step').forEach(s => s.classList.remove('active'));
  document.getElementById('step-' + n).classList.add('active');
  document.getElementById('btn-back').style.display = n > 1 ? 'block' : 'none';
  document.getElementById('btn-next').style.display = n === totalSteps ? 'none' : 'block';
  document.getElementById('nav').style.display = n === 1 ? 'none' : 'flex';
  if (n === totalSteps) document.getElementById('nav').style.display = 'none';
  updateProgress();
}}

function selectDevice(device) {{
  selectedDevice = device;
  document.querySelectorAll('.device-btn').forEach(b => {{
    b.style.borderColor = '';
    b.style.background = '';
  }});
  event.currentTarget.style.borderColor = 'var(--accent)';
  event.currentTarget.style.background = 'var(--accent-light)';

  // Настраиваем шаг 2
  document.getElementById('download-link').href = HAPP_LINKS[device];
  document.getElementById('download-desc').textContent = STORE_LABELS[device];

  // Настраиваем deep link для шага 3
  document.getElementById('add-sub-btn').href = 'happ://add-sub?url=' + encodeURIComponent(SUB_URL);

  currentStep = 2;
  showStep(2);
  document.getElementById('btn-next').disabled = false;
}}

function nextStep() {{
  if (currentStep < totalSteps) {{
    currentStep++;
    showStep(currentStep);
  }}
}}

function prevStep() {{
  if (currentStep > 1) {{
    currentStep--;
    showStep(currentStep);
  }}
}}

function showManual() {{
  const url = SUB_URL;
  navigator.clipboard.writeText(url).then(() => {{
    alert('Ссылка скопирована!\\n\\nВ приложении Happ:\\nНастройки → Добавить подписку → Вставить ссылку');
  }}).catch(() => {{
    prompt('Скопируйте эту ссылку и вставьте в Happ:', url);
  }});
  return false;
}}

// Инициализация
showStep(1);
</script>
</body>
</html>"""


async def handle_subscription(request: web.Request) -> web.Response:
    sub_id = request.match_info.get("sub_id", "")
    user_agent = request.headers.get("User-Agent", "")

    if is_vpn_client(user_agent):
        return await proxy_subscription(sub_id, request)

    html = render_page(sub_id)
    return web.Response(text=html, content_type="text/html", charset="utf-8")


async def main():
    app = web.Application()
    app.router.add_get("/sub/{sub_id}", handle_subscription)
    app.router.add_get("/sub/{sub_id}/", handle_subscription)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    print("Subscription page running on http://0.0.0.0:8080")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())