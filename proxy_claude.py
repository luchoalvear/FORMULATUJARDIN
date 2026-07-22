"""Proxy local para llamadas a la API de Anthropic desde el navegador.

La API de Anthropic bloquea por CORS las llamadas hechas directamente desde
JavaScript en el navegador. Este proxy corre en tu propio computador, recibe
la petición del navegador (sin problema de CORS porque es localhost) y la
reenvía a Anthropic como una llamada servidor-a-servidor, que no tiene esa
restricción.

Uso:
    python proxy_claude.py
    (o "py proxy_claude.py" si "python" no está en el PATH)

Deja esta ventana abierta mientras uses la Redacción Asistida por IA.
"""
import http.server
import json
import urllib.request
import urllib.error

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
PORT = 8787


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "x-api-key, anthropic-version, content-type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path != "/v1/messages":
            self.send_response(404)
            self._cors_headers()
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        req = urllib.request.Request(
            ANTHROPIC_URL,
            data=body,
            method="POST",
            headers={
                "x-api-key": self.headers.get("x-api-key", ""),
                "anthropic-version": self.headers.get("anthropic-version", "2023-06-01"),
                "content-type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:
                status = resp.status
                data = resp.read()
        except urllib.error.HTTPError as e:
            status = e.code
            data = e.read()
        except Exception as e:
            self.send_response(502)
            self._cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
            return

        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        print("[proxy]", self.address_string(), *args)


if __name__ == "__main__":
    server = http.server.HTTPServer(("localhost", PORT), ProxyHandler)
    print(f"Proxy Claude API corriendo en http://localhost:{PORT}")
    print("Reenvía peticiones a " + ANTHROPIC_URL)
    print("Deja esta ventana abierta. Presiona Ctrl+C para detener.")
    server.serve_forever()
