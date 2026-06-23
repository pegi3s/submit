FROM pegi3s/docker

ENV DEBIAN_FRONTEND=noninteractive

# Install only the libraries required for Firefox to run
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      git \
      build-essential \
      autoconf \
      automake \
      libtool \
      ca-certificates \
      wget \
      tar \
      xz-utils \
      libgtk-3-0 \
      libdbus-glib-1-2 \
      libx11-xcb1 \
      libasound2t64 \
      fonts-liberation \
      libgbm1 \
      libcanberra-gtk3-module \
      openssh-client \
      sshpass \
    && rm -rf /var/lib/apt/lists/*

# Download and extract Firefox
RUN wget -O /tmp/firefox.tar.xz \
      "https://download.mozilla.org/?product=firefox-latest&os=linux64" && \
    tar -xJf /tmp/firefox.tar.xz -C /opt && \
    ln -sf /opt/firefox/firefox /usr/local/bin/firefox && \
    rm -f /tmp/firefox.tar.xz

# Basic configuration to skip first-run screens
RUN mkdir -p /opt/firefox/defaults/pref && \
    echo 'pref("general.config.filename", "mozilla.cfg");' > /opt/firefox/defaults/pref/local-settings.js && \
    echo 'pref("general.config.obscure_value", 0);' >> /opt/firefox/defaults/pref/local-settings.js && \
    printf 'lockPref("browser.aboutwelcome.enabled", false);\nlockPref("datareporting.policy.dataSubmissionEnabled", false);' > /opt/firefox/mozilla.cfg

ENV DISPLAY=:0

# Install streamlit

RUN apt update && apt install -y python3-pip
RUN pip install streamlit --break-system-packages
RUN pip install streamlit-scroll-to-top --break-system-packages
RUN mkdir -p ~/.streamlit/
RUN echo "[browser]\ngatherUsageStats = false\n" > ~/.streamlit/config.toml
RUN echo "[server]\nheadless = true\n" > ~/.streamlit/config.toml

# Copy Python script

COPY submit.py /opt
WORKDIR /opt

# Clone the project

RUN pip install python-dotenv --break-system-packages

RUN pip install dropbox --break-system-packages

#RUN git clone https://github.com/pegi3s/dockerfiles.git #########################

# Install Node.js 20 LTS (required for Angular 21 build)
RUN wget -O /tmp/node.tar.xz \
      "https://nodejs.org/dist/v20.19.5/node-v20.19.5-linux-x64.tar.xz" && \
    tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 --no-same-owner && \
    rm /tmp/node.tar.xz

# Clone, patch and build bdip-web-manager
RUN git clone --depth=1 https://github.com/pegi3s/bdip-web-manager.git /opt/bdip-web-manager
COPY patch_angular.py /tmp/patch_angular.py
RUN python3 /tmp/patch_angular.py
RUN cd /opt/bdip-web-manager && npm ci && npm run build

# Symlink the Angular dist output (handles with/without browser/ subfolder)
RUN proj=$(ls /opt/bdip-web-manager/dist/) && \
    if [ -d "/opt/bdip-web-manager/dist/$proj/browser" ]; then \
        ln -s "/opt/bdip-web-manager/dist/$proj/browser" /opt/bdip-web-manager-dist; \
    else \
        ln -s "/opt/bdip-web-manager/dist/$proj" /opt/bdip-web-manager-dist; \
    fi

# Build start script
RUN echo '#!/bin/bash' > /opt/start && \
    echo 'python3 -m http.server 4200 --directory /opt/bdip-web-manager-dist &' >> /opt/start && \
    echo 'firefox http://localhost:8501 &' >> /opt/start && \
    echo 'exec streamlit run submit.py' >> /opt/start && \
    chmod 777 /opt/start

CMD ["/opt/start"]
 

# docker run -v /var/run/docker.sock:/var/run/docker.sock   -v ~/.ssh:/root/.ssh   -v /submit_history:/submit_history -e USERID=$UID   -e USER=$USER   -e DISPLAY=$DISPLAY   -v /tmp/.X11-unix:/tmp/.X11-unix   -v $PWD/.config.ini:/opt/.config.ini   -v $PWD:/data pegi3s/submit