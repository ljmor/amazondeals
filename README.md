# Bot de ofertas de tecnología → Discord

Revisa los feeds de Slickdeals cada 10 minutos, filtra ofertas de tecnología de
marcas reconocidas según tus umbrales y las envía a un canal de Discord.
Corre gratis en GitHub Actions: no necesitas servidor ni tener tu PC encendida.

## Instalación (una sola vez, ~10 min)

### 1. Crear el webhook de Discord
1. En tu servidor de Discord, abre el canal donde quieres las alertas.
2. **Editar canal → Integraciones → Webhooks → Nuevo webhook**.
3. Ponle nombre (ej. "Ofertas") y pulsa **Copiar URL del webhook**.
4. En tu celular, activa las notificaciones de ese canal en "Todos los mensajes".

### 2. Crear el repositorio en GitHub
1. Crea un repo **público** nuevo en github.com (ej. `bot-ofertas`).
   Los repos públicos tienen minutos ilimitados de Actions; tu webhook
   sigue privado porque va como *secret*.
2. Sube todos estos archivos, **incluida la carpeta `.github/`**.
   (En la web: *Add file → Upload files* y arrastra el contenido de la carpeta.)

### 3. Guardar el webhook como secret
1. En el repo: **Settings → Secrets and variables → Actions → New repository secret**.
2. Name: `DISCORD_WEBHOOK`
3. Secret: la URL que copiaste en el paso 1.

### 4. Activar y probar
1. Pestaña **Actions** → si pide habilitar workflows, acéptalo.
2. Elige **Bot de ofertas → Run workflow**.
3. La primera ejecución solo registra las ofertas actuales (no envía nada, para
   no inundar el canal). Desde la siguiente, avisa las nuevas que pasen los filtros.

Si en los logs ves `Feed vacío o bloqueado`, avísame: significa que Slickdeals
está bloqueando las IPs de GitHub y hay que cambiar de fuente.

## Ajustar filtros

Todo está al inicio de `bot_ofertas.py`. Edítalo directamente en GitHub (ícono
del lápiz) y los cambios aplican en la siguiente ejecución.

| Variable | Qué hace | Valor |
|---|---|---|
| `PRECIO_MAX` | Precio máximo, productos nuevos | 400 |
| `DESCUENTO_MIN` | % mínimo, productos nuevos | 30 |
| `EXIGIR_DESCUENTO` | Descartar nuevos sin % detectable | False |
| `ACEPTAR_USADOS` | Aceptar usados/reacondicionados | True |
| `PRECIO_MAX_USADO` | Precio máximo, usados | 300 |
| `DESCUENTO_MIN_USADO` | % mínimo, usados | 50 |
| `SOLO_AMAZON` | Solo ofertas de Amazon | False |
| `CATEGORIAS`, `MARCAS`, `EXCLUIR` | Listas de palabras clave | — |

Para cambiar la frecuencia, edita `cron` en `.github/workflows/ofertas.yml`
(el mínimo que permite GitHub es cada 5 minutos).

## Notas
- El bot hace un commit de `ofertas_vistas.json` cuando encuentra ofertas nuevas.
  Es normal y además mantiene el repo activo (GitHub pausa los workflows
  programados de repos públicos tras 60 días sin actividad).
- GitHub puede retrasar las ejecuciones programadas varios minutos en horas pico.
- Para probarlo en tu PC:
  `pip install -r requirements.txt` y luego
  `DISCORD_WEBHOOK="tu_url" python bot_ofertas.py --una-vez`
