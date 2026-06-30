# Mini Hospital Management System (HMS) - Python Serverless Backend Track

This is a complete, ready-to-run Hospital Management System (HMS) focused on doctor availability scheduling, patient appointment bookings (with race-condition prevention), a local serverless email service, and Google Calendar OAuth2 synchronization.

---

## Setup and Run

Follow these instructions to run the entire system locally on a fresh Windows machine.

### Prerequisites
1. **Python 3.13+**: Ensure Python is installed and in your environment PATH. (We verified `Python 3.13.7` is installed on your machine).
2. **Node.js & npm** (Required for the serverless offline email service):
   If you do not have Node.js and npm installed, run the following command in PowerShell as Administrator to install them instantly via Windows Package Manager:
   ```powershell
   winget install OpenJS.NodeJS
   ```
   *Note: Close and reopen your terminal after installation to refresh your environment PATH.*
3. **Git**: If not installed, you can install it using:
   ```powershell
   winget install Git.Git
   ```

---

### Step 1: Clone and Set Up the Python Environment
Open a terminal in the root directory (`TASK1`) and execute:
```powershell
# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install all dependencies
pip install -r requirements.txt
```

### Step 2: Initialize the Database
The application supports PostgreSQL by default (configured via `.env` file), but falls back automatically to a local SQLite database (`db.sqlite3`) for instant setup if PostgreSQL is not active.
To set up database schemas:
```powershell
cd hms
python manage.py migrate
```

### Step 3: Run the Mock SMTP Console Server
Open a **new terminal** in the root project folder and run our zero-dependency SMTP server. It captures all emails sent by the serverless function and prints them to the terminal console:
```powershell
python mock_smtp.py
```

### Step 4: Run the Serverless Email Service
Open a **new terminal** in the `email-service` directory to install dependencies and boot up `serverless-offline`:
```powershell
cd email-service
npm install
npm start
```
*This command launches the serverless email function locally at `http://127.0.0.1:3000`.*

### Step 5: Start the Django HMS Server
Return to your terminal in the `hms` folder (with `venv` activated) and launch the web server:
```powershell
python manage.py runserver
```
Open your browser and navigate to: **`http://127.0.0.1:8000`**

### (Optional) Create a Superuser
To access the Django Admin panel (`http://127.0.0.1:8000/admin/`):
```powershell
python manage.py createsuperuser
```

---

## System Architecture

### 1. Overview and Integration Flow
The system is divided into two distinct components:
- **Django Core Application (`hms/`)**: Manages the relational database, session authentication, availability schedules, and patient booking forms. When actions occur (e.g., signup, booking completion), Django triggers HTTP POST requests to the serverless function.
- **Serverless Email Service (`email-service/`)**: Built using the Serverless Framework (`serverless.yml`) and `serverless-offline`. It runs a local HTTP handler (`handler.py`) that receives payloads from Django and sends HTML notifications using Python's standard `smtplib` package (dispatching to our console Mock SMTP server on port 1025).

### 2. Data Model Decisions
We designed four relational models in `main/models.py`:
- **`User`**: Extends Django's `AbstractUser` to support role-based categorization (`DOCTOR` vs. `PATIENT`) on a single entity, which streamlines access checks.
- **`AvailabilitySlot`**: Belongs to a doctor. Holds `start_time` and `end_time`. Includes database constraints (`unique_together` on doctor and start time) and validation logic to prevent setting slots in the past.
- **`Booking`**: Links a patient, a doctor, and an availability slot. Features a `OneToOneField` to `AvailabilitySlot` to prevent double-booking at the database integrity level. Stores Google Calendar event IDs for sync references.
- **`GoogleCredential`**: Stores OAuth2 token parameters (`token`, `refresh_token`, `scopes`, `expiry`) mapped to each user, facilitating automated token refreshes.

### 3. Role-Based Access Enforcement
Role-based access is strictly enforced at two levels:
- **Custom View Decorators**: In `main/decorators.py`, we created `@doctor_required` and `@patient_required` wrappers. If a patient attempts to access a doctor dashboard or slot creator, they are blocked and redirected with an error banner.
- **Database/Form Validation**: Models use `limit_choices_to` constraints to ensure a slot can only belong to a User with the `DOCTOR` role, and a booking can only belong to a `PATIENT`.

