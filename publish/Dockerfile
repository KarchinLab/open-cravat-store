FROM python:3.6

RUN pip install aiohttp open-cravat

VOLUME /mnt/temp
VOLUME /mnt/uploads
VOLUME /mnt/final
VOLUME /mnt/app

ENV CRAVATSTORE_CONFIG_PATH  /mnt/app/config.yml

WORKDIR /usr/src/app
COPY crawler.py .
COPY email_templates.py .
COPY utils.py .
COPY main.py .

EXPOSE 80

CMD ["python","/usr/src/app/main.py"]
