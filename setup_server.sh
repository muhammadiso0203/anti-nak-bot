#!/usr/bin/env bash
# ==========================================================
#   NAKRUTKA BLOCKER BOT — TO'LIQ AVTOMATIK SERVER O'RNATUVCHI
#   Ubuntu / Debian (MobaXterm orqali ishga tushirish uchun)
# ==========================================================

set -e

# Ranglar
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}==========================================================${NC}"
echo -e "${GREEN}    NAKRUTKA BLOCKER BOT — SERVERGA O'RNATISH (VPS)${NC}"
echo -e "${CYAN}==========================================================${NC}"
echo ""

# Root tekshiruvi
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[XATO] Iltimos, ushbu skriptni root foydalanuvchisi sifatida ishga tushiring (sudo bash ...)${NC}"
  exit 1
fi

APP_DIR="/root/anti-nak-bot"
REPO_URL="https://github.com/muhammadiso0203/anti-nak-bot.git"
DOMAIN="anti-nak.akbarovich.uz"
PORT="8080"

# 1. Tizim paketlarini yangilash va kerakli dasturlarni o'rnatish
echo -e "${YELLOW}[1/6] Kerakli dasturlar o'rnatilmoqda (Python, Nginx, Git, Certbot)...${NC}"
apt update -y
apt install -y python3 python3-pip python3-venv git nginx certbot python3-certbot-nginx curl ufw

# 2. Loyiha kodini yuklab olish
echo -e "${YELLOW}[2/6] Botingiz kodi yuklab olinmoqda (${APP_DIR})...${NC}"
if [ -d "$APP_DIR" ]; then
    echo -e "${BLUE}Eski papka topildi, yangilanmoqda...${NC}"
    cd "$APP_DIR"
    git fetch --all
    git reset --hard origin/main
else
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# 3. Python virtual muhitini (venv) yaratish va kutubxonalarni o'rnatish
echo -e "${YELLOW}[3/6] Python virtual muhiti yaratilmoqda va kutubxonalar o'rnatilmoqda...${NC}"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. .env faylini sozlash (agar mavjud bo'lmasa yoki to'ldirilishi kerak bo'lsa)
echo -e "${YELLOW}[4/6] .env sozlamalar fayli yaratilmoqda...${NC}"
cat << 'EOF' > "$APP_DIR/.env"
# ==========================================================
#  NAKRUTKA BLOCKER BOT — SERVER SOZLAMALARI
# ==========================================================
BOT_TOKEN=9019460359:AAEcMmWFyXENoarUqTkLAeGUePWDrSCilUk
ADMIN_IDS=8655133854
LOG_CHAT_ID=

MODE=ban
SCORE_THRESHOLD=50
NEW_ACCOUNT_ID=8200000000
VERY_NEW_ACCOUNT_ID=8600000000
OLD_ACCOUNT_ID=1500000000

BURST_WINDOW=60
BURST_LIMIT=8
AUTO_ROTATE_LINK=0
PROTECT_PREMIUM=0

DB_PATH=nakrutka.db

WEBAPP_URL=https://anti-nak.akbarovich.uz
WEBAPP_PORT=8080

API_ID=24412350
API_HASH=ffee904f060c14e69a6e0d56606fd0ca
SESSION_NAME=scanner
EOF

# 5. Nginx konfiguratsiyasi
echo -e "${YELLOW}[5/6] Nginx veb-serveri sozlanmoqda (${DOMAIN})...${NC}"

NGINX_CONF="/etc/nginx/sites-available/$DOMAIN"
cat << EOF > "$NGINX_CONF"
server {
    listen 80;
    server_name $DOMAIN bot.akbarovich.uz app.akbarovich.uz akbarovich.uz;

    client_max_body_size 64M;

    location / {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

ln -sf "$NGINX_CONF" "/etc/nginx/sites-enabled/"
rm -f /etc/nginx/sites-enabled/default

# Firewall (ufw) portlarini ochish
if ufw status | grep -q "Status: active"; then
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw allow 22/tcp
fi

nginx -t
systemctl restart nginx

# SSL sertifikati (Certbot / HTTPS)
echo -e "${CYAN}HTTPS (SSL) sertifikati o'rnatilmoqda...${NC}"
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect || {
    echo -e "${YELLOW}[OGOHLANTIRISH] SSL sertifikati hozir o'rnatilmadi.${NC}"
    echo -e "${YELLOW}Sababi: '${DOMAIN}' domenining A yozuvi hali ushbu server IP siga yo'naltirilmagan bo'lishi mumkin.${NC}"
    echo -e "${YELLOW}Domen DNS sozlamalarini server IP siga yo'naltirgach, quyidagi buyruqni bering:${NC}"
    echo -e "${GREEN}certbot --nginx -d $DOMAIN --redirect${NC}"
}

# 6. Systemd xizmatini yaratish (Bot 24/7 o'chmasdan fonda ishlashi uchun)
echo -e "${YELLOW}[6/6] Bot uchun 24/7 avtomatik tizim xizmati (systemd) yaratilmoqda...${NC}"

SERVICE_FILE="/etc/systemd/system/anti-nak-bot.service"
cat << EOF > "$SERVICE_FILE"
[Unit]
Description=Nakrutka Blocker Telegram Bot & Web App
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python3 $APP_DIR/bot.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
EnvironmentFile=$APP_DIR/.env

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable anti-nak-bot
systemctl restart anti-nak-bot

echo ""
echo -e "${GREEN}==========================================================${NC}"
echo -e "${GREEN}   TABRIKLAYMIZ! BOT VA WEB APP MUVAFFAQIYATLI O'RNATILDI! ${NC}"
echo -e "${GREEN}==========================================================${NC}"
echo ""
echo -e "${CYAN}1. Bot va Web App holati:${NC}"
systemctl status anti-nak-bot --no-pager -l || true
echo ""
echo -e "${YELLOW}MUHIM ESMATMA (Domen bo'yicha):${NC}"
echo -e "Agar ${DOMAIN} domenini hali Vercel'dan ushbu server IP raqamiga yo'naltirmagan bo'lsangiz:"
echo -e "1. Domen olgan profilingiz (DNS boshqaruvi) ga kiring."
echo -e "2. ${DOMAIN} ning A yozuvini (A Record) ushbu serveringizning IP raqamiga o'zgartiring."
echo -e "3. Shundan so'ng serverda quyidagi buyruqni yozib HTTPS ni yoqing:"
echo -e "   ${GREEN}certbot --nginx -d ${DOMAIN} --redirect${NC}"
echo ""
echo -e "${CYAN}FOYDALI BUYRUQLAR (MobaXterm uchun):${NC}"
echo -e "• Bot loglarini jonli kuzatish:  ${GREEN}journalctl -u anti-nak-bot -f${NC}"
echo -e "• Botni qayta ishga tushirish:   ${GREEN}systemctl restart anti-nak-bot${NC}"
echo -e "• Botni to'xtatish:             ${GREEN}systemctl stop anti-nak-bot${NC}"
echo -e "• Skaner akkauntini ulash:      ${GREEN}cd $APP_DIR && source venv/bin/activate && python login.py${NC}"
echo ""
