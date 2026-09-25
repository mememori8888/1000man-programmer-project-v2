FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock.txt .
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY app.py core.py finance.py thoughts.py ./
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "app.py"]
