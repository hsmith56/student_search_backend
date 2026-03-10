# Student Search API Backend

FastAPI backend for student search, authentication, favorites, feedback, notifications, and Beacon-backed data refresh.

## What This Is

This project is the backend for a student search system. Its job is to make student information easier to find, safer to access, and simpler to manage for the people who need it.

Without this functionality, there is no way to quickly, effectively, and accurately search the data based on information that is unavailable due to lack of a solution. That creates friction for those who need to find the right student, review details, track placement changes, or quickly keep track of important records for follow-up.

This backend fixes that by turning the data into an authenticated search experience. In simple terms:

- users sign in
- the system checks what data they are allowed to access
- the backend provides fast search and filtered results
- related actions like favorites, feedback, and placement updates are handled in one place

At a high level, it works by pulling student data into a local application database, exposing that data through secure API endpoints, and requiring login cookies for protected features. That gives the frontend a reliable way to show searchable student records without exposing the full underlying data source directly.

## Data Access and Separation

Student search and filtering are performed inside this backend against the local SQLite database. The app does not depend on a third-party search engine, AI service, or external processing tool to search the student records.

The upstream Beacon system is used only to refresh and hydrate the local database. End users do not authenticate against Beacon, and app account creation is fully separate from the Beacon credentials used by the server to populate data.

In practice, that means:

- user accounts belong to this application, not to the upstream data source
- login and session cookies are managed locally by this backend
- Beacon credentials are server-side configuration values in `.env`
- full student detail routes and most operational routes require an authenticated account

Optional route analytics can be enabled with `POST_HOG_API_KEY` and `POST_HOG_HOST`. If those values are left unset, the PostHog client stays disabled. Core search and filtering still run locally either way. This is currently being used to anonymously track the number of times searches are performed, as well as the number of individual student profiles are examined.

## Data Cleaning and Privacy

During refresh, the backend pulls source records from Beacon, reshapes them into a smaller application-specific format, and drops several direct identity and contact fields before writing to `student_full_view`.

Fields explicitly removed during hydration include:

- `emailaddress`
- `namelast`
- `namemiddle`
- `birthcity`
- `birthcountryid`
- `birthcountry`
- `residenceCountryId`
- `genderid`
- `productid`
- `skypeid`
- `atlasId`
- `englishTest`
- `hostFamily`
- `schoolReady`

This means the stored student search dataset is privacy-reduced rather than a raw copy of the upstream record. It intentionally avoids storing direct contact details and several full identity fields.

The database retains the minimal operational identifiers such as `first_name`, `app_id`, `pax_id`, and `usahsid` because those are needed for search, matching, and linking records across the application.

### `student_full_view` Stored Fields

| Field | What it is used for |
| --- | --- |
| `id` | Internal primary key for the stored student record |
| `first_name` | First-name display and lightweight text search |
| `app_id` | Application identifier used to look up a student profile |
| `pax_id` | Participant identifier retained for record linkage |
| `country` | Country-of-origin filtering and display |
| `gpa` | GPA display and minimum-GPA filtering |
| `english_score` | English score display and comparison |
| `applying_to_grade` | Grade-placement context |
| `usahsid` | Program/student code used for lookup and grants logic |
| `program_type` | Program term/type filtering |
| `adjusted_age` | Search sorting and age-based filtering |
| `selected_interests` | Structured interest matching |
| `urban_request` | Placement preference display/filtering |
| `placement_status` | Search status filtering and operational tracking |
| `gender_desc` | Gender display/filtering |
| `current_grade` | Current school-grade context |
| `status` | Underlying application status |
| `states` | Preferred-state filtering |
| `early_placement` | Early-placement preference/flag |
| `tuition_placement` | Tuition-placement flag |
| `single_placement` | Single-placement preference |
| `double_placement` | Double-placement preference |
| `free_text_interests` | Additional searchable interest text |
| `family_description` | Family preference/context text |
| `favorite_subjects` | Searchable academic-interest text |
| `photo_comments` | Searchable text extracted from photo comments |
| `religion` | Religious-preference/search data |
| `allergy_comments` | Searchable allergy notes |
| `dietary_restrictions` | Searchable dietary notes |
| `religious_frequency` | Religious-practice filtering |
| `intro_message` | Searchable student introduction text |
| `message_to_host_family` | Searchable host-family letter text |
| `message_from_natural_family` | Searchable natural-family letter text |
| `media_link` | Video/media availability |
| `health_comments` | Searchable health-related notes |
| `live_with_pets` | Pet compatibility filtering |
| `local_coordinator` | Local coordinator assignment or display field |

## What This Repo Runs

- FastAPI application entrypoint: `main.py`
- SQLite database: `user_auth.db`
- Environment/config loader: `core/config.py`
- Local reverse proxy configs:
  - Windows/local HTTPS: `nginx.conf`
  - Unix/Linux proxying: `nginx_unix.conf`

## Requirements

