# Helpdesk Pro - Sistema de Tickets 🎫

**Helpdesk Pro** es un sistema de tickets robusto y moderno, diseñado para una gestión de soporte al cliente eficiente y profesional. Esta aplicación permite que usuarios anónimos envíen solicitudes de soporte de manera sencilla, mientras proporciona un potente backend para que administradores y agentes puedan gestionar, asignar y resolver los tickets de forma organizada.


## ✨ Características Principales

Este sistema de helpdesk incluye un amplio conjunto de características avanzadas para optimizar el flujo de trabajo de soporte.

#### 👤 Gestión de Usuarios y Roles
- **Usuarios Anónimos:** Pueden crear tickets sin necesidad de registrarse. Reciben un enlace de seguimiento único para cada ticket, permitiéndoles consultar su progreso en cualquier momento.
- **Rol de Agente:** Los agentes pueden ver y gestionar los tickets que se les asignan, así como comunicarse con los clientes.
- **Rol de Administrador:** El administrador tiene control total sobre el sistema, pudiendo gestionar agentes, áreas y categorías de tickets, supervisar todos los tickets y visualizar estadísticas del sistema.

#### 🎫 Gestión de Tickets
- **Asignación Automática:** Los tickets se distribuyen de manera automática y equitativa entre los agentes del área correspondiente, basándose en la categoría predefinida del problema.
- **Sistema de Prioridades:** Los tickets reciben automáticamente una prioridad ('Baja', 'Media', 'Alta') según la categoría definida por el administrador.
- **Historial de Conversación:** Cada ticket cuenta con un historial completo de todas las interacciones entre el cliente y los agentes para un seguimiento fácil.
- **Archivos Adjuntos:** Los usuarios pueden adjuntar imágenes (hasta 2) al crear un ticket para ilustrar mejor su problema.

#### ⚙️ Automatización y Administración del Sistema
- **Cierre Automático de Tickets:** Los tickets se cierran automáticamente si no hay respuesta del cliente tras 72 horas de la última comunicación de un agente.
- **Limpieza Automática de Adjuntos:** Los archivos adjuntos de tickets cerrados hace más de 7 días se eliminan automáticamente para proteger la privacidad y gestionar el espacio de almacenamiento.
- **Asistente de Instalación Web:** Configura la aplicación por primera vez a través de una interfaz web, sin necesidad de editar variables de entorno.
- **Notificaciones por Email:**
    - El cliente recibe su enlace de seguimiento al crear un ticket.
    - El agente es notificado cuando se le asigna un nuevo ticket.
    - El cliente es notificado cuando un agente responde a su ticket.

#### 🔒 Seguridad
- **Protección con CAPTCHA:** CAPTCHA basado en imágenes para proteger el formulario de creación de tickets contra bots y spam.
- **Cambio de Contraseña Forzado:** Los nuevos agentes deben cambiar su contraseña en su primer inicio de sesión.
- **Control de Acceso Basado en Roles:** Los agentes y administradores tienen roles definidos con permisos específicos.

#### 📊 Reportes y Estadísticas
- **Dashboard de Administrador:** Un panel de resumen para el administrador que muestra tickets abiertos, sin asignar, de alta prioridad y la actividad reciente.
- **Página de Estadísticas:** Gráficos visuales que muestran los tickets por categoría y por área.

## 🛠️ Stack Tecnológico

- **Backend:** Python, Flask
- **Base de Datos:** PostgreSQL
- **Frontend:** HTML5, CSS3, Bootstrap 5
- **Autenticación:** Flask-Login
- **Despliegue:** Docker, Docker Compose
- **Procesamiento de Imágenes (CAPTCHA):** Pillow
- **Envío de Correos:** Flask-Mail

## 🚀 Cómo Empezar

Esta aplicación está diseñada para ser desplegada fácilmente usando Docker.

1. **Clona el repositorio:**
   ```bash
   git clone https://github.com/GamersEC/helpdesk
   cd helpdesk
   ```
2. **Configura el entorno de Docker:**
El archivo docker-compose.yml ya tiene las credenciales para el servicio de PostgreSQL. Se recomienda cambiarlas para un entorno de producción.
No necesitas un archivo .env para la configuración inicial.
Construye y ejecuta la aplicación:
   ```bash 
   docker-compose up --build
3. **Instalación vía Web:**
- Abre tu navegador y ve a http://localhost:8000.
- Como es la primera vez que se ejecuta la aplicación, serás redirigido al asistente de instalación.
- Configura lo siguiente:
  - La cuenta de Administrador.
  - La zona horaria.
  - El correo SMTP.
- Finaliza la instalación e inicia sesión con tus nuevas credenciales de administrador.
4. **Configuración Inicial del Helpdesk:**
- Una vez logueado como admin, ve a la sección "Administración" y crea:
  - Áreas (ej. "Soporte Técnico", "Facturación").
  - Categorías (ej. "Problema para acceder a mi cuenta") y asígnalas a un área y una prioridad.
  - Agentes y asígnalos a un área de trabajo.

  

¡Tu helpdesk está listo para usarse!