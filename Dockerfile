FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

COPY . /app/

# 🔥 Clone Adobe SDK repo and install it locally
RUN git clone https://github.com/adobe/pdfservices-python-sdk.git /app/adobe-sdk && \
    pip install ./adobe-sdk

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

CMD ["python", "main.py"]
