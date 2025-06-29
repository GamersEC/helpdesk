# Helpdesk Pro

Un sistema de helpdesk basado en Flask, diseñado para la gestión de tickets de soporte. Permite a los clientes crear tickets con adjuntos, seguir su estado, y a los agentes gestionarlos desde un panel de administración.

## ✨ Características

- Creación de tickets con campos personalizables
- Panel de seguimiento de tickets para los clientes
- Dashboard de agentes para gestionar y cerrar tickets
- Soporte para adjuntos (imágenes)
- Captcha visual con letras/números y ruido para prevenir envíos automatizados o abusivos
- Autocierre de tickets inactivos después de 72 horas
- Limpieza automática de archivos adjuntos de tickets cerrados
- Notificaciones por correo electrónico al cliente con el link de seguimiento
- Sistema de autenticación de agentes con Flask-Login
- Base de datos PostgreSQL

## 🚀 Tecnologías utilizadas

- Python
- Flask
- SQLAlchemy
- Flask-Login
- Flask-Mail
- PostgreSQL
- Bootstrap (para la interfaz)
- Docker
