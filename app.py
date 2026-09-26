import os
import json
import smtplib
from datetime import datetime
from email.message import EmailMessage
from flask import Flask, render_template, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

app = Flask(__name__)

CONFIG_FILE = "config.json"
DATA_FILE = "sensor_data.json"
HISTORIAL_FILE = "historial_emails.json"

def cargar_config():
    """Lee y devuelve los parámetros de configuración desde config.json."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def obtener_lecturas_sensor():
    """Lee las lecturas actuales del sensor de humedad y temperatura."""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"humedad_ambiente": 45.0, "temperatura_ambiente": 22.0}

def obtener_ruta_imagen_husky():
    """Verifica si existe el archivo 'captura_husky.jpg'."""
    ruta_imagen = "captura_husky.jpg"
    if os.path.exists(ruta_imagen):
        return ruta_imagen
    return None

def registrar_historial_email(tipo, humedad, temperatura, destinatarios, estado, error_msg=None):
    """Guarda un registro del correo enviado en historial_emails.json."""
    historial = []
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, "r", encoding="utf-8") as f:
                historial = json.load(f)
        except Exception:
            historial = []

    nuevo_registro = {
        "fecha_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tipo": tipo,  # "Automático" o "Prueba"
        "humedad": humedad,
        "temperatura": temperatura,
        "destinatarios": destinatarios,
        "estado": estado,  # "Exitoso" o "Fallido"
        "error": error_msg
    }

    # Guardar los registros más recientes primero
    historial.insert(0, nuevo_registro)

    # Mantener solo los últimos 50 registros para no saturar el archivo
    historial = historial[:50]

    with open(HISTORIAL_FILE, "w", encoding="utf-8") as f:
        json.dump(historial, f, indent=2, ensure_ascii=False)

def enviar_correo_alerta(humedad, temperatura, ruta_imagen=None, es_prueba=False):
    """Construye, envía y registra el correo de alerta."""
    config = cargar_config()
    destinatarios = config.get("correos_destinatarios", [])
    tipo_envio = "Prueba" if es_prueba else "Automático"

    if not destinatarios:
        print("No hay correos registrados para enviar la alerta.")
        registrar_historial_email(tipo_envio, humedad, temperatura, [], "Fallido", "Sin destinatarios configurados")
        return

    remitente_email = os.getenv("REMITENTE_EMAIL")
    remitente_password = os.getenv("REMITENTE_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))

    if not remitente_email or not remitente_password:
        registrar_historial_email(tipo_envio, humedad, temperatura, destinatarios, "Fallido", "Credenciales SMTP faltantes")
        raise ValueError("Credenciales SMTP no configuradas en el archivo .env")

    fecha_hora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cuerpo_texto = f"""‼️ALERTA‼️

Se detectó que los valores de humedad/temperatura de el objeto a cuidar, salieron de los valores preestablecidos. Porfavor, realizar URGENTEMENTE una revisión manual para combatir la alerta.

Humedad del ambiente: {humedad}%

Temperatura del ambiente: {temperatura}%

Imagen: {"[Imagen adjunta]" if ruta_imagen else "No disponible"}

Fecha y hora: {fecha_hora_str}"""

    msg = EmailMessage()
    msg['Subject'] = f"‼️ ALERTA ({tipo_envio.upper()}): Valores fuera de rango ‼️"
    msg['From'] = remitente_email
    msg['To'] = ", ".join(destinatarios)
    msg.set_content(cuerpo_texto)

    if ruta_imagen and os.path.exists(ruta_imagen):
        try:
            with open(ruta_imagen, 'rb') as f:
                img_data = f.read()
                img_name = os.path.basename(ruta_imagen)
            msg.add_attachment(img_data, maintype='image', subtype='jpeg', filename=img_name)
        except Exception as e:
            print(f"Error al adjuntar imagen: {e}")

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(remitente_email, remitente_password)
            server.send_message(msg)
            print(f"[{fecha_hora_str}] Alerta ({tipo_envio}) enviada a: {destinatarios}")
            
            # Registrar envío exitoso
            registrar_historial_email(tipo_envio, humedad, temperatura, destinatarios, "Exitoso")
    except Exception as e:
        registrar_historial_email(tipo_envio, humedad, temperatura, destinatarios, "Fallido", str(e))
        raise e

def verificar_sensores():
    """Tarea periódica de monitoreo."""
    config = cargar_config()
    datos = obtener_lecturas_sensor()
    
    hum = datos.get("humedad_ambiente", 0)
    temp = datos.get("temperatura_ambiente", 0)

    h_min = config.get("humedad_min", 0)
    h_max = config.get("humedad_max", 100)
    t_min = config.get("temperatura_min", -10)
    t_max = config.get("temperatura_max", 50)

    if hum < h_min or hum > h_max or temp < t_min or temp > t_max:
        ruta_img = obtener_ruta_imagen_husky()
        try:
            enviar_correo_alerta(hum, temp, ruta_img, es_prueba=False)
        except Exception as e:
            print(f"Error en verificación programada: {e}")

# Programador de tareas en segundo plano
scheduler = BackgroundScheduler()
config_inicial = cargar_config()
intervalo = config_inicial.get("intervalo_segundos", 60)
scheduler.add_job(verificar_sensores, 'interval', seconds=intervalo, id='job_monitoreo')
scheduler.start()

# --- RUTAS DE LA APLICACIÓN WEB ---

@app.route("/")
def index():
    """Página principal con panel, ajustes e historial de correos."""
    config = cargar_config()
    datos = obtener_lecturas_sensor()
    
    # Cargar historial para mostrarlo en la tabla HTML
    historial = []
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, "r", encoding="utf-8") as f:
                historial = json.load(f)
        except Exception:
            historial = []

    return render_template("index.html", config=config, datos=datos, historial=historial)

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
    datos = request.json
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2)
    return jsonify({"status": "ok"})

@app.route("/api/test-email", methods=["POST"])
def enviar_email_prueba():
    datos = obtener_lecturas_sensor()
    hum = datos.get("humedad_ambiente", 0)
    temp = datos.get("temperatura_ambiente", 0)
    ruta_img = obtener_ruta_imagen_husky()

    try:
        enviar_correo_alerta(hum, temp, ruta_img, es_prueba=True)
        return jsonify({"status": "ok", "message": "Correo de prueba enviado correctamente."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
