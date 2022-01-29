FROM python:3.10

WORKDIR /src
ADD requirements.txt .
RUN pip install -r requirements.txt

ADD . .
RUN ["python", "main.py"]
