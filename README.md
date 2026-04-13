# FastAPI + Supabase Backend

This backend is a FastAPI service for the existing mobile app. It stores user profiles in Supabase, tracks likes/interests, and exposes a simple matches API when two users mutually connect.

## Project Structure

```text
backend/
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   ├── supabase_client.py
│   │   └── auth.py
│   ├── schemas/
│   │   ├── profile.py
│   │   ├── interest.py
│   │   └── match.py
│   ├── routes/
│   │   ├── profile.py
│   │   ├── interests.py
│   │   └── matches.py
│   └── services/
│       └── match_service.py
├── .env
├── requirements.txt
└── README.md
```

## What This API Does

- Verifies Supabase bearer tokens on protected routes.
- Lets each user create and update their own profile.
- Stores partner preferences alongside the profile row.
- Returns discover and filtered search results for profiles.
- Tracks sent and received interests.
- Creates a `matches` row when interest becomes mutual or is accepted.

## Suggested Supabase Tables

Run this in the Supabase SQL editor before starting the API:

```sql
create extension if not exists "pgcrypto";

create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  name text,
  phone text,
  gender text,
  age int check (age between 18 and 99),
  height text,
  religion text,
  education text,
  title text,
  caste text,
  bio text,
  city text,
  state text,
  country text,
  image text,
  is_online boolean not null default false,
  preferred_age_min int,
  preferred_age_max int,
  preferred_location text,
  preferred_state text,
  preferred_city text,
  preferred_district text,
  preferred_religion text,
  preferred_education text,
  preferred_profession text,
  preferred_caste text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.profile_photos (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  image_url text not null,
  storage_path text not null unique,
  is_primary boolean not null default false,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create unique index if not exists profile_photos_one_primary_per_profile_idx
  on public.profile_photos (profile_id)
  where is_primary = true;

create table if not exists public.interests (
  id uuid primary key default gen_random_uuid(),
  sender_id uuid not null references public.profiles (id) on delete cascade,
  receiver_id uuid not null references public.profiles (id) on delete cascade,
  status text not null default 'pending'
    check (status in ('pending', 'accepted', 'rejected', 'withdrawn', 'matched')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (sender_id, receiver_id),
  check (sender_id <> receiver_id)
);

create table if not exists public.matches (
  id uuid primary key default gen_random_uuid(),
  user_one_id uuid not null references public.profiles (id) on delete cascade,
  user_two_id uuid not null references public.profiles (id) on delete cascade,
  status text not null default 'matched' check (status in ('matched')),
  matched_at timestamptz not null default timezone('utc', now()),
  created_at timestamptz not null default timezone('utc', now()),
  unique (user_one_id, user_two_id),
  check (user_one_id <> user_two_id)
);

create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  sender_id uuid not null references public.profiles (id) on delete cascade,
  receiver_id uuid not null references public.profiles (id) on delete cascade,
  body text not null,
  is_read boolean not null default false,
  created_at timestamptz not null default timezone('utc', now()),
  read_at timestamptz
);

create index if not exists messages_sender_receiver_created_idx
  on public.messages (sender_id, receiver_id, created_at desc);

create index if not exists messages_receiver_read_idx
  on public.messages (receiver_id, is_read, created_at desc);

create table if not exists public.shortlists (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  target_profile_id uuid not null references public.profiles (id) on delete cascade,
  created_at timestamptz not null default timezone('utc', now()),
  unique (user_id, target_profile_id),
  check (user_id <> target_profile_id)
);

create index if not exists shortlists_user_created_idx
  on public.shortlists (user_id, created_at desc);
```

If your `profiles` table already exists, run this too:

```sql
alter table public.profiles add column if not exists preferred_state text;
alter table public.profiles add column if not exists preferred_city text;
alter table public.profiles add column if not exists preferred_district text;
alter table public.profiles add column if not exists preferred_profession text;
```

## Auth Flow

This API expects the mobile app to authenticate with Supabase Auth and then call FastAPI with:

```http
Authorization: Bearer <supabase_access_token>
```

The backend validates that access token with Supabase before allowing access to protected routes.

## Setup

1. Create a virtual environment.
2. Install packages:

```bash
pip install -r requirements.txt
```

3. Update `.env` with your Supabase project values.
4. Start the API from the `backend/` folder:

```bash
uvicorn app.main:app --reload
```

5. Open Swagger docs:

```text
http://127.0.0.1:8000/docs
```

## Docker Build

This project includes [Dockerfile](/d:/PROJECT/backend/Dockerfile:1) and [.dockerignore](/d:/PROJECT/backend/.dockerignore:1).

Build the image:

```bash
docker build -t bandhanaa-backend .
```

