FROM python:3.14-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=7860
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py app_operational.py app_refinement.py LICENSE ./
COPY second_brain/ ./second_brain/
COPY data/ ./data/
COPY static/ ./static/
# These existing public routes expose retained records, not training inputs.
COPY train/training_receipt.json train/eval_report.json ./train/
EXPOSE 7860
CMD ["uvicorn", "app_refinement:app", "--host", "0.0.0.0", "--port", "7860"]
