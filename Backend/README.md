# Backend Setup Guide

This backend is a Python FastAPI application that analyzes source code and stores graph data in Neo4j.

## Prerequisites

- Windows 10 or Windows 11
- Python 3.12 installed
- PowerShell
- Internet access for installing Python packages
- A reachable Neo4j instance configured in `.env`

## Project Setup

1. Open PowerShell and go to the backend folder.

```powershell
cd F:\spl3\Backend
```

2. Create a virtual environment.

```powershell
py -3.12 -m venv venv
```

3. Allow script execution for the current PowerShell session and activate the virtual environment.

```powershell
Set-ExecutionPolicy -Scope Process RemoteSigned
.\venv\Scripts\Activate.ps1
```

4. Upgrade pip.

```powershell
python -m pip install --upgrade pip
```

5. Install the project dependencies.

```powershell
pip install -r requirements.txt
```

## Run the Backend

Start the API server with Uvicorn:

```powershell
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

## Check If the Server Is Running

Open this URL in a browser or test it from PowerShell:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/health
```

## Notes

- The Neo4j connection is read from `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` in `Backend/.env` (see `.env.example`).
- To use a different Neo4j server, just change those values in `.env`.
- The upload endpoint accepts single files, multiple files, or ZIP uploads.

## Common Commands

Deactivate the virtual environment:

```powershell
deactivate
```

Install a fresh copy of all dependencies again:

```powershell
pip install --force-reinstall -r requirements.txt
```
