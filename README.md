# 🌡️ Sistema de Monitoreo de Humedad y Temperatura con Alertas por Correo

Aplicación web desarrollada en Python con **Flask** para monitorear en tiempo real los valores de temperatura y humedad ambiental de un sensor conectado a **Arduino**. Si las lecturas sobrepasan o bajan de los límites configurados por el usuario, el sistema envía automáticamente una notificación de correo electrónico con soporte para adjuntar capturas tomadas por **HuskyLens**.

---

## 🛠️ Características Principales

- **Panel Web interactivo:** Visualiza lecturas actuales y permite modificar en tiempo real:
  - Rangos mínimos y máximos de temperatura (°C) y humedad (%).
  - Tiempo/frecuencia de verificación periódica (en segundos).
  - Lista de destinatarios de correo.
- **Formato de Alerta Estandarizado:** Envía notificaciones de urgencia respetando la plantilla definida.
- **Soporte HuskyLens:** Preparado para detectar y adjuntar imágenes capturadas por la cámara al momento de emitir la alerta.
- **Seguridad e Integración:** Manejo de credenciales mediante variables de entorno (`.env`) para evitar publicar datos sensibles en repositorios públicos.

---

🚀 Instalación y Configuración
1. Clonar el repositorio
Bash
git clone [https://github.com/TU_USUARIO/TU_REPOSITORIO.git](https://github.com/TU_USUARIO/TU_REPOSITORIO.git)
cd TU_REPOSITORIO
2. Crear y activar un entorno virtual
En Linux / macOS:

Bash
python3 -m venv venv
source venv/bin/activate
En Windows:

Bash
python -m venv venv
venv\Scripts\activate
3. Instalar dependencias
Bash
pip install -r requirements.txt
4. Configurar variables de entorno (.env)
Crea un archivo llamado .env en la raíz del proyecto con la configuración de tu cuenta emisora de correo:

Fragmento de código
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
REMITENTE_EMAIL=tu_correo@gmail.com
REMITENTE_PASSWORD=tu_contraseña_de_aplicacion
Nota: Si utilizas Gmail, genera una Contraseña de Aplicación desde la configuración de seguridad de tu cuenta de Google.

💻 Uso de la Aplicación
Inicia el servidor ejecutando:

Bash
python app.py
Abre tu navegador e ingresa a http://localhost:5000.

Desde el panel web podrás modificar los límites del sensor y la lista de correos destino.

📸 Integración con HuskyLens
El sistema verifica automáticamente la presencia del archivo captura_husky.jpg en la raíz del proyecto al momento de enviar una alerta. Cuando integres la cámara HuskyLens, guarda la foto capturada con ese nombre para que sea adjuntada de forma automática en el correo de notificación.


## 📁 Estructura del Proyecto
```text
monitoreo-sensores/
├── .env                  # Variables de entorno (Credenciales SMTP)
├── .gitignore            # Archivos excluidos de Git
├── app.py                # Aplicación Flask y lógica de monitoreo
├── config.json           # Configuración de umbrales y tiempos
├── requirements.txt      # Dependencias del proyecto
└── templates/
    └── index.html        # Interfaz web de monitoreo