- Python `>=3.9.2`
- [`uv`](https://docs.astral.sh/uv/)
- A `.env` file in the repo root
- Beacon credentials if you need student refresh scripts or refresh endpoints

## Quick Start

1. Install dependencies:

```powershell
uv sync
```

2. Create `.env` from the example:

```powershell
Copy-Item .env.example .env
```

3. Update the values you actually need in `.env`.

4. Start the API in development mode:

```powershell
uv run fastapi dev
```

5. Production-style run command:

```powershell
uv run fastapi run
```

By default the app initializes the SQLite schema on startup and reads settings from `.env`.

## Required Setup

At minimum, set or confirm these values in `.env`:

```env
APP_NAME=student-search-api
ENVIRONMENT=development
DATABASE_PATH=./user_auth.db
BEARER_TOKEN_PATH=./bearer_token
CORS_ORIGINS=https://localhost,http://localhost,https://hsmithtech.com,https://www.hsmithtech.com,*

BEACON_USERNAME=
BEACON_PASSWORD=
```

Useful optional settings already supported by the app:

```env
BEACON_BASE_URL=https://api.ciee.org
BEACON_THREADS=16
BEACON_TIMEOUT_SECONDS=30
BEACON_MAX_RETRIES=3
BEACON_RETRY_BACKOFF_SECONDS=1
BEACON_STAGE1_PAGE_FETCH_WORKERS=4
BEACON_STAGE1_DB_READ_WORKERS=16

LOG_DIR=./log
LOG_FILE_NAME=app.log
LOG_LEVEL=INFO
LOG_MAX_BYTES=5242880
LOG_BACKUP_COUNT=5
LOG_TO_CONSOLE=true

SMTP_USER=
SMTP_PASS=
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_TIMEOUT_SECONDS=30
SIGNUP_INVITE_URL=https://www.hsmithdev.xyz/login
RPM_SIGNUP_CODE=
LC_SIGNUP_CODE=
POST_HOG_API_KEY=
POST_HOG_HOST=
```

## How To Run

### Development

Use this when working locally and you want auto-reload:

```powershell
uv run fastapi dev
```

Expected behavior in development:

- FastAPI docs are available at `/docs`
- ReDoc is available at `/redoc`
- OpenAPI JSON is available at `/openapi.json`
- CORS uses `CORS_ORIGINS` from `.env`, or the built-in defaults if unset

### Production-Style Local Run

Use this when you want to run the app without dev reload:

```powershell
uv run fastapi run
```

This is also the command used by the checked-in systemd service template in [`deploy/systemd/student-search-backend.service`](/c:/Users/Harrison/Desktop/Development/Student_Search/Backend/deploy/systemd/student-search-backend.service).

## Environment Differences

The code only treats `production` specially. Any other `ENVIRONMENT` value behaves like development/non-production.

### `ENVIRONMENT=development` (or anything other than `production`)

- API docs stay enabled
- `CORS_ORIGINS` is read from `.env`
- If `CORS_ORIGINS` is omitted, the backend falls back to these defaults:
  - `https://localhost`
  - `http://localhost`
  - `https://hsmithtech.com`
  - `https://www.hsmithtech.com`
  - `*`

### `ENVIRONMENT=production`

- `DOMAIN` becomes required
- `/docs`, `/redoc`, and `/openapi.json` are disabled
- CORS is not taken from `CORS_ORIGINS`; it is derived from `DOMAIN`
- Allowed origins become:
  - `http://<DOMAIN>`
  - `https://<DOMAIN>`

### Important Auth/Proxy Behavior In Every Environment

- Auth uses cookies, not bearer tokens for browser sessions
- Session state and refresh tokens are stored in memory
- Restarting the backend invalidates active sessions
- Cookies are set with `secure=True` and `samesite="none"`
- In practice, that means HTTPS should be used wherever browser auth needs to work reliably
- Because sessions are in memory, run a single backend process for production deployment

## Local Development Layout

Typical local setup:

- Frontend running separately on `http://127.0.0.1:3000`
- Backend running on `http://127.0.0.1:8000`
- Optional local nginx TLS proxy in [`nginx.conf`](/c:/Users/Harrison/Desktop/Development/Student_Search/Backend/nginx.conf)

Current proxy conventions:

- Frontend served from `/`
- Backend proxied under `/api/`
- WebSocket endpoint exposed at `/notifications/ws/placements`

If you need local HTTPS for secure cookies, use the nginx-based setup and local certificates rather than talking to the backend directly over plain HTTP.

## Unix / Linux Deployment Notes

For Unix-style reverse proxying, see [`nginx_unix.conf`](/c:/Users/Harrison/Desktop/Development/Student_Search/Backend/nginx_unix.conf).

For the fuller Raspberry Pi deployment workflow, see [`Deployer.MD`](/c:/Users/Harrison/Desktop/Development/Student_Search/Backend/Deployer.MD).

The intended production shape is:

- nginx in front
- frontend served separately
- FastAPI backend running locally on port `8000`
- SQLite stored on disk on the same machine
- one backend process only

## Common Commands

Run the API:

```powershell
uv run fastapi dev
uv run fastapi run
```

Manual student refresh:

```powershell
uv run scripts/refresh_students.py
```

Testing helper to swap statuses:

```powershell
uv run scripts/switch_allocated_to_unassigned.py --count 5
```

News feed utilities:

```powershell
uv run scripts/clear_news_feed.py
uv run scripts/add_news_feed_event.py --student-id 12345 --first-name Alice
```

Placement metrics utilities:

```powershell
uv run python scripts/export_placement_data.py
uv run python scripts/import_placement_metrics.py
```

## API/Runtime Notes

- Database initialization runs during app startup
- Most routers are protected globally in `main.py`
- `guest_search` and auth routes are public entry points
- `POST /students/update_db` is the mutating refresh endpoint
- WebSocket notifications are served from `/notifications/ws/placements`
- The backend expects login cookies before a browser opens the WebSocket

## Smoke Check

After startup, the main endpoints worth checking are:

1. `POST /auth/login`
2. `GET /auth/me`
3. `POST /students/search`
4. `GET /user/favorites`
5. `POST /feedback/`
