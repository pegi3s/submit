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

# Firefox profile with pre-configured preferences to skip first-run screens
RUN mkdir -p /opt/firefox-profile /opt/firefox/distribution && \
    printf 'user_pref("browser.aboutwelcome.enabled", false);\nuser_pref("browser.startup.homepage_override.mstone", "ignore");\nuser_pref("startup.homepage_welcome_url", "");\nuser_pref("startup.homepage_override_url", "");\nuser_pref("toolkit.telemetry.reportingpolicy.firstRun", false);\nuser_pref("datareporting.policy.firstRunURL", "");\nuser_pref("datareporting.policy.dataSubmissionEnabled", false);\nuser_pref("browser.shell.checkDefaultBrowser", false);\nuser_pref("browser.tabs.firefox-view", false);\nuser_pref("browser.migrate.content-modal.about-welcome.enabled", false);\nuser_pref("trailhead.firstrun.didSeeAboutWelcome", true);\nuser_pref("browser.startup.page", 0);\nuser_pref("identity.fxaccounts.enabled", false);\nuser_pref("services.sync.engine.addons", false);\nuser_pref("browser.newtabpage.activity-stream.asrouter.providers.onboarding", "{}");\nuser_pref("messaging-system.rsexperimentloader.enabled", false);\nuser_pref("browser.onboarding.enabled", false);\nuser_pref("browser.onboarding.seen-tourset-version", 999);\nuser_pref("datareporting.policy.dataSubmissionPolicyBypassNotification", true);\nuser_pref("datareporting.policy.dataSubmissionPolicyAcceptedVersion", 2);\nuser_pref("datareporting.policy.dataSubmissionPolicyNotifiedTime", 1750000000000);' > /opt/firefox-profile/user.js && \
    cp /opt/firefox-profile/user.js /opt/firefox-profile/prefs.js && \
    printf '{"created":1750000000000,"firstUse":1750000000000}' > /opt/firefox-profile/times.json && \
    printf '{"policies":{"DisableFirefoxStudies":true,"DisableTelemetry":true,"DontCheckDefaultBrowser":true,"OverrideFirstRunPage":"","OverridePostUpdatePage":"","NoDefaultBookmarks":true}}' > /opt/firefox/distribution/policies.json

ENV DISPLAY=:0
ENV MOZ_AUTOMATION=1

# Install streamlit

RUN apt update && apt install -y python3-pip
RUN pip install streamlit --break-system-packages
RUN pip install streamlit-scroll-to-top --break-system-packages
RUN mkdir -p ~/.streamlit/
RUN echo "[browser]\ngatherUsageStats = false\n" > ~/.streamlit/config.toml
RUN echo "[server]\nheadless = true\n" > ~/.streamlit/config.toml

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
    echo 'HTTP_PID=$!' >> /opt/start && \
    echo 'streamlit run submit.py &' >> /opt/start && \
    echo 'STREAMLIT_PID=$!' >> /opt/start && \
    echo 'firefox --profile /opt/firefox-profile http://localhost:8501' >> /opt/start && \
    echo 'kill $STREAMLIT_PID $HTTP_PID 2>/dev/null' >> /opt/start && \
    echo 'wait' >> /opt/start && \
    chmod 777 /opt/start


COPY submit.py /opt

CMD ["/opt/start"]
 

# docker run -v /var/run/docker.sock:/var/run/docker.sock   -v ~/.ssh:/root/.ssh   -v /submit_history:/submit_history -e USERID=$UID   -e USER=$USER   -e DISPLAY=$DISPLAY   -v /tmp/.X11-unix:/tmp/.X11-unix   -v $PWD/.config.ini:/opt/.config.ini   -v $PWD:/data pegi3s/submit
