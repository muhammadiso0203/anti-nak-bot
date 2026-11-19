#!/usr/bin/env bash
# ==========================================================
#   CLOUDFLARE HTTPS TUNNEL O'RNATUVCHI (NAT / Router uchun)
#   Server router ortida (192.168.x.x) bo'lganda 100% ishlaydi!
# ==========================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}==========================================================${NC}"
echo -e "${GREEN}    CLOUDFLARE HTTPS TUNNEL O'RNATILMOQDA...${NC}"
echo -e "${CYAN}==========================================================${NC}"

if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[XATO] Iltimos, root sifatida ishga tushiring (sudo su)${NC}"
  exit 1
fi

APP_DIR="/root/anti-nak-bot"
LOG_FILE="/var/log/cloudflared.log"

# 1. Cloudflared o'rnatish
if ! command -v cloudflared &> /dev/null; then
    echo -e "${YELLOW}[1/4] Cloudflared paketi yuklab olinmoqda va o'rnatilmoqda...${NC}"
    curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o /tmp/cloudflared.deb
    dpkg -i /tmp/cloudflared.deb
    rm -f /tmp/cloudflared.deb
else
    echo -e "${GREEN}[1/4] Cloudflared allaqachon o'rnatilgan.${NC}"
fi

# 2. Systemd xizmatini sozlash (avtomatik 24/7 orqa fonda ishlash uchun)
echo -e "${YELLOW}[2/4] Cloudflare Tunnel xizmati sozlanmoqda...${NC}"
cat << EOF > /etc/systemd/system/cloudflared-tunnel.service
[Unit]
Description=Cloudflare Tunnel for Anti-Nak Web App
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/cloudflared tunnel --url http://127.0.0.1:8080
Restart=always
RestartSec=5
StandardOutput=append:$LOG_FILE
StandardError=append:$LOG_FILE

[Install]
WantedBy=multi-user.target
EOF

# Eski logni tozalab yangidan ishga tushiramiz
rm -f "$LOG_FILE"
systemctl daemon-reload
systemctl enable cloudflared-tunnel
systemctl restart cloudflared-tunnel

# 3. Havola olinishini kutish
echo -e "${YELLOW}[3/4] Bepul xavfsiz HTTPS havola olinmoqda (5 soniya kuting)...${NC}"
TUNNEL_URL=""
for i in {1..15}; do
    sleep 1
    if [ -f "$LOG_FILE" ]; then
        TUNNEL_URL=$(grep -o 'https://[a-zA-Z0-9.-]*\.trycloudflare\.com' "$LOG_FILE" | tail -n 1 || true)
        if [ -n "$TUNNEL_URL" ]; then
            break
        fi
    fi
done

if [ -z "$TUNNEL_URL" ]; then
    echo -e "${RED}[XATO] Havolani olib bo'lmadi. Log faylini tekshiring: cat $LOG_FILE${NC}"
    exit 1
fi

echo -e "${GREEN}Yangi xavfsiz HTTPS havola olindi:${NC} ${CYAN}$TUNNEL_URL${NC}"

# 4. .env fayliga yangi havolani yozish va botni yangilash
echo -e "${YELLOW}[4/4] Botingiz sozlamalari yangilanmoqda...${NC}"
if [ -f "$APP_DIR/.env" ]; then
    sed -i "s|^WEBAPP_URL=.*|WEBAPP_URL=$TUNNEL_URL|" "$APP_DIR/.env"
fi

systemctl restart anti-nak-bot

echo ""
echo -e "${GREEN}==========================================================${NC}"
echo -e "${GREEN}   TABRIKLAYMIZ! WEB APP 100% ISHGA TUSHDI!               ${NC}"
echo -e "${GREEN}==========================================================${NC}"
echo ""
echo -e "Sizning Web App havolangiz: ${CYAN}$TUNNEL_URL${NC}"
echo ""
echo -e "${GREEN}ENDI TELEGRAMGA O'TING:${NC}"
echo -e "Telegram botingizga kiring va pastdagi ${YELLOW}«Ilova»${NC} menyusini yoki ${YELLOW}/app${NC} tugmasini bosing!"
echo -e "Web App endi to'g'ridan-to'g'ri haqiqiy kanallaringiz bilan ochiladi!"
echo ""
