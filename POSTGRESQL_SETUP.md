# DEAR ERP PostgreSQL Setup

## Install PostgreSQL

Windows:

1. Download PostgreSQL from https://www.postgresql.org/download/windows/
2. Install PostgreSQL 16 or newer.
3. Keep note of the `postgres` password.

Create database and user:

```sql
CREATE DATABASE dear_erp;
CREATE USER dear_erp_user WITH PASSWORD 'change-password';
GRANT ALL PRIVILEGES ON DATABASE dear_erp TO dear_erp_user;
```

## Configure Environment

Copy `.env.example` to `.env`:

```powershell
copy .env.example .env
```

Edit:

```text
DATABASE_URL=postgresql+psycopg://dear_erp_user:change-password@localhost:5432/dear_erp
SECRET_KEY=your-production-secret
```

## Initialize Tables

```powershell
cd C:\Users\USER\DEAR_ERP
python -m pip install -r requirements.txt
python -c "from app import app, init_database; ctx=app.app_context(); ctx.push(); init_database(); ctx.pop()"
```

## Migrate Existing SQLite Data

Run after PostgreSQL tables exist:

```powershell
$env:DATABASE_URL="postgresql+psycopg://dear_erp_user:change-password@localhost:5432/dear_erp"
$env:SQLITE_PATH="dear_erp.db"
python migrate_sqlite_to_postgres.py
```

Move existing product images from `uploads` into:

```text
static/uploads/products
```

The migration script converts old `image_filename` values into `image_path` values like `uploads/products/file.jpg`.
