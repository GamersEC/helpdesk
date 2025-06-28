# Usa una imagen oficial de Python como base.
# 'slim' es una versión más ligera, ideal para producción.
FROM python:3.9-slim

# Establece el directorio de trabajo dentro del contenedor en /app
# A partir de aquí, todos los comandos se ejecutarán en este directorio.
WORKDIR /app

# Copia primero el archivo de dependencias.
# Esto aprovecha el sistema de caché de Docker para acelerar futuras construcciones.
COPY requirements.txt .

# Instala las dependencias listadas en requirements.txt
# --no-cache-dir reduce el tamaño final de la imagen.
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del código de tu aplicación al directorio de trabajo del contenedor.
# ESTA ES LA LÍNEA CORREGIDA
COPY . .

# El comando para ejecutar tu aplicación (este será sobreescrito por el 'command' en docker-compose.yml,
# pero es una buena práctica tenerlo aquí).
CMD ["flask", "run", "--host=0.0.0.0", "--port=8000"]