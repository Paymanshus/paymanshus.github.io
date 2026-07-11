# Build from the REPO ROOT, not agent/, so this can COPY content/resumedump.md
# (outside the agent/ build context otherwise):
#   docker build -f agent/Dockerfile -t paymanshu-voice-agent .
FROM python:3.12-slim

WORKDIR /app

COPY agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent/ .
# Resume dump feeds the voice agent's BM25 index (agent/resume_context.py).
# Lives outside agent/, hence the repo-root build context.
COPY content/resumedump.md ./content/resumedump.md

# Pre-download the turn-detector model at build time so cold starts don't
# pay for it on first request.
RUN python main.py download-files

EXPOSE 8080

CMD ["python", "main.py", "start"]