Run the container:

```bash
docker run --env-file .env -p 8000:8000 bandhanaa-backend
```

Then open:

```text
http://127.0.0.1:8000/docs
```

For mobile release builds, point the app to your public backend URL, for example:

```env
EXPO_PUBLIC_API_BASE_URL=https://api.yourdomain.com/api/v1
```

## Deploy on Render with GitHub

You can deploy this backend to Render directly from GitHub without Docker.

This repo now includes [render.yaml](/d:/PROJECT/render.yaml:1), which tells Render:

- use a Python web service
- deploy from the `backend/` folder
- install packages with `pip install -r requirements.txt`
- start FastAPI with `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- health check on `/api/v1/health`

### Steps

1. Push this project to GitHub.
2. Open Render and connect your GitHub account.
3. In Render, click `New` -> `Blueprint`.
4. Select your GitHub repository.
5. Render will detect [render.yaml](/d:/PROJECT/render.yaml:1).
6. Before deploy, add these environment variables in Render for the backend service:

```text
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
APP_NAME
CORS_ORIGINS
PROFILE_NAME_COLUMN
PROFILE_PHOTOS_BUCKET
```

7. Deploy the Blueprint.

After deploy, Render gives you a public URL like:

```text
https://bandhanaa-backend.onrender.com
```

Then update your mobile app env:

```env
EXPO_PUBLIC_API_BASE_URL=https://bandhanaa-backend.onrender.com/api/v1
```

### Notes

- Render automatically redeploys when you push to the linked GitHub branch.
- Render requires your web service to bind to `0.0.0.0` and use the platform `PORT`.
- Because this backend is inside `backend/`, the `rootDir: backend` setting in [render.yaml](/d:/PROJECT/render.yaml:1) is important.

## Main Endpoints

### System

- `GET /api/v1/health`

### Auth

- `POST /api/v1/auth/signup`
- `POST /api/v1/auth/login`

### Profiles

- `GET /api/v1/profiles/me`
- `PUT /api/v1/profiles/me`
- `GET /api/v1/profiles/me/photos`
- `POST /api/v1/profiles/me/photos`
- `PATCH /api/v1/profiles/me/photos/{photo_id}/primary`
- `DELETE /api/v1/profiles/me/photos/{photo_id}`
- `PUT /api/v1/profiles/preferences`
- `GET /api/v1/profiles/discover`
- `GET /api/v1/profiles/search`
- `GET /api/v1/profiles/{profile_id}`
- `GET /api/v1/profiles/{profile_id}/photos`

### Interests

- `POST /api/v1/interests`
- `GET /api/v1/interests/received`
- `GET /api/v1/interests/sent`
- `PATCH /api/v1/interests/{interest_id}`

### Matches

- `GET /api/v1/matches`

### Chats

- `GET /api/v1/chats`
- `GET /api/v1/chats/{profile_id}/messages`
- `POST /api/v1/chats/{profile_id}/messages`

### Shortlists

- `GET /api/v1/shortlists/me`
- `POST /api/v1/shortlists`
- `DELETE /api/v1/shortlists/{target_profile_id}`

## Example Requests

Sign up:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Rahul Verma",
    "email": "rahul@example.com",
    "password": "supersecret123",
    "phone": "9876543210",
    "gender": "male"
  }'
```

Log in:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "rahul@example.com",
    "password": "supersecret123"
  }'
```

Update my profile:

```bash
curl -X PUT "http://127.0.0.1:8000/api/v1/profiles/me" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Rahul Verma",
    "age": 29,
    "title": "Business Analyst",
    "city": "Bangalore",
    "state": "Karnataka",
    "country": "India",
    "bio": "Looking for a meaningful connection."
  }'
```

Search profiles:

```bash
curl "http://127.0.0.1:8000/api/v1/profiles/search?age_min=25&age_max=30&city=Hyderabad" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Send interest:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/interests" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "receiver_id": "target-profile-uuid"
  }'
```

Accept a received interest:

```bash
curl -X PATCH "http://127.0.0.1:8000/api/v1/interests/interest-uuid" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "accepted"
  }'
```

## Notes

- Keep the Supabase `service_role` key on the server only.
- If your mobile app will talk only to FastAPI for data access, do not expose your tables directly to the client.
- Create a public Supabase Storage bucket named `profile-images`, or let the backend create it automatically on first upload.
- `profiles.image` is treated as the current primary photo, while `profile_photos` stores the full gallery.
- This scaffold is ready for adding chat hooks and subscription logic later.
- Chat is available only between matched users, and chat history is stored in `messages`.
- Home heart actions are backed by `shortlists`, and the shortlist page reads from that table.
