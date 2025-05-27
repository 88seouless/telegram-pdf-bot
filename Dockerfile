# Clone Adobe SDK repo and install locally
RUN git clone https://github.com/adobe/pdfservices-python-sdk.git /app/adobe-sdk && \
    pip install ./adobe-sdk
