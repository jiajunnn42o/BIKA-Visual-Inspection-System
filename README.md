# BIKA Visual Inspection System

BIKA Visual Inspection System is a web-based industrial visual inspection platform developed as a Final Year Project.

The system is designed to support automated product quality inspection, user management, inspection records, reports, analytics, and AI-assisted visual inspection workflows.

The current version includes a complete authentication and account registration workflow with email verification, SuperAdmin approval, account security, and password recovery.

---

## Current Features

### Authentication

- User registration
- Email verification using a 6-digit OTP
- Email verification code expiry and resend protection
- SuperAdmin registration approval
- Registration rejection with reason
- Email notification when registration information is updated
- Email notification when registration is approved or rejected
- Email or username login
- Failed login attempt tracking
- Automatic account locking
- Forgot password
- Password reset using a 6-digit OTP
- Password reset security notification
- Malaysian mobile number validation and normalization
- Role-based account structure

### User Roles

The system currently supports three roles:

- User
- Admin
- SuperAdmin

Public registration always creates a `User` account. Role assignment is controlled by the SuperAdmin.

---

## Technology Stack

### Backend

- Python 3.12
- Flask
- Flask-SQLAlchemy
- Flask-Migrate
- Flask-Login
- Flask-WTF
- Flask-Mail
- PostgreSQL
- psycopg

### Frontend

- HTML
- Jinja2
- CSS
- JavaScript
- Inter font

### Planned AI / Data Components

- YOLO-based instance segmentation
- PyTorch
- Ultralytics
- OpenCV
- Pillow
- NumPy
- Pandas
- Chart.js

---

# Installation

## 1. Prerequisites

Install the following software before setting up the project:

- Python 3.12 or later
- PostgreSQL
- Git
- Node.js and npm
- Visual Studio Code or another code editor

Recommended versions used during development:

```text
Python      3.12.x
PostgreSQL  17.x
Node.js     22.x
npm         10.x
