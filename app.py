import os
import json
import time
import ssl
import threading
import smtplib
from datetime import datetime
from email.message import EmailMessage


import serial
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

app = Flask(__name__)

CONFIG_FILE = "config.json"
DATA_FILE = "sensor_data.json"
HISTORIAL_FILE = "historial_emails.json"

# Configuración del puerto USB con Arduino
PUERTO_COM = os.getenv("PUERTO_COM", "COM5")
BAUDIOS = int(os.getenv("BAUDIOS", 9600))

# Control de intervalo para no saturar con correos mientras la alerta siga activa
ultimo_envio_alerta = 0
ultimo_envio_hongo = 0
COOLDOWN_SEGUNDOS = 45

# Mapa de imágenes según el ID detectado por la HuskyLens
IMAGENES_HUSKY = {
    1: "tela_id_1.jpg",
    2: "tela_id_2.jpg",
    3: "hongos_textil.jpg"  # Foto de evidencia de proliferación fúngica
}
IMAGEN_DEFAULT = "captura_husky.jpg"

# Estado en memoria para lectura en tiempo real sin saturar el disco
datos_en_memoria = {
    "temperatura_ambiente": 22.0,
    "humedad_ambiente": 45.0,
    "luz_ambiente": 30.0,
    "husky_id": 0,
    "conectado": False
}
lock_datos = threading.Lock()
ultimo_volcado_disco = 0


def cargar_config():
    """Lee y devuelve los parámetros de configuración desde config.json."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[CONFIG] Error al leer {CONFIG_FILE}: {e}")
            
    return {
        "correos_destinatarios": [],
        "temperatura_min": 15.0,
        "temperatura_max": 28.0,
        "humedad_min": 35.0,
        "humedad_max": 65.0,
        "luz_max": 75.0,
        "intervalo_segundos": 60
    }


def obtener_lecturas_sensor():
    """Devuelve las lecturas más recientes desde la memoria."""
    with lock_datos:
        return dict(datos_en_memoria)


def obtener_ruta_imagen_husky(id_objeto=0):
    """Selecciona la foto de la pieza según el ID detectado por HuskyLens."""
    ruta = IMAGENES_HUSKY.get(id_objeto, IMAGEN_DEFAULT)
    if os.path.exists(ruta):
        return ruta
    if os.path.exists(IMAGEN_DEFAULT):
        return IMAGEN_DEFAULT
    return None


def registrar_historial_email(tipo, humedad, temperatura, luz, destinatarios, estado, error_msg=None):
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
        "temperatura": temperatura,
        "humedad": humedad,
        "luz": luz,
        "destinatarios": destinatarios,
        "estado": estado,  # "Exitoso" o "Fallido"
        "error": error_msg
    }

    historial.insert(0, nuevo_registro)
    historial = historial[:50]  # Mantener últimos 50 eventos

    try:
        with open(HISTORIAL_FILE, "w", encoding="utf-8") as f:
            json.dump(historial, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[HISTORIAL] Error al guardar historial: {e}")


def enviar_correo_alerta(humedad, temperatura, luz, ruta_imagen=None, es_prueba=False, id_objeto=0):
    """Construye, despacha y registra el correo de alerta adjuntando la fotografía."""
    config = cargar_config()
    destinatarios = config.get("correos_destinatarios", [])
    tipo_envio = "Prueba" if es_prueba else "Automático"

    if not destinatarios:
        print("[CORREO] No hay destinatarios configurados.")
        registrar_historial_email(tipo_envio, humedad, temperatura, luz, [], "Fallido", "Sin destinatarios configurados")
        return

    remitente_email = os.getenv("REMITENTE_EMAIL")
    remitente_password = os.getenv("REMITENTE_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))

    if not remitente_email or not remitente_password:
        registrar_historial_email(tipo_envio, humedad, temperatura, luz, destinatarios, "Fallido", "Credenciales SMTP faltantes en .env")
        raise ValueError("Credenciales SMTP no configuradas en el archivo .env")

    fecha_hora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pieza_info = f"Tela / Pieza Arqueológica ID #{id_objeto}" if id_objeto > 0 else "Pieza en vitrina"

    cuerpo_texto = f"""ALERTA DE CONSERVACION PREVENTIVA

