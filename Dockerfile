# Use a Debian-based Python image for full apt support
FROM python:3.10-bullseye

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system packages including Java
RUN apt-get update && \
    apt-get install -y wget curl gnupg2 openjdk-11-jre-headless && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set Java path for tabula
ENV JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install Python dependencies
RUN pip install --upgrade pip && pip install -r requirements.txt

# Expose Streamlit default port
EXPOSE 8501

# Start the Streamlit app
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
