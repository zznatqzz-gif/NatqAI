FROM ghcr.io/cirruslabs/android-sdk:35
USER root
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jdk-headless unzip curl python3 python3-pip \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL https://services.gradle.org/distributions/gradle-8.7-bin.zip -o /tmp/gradle.zip \
 && unzip -q /tmp/gradle.zip -d /opt && rm /tmp/gradle.zip \
 && ln -s /opt/gradle-8.7/bin/gradle /usr/local/bin/gradle \
 && useradd --create-home --uid 10001 builder
WORKDIR /srv/builder
COPY requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages fastapi 'uvicorn[standard]' python-multipart
COPY android_builder/worker.py ./worker.py
RUN chown -R builder:builder /srv/builder \
 && chmod -R a-w /opt/gradle-8.7 /opt/android-sdk-linux
USER builder
ENV ANDROID_HOME=/opt/android-sdk-linux ANDROID_SDK_ROOT=/opt/android-sdk-linux JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=3 CMD curl -fsS http://127.0.0.1:8080/health || exit 1
CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8080"]