Se detecto que los parametros ambientales para la {pieza_info} han superado los umbrales de seguridad preestablecidos.

Valores registrados en tiempo real:
- Temperatura ambiente: {temperatura} C
- Humedad relativa: {humedad} %
- Nivel de radiacion luminosa (Luz): {luz} %

Fotografia de la pieza: {"[Imagen adjunta]" if ruta_imagen else "No disponible"}
Fecha y hora del reporte: {fecha_hora_str}

Por favor, realizar una inspeccion tecnica urgente en la vitrina de conservacion."""

    msg = EmailMessage()
    msg['Subject'] = f"ALERTA ({tipo_envio.upper()}): {pieza_info} fuera de rango"
    msg['From'] = remitente_email
    msg['To'] = ", ".join(destinatarios)
    msg.set_content(cuerpo_texto, charset='utf-8')

    # Adjuntar fotografía si existe
    if ruta_imagen and os.path.exists(ruta_imagen):
        try:
            with open(ruta_imagen, 'rb') as f:
                img_data = f.read()
                img_name = os.path.basename(ruta_imagen)
            msg.add_attachment(img_data, maintype='image', subtype='jpeg', filename=img_name)
        except Exception as e:
            print(f"[CORREO] Error al adjuntar imagen: {e}")

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(remitente_email, remitente_password)
            server.send_message(msg)
            print(f"[{fecha_hora_str}] Alerta enviada exitosamente a: {destinatarios}")
            registrar_historial_email(tipo_envio, humedad, temperatura, luz, destinatarios, "Exitoso")
    except Exception as e:
        registrar_historial_email(tipo_envio, humedad, temperatura, luz, destinatarios, "Fallido", str(e))
        raise e

def enviar_correo_alerta_hongos(humedad, temperatura, luz, ruta_imagen=None):
    """Envía un correo de máxima prioridad ante la detección visual de colonias fúngicas."""
    config = cargar_config()
    destinatarios = config.get("correos_destinatarios", [])

    if not destinatarios:
        print("[CORREO HONGOS] No hay destinatarios configurados.")
        registrar_historial_email("Emergencia Biológica", humedad, temperatura, luz, [], "Fallido", "Sin destinatarios")
        return

    remitente_email = os.getenv("REMITENTE_EMAIL", "").strip()
    remitente_password = os.getenv("REMITENTE_PASSWORD", "").strip().replace(" ", "")
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("SMTP_PORT", 465))

    if not remitente_email or not remitente_password:
        registrar_historial_email("Emergencia Biológica", humedad, temperatura, luz, destinatarios, "Fallido", "Credenciales SMTP faltantes en .env")
        raise ValueError("Credenciales SMTP no configuradas en el archivo .env")

    fecha_hora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cuerpo_texto = f"""🚨 ALERTA CRITICA DE BIODETERIORO: PROLIFERACION FUNGICA DETECTADA 🚨

El sistema de vision artificial (HuskyLens) ha identificado patrones correspondientes a CRECIMIENTO MICOTICO / COLONIAS DE MOHO sobre el soporte textil patrimonial en vitrina.

PARAMETROS AMBIENTALES EN EL MOMENTO DE LA DETECCION:
- Humedad relativa: {humedad} %
- Temperatura ambiente: {temperatura} C
- Nivel de luz: {luz} %

EVIDENCIA VISUAL ADJUNTA: {"[hongos_textil.jpg adjunta]" if ruta_imagen else "No disponible"}
FECHA Y HORA DEL REPORTE: {fecha_hora_str}

