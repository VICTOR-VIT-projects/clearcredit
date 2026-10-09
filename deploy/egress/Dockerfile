# Egress allowlist proxy: the API's ONLY way out. Allows HTTPS CONNECT to the Base Sepolia RPC, nothing else.
FROM alpine:3.22
RUN apk add --no-cache tinyproxy
COPY deploy/egress/tinyproxy.conf /etc/tinyproxy/tinyproxy.conf
COPY deploy/egress/allow /etc/tinyproxy/allow
USER tinyproxy
EXPOSE 8888
CMD ["tinyproxy", "-d", "-c", "/etc/tinyproxy/tinyproxy.conf"]
