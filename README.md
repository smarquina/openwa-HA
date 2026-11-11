# OpenWA WhatsApp para Home Assistant

[![Quality gate](https://sonarcloud.io/api/project_badges/quality_gate?project=smarquina_openwa-HA)](https://sonarcloud.io/summary/new_code?id=smarquina_openwa-HA)

Integración para enviar avisos de texto desde Home Assistant a chats individuales y grupos mediante una sesión de WhatsApp vinculada en OpenWA.

## Compatibilidad

Usa la API REST de [rmyndharis/OpenWA](https://github.com/rmyndharis/OpenWA/blob/main/docs/06-api-specification.md) (`ghcr.io/rmyndharis/openwa`, puerto habitual 2785). La comprobación usa `GET /api/sessions/{id}` y el envío usa `POST /api/sessions/{id}/messages/send-text`. El cliente espera una sesión con `id` coincidente, `status: ready` y, si el servidor informa `engineLoaded`, que el motor esté cargado. El envío confirmado por la API devuelve HTTP 201 y un `messageId`.

Esta variante de OpenWA tiene un contrato distinto del Easy API de `@open-wa/wa-automate`. Comprueba en Portainer la imagen y su etiqueta antes de instalar. Requiere Home Assistant 2026.10 o posterior.

## Instalación y configuración

1. En HACS, añade `https://github.com/smarquina/openwa-HA` como repositorio personalizado de tipo integración e instala OpenWA WhatsApp. Para instalación manual, copia `custom_components/openwa_whatsapp` a `/config/custom_components/openwa_whatsapp`.
2. Reinicia Home Assistant y añade **OpenWA WhatsApp** desde **Ajustes → Dispositivos y servicios**.
3. Introduce la URL base sin `/api`, el ID de sesión de OpenWA y la clave. Usa una clave `OPERATOR` dedicada y limitada a esa sesión si tu versión de OpenWA permite ese ámbito. Configura la sesión y escanea el QR desde OpenWA.
4. Usa HTTPS con un certificado de confianza para Home Assistant. En una LAN de confianza puedes introducir una IP privada literal, por ejemplo `http://192.168.1.20:2785`, y activar **Permitir HTTP sin cifrar a una IP privada**. HTTP transmite la clave y el mensaje en claro.

La acción `openwa_whatsapp.send_message` admite `chat_id`, `message` y `entry_id`. Si hay varias entradas cargadas, indica `entry_id` para seleccionar la cuenta. Gestiona las sesiones desde OpenWA.

```yaml
action: openwa_whatsapp.send_message
data:
  chat_id: "15551234567@c.us"
  message: "La lavadora ha terminado."
```

## Red local con Docker y Portainer

Con un Stack en modo bridge, publica el puerto en la IP LAN del host Docker. Conserva la imagen, configuración y volúmenes de tu Stack.

```yaml
ports:
  - "192.168.1.20:2785:2785"
```

Restringe el puerto en el host Docker a la IP desde la que llega Home Assistant. Si Docker usa el backend iptables, este ejemplo aplica al tráfico reenviado de un puerto publicado en IPv4. Sustituye las dos IP y añade la regla a la configuración persistente del firewall. Verifica el orden con `iptables -S DOCKER-USER`.

```sh
sudo iptables -I DOCKER-USER 1 -p tcp ! -s 192.168.1.10 \
  -m conntrack --ctdir ORIGINAL --ctorigdst 192.168.1.20 --ctorigdstport 2785 \
  -j DROP
```

La regla usa la dirección y el puerto anteriores a la traducción de Docker. Para `network_mode: host`, aplica el filtrado en `INPUT`. Para el backend nativo nftables, usa una cadena de filtrado de reenvío propia con prioridad anterior a las reglas de Docker. Las reglas IPv4 del ejemplo cubren únicamente la publicación IPv4 indicada. Consulta la [documentación de red de Docker](https://docs.docker.com/engine/network/firewall-iptables/).

Comprueba el acceso desde Home Assistant y desde otro equipo de la LAN. Mantén el puerto fuera de las redirecciones WAN. El contenedor OpenWA requiere salida hacia WhatsApp. El puerto 2785 puede servir también el panel administrativo de OpenWA, por lo que el filtro de red restringe el panel junto con la API.

## Envíos, reintentos y privacidad

- Cada llamada valida la sesión justo antes de enviar. Ante errores transitorios de lectura, repite la consulta una vez tras un segundo. La integración envía como máximo un POST por llamada y desactiva las redirecciones.
- Si OpenWA pudo procesar el POST pero la respuesta no lo confirma, la acción falla con un resultado desconocido. Comprueba el chat antes de repetir el aviso. Un HTTP 201 confirma la aceptación por el servidor, sin confirmación de entrega. Dos llamadas de la automatización son dos solicitudes independientes.
- La clave se introduce en un campo de contraseña y queda en los datos de la entrada de configuración de Home Assistant. Restringe el acceso a su almacenamiento y copias de seguridad y rota la clave desde **Reconfigurar**. La integración devuelve errores predefinidos y omite cuerpos de respuesta, claves, destinatarios y textos en sus errores y logs. Las trazas de automatizaciones de Home Assistant pueden conservar los datos de la acción, incluidos el chat y el texto. OpenWA conserva sus propios registros según su configuración.

## Pruebas

Con Python 3.14, en un entorno virtual:

```sh
python -m pip install -r requirements-test.txt
python -m pytest -q --asyncio-mode=auto
```

Para validar el despliegue, confirma primero que la configuración acepta la sesión vinculada. Envía un único aviso desde **Herramientas de desarrollador → Acciones** a un chat de prueba y verifica que llega una sola vez.

## Estado y autenticación

La integración comprueba la sesión al crear la entrada, al cargarla y antes de cada envío. Si el servidor no está disponible al arrancar, Home Assistant vuelve a intentar la carga. Si la API rechaza la clave con HTTP 401, Home Assistant solicita nuevas credenciales. HTTP 403 indica que la clave carece de permisos para la operación.

En **Ajustes → Dispositivos y servicios**, selecciona **Reconfigurar** para cambiar la dirección, el ID de sesión o la clave. La descarga de diagnósticos contiene el estado de la entrada y la opción HTTP, sin incluir la dirección, la clave ni el ID de sesión.

## Retirada

Elimina la entrada desde **Ajustes → Dispositivos y servicios** y retira la carpeta `/config/custom_components/openwa_whatsapp`. Reinicia Home Assistant. La sesión de WhatsApp y sus archivos pertenecen a OpenWA y se administran en el servidor.

## Resolución de problemas

- **No conecta**. Comprueba la dirección, el puerto, el firewall y la disponibilidad de OpenWA desde Home Assistant.
- **La sesión no está lista**. Abre OpenWA, revisa el estado y completa la vinculación mediante QR cuando sea necesario.
- **Credenciales o permisos**. Comprueba la clave y su acceso a la sesión. El envío requiere permisos de operador en OpenWA.
- **Resultado desconocido**. Revisa el chat antes de volver a enviar. Una respuesta de aceptación de OpenWA tampoco confirma la entrega al dispositivo del destinatario.
- **Varias entradas**. Indica `entry_id` en la acción para seleccionar la cuenta.