ACCIONES PROTOCOLARES RECOMENDADAS:
1. Proceder a la inmediata cuarentena y aislamiento de la vitrina para evitar dispersion de esporas fúngicas hacia otras piezas.
2. Regular inmediatamente la humedad ambiental por debajo del 50% HR para inhibir el metabolismo activo de hifas.
3. Solicitar inspeccion urgente del equipo de conservacion y restauracion textil."""

    msg = EmailMessage()
    msg['Subject'] = "🚨 [URGENTE] ALERTA BIOLOGICA: Moho / Hongos detectados en pieza textil"
    msg['From'] = remitente_email
    msg['To'] = ", ".join(destinatarios)
    msg.set_content(cuerpo_texto, charset='utf-8')

    # Adjuntar la captura de evidencia
    if ruta_imagen and os.path.exists(ruta_imagen):
        try:
            with open(ruta_imagen, 'rb') as f:
                img_data = f.read()
                img_name = os.path.basename(ruta_imagen)
            msg.add_attachment(img_data, maintype='image', subtype='jpeg', filename=img_name)
        except Exception as e:
            print(f"[CORREO HONGOS] Error al adjuntar imagen: {e}")

    contexto_ssl = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port, context=contexto_ssl, timeout=15) as server:
            server.login(remitente_email, remitente_password)
            server.send_message(msg)
            print(f"[{fecha_hora_str}] Alerta de emergencia biologica enviada exitosamente a: {destinatarios}")
            registrar_historial_email("Emergencia Biológica", humedad, temperatura, luz, destinatarios, "Exitoso")
    except Exception as e:
        registrar_historial_email("Emergencia Biológica", humedad, temperatura, luz, destinatarios, "Fallido", str(e))
        raise e

def evaluar_condiciones_alerta(datos):
    """Comprueba condiciones ambientales y emergencias biológicas por visión artificial."""
    global ultimo_envio_alerta, ultimo_envio_hongo

    config = cargar_config()

    hum = float(datos.get("humedad_ambiente", 0))
    temp = float(datos.get("temperatura_ambiente", 0))
    luz = float(datos.get("luz_ambiente", 0))
    id_husky = int(datos.get("husky_id", 0))
    ahora = time.time()

    # =========================================================================
    # CASO 1: EMERGENCIA BIOLÓGICA (ID 3 = HONGOS) -> DISPARO INMEDIATO
    # =========================================================================
    if id_husky == 3:
        if ahora - ultimo_envio_hongo > COOLDOWN_SEGUNDOS:
            ultimo_envio_hongo = ahora
            print("[ALERTA BIOLOGICA] ¡Patron micotico detectado en textil (ID 3)! Despachando correo...")
            ruta_img = obtener_ruta_imagen_husky(3)
            try:
                enviar_correo_alerta_hongos(hum, temp, luz, ruta_img)
            except Exception as e:
                print(f"[ERROR HONGOS] No se pudo enviar el correo de alerta: {e}")
        return  # Prioridad absoluta: si hay hongos, no superponer con alerta de sensores

    # =========================================================================
    # CASO 2: ALERTA PREVENTIVA POR SENSORES (IDs 1 y 2 = PIEZAS EN VITRINA)
    # =========================================================================
    h_min = float(config.get("humedad_min", 0))
    h_max = float(config.get("humedad_max", 100))
    t_min = float(config.get("temperatura_min", -10))
    t_max = float(config.get("temperatura_max", 50))
    luz_max = float(config.get("luz_max", 80))

    fuera_de_rango = (hum < h_min or hum > h_max or
                      temp < t_min or temp > t_max or
                      luz > luz_max)

    if fuera_de_rango and id_husky > 0:
        if ahora - ultimo_envio_alerta > COOLDOWN_SEGUNDOS:
            ultimo_envio_alerta = ahora
            print(f"[ALERTA PREVENTIVA] Parametros anomalos en pieza ID #{id_husky}. Enviando correo...")
            ruta_img = obtener_ruta_imagen_husky(id_husky)
            try:
                enviar_correo_alerta(hum, temp, luz, ruta_img, es_prueba=False, id_objeto=id_husky)
            except Exception as e:
                print(f"[ERROR ALERTA] Fallo despacho de sensores: {e}")


# =========================================================================
# HILO EN SEGUNDO PLANO: RECEPTOR SERIAL DE ARDUINO
# =========================================================================
def lector_serie_arduino():
    global ultimo_volcado_disco
    ser = None
    print(f"[SERIAL] Iniciando hilo de comunicación en {PUERTO_COM}...")

    while True:
        try:
            if ser is None or not ser.is_open:
                ser = serial.Serial(PUERTO_COM, BAUDIOS, timeout=1)
                print(f"[SERIAL] Conectado exitosamente a Arduino en {PUERTO_COM}")
                time.sleep(2)  # Pausa de estabilización tras el reset por DTR
                with lock_datos:
                    datos_en_memoria["conectado"] = True

            linea = ser.readline().decode('utf-8', errors='ignore').strip()
            if linea.startswith("{") and linea.endswith("}"):
                try:
                    lectura = json.loads(linea)

                    # Compatibilidad bidireccional de nombres (Arduino emite "objeto" o "husky_id")
                    h_id = lectura.get("husky_id", lectura.get("objeto", 0))

                    with lock_datos:
                        datos_en_memoria["temperatura_ambiente"] = float(lectura.get("temperatura", 20.0))
                        datos_en_memoria["humedad_ambiente"] = float(lectura.get("humedad", 40.0))
                        datos_en_memoria["luz_ambiente"] = float(lectura.get("luz", 0.0))
                        datos_en_memoria["husky_id"] = int(h_id)
                        datos_en_memoria["conectado"] = True
                        datos_actuales = dict(datos_en_memoria)

                    # Guardar en disco cada 3 segundos para no desgastar ni bloquear I/O
                    ahora = time.time()
                    if ahora - ultimo_volcado_disco >= 3.0:
                        ultimo_volcado_disco = ahora
                        try:
                            with open(DATA_FILE, "w", encoding="utf-8") as f:
                                json.dump(datos_actuales, f, indent=2)
                        except Exception:
                            pass

                    # Evaluar condiciones de alerta
                    evaluar_condiciones_alerta(datos_actuales)

                except json.JSONDecodeError:
                    pass

        except Exception as e:
            with lock_datos:
                datos_en_memoria["conectado"] = False
            if ser:
                try:
                    ser.close()
                except Exception:
                    pass
            ser = None
            print(f"[SERIAL] Puerto {PUERTO_COM} no disponible ({e}). Reintentando en 3s...")
            time.sleep(3)


# Iniciar el hilo de lectura continua USB
hilo_arduino = threading.Thread(target=lector_serie_arduino, daemon=True)
hilo_arduino.start()


# =========================================================================
# RUTAS DE LA APLICACIÓN WEB (FLASK)
# =========================================================================
@app.route("/")
def index():
    """Página principal con panel de control, valores e historial."""
    config = cargar_config()
    datos = obtener_lecturas_sensor()

    historial = []
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, "r", encoding="utf-8") as f:
                historial = json.load(f)
        except Exception:
            historial = []

    return render_template("index.html", config=config, datos=datos, historial=historial)


@app.route("/api/sensores", methods=["GET"])
def api_sensores():
    """Endpoint consultado periódicamente por el JavaScript del HTML."""
    return jsonify(obtener_lecturas_sensor())


@app.route("/api/config", methods=["POST"])
def actualizar_config():
    """Guarda nuevos umbrales y destinatarios desde el formulario web."""
    data = request.json
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return jsonify({"status": "ok", "message": "Configuración guardada correctamente."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/test-email", methods=["POST"])
def enviar_email_prueba():
    """Dispara un correo de verificación bajo demanda desde la interfaz."""
    datos = obtener_lecturas_sensor()
    hum = datos.get("humedad_ambiente", 0)
    temp = datos.get("temperatura_ambiente", 0)
    luz = datos.get("luz_ambiente", 0)
    id_h = datos.get("husky_id", 0)

    ruta_img = obtener_ruta_imagen_husky(id_h)

    try:
        enviar_correo_alerta(hum, temp, luz, ruta_img, es_prueba=True, id_objeto=id_h)
        return jsonify({"status": "ok", "message": "Correo de prueba enviado correctamente con foto adjunta."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    # use_reloader=False es obligatorio para no duplicar hilos sobre COM7
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