### 4. Google Calendar OAuth2 Integration
- **Flow**: The application integrates a standard Google OAuth2 flow using `google-auth-oauthlib`. Users go to `/oauth2/connect/`, which redirects to Google's consent screen (requesting `https://www.googleapis.com/auth/calendar` scope offline). Google redirects back to `/oauth2/callback/`, where the code is exchanged for an access token and refresh token, saved under `GoogleCredential`.
- **Sync**: When a booking is finalized, the server retrieves credentials for both the doctor and the patient, checks if they are expired, refreshes them if necessary, and makes two independent API calls to Google Calendar to insert events.
- **Mock Mode Fallback**: If Google API client details are not configured in `.env`, the system automatically activates **Mock Mode**. Instead of throwing errors or crashing, it writes the JSON event payload to a local log file `mock_google_calendar_events.json` and displays a confirmation banner, allowing complete local verification.

### 5. Concurrency and Race-Condition Prevention
To handle concurrent booking requests where multiple patients attempt to book the same slot simultaneously, the application utilizes:
- **`transaction.atomic()`**: All slot checking, booking creation, and slot status updates run inside a single database transaction block.
- **`select_for_update()`**: When a patient attempts to book a slot, the system queries the availability slot using `AvailabilitySlot.objects.select_for_update().get(id=slot_id)`. This obtains a row-level lock on the slot. If a second patient attempts to access the same row, they are blocked until the first transaction completes.
- **State Validation**: If the first transaction succeeds and books the slot, the second transaction is unblocked, detects that `slot.is_booked` is now `True`, aborts immediately, and displays a friendly user-facing alert: *"This slot is no longer available. Someone else just booked it!"*.

---

## The Design Decision

### Naming the Problem
**How to balance real-world API integrations (Google Calendar OAuth2 & PostgreSQL) with zero-setup local evaluation requirements?**
During evaluation, reviewers run projects on fresh local environments. Forcing a reviewer to create a Google Cloud Developer console project, configure OAuth consent screens, export client secrets, and install/configure a local PostgreSQL database before booting up the application creates massive friction. However, dropping these features violates the task requirements.

### Options Considered
- **Approach A (Strict Production-Only Setup)**: Enforce PostgreSQL and actual Google OAuth2 configs. If environmental variables are absent, the application crashes, or booking fails.
- **Approach B (Hybrid OAuth2 & DB Fallback Adapter - Chosen)**: Implement a fully compliant PostgreSQL configuration and Google Calendar API integration code, but configure automatic adapters. If DB variables are missing, Django defaults to SQLite. If Google API secrets are missing in `.env`, the system activates a calendar "Mock Mode" which logs event details to a local JSON file (`mock_google_calendar_events.json`) and connects profiles with mock credentials.

### Defending the Decision (Approach B)
We defended and built **Approach B** for three reasons:
1. **Frictionless Evaluator Experience**: It guarantees that the reviewer can run `python manage.py migrate` and start the server immediately. Zero manual developer console setups are needed to test the booking flow.
2. **Deterministic Payload Verification**: In Mock Mode, the reviewer can inspect `mock_google_calendar_events.json` to verify that the Google Calendar event details constructed (such as title, description, and start/end times) match the exact schema specified in the instructions.
3. **Clean Code Isolation**: The live API code (token refreshing, Google discovery builder, OAuth redirect flows) is fully written and separated inside `main/calendar_helper.py` and `main/views.py`. Providing a real client ID and database config in `.env` instantly activates the production setup without modifying a single line of python code.

---

## Limitations

If this application were deployed to a production environment, the following components would break or degrade:

1. **Synchronous HTTP Requests (Django to Serverless)**:
   - *What breaks*: Currently, the Django view makes synchronous POST requests to the local serverless email service. If the serverless endpoint is slow, times out, or has high latency, the user's browser hangs, locking the database transaction.
   - *Fix*: Offload the serverless API requests to an asynchronous task queue like **Celery** (backed by Redis or RabbitMQ) to execute tasks out-of-band without blocking user threads.
2. **SQLite Database Concurrency**:
   - *What breaks*: SQLite locks the entire database file during writes. If hundreds of users book appointments simultaneously, requests will fail with "Database is Locked" errors.
   - *Fix*: Require PostgreSQL in production. PostgreSQL supports true row-level locking, which makes our `select_for_update()` transaction locking highly efficient under heavy concurrent loads.
3. **Google OAuth2 Single-Redirect URIs**:
   - *What breaks*: Locally, we redirect to `http://127.0.0.1:8000`. In production, Google requires secure SSL endpoints (`https://...`) and strict domain white-lists.
   - *Fix*: Configure dynamic callback URLs based on Django's request host and secure sessions using HTTPS cookies.
4. **Mock SMTP Console Server Security**:
   - *What breaks*: The local socket SMTP server is unencrypted, single-threaded, and does not send actual emails.
   - *Fix*: Switch the serverless email handler to connect to a production-grade SMTP service (like **AWS SES** or SendGrid) using TLS encryption.
