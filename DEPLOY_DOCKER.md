# Docker deployment for `yanina-beauty.by`

## 1. Prepare the server

Install Docker and Docker Compose plugin:

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo systemctl enable --now docker
```

## 2. Clone the project

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL> yanina-beauty
cd yanina-beauty
cp .env.prod.example .env.prod
```

Fill in `.env.prod` with your real values.

## 3. Point the domain to the server

Create DNS records for:

- `yanina-beauty.by`
- `www.yanina-beauty.by`

Both should point to your server IP.

## 4. Start the containers

```bash
docker compose --env-file .env.prod up -d --build
```

## 5. Create admin user

```bash
docker compose --env-file .env.prod exec web python manage.py createsuperuser --settings=config.settings.prod
```

## 6. Open the site

- Main site: `http://yanina-beauty.by`
- Admin: `http://yanina-beauty.by/admin/`

## 7. Useful commands

View logs:

```bash
docker compose --env-file .env.prod logs -f
```

Restart after changes:

```bash
docker compose --env-file .env.prod up -d --build
```

Stop:

```bash
docker compose --env-file .env.prod down
```

## 8. HTTPS

If your server already has a shared `caddy` container, connect this project to the same Docker network and proxy to:

```caddy
yanina-beauty.by, www.yanina-beauty.by {
    reverse_proxy yanina-beauty-web-1:8000
}
```

If you use the standalone `nginx` profile instead, the next step is to add SSL with Let's Encrypt and switch:

- `SECURE_SSL_REDIRECT=True`
- `CSRF_TRUSTED_ORIGINS=https://yanina-beauty.by,https://www.yanina-beauty.by`
- `SECURE_HSTS_SECONDS=31536000`

If you want, the next step can be a full HTTPS setup with Let's Encrypt inside Docker as well.
