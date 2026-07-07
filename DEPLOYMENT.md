# TransPulse Deployment Guide

TransPulse is configured to be deployed seamlessly onto cloud platforms like Render. This guide provides the necessary steps to deploy the application in a production environment.

## 1. GitHub Integration
1. Ensure your local repository is pushed to a remote GitHub repository.
2. The `render.yaml` blueprint is included in the root directory to automate the deployment process.

## 2. Render Deployment
1. Log in to your Render dashboard.
2. Select **New** -> **Blueprint**.
3. Connect your GitHub repository containing the TransPulse codebase.
4. Render will automatically detect the `render.yaml` file and provision the necessary Web Service and PostgreSQL Database.

## 3. Environment Variables
The following environment variables are securely managed. In Render, these can be set under the **Environment** tab of your Web Service:
- `SECRET_KEY`: A cryptographically secure random string.
- `FLASK_ENV`: Set this strictly to `production`.
- `MAIL_USERNAME` / `MAIL_PASSWORD`: SMTP credentials for the system's automated email notifications.
- *Note:* `DATABASE_URL` is automatically provisioned and injected by Render via the blueprint.

## 4. Database Setup
The blueprint automatically runs the `flask db upgrade` command during the build phase. This ensures your PostgreSQL schema is perfectly aligned with the SQLAlchemy models before the application boots.

## 5. Static Files & Gunicorn
TransPulse uses `gunicorn` as the production WSGI server. 
- The Start Command defined in `render.yaml` is `gunicorn app:app`.
- Static files (CSS, JS, Images, Leaflet assets) are served directly by the application and cached via the integrated ServiceWorker.

## 6. HTTPS
Render automatically provisions and manages SSL/TLS certificates for your application. The `config.py` intelligently detects the `production` environment and enforces secure, HTTPOnly cookies across the platform to leverage this secure layer.
