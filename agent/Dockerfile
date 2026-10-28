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
# Blog posts, /cooking projects and the owner's notes feed the knowledge index
# (resume_context.get_knowledge_index), used only on a strong topic match.
COPY content/blog/ ./content/blog/
COPY content/cooking/ ./content/cooking/
COPY content/about/ ./content/about/

# Pre-download the turn-detector model at build time so cold starts don't
# pay for it on first request.
RUN python main.py download-files

EXPOSE 8080

CMD ["python", "main.py", "start"]
