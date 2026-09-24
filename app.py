import os
import json
import smtplib
from datetime import datetime
from email.message import EmailMessage
from flask import Flask, render_template, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

# Cargar las credenciales desde el archivo .env
load_dotenv()

app = Flask(__name__)

CONFIG_FILE = "config.json"
DATA_FILE = "sensor_data.json"

def cargar_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def obtener_lecturas_sensor():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"humedad_ambiente": 45.0, "temperatura_ambiente": 22.0}

def obtener_ruta_imagen_husky():
    """
    Función para adjuntar la foto tomada por la HuskyLens.
    Busca la imagen 'captura_husky.jpg' en el directorio del proyecto.
    """
    ruta_imagen = "captura_husky.jpg"
    if os.path.exists(ruta_imagen):
        return ruta_imagen
    return None

def enviar_correo_alerta(humedad, temperatura, ruta_imagen=None):
    config = cargar_config()
    destinatarios = config.get("correos_destinatarios", [])
    if not destinatarios:
        print("No hay correos registrados para enviar la alerta.")
        return

    remitente_email = os.getenv("REMITENTE_EMAIL")
    remitente_password = os.getenv("REMITENTE_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))

    if not remitente_email or not remitente_password:
        print("Error: Credenciales SMTP no configuradas en el archivo .env")
        return

    fecha_hora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Formato exacto según el Google Doc especificado
    cuerpo_texto = f"""‼️ALERTA‼️

Se detectó que los valores de humedad/temperatura de el objeto a cuidar, salieron de los valores preestablecidos. Porfavor, realizar URGENTEMENTE una revisión manual para combatir la alerta.

Humedad del ambiente: {humedad}%

Temperatura del ambiente: {temperatura}%

Imagen: {"[Imagen adjunta]" if ruta_imagen else "No disponible"}

Fecha y hora: {fecha_hora_str}"""

    msg = EmailMessage()
    msg['Subject'] = "‼️ ALERTA: Valores fuera de rango ‼️"
    msg['From'] = remitente_email
    msg['To'] = ", ".join(destinatarios)
    msg.set_content(cuerpo_texto)

    # Adjuntar la foto capturada por la HuskyLens
    if ruta_imagen and os.path.exists(ruta_imagen):
        try:
            with open(ruta_imagen, 'rb') as f:
                img_data = f.read()
                img_name = os.path.basename(ruta_imagen)
            msg.add_attachment(img_data, maintype='image', subtype='jpeg', filename=img_name)
        except Exception as e:
            print(f"Error al adjuntar la imagen de HuskyLens: {e}")

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(remitente_email, remitente_password)
            server.send_message(msg)
            print(f"[{fecha_hora_str}] Alerta enviada a: {destinatarios}")
    except Exception as e:
        print(f"Error enviando correo: {e}")

def verificar_sensores():
    config = cargar_config()
    datos = obtener_lecturas_sensor()
    
    hum = datos.get("humedad_ambiente", 0)
    temp = datos.get("temperatura_ambiente", 0)

    h_min = config.get("humedad_min", 0)
    h_max = config.get("humedad_max", 100)
    t_min = config.get("temperatura_min", -10)
    t_max = config.get("temperatura_max", 50)

    # Verificar si están fuera de los rangos preestablecidos
    if hum < h_min or hum > h_max or temp < t_min or temp > t_max:
        ruta_img = obtener_ruta_imagen_husky()
        enviar_correo_alerta(hum, temp, ruta_img)

# Programador de tareas periódicas
scheduler = BackgroundScheduler()
config_inicial = cargar_config()
intervalo = config_inicial.get("intervalo_segundos", 60)
scheduler.add_job(verificar_sensores, 'interval', seconds=intervalo, id='job_monitoreo')
scheduler.start()

# Rutas de la interfaz web
@app.route("/")
def index():
    config = cargar_config()
    datos = obtener_lecturas_sensor()
    return render_template("index.html", config=config, datos=datos)

@app.route("/api/config", methods=["POST"])
def actualizar_config():
    data = request.json
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    
    nuevo_intervalo = data.get("intervalo_segundos", 60)
    scheduler.reschedule_job('job_monitoreo', trigger='interval', seconds=nuevo_intervalo)
    
    return jsonify({"status": "ok", "message": "Configuración actualizada"})

@app.route("/api/sensor", methods=["POST"])
def recibir_datos_arduino():
    """
    Endpoint para que el Arduino envíe datos por HTTP POST:
    {"humedad_ambiente": 40.0, "temperatura_ambiente": 25.0}
    """
    datos = request.json
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2)
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
