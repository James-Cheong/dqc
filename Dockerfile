# set base image (host OS)
FROM python:3.9.7-buster

# set the working directory in the container
WORKDIR /app

# copy the dependencies file to the working directory
COPY main.py requirements.txt settings.json /app/
COPY DQC /app/DQC
COPY templates /app/templates

RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/10/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update && ACCEPT_EULA=Y apt-get install -y msodbcsql17 \
    && apt-get install -y unixodbc-dev && mkdir /log && sed -i -E 's/(CipherString\s*=\s*DEFAULT@SECLEVEL=)2/\11/' /etc/ssl/openssl.cnf
# install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# command to run on container start
CMD [ "python", "main.py" ]
