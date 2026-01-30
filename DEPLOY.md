# Деплой на VPS

## Быстрый старт

1. **Клонируйте репозиторий на VPS:**
```bash
git clone <your-repo-url>
cd node-hr
```

2. **Создайте файл с переменными окружения:**
```bash
cp env.example .env
nano .env
```

3. **Добавьте ваш Mistral API ключ в `.env`:**
```
MISTRAL_API_KEY=your_actual_api_key_here
```

4. **Запустите через Docker Compose:**
```bash
docker-compose up -d --build
```

5. **Проверьте статус:**
```bash
docker-compose ps
docker-compose logs -f
```

6. **Откройте в браузере:**
```
http://your-vps-ip:8000
```

## Управление

### Остановка
```bash
docker-compose down
```

### Перезапуск
```bash
docker-compose restart
```

### Просмотр логов
```bash
docker-compose logs -f nodehr
```

### Обновление кода
```bash
git pull
docker-compose up -d --build
```

## Настройка Nginx (опционально)

Если хотите использовать домен и HTTPS:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Безопасность

- ✅ Не коммитьте `.env` файл в git
- ✅ Используйте сильные пароли для API ключей
- ✅ Настройте firewall (ufw) на VPS
- ✅ Используйте HTTPS через Nginx + Let's Encrypt
