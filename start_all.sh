#!/bin/bash

echo "Stopping existing services..."
killall node uvicorn 2>/dev/null || true
sleep 1
# Force-free ports just in case
lsof -ti :5173 | xargs kill -9 2>/dev/null || true
lsof -ti :5174 | xargs kill -9 2>/dev/null || true
lsof -ti :8001 | xargs kill -9 2>/dev/null || true
sleep 1

echo "Starting Backend (Uvicorn on port 8001)..."
cd backend
source venv/bin/activate
nohup uvicorn main:app --port 8001 --env-file .env > uvicorn.log 2>&1 &
cd ..

echo "Starting Frontend (Vite)..."
cd frontend
nohup npm run dev > vite.log 2>&1 &
cd ..

echo "========================================="
echo "✅ All services successfully started!"
echo "📡 Frontend: http://localhost:5173"
echo "⚙️  Backend:  http://localhost:8001"
echo "🌐 Production: https://twocareai-backend.onrender.com"
echo "========================================="
