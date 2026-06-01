# VPN Bot — Telegram бот для продажи VPN подписок

Полноценный бот на **Python + aiogram 3** с поддержкой 3x-ui, тремя платёжными системами и реферальной программой.

---

## Структура проекта

```
vpn_bot/
├── main.py                    # Точка входа
├── requirements.txt
├── .env.example               # Шаблон переменных окружения
├── vpn_bot.service            # systemd unit
├── config/
│   └── settings.py            # Все настройки из .env
├── database/
│   ├── models.py              # SQLAlchemy модели
│   ├── engine.py              # Подключение к БД
│   └── repositories.py        # Слой доступа к данным
├── services/
│   ├── xui.py                 # Клиент 3x-ui + поддержка узлов
│   ├── subscription.py        # Бизнес-логика подписок
│   ├── payments.py            # ЮКасса, CryptoBot, Stars
│   └── scheduler.py           # Уведомления об истечении
└── bot/
    ├── handlers/              # Хендлеры команд и кнопок
    │   ├── start.py
    │   ├── subscription.py
    │   ├── payments.py
    │   ├── referral.py
    │   └── admin.py
    ├── keyboards/             # Все клавиатуры
    └── middlewares/           # DB, User, Ban middleware
```

---

## Быстрый старт

### 1. Клонировать и настроить окружение

```bash
# Создать пользователя
sudo useradd -m -s /bin/bash vpnbot
sudo su - vpnbot

# Скопировать файлы в /opt/vpn_bot
sudo mkdir -p /opt/vpn_bot
sudo cp -r . /opt/vpn_bot/
sudo chown -R vpnbot:vpnbot /opt/vpn_bot

cd /opt/vpn_bot

# Виртуальное окружение
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Настроить PostgreSQL

```bash
sudo apt install postgresql -y
sudo -u postgres psql

# Внутри psql:
CREATE USER vpnbot WITH PASSWORD 'strong_password_here';
CREATE DATABASE vpn_bot OWNER vpnbot;
GRANT ALL PRIVILEGES ON DATABASE vpn_bot TO vpnbot;
\q
```

### 3. Заполнить .env

```bash
cp .env.example .env
nano .env
```

Обязательно заполнить:
- `BOT_TOKEN` — получить у @BotFather
- `ADMIN_IDS` — ваш Telegram ID (узнать у @userinfobot)
- `DATABASE_URL` — строка подключения к PostgreSQL
- `XUI_HOST`, `XUI_USERNAME`, `XUI_PASSWORD`, `XUI_INBOUND_ID` — данные вашей 3x-ui

### 4. Настроить 3x-ui

Убедитесь что в 3x-ui:
1. Включён API: **Настройки → Настройки панели → включить API**
2. У вашего inbound (VLESS+WS+TLS) есть правильный ID
3. В `.env` указан `XUI_INBOUND_ID` — это число из колонки "ID" в списке inbound

### 5. Настроить платёжные системы

**ЮКасса:**
- Зарегистрируйтесь на yookassa.ru
- Создайте магазин, получите `shopId` и `secretKey`
- Настройте webhook на: `https://your-domain.com/webhook/yookassa` (опционально, бот и без этого работает через polling)

**CryptoBot:**
- Напишите @CryptoBot → "Create App"
- Скопируйте API токен
- Для теста используйте `CRYPTOBOT_NETWORK=testnet`

**Telegram Stars:**
- Не требует дополнительной настройки — работает сразу через Telegram

### 6. Запустить

```bash
# Тест запуска
source venv/bin/activate
python main.py

# systemd (автозапуск)
sudo cp vpn_bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vpn_bot
sudo systemctl start vpn_bot

# Проверить статус
sudo systemctl status vpn_bot
sudo journalctl -u vpn_bot -f
```

---

## Добавление нового узла (сервера)

Когда купите второй VPS — просто раскомментируйте блок в `services/xui.py`:

```python
# В функции setup_xui():
node2 = XUIClient(
    host="https://node2.example.com:2053",
    username="admin",
    password="password",
    inbound_id=1,
    node_name="node2_de",
)
xui_manager.add_node("node2_de", node2)
```

Клиенты автоматически будут создаваться на всех узлах с одним и тем же UUID — пользователь получит единый конфиг, работающий на всех серверах.

---

## Функционал бота

### Пользователь
- `/start` — приветствие, регистрация (с поддержкой реф. ссылки)
- **🔑 Мой доступ** — статус подписки, ссылка подключения, инструкции (iOS/Android/Desktop)
- **💳 Купить подписку** — выбор тарифа и способа оплаты
- **👥 Реферальная программа** — реф. ссылка, статистика, баланс
- **ℹ️ Помощь** — контакт поддержки

### Тарифы
| Тариф | Срок | Цена |
|---|---|---|
| Пробный | 7 дней | Бесплатно |
| Месяц | 30 дней | 299₽ |
| Месяц (реф. скидка) | 30 дней | 149₽ |

### Реферальная программа
- Реферер получает **50₽** на баланс когда его реферал активирует пробный период
- Реферал получает **скидку 50%** на первую покупку

### Уведомления
- За **3 дня** до истечения подписки
- В **день истечения** — доступ отключается, приходит уведомление

### Администратор (`/admin`)
- 📊 Статистика (пользователи, подписки, доход)
- ✅ Ручная выдача подписки по Telegram ID
- ❌ Ручной отзыв подписки
- 📢 Рассылка (текст или фото+текст) всем пользователям
- 🔍 Поиск информации о пользователе

---

## Безопасность

- Все секреты — только в `.env`, не в коде
- Middleware проверяет бан перед каждым запросом
- Платежи верифицируются через API провайдера перед активацией
- Реферальный бонус начисляется только при активации пробного периода (не при регистрации)
- Пробный период — строго один раз

---

## Частые вопросы

**Как узнать XUI_INBOUND_ID?**
Зайдите в 3x-ui → Inbounds → в таблице первый столбец "ID" у вашего inbound.

**Ссылка vless:// не формируется?**
Проверьте что в 3x-ui у inbound правильно настроен `streamSettings` с WS и TLS. Бот читает их через API.

**CryptoBot не создаёт счёт?**
Убедитесь что токен от mainnet, а не testnet (или наоборот — в зависимости от `CRYPTOBOT_NETWORK`).
